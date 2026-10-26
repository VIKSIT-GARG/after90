"""Bounded Azure Responses transport with cancellable total request deadlines.

The complete async operation (connection, headers, body and response closure) is
wrapped in one deadline. Streaming prevents an unbounded response allocation.
No thread is left running when a slow response falls back. Duration is transport
wall time, not claimed model inference latency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import multiprocessing
import re
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

AZURE_HOST_SUFFIXES = (".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com")
MAX_RESPONSE_BYTES = 64 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class ProviderFailure(ValueError):
    """A fixed public reason code; no provider body, URL or credential is shown."""

    def __init__(self, reason: str, *, http_status: int | None = None,
                 attempted: bool = False, telemetry: dict | None = None):
        known = {"invalid_endpoint", "not_configured", "http_error", "timeout",
                 "transport_error", "malformed_response", "response_too_large"}
        self.reason = reason if reason in known else "transport_error"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.attempted = attempted
        self.telemetry = telemetry
        super().__init__(self.reason)


@dataclass(frozen=True)
class ProviderResponse:
    response: dict[str, Any]
    telemetry: dict[str, Any]


def endpoint_allowed(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https" and url.hostname
            and any(url.hostname.endswith(suffix) for suffix in AZURE_HOST_SUFFIXES)
            and url.port in (None, 443) and url.username is None and url.password is None
            and url.path == "/openai/v1/responses" and not url.query and not url.fragment
        )
    except (TypeError, ValueError):
        return False


def _identifier(value: Any, secret: str) -> str | None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or "://" in value:
        return None
    if secret and secret in value:
        return None
    return value


def _tokens(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def response_telemetry(response: Mapping[str, Any], headers: Mapping[str, str], *,
                       duration_ms: float, secret: str = "") -> dict[str, Any]:
    """Retain only optional, bounded provider-reported operational fields.

    Missing usage remains unknown. A deployment setting is not substituted for
    the returned model identity, and total tokens are never invented from parts.
    """
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    duration = float(duration_ms)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("duration must be finite and nonnegative")
    normalized_headers = {str(key).lower(): value for key, value in headers.items()}
    return {
        "provider_response_id": _identifier(response.get("id"), secret),
        "provider_request_id": _identifier(normalized_headers.get("x-request-id") or normalized_headers.get("apim-request-id"), secret),
        "provider_model": _identifier(response.get("model"), secret),
        "input_tokens": _tokens(usage.get("input_tokens")),
        "output_tokens": _tokens(usage.get("output_tokens")),
        "total_tokens": _tokens(usage.get("total_tokens")),
        "provider_request_ms": round(duration, 3),
    }


async def request_json_async(url: str, key: str, body: dict, timeout: float = 3,
                             max_bytes: int = MAX_RESPONSE_BYTES, *,
                             transport: httpx.AsyncBaseTransport | None = None) -> ProviderResponse:
    """Send one Responses request; the injected transport is for local tests.

    URL validation is never bypassed by this API, including when a test transport
    is supplied. Redirects cannot forward the authorization header elsewhere.
    """
    if not endpoint_allowed(url):
        raise ProviderFailure("invalid_endpoint")
    if not isinstance(key, str) or not key.strip():
        raise ProviderFailure("not_configured")
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2 * 1024 * 1024:
        raise ValueError("response byte limit is invalid")
    started = time.perf_counter()
    attempted = False
    received_headers: dict[str, str] = {}

    async def operation() -> tuple[dict, dict]:
        nonlocal attempted, received_headers
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout),
                                     follow_redirects=False, trust_env=transport is None) as client:
            attempted = True
            async with client.stream("POST", url, json=body,
                                     headers={"Content-Type": "application/json", "Accept-Encoding": "identity", "api-key": key}) as response:
                received_headers = dict(response.headers)
                if not response.is_success:
                    raise ProviderFailure("http_error", http_status=response.status_code)
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ProviderFailure("malformed_response")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > max_bytes:
                        raise ProviderFailure("response_too_large")
                    raw.extend(chunk)
                try:
                    parsed = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ProviderFailure("malformed_response") from None
                if not isinstance(parsed, dict):
                    raise ProviderFailure("malformed_response")
                return parsed, dict(response.headers)

    try:
        parsed, headers = await asyncio.wait_for(operation(), timeout=float(timeout))
    except ProviderFailure as error:
        raise ProviderFailure(error.reason, http_status=error.http_status, attempted=attempted,
                              telemetry=response_telemetry({}, received_headers,
                              duration_ms=(time.perf_counter() - started) * 1000, secret=key)) from None
    except (TimeoutError, httpx.TimeoutException):
        raise ProviderFailure("timeout", attempted=attempted,
                              telemetry=response_telemetry({}, received_headers,
                              duration_ms=(time.perf_counter() - started) * 1000, secret=key)) from None
    except (httpx.HTTPError, OSError):
        raise ProviderFailure("transport_error", attempted=attempted,
                              telemetry=response_telemetry({}, received_headers,
                              duration_ms=(time.perf_counter() - started) * 1000, secret=key)) from None
    except (TypeError, ValueError):
        raise ProviderFailure("malformed_response", attempted=attempted,
                              telemetry=response_telemetry({}, received_headers,
                              duration_ms=(time.perf_counter() - started) * 1000, secret=key)) from None
    return ProviderResponse(parsed, response_telemetry(parsed, headers,
                            duration_ms=(time.perf_counter() - started) * 1000, secret=key))


def _process_request(connection, url, key, body, timeout, max_bytes):
    """Child boundary also contains uncancellable native DNS resolver work."""
    try:
        connection.send(("attempted", None))
        result = asyncio.run(request_json_async(url, key, body, timeout, max_bytes))
        connection.send(("success", result))
    except ProviderFailure as error:
        connection.send(("failure", (error.reason, error.http_status, error.attempted, error.telemetry)))
    except Exception:
        connection.send(("failure", ("transport_error", None, True, None)))
    finally:
        connection.close()


def request_json(url: str, key: str, body: dict, timeout: float = 3,
                 max_bytes: int = MAX_RESPONSE_BYTES) -> ProviderResponse:
    """Sync adapter with a process boundary for noncancellable OS DNS calls.

    The parent owns the total deadline, including child startup. Terminating the
    isolated child cannot strand a native resolver thread in the API process.
    Credentials travel over private IPC, never OS command lines or logs.
    """
    if not endpoint_allowed(url):
        raise ProviderFailure("invalid_endpoint")
    if not isinstance(key, str) or not key.strip():
        raise ProviderFailure("not_configured")
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2 * 1024 * 1024:
        raise ValueError("response byte limit is invalid")
    started = time.perf_counter()
    parent, child = multiprocessing.get_context("spawn").Pipe(duplex=False)
    process = multiprocessing.get_context("spawn").Process(
        target=_process_request, args=(child, url, key, body, timeout, max_bytes), daemon=True)
    attempted = False
    try:
        process.start()
        child.close()
        while True:
            remaining = timeout - (time.perf_counter() - started)
            if remaining <= 0 or not parent.poll(max(0, remaining)):
                raise ProviderFailure("timeout", attempted=attempted,
                    telemetry=response_telemetry({}, {}, duration_ms=(time.perf_counter() - started) * 1000))
            kind, payload = parent.recv()
            if kind == "attempted":
                attempted = True
                continue
            if kind == "failure":
                reason, status, did_attempt, telemetry = payload
                raise ProviderFailure(reason, http_status=status, attempted=did_attempt, telemetry=telemetry)
            return payload
    except (OSError, EOFError, RuntimeError):
        raise ProviderFailure("transport_error", attempted=attempted) from None
    finally:
        parent.close()
        child.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=.05)
            if process.is_alive():
                process.kill()
                process.join(timeout=.05)
            if not process.is_alive():
                process.close()
