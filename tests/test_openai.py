"""OpenAI provider (gpt-6-luna) tests, offline: the Chat Completions API is replaced by httpx.MockTransport, so the
real client code runs (request shape, streaming, JSON mode, refused settings, errors, retries, key redaction)."""
from __future__ import annotations

import json

import httpx
import pytest

from nyaya import config, llm, privacy

REAL_CHAT, REAL_STREAM, REAL_JSON, REAL_PING = llm.chat, llm.stream, llm.chat_json, llm.ping   # before the fake LLM
KEY = "sk-proj-TESTONLY0123456789abcdefghij"


@pytest.fixture
def openai(monkeypatch):
    """Switch to the OpenAI provider against a scripted fake API; returns (requests, replies)."""
    requests: list[httpx.Request] = []
    replies: list = []

    def handle(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        r = replies.pop(0) if len(replies) > 1 else replies[0]
        return r(req) if callable(r) else r

    orig = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: orig(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_unsupported", {})
    monkeypatch.setattr(llm, "_breakers", {})
    monkeypatch.setattr(llm, "_sleep", lambda attempt: None)
    for name, fn in (("chat", REAL_CHAT), ("stream", REAL_STREAM), ("chat_json", REAL_JSON), ("ping", REAL_PING)):
        monkeypatch.setattr(llm, name, fn)   # the real client, not the suite's fake model
    for k, v in {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": KEY, "OPENAI_BASE_URL": "https://api.openai.test/v1",
                 "LLM_MODEL": "gpt-6-luna", "FAST_LLM_MODEL": "gpt-6-luna", "LLM_FALLBACK_MODEL": "",
                 "LLM_RETRIES": 1, "LLM_THINK": "low"}.items():
        monkeypatch.setattr(config, k, v)
    return requests, replies


def ok(content: str = "Section 138 provides for imprisonment up to two years.", usage=None) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}],
                                     "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20}})


def err(status: int, code: str, message: str = "", param=None) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message or code, "code": code, "param": param,
                                                  "type": "invalid_request_error"}})


def body(req: httpx.Request) -> dict:
    return json.loads(req.content)


def test_chat_request_shape_and_reply(openai):
    requests, replies = openai
    replies.append(ok())
    info: dict = {}
    assert REAL_CHAT([{"role": "user", "content": "Punishment under section 138?"}], info=info).startswith("Section 138")
    req = requests[0]
    assert str(req.url) == "https://api.openai.test/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    b = body(req)
    assert b["model"] == "gpt-6-luna" and b["reasoning_effort"] == "low" and b["stream"] is False
    assert "think" not in b and "options" not in b                                   # no Ollama-only fields
    assert info == {"model": "gpt-6-luna", "fallback": False, "ok": True}
    assert llm.provider_name() == "OpenAI"


def test_a_refused_setting_is_dropped_and_remembered(openai):
    requests, replies = openai
    replies += [err(400, "unsupported_parameter", "Unsupported parameter: 'temperature' is not supported with this "
                                                   "model.", "temperature"), ok(), ok()]
    assert REAL_CHAT([{"role": "user", "content": "q1"}])
    assert "temperature" in body(requests[0]) and "temperature" not in body(requests[1])
    REAL_CHAT([{"role": "user", "content": "q2"}])
    assert "temperature" not in body(requests[2]) and len(requests) == 3            # learnt: no second refusal


def test_json_mode(openai):
    requests, replies = openai
    replies.append(ok('{"intent": "research", "query": "cheque dishonour"}'))
    out = REAL_JSON([{"role": "user", "content": "Classify as json: cheque bounce"}], default={"intent": "x"})
    assert out == {"intent": "research", "query": "cheque dishonour"}
    assert body(requests[0])["response_format"] == {"type": "json_object"}


def test_streaming_tokens_and_usage(openai):
    requests, replies = openai
    events = [{"choices": [{"delta": {"role": "assistant"}}]},
              {"choices": [{"delta": {"content": "**Short answer** — "}}]},
              {"choices": [{"delta": {"content": "up to two years [1]."}}]},
              {"choices": [], "usage": {"prompt_tokens": 3500, "completion_tokens": 400,
                                        "prompt_tokens_details": {"cached_tokens": 2048}}}]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    replies.append(httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"}))
    with llm.track():
        text = "".join(REAL_STREAM([{"role": "user", "content": "Punishment?"}]))
        used = llm.calls()
    assert text == "**Short answer** — up to two years [1]."
    b = body(requests[0])
    assert b["stream"] is True and b["stream_options"] == {"include_usage": True}
    assert {"in": 3500, "out": 400, "cached": 2048} in [c.get("usage") for c in used]
    assert any(c.get("ok") and c.get("model") == "gpt-6-luna" for c in used)


def test_no_credit_is_reported_at_once_without_retrying(openai):
    requests, replies = openai
    replies.append(err(429, "insufficient_quota", "You exceeded your current quota."))
    with pytest.raises(llm.LLMError) as exc:
        REAL_CHAT([{"role": "user", "content": "q"}])
    assert "no credit" in str(exc.value) and not exc.value.transient and len(requests) == 1


def test_rate_limit_is_retried_then_reported_as_temporary(openai):
    requests, replies = openai
    replies.append(err(429, "rate_limit_exceeded", "Rate limit reached"))
    with pytest.raises(llm.LLMError) as exc:
        REAL_CHAT([{"role": "user", "content": "q"}])
    assert exc.value.transient and len(requests) == 2                               # LLM_RETRIES = 1


def test_bad_key_and_missing_model(openai):
    requests, replies = openai
    replies.append(err(401, "invalid_api_key", "Incorrect API key provided"))
    with pytest.raises(llm.LLMError, match="OPENAI_API_KEY"):
        REAL_CHAT([{"role": "user", "content": "q"}])
    replies[:] = [err(404, "model_not_found", "The model `gpt-6-luna` does not exist")]
    with pytest.raises(llm.LLMError, match="Model not available"):
        REAL_CHAT([{"role": "user", "content": "q"}])


def test_ping_lists_models_without_spending_tokens(openai):
    requests, replies = openai
    replies.append(httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]}))
    assert REAL_PING() == (True, "HTTP 200")
    assert requests[0].url.path == "/v1/models" and requests[0].method == "GET"


def test_openai_keys_never_reach_the_logs(openai):
    line = privacy.scrub(f"calling with key {KEY} and sk-abcdefghijklmnopqrstuvwxyz0123")
    assert KEY not in line and "sk-abcdefghij" not in line
