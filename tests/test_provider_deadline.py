"""Regression tests for a total (rather than per-read) provider deadline."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

import httpx
import pytest

from backend.matchlens.provider import ProviderFailure, request_json_async

URL = "https://test.openai.azure.com/openai/v1/responses"
KEY = "synthetic-test-secret"


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay, self.closed = chunks, delay, False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


def test_drip_stream_total_deadline_closes_response():
    stream = Stream([b" "] * 30, .025)
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
        started = time.monotonic()
        with pytest.raises(ProviderFailure) as caught:
            await request_json_async(URL, KEY, {}, .12, transport=transport)
        assert time.monotonic() - started < .45
        assert caught.value.reason == "timeout"
        assert caught.value.attempted is True
        assert caught.value.telemetry["provider_request_ms"] >= 100
        assert stream.closed
        assert len(asyncio.all_tasks()) == 1
    asyncio.run(run())


def test_header_stall_is_cancelled_without_background_task():
    cancelled = []
    async def handler(request):
        try:
            await asyncio.sleep(2)
        finally:
            cancelled.append(True)
    async def run():
        with pytest.raises(ProviderFailure, match="timeout"):
            await request_json_async(URL, KEY, {}, .05, transport=httpx.MockTransport(handler))
        assert cancelled == [True]
        assert len(asyncio.all_tasks()) == 1
    asyncio.run(run())


def test_real_socket_drip_cannot_extend_total_deadline():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                for _ in range(20):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(.04)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    class LocalTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport()
            self.closed = False
        async def handle_async_request(self, request):
            local = httpx.Request(request.method, f"http://127.0.0.1:{server.server_port}/", headers=request.headers,
                                  content=await request.aread(), extensions=request.extensions)
            return await self.inner.handle_async_request(local)
        async def aclose(self):
            self.closed = True
            await self.inner.aclose()
    async def run():
        transport = LocalTransport()
        started = time.monotonic()
        with pytest.raises(ProviderFailure, match="timeout"):
            await request_json_async(URL, KEY, {}, .16, transport=transport)
        assert time.monotonic() - started < .5
        assert transport.closed
    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


@pytest.mark.parametrize("payload,limit,reason", [(b"x" * 33, 32, "response_too_large"), (b"[]", 32, "malformed_response"), (b"invalid", 32, "malformed_response")])
def test_bad_response_is_bounded_and_closed(payload, limit, reason):
    stream = Stream([payload])
    async def run():
        with pytest.raises(ProviderFailure) as caught:
            await request_json_async(URL, KEY, {}, max_bytes=limit,
                                     transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)))
        assert caught.value.reason == reason
        assert caught.value.attempted
        assert stream.closed
    asyncio.run(run())


def test_redirect_is_not_followed_and_does_not_expose_error_body():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.com/"}, text=KEY)
    async def run():
        with pytest.raises(ProviderFailure) as caught:
            await request_json_async(URL, KEY, {}, transport=httpx.MockTransport(handler))
        assert caught.value.reason == "http_error"
        assert caught.value.http_status == 302
        assert KEY not in str(caught.value)
        assert calls == [URL]
    asyncio.run(run())


@pytest.mark.parametrize("url", ["http://test.openai.azure.com/openai/v1/responses", "https://evil.example/openai/v1/responses", URL + "?key=secret", "https://test.openai.azure.com.evil.example/openai/v1/responses"])
def test_invalid_endpoint_never_attempts_transport(url):
    def handler(request):
        raise AssertionError("must not call transport")
    async def run():
        with pytest.raises(ProviderFailure) as caught:
            await request_json_async(url, KEY, {}, transport=httpx.MockTransport(handler))
        assert caught.value.reason == "invalid_endpoint"
        assert not caught.value.attempted
        assert caught.value.telemetry is None
    asyncio.run(run())


def _blocked_native_dns_worker(connection, *args):
    """Reproduce asyncio default executor shutdown waiting on native DNS."""
    import socket
    def blocked_getaddrinfo(*args, **kwargs):
        time.sleep(5)
        return []
    socket.getaddrinfo = blocked_getaddrinfo
    connection.send(("attempted", None))
    async def run():
        await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, "test.openai.azure.com", 443), .03)
    try:
        asyncio.run(run())
    except TimeoutError:
        pass
    finally:
        connection.close()


def test_sync_deadline_kills_native_dns_executor_without_waiting(monkeypatch):
    import multiprocessing
    from backend.matchlens import provider
    monkeypatch.setattr(provider, "_process_request", _blocked_native_dns_worker)
    before = {process.pid for process in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(ProviderFailure) as caught:
        provider.request_json(URL, KEY, {}, timeout=.7)
    elapsed = time.monotonic() - started
    assert caught.value.reason == "timeout"
    assert elapsed < 1.1
    assert {process.pid for process in multiprocessing.active_children()} <= before


def _success_worker(connection, *args):
    from backend.matchlens.provider import ProviderResponse
    connection.send(("attempted", None))
    connection.send(("success", ProviderResponse({"id": "resp_child"}, {"provider_request_ms": 1})))
    connection.close()


def test_sync_process_returns_typed_result_and_reaps_child(monkeypatch):
    from backend.matchlens import provider
    monkeypatch.setattr(provider, "_process_request", _success_worker)
    result = provider.request_json(URL, KEY, {}, timeout=3)
    assert result.response["id"] == "resp_child"
    assert result.telemetry["provider_request_ms"] == 1
