import pytest
import requests

from eval import openrouter


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = str(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def ok(content="FINAL ANSWER: 1", finish="stop", cost=0.002):
    return Resp(200, {"choices": [{"finish_reason": finish, "message": {"content": content}}],
                      "usage": {"cost": cost, "total_tokens": 10}})


@pytest.fixture
def png(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(openrouter.time, "sleep", lambda s: None)
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG")
    return str(p)


def script(monkeypatch, responses):
    seen = []

    def post(url, json, headers, timeout):
        seen.append(json)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(openrouter.requests, "post", post)
    return seen


def test_success_payload(png, monkeypatch):
    seen = script(monkeypatch, [ok()])
    r = openrouter.call("m/x", "Q", png, max_tokens=500, effort="high")
    assert (r["error"], r["finish_reason"], r["content"], r["cost"]) == ("", "stop", "FINAL ANSWER: 1", 0.002)
    p = seen[0]
    assert p["temperature"] == 0 and p["max_tokens"] == 500 and p["reasoning"] == {"effort": "high"}
    assert p["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_retries_then_succeeds(png, monkeypatch):
    script(monkeypatch, [Resp(429, {"error": "rate"}), requests.Timeout("slow"), Resp(502, None),
                         ok(content="", cost=0.001), ok()])
    r = openrouter.call("m/x", "Q", png, max_tokens=500)
    assert r["error"] == "" and r["attempts"] == 5 and len(r["attempt_errors"]) == 4
    assert r["cost"] == pytest.approx(0.003)  # the empty-content attempt was billed too


def test_no_retry_on_client_error(png, monkeypatch):
    script(monkeypatch, [Resp(402, {"error": "no credits"})])
    r = openrouter.call("m/x", "Q", png, max_tokens=500)
    assert r["error"] == "api_error" and r["attempts"] == 1


def test_length_is_not_retried(png, monkeypatch):
    script(monkeypatch, [ok(content="", finish="length")])
    r = openrouter.call("m/x", "Q", png, max_tokens=500)
    assert (r["error"], r["finish_reason"], r["attempts"]) == ("length", "length", 1)


def test_gives_up_after_max_attempts(png, monkeypatch):
    script(monkeypatch, [Resp(503, {"error": "down"})] * openrouter.MAX_ATTEMPTS)
    r = openrouter.call("m/x", "Q", png, max_tokens=500)
    assert r["error"] == "api_error" and r["attempts"] == openrouter.MAX_ATTEMPTS
