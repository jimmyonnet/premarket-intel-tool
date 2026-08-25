from types import SimpleNamespace

import sys

import pytest

from scripts import notify_summary


def test_line_notify_token_is_ignored_without_printing_token(monkeypatch, capsys):
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_USER_ID", raising=False)
    monkeypatch.setenv("LINE_NOTIFY_TOKEN", "legacy-secret-value")

    assert notify_summary.send_line_message("hello") is False
    output = capsys.readouterr().err
    assert "LINE_NOTIFY_TOKEN ignored" in output
    assert "legacy-secret-value" not in output


def test_line_messaging_requires_both_opt_in_values(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token-for-test")
    monkeypatch.delenv("LINE_USER_ID", raising=False)

    assert notify_summary.send_line_message("hello") is False


def test_line_messaging_api_uses_push_endpoint_and_bearer_header(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token-for-test")
    monkeypatch.setenv("LINE_USER_ID", "user-for-test")
    calls = []

    def fake_post(url, data=None, form_data=None, headers=None):
        calls.append((url, data, headers))
        return True

    monkeypatch.setattr(notify_summary, "send_http_post", fake_post)

    assert notify_summary.send_line_message("hello") is True
    assert calls == [
        (
            "https://api.line.me/v2/bot/message/push",
            {"to": "user-for-test", "messages": [{"type": "text", "text": "hello"}]},
            {"Authorization": "Bearer token-for-test"},
        )
    ]


def test_webhook_failure_log_contains_only_scheme_and_host(monkeypatch, capsys):
    def fail_urlopen(request, timeout=15):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify_summary.urllib.request, "urlopen", fail_urlopen)
    secret_url = "https://hooks.example.test/path/secret-token?token=secret-query"

    assert notify_summary.send_http_post(secret_url, data={"ok": True}) is False
    output = capsys.readouterr().err
    assert "https://hooks.example.test" in output
    assert "/path/secret-token" not in output
    assert "secret-query" not in output


def test_configured_channels_all_failing_are_reported_as_delivery_failure(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://hooks.example.test/path/token")
    monkeypatch.delenv("ERROR_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_USER_ID", raising=False)
    monkeypatch.setattr(notify_summary, "send_http_post", lambda *args, **kwargs: False)

    assert notify_summary._dispatch_results(
        "hello", discord_url="https://hooks.example.test/path/token", generic_url=None, generic_payload=None
    ) is False
    assert "All configured notification channels failed" in capsys.readouterr().err


def test_cli_returns_nonzero_when_notification_delivery_fails(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["notify_summary.py", "--mode", "failure"])
    monkeypatch.setattr(notify_summary, "notify_failure", lambda: False)

    with pytest.raises(SystemExit) as exc_info:
        notify_summary.main()

    assert exc_info.value.code == 1
