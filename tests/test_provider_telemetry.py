"""Provider usage is optional, bounded, and distinct from transport wall time."""
import asyncio

import httpx
import pytest

from backend.matchlens.provider import ProviderFailure, request_json_async, response_telemetry


def test_reported_identity_and_usage_are_preserved():
    result = response_telemetry({"id": "resp_abc", "model": "gpt-4.1-mini", "usage": {
        "input_tokens": 17, "output_tokens": 8, "total_tokens": 25}},
        {"APIM-Request-ID": "req-123"}, duration_ms=123.4567)
    assert result == {"provider_response_id": "resp_abc", "provider_request_id": "req-123",
                      "provider_model": "gpt-4.1-mini", "input_tokens": 17, "output_tokens": 8,
                      "total_tokens": 25, "provider_request_ms": 123.457}


def test_missing_usage_stays_unknown_without_inventing_totals():
    result = response_telemetry({"usage": {"input_tokens": 2, "output_tokens": 3}}, {}, duration_ms=0)
    assert result["total_tokens"] is None
    assert result["provider_model"] is None
    assert "inference_latency_ms" not in result


@pytest.mark.parametrize("value", [True, -1, 1.5, "12", 1_000_000_001, None])
def test_invalid_token_counts_are_unknown(value):
    result = response_telemetry({"usage": {"input_tokens": value, "output_tokens": value, "total_tokens": value}}, {}, duration_ms=1)
    assert all(result[k] is None for k in ("input_tokens", "output_tokens", "total_tokens"))


@pytest.mark.parametrize("value", ["x" * 257, "model\nsecret", "https://secret.example", "prefix-super-secret-key"])
def test_identifiers_cannot_echo_credentials_or_unbounded_text(value):
    result = response_telemetry({"id": value, "model": value}, {"x-request-id": value}, duration_ms=1, secret="super-secret-key")
    assert all(result[k] is None for k in ("provider_response_id", "provider_model", "provider_request_id"))


def test_request_measures_wall_time_and_returns_optional_usage():
    async def handler(request):
        await asyncio.sleep(.02)
        return httpx.Response(200, json={"id": "resp_test", "model": "model-1", "usage": {"input_tokens": 4}}, headers={"x-request-id": "request-1"})
    async def run():
        result = await request_json_async("https://test.openai.azure.com/openai/v1/responses", "synthetic-test-secret", {}, transport=httpx.MockTransport(handler))
        assert result.telemetry["provider_request_ms"] >= 15
        assert result.telemetry["input_tokens"] == 4
        assert result.telemetry["output_tokens"] is None
        assert result.telemetry["provider_request_id"] == "request-1"
        assert result.response["id"] == "resp_test"
    asyncio.run(run())


def test_failure_keeps_only_sanitized_operational_metadata():
    async def run():
        with pytest.raises(ProviderFailure) as caught:
            await request_json_async("https://test.openai.azure.com/openai/v1/responses", "synthetic-test-secret", {},
                transport=httpx.MockTransport(lambda r: httpx.Response(500, text="secret internals", headers={"x-request-id": "req-500"})))
        assert caught.value.attempted
        assert caught.value.telemetry["provider_request_id"] == "req-500"
        assert caught.value.telemetry["provider_request_ms"] >= 0
        assert "secret internals" not in repr(caught.value)
    asyncio.run(run())
