"""Readiness checks never confuse configuration or mocks with live proof."""

import json
import subprocess
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_ai_readiness as readiness


CONFIG = {
    "FOUNDRY_RESPONSES_URL": "https://after90.openai.azure.com/openai/v1/responses",
    "FOUNDRY_MODEL": "test-model",
    "FOUNDRY_API_KEY": "secret-test-key",
}


@pytest.fixture(autouse=True)
def no_cli(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", lambda _: None)


def test_offline_missing_configuration_is_not_live_proof(monkeypatch):
    monkeypatch.setattr(readiness, "live_probe", lambda *_args: pytest.fail("offline called network"))
    report = readiness.check_readiness({})
    assert report["configuration"] == "not_configured"
    assert report["foundry_live_probe"]["status"] == "live_not_tested"
    assert report["azure_cli_auth"] == "cli_not_installed"
    assert all(value == "unverified" for value in report["manual_gates"].values())


def test_configured_is_not_live_verified_and_contains_no_values():
    report = readiness.check_readiness(CONFIG)
    assert report["configuration"] == "configured"
    assert report["foundry_live_probe"]["status"] == "live_not_tested"
    encoded = json.dumps(report)
    for value in CONFIG.values():
        assert value not in encoded


@pytest.mark.parametrize("url", [
    "http://after90.openai.azure.com/openai/v1/responses",
    "https://localhost/openai/v1/responses",
    "https://after90.openai.azure.com.evil.test/openai/v1/responses",
    "https://user:password@after90.openai.azure.com/openai/v1/responses",
    "https://after90.openai.azure.com:8080/openai/v1/responses",
    "https://after90.openai.azure.com/openai/v1/responses?secret=x",
    "https://after90.openai.azure.com/openai/v1/responses#fragment",
    "https://after90.openai.azure.com/other",
    "https://after90.openai.azure.com:invalid/openai/v1/responses",
])
def test_endpoint_validation_rejects_unsafe_or_wrong_shape(url, monkeypatch):
    monkeypatch.setattr(readiness, "build_opener", lambda *_: pytest.fail("unsafe endpoint attempted"))
    assert not readiness.endpoint_valid(url)
    report = readiness.check_readiness({**CONFIG, "FOUNDRY_RESPONSES_URL": url}, live=True)
    assert report["configuration"] == "invalid_configuration"
    assert report["foundry_live_probe"] == {"status": "fail", "reason": "invalid_endpoint"}


def test_missing_credentials_do_not_attempt_live(monkeypatch):
    monkeypatch.setattr(readiness, "live_probe", lambda *_: pytest.fail("missing config attempted"))
    report = readiness.check_readiness({"FOUNDRY_API_KEY": "key"}, live=True)
    assert report["foundry_live_probe"]["status"] == "live_not_tested"
    assert report["foundry_live_probe"]["reason"] == "configuration_missing"


def fake_opener(monkeypatch, response, observed=None):
    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, limit):
            assert limit == readiness.MAX_RESPONSE_BYTES + 1
            return json.dumps(response).encode()

    class Opener:
        def open(self, request, timeout):
            if observed is not None:
                observed.update(request=request, timeout=timeout)
            return Handle()

    def build(handler):
        assert isinstance(handler, readiness.NoRedirect)
        return Opener()

    monkeypatch.setattr(readiness, "build_opener", build)


def good_response():
    packet, _ = readiness.smoke_input()
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps({
        "insight_id": packet["insight_id"], "interpretation_code": "GOAL_RECORDED",
        "evidence_event_ids": packet["evidence_event_ids"],
        "explanation": "The supplied synthetic goal changed the recorded score.",
    })}]}]}


def test_live_probe_uses_real_synthetic_evidence_and_strict_responses_schema(monkeypatch):
    observed = {}
    fake_opener(monkeypatch, good_response(), observed)
    report = readiness.check_readiness(CONFIG, live=True)
    assert report["foundry_live_probe"]["status"] == "pass"
    assert report["foundry_live_probe"]["semantic_quality"] == "not_evaluated"
    request = observed["request"]
    payload = json.loads(request.data)
    assert request.get_header("Api-key") == CONFIG["FOUNDRY_API_KEY"]
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 400
    facts = json.loads(payload["input"][1]["content"])
    assert facts["synthetic"] is True
    assert facts["verified_facts"]["goal_event_id"] in facts["evidence_event_ids"]
    assert observed["timeout"] == 5


@pytest.mark.parametrize("response", [
    {"output_text": "not JSON"},
    {"output_text": json.dumps({"insight_id": "wrong"})},
    {"status": "incomplete"},
    {"output_text": "[]"},
    None,
])
def test_invalid_response_does_not_pass_access_gate(monkeypatch, response):
    fake_opener(monkeypatch, response)
    result = readiness.live_probe(CONFIG)
    assert result["status"] == "fail"


def test_network_errors_are_sanitized(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise URLError("secret-test-key https://private-endpoint")
    monkeypatch.setattr(readiness, "build_opener", lambda *_: Opener())
    result = readiness.live_probe(CONFIG)
    assert result == {"status": "fail", "reason": "network_or_timeout"}
    assert "secret" not in json.dumps(result)


def test_http_errors_are_sanitized(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise HTTPError(CONFIG["FOUNDRY_RESPONSES_URL"], 401, CONFIG["FOUNDRY_API_KEY"], {}, None)
    monkeypatch.setattr(readiness, "build_opener", lambda *_: Opener())
    assert readiness.live_probe(CONFIG) == {"status": "fail", "reason": "http_error", "http_status": 401}


def test_redirects_cannot_forward_key():
    assert readiness.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.test") is None


def test_azure_cli_reports_cached_auth_without_account_details(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "which", lambda _: "/usr/bin/az")
    def run(args, **kwargs):
        assert args == ["/usr/bin/az", "account", "show", "--query", "state", "--output", "tsv"]
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(args, 0, stdout="Enabled\n", stderr="")
    monkeypatch.setattr(readiness.subprocess, "run", run)
    assert readiness.azure_auth_status() == "cached_account_enabled"


def test_main_reports_missing_configuration_with_exit_two(monkeypatch, capsys):
    for name in readiness.REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(readiness.sys, "argv", ["check_ai_readiness.py", "--live"])
    assert readiness.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["foundry_live_probe"] == {"status": "live_not_tested", "reason": "configuration_missing"}


def test_main_offline_configured_is_zero_without_claiming_live(monkeypatch, capsys):
    for name, value in CONFIG.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(readiness.sys, "argv", ["check_ai_readiness.py"])
    assert readiness.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["configuration"] == "configured"
    assert report["foundry_live_probe"]["status"] == "live_not_tested"
