"""Language-model client with streaming, JSON mode, retries and user-friendly errors, for two providers
(config.LLM_PROVIDER):
* openai - OpenAI's Chat Completions API (default model gpt-6-luna), key in OPENAI_API_KEY;
* ollama - Ollama Cloud with an API key, or a local Ollama server.
One pooled HTTP connection is reused for every call, which keeps per-request latency low.

OpenAI models differ in which optional settings they accept (some reasoning models refuse `temperature`, for
example). When the API names an optional setting as unsupported, it is dropped for that model and the call is
repeated once; the rest of the app never needs to know.

This is the single point where text leaves the server for the language model, so personal identifiers are
pseudonymised here (privacy.redact_messages) and restored in the reply.

Resilience, all bounded:
* retries on overload / server errors / network errors with exponential back-off and full jitter;
* a circuit breaker per model: after repeated failures the model is skipped for a short time instead of making every
  request wait for timeouts;
* an approved fallback model (LLM_FALLBACK_MODEL, same provider and the same already-authorised prompt) used when the
  main model fails or its circuit is open — every call records which model answered, so answers can say so.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

import httpx

from . import config, privacy

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Message is safe to show to the user. `transient` = worth retrying later; `fallback_ok` = another model may work."""

    def __init__(self, message: str, *, transient: bool = False, fallback_ok: bool | None = None):
        super().__init__(message)
        self.transient = transient
        self.fallback_ok = transient if fallback_ok is None else fallback_ok


_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _openai() -> bool:
    return config.LLM_PROVIDER == "openai"


def provider_name() -> str:
    if _openai():
        return "OpenAI"
    return "Ollama Cloud" if "ollama.com" in config.OLLAMA_HOST else "Local Ollama"


def _http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            headers = {"User-Agent": "NyaySutra-AI/1.0"}
            key = config.OPENAI_API_KEY if _openai() else config.OLLAMA_API_KEY
            if key:
                headers["Authorization"] = f"Bearer {key}"
            base = config.OPENAI_BASE_URL if _openai() else config.OLLAMA_HOST
            _client = httpx.Client(base_url=base, headers=headers,
                                   timeout=httpx.Timeout(config.LLM_TIMEOUT, connect=15),
                                   limits=httpx.Limits(max_keepalive_connections=8, max_connections=16))
        return _client


# ── Which models answered (per request / job) ────────────────────────────────
_calls: ContextVar[list | None] = ContextVar("nyaya_llm_calls", default=None)


@contextmanager
def track():
    """Record every model call made inside this block (see calls())."""
    token = _calls.set([])
    try:
        yield
    finally:
        _calls.reset(token)


def calls() -> list[dict]:
    return list(_calls.get() or [])


def _record(**kw) -> None:
    lst = _calls.get()
    if lst is not None:
        lst.append(kw)


# ── Circuit breaker ──────────────────────────────────────────────────────────
class Breaker:
    def __init__(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            return time.monotonic() >= self.open_until

    def success(self) -> None:
        with self.lock:
            self.failures, self.open_until = 0, 0.0

    def failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= config.LLM_BREAKER_FAILURES:
                self.open_until = time.monotonic() + config.LLM_BREAKER_SECONDS
                self.failures = 0
                log.warning("LLM circuit opened for %ss after repeated failures", config.LLM_BREAKER_SECONDS)


_breakers: dict[str, Breaker] = {}


def breaker(model: str) -> Breaker:
    return _breakers.setdefault(model, Breaker())


def breaker_state() -> dict[str, str]:
    return {m: ("open" if not b.allow() else "closed") for m, b in _breakers.items()}


def _models(model: str | None) -> list[str]:
    """The model to use, then the approved fallback for it (only the main answer model has one)."""
    primary = model or config.LLM_MODEL
    fb = config.LLM_FALLBACK_MODEL
    return [primary, fb] if primary == config.LLM_MODEL and fb and fb != primary else [primary]


def _sleep(attempt: int) -> None:
    time.sleep(random.uniform(0, min(8.0, 1.0 * 2 ** attempt)))   # full jitter, capped


# OpenAI: optional settings a model refused (model -> names), learnt from the API's own error replies.
_OPTIONAL = ("temperature", "reasoning_effort", "response_format", "max_completion_tokens", "stream_options")
_unsupported: dict[str, set[str]] = {}


def _payload(messages: list[dict], model: str | None, stream: bool, json_mode: bool, temperature: float,
             max_tokens: int | None) -> dict:
    model = model or config.LLM_MODEL
    if _openai():
        p = {"model": model, "messages": messages, "stream": stream, "temperature": temperature,
             "reasoning_effort": config.LLM_THINK or "low"}
        if max_tokens:
            p["max_completion_tokens"] = max_tokens
        if json_mode:
            p["response_format"] = {"type": "json_object"}
        if stream:
            p["stream_options"] = {"include_usage": True}   # token counts, for the cost record
        return p
    p: dict = {"model": model, "messages": messages, "stream": stream,
               "options": {"temperature": temperature}}
    if max_tokens:
        p["options"]["num_predict"] = max_tokens
    if json_mode:
        p["format"] = "json"
    if model.startswith("gpt-oss"):
        p["think"] = config.LLM_THINK or "low"
    return p


def _for_model(body: dict, model: str) -> dict:
    """The request for this model, without settings it has refused before (OpenAI)."""
    drop = _unsupported.get(model, set())
    return {k: v for k, v in {**body, "model": model}.items() if k not in drop}


def _refused_setting(r: httpx.Response) -> str | None:
    """OpenAI 400 that names an optional setting this model does not accept (then it is dropped and retried)."""
    if not _openai() or r.status_code != 400:
        return None
    try:
        err = r.json().get("error") or {}
    except ValueError:
        return None
    text = f"{err.get('param') or ''} {err.get('message') or ''}".lower()
    return next((k for k in _OPTIONAL if k in text), None)


_NO_CREDIT = ("insufficient_quota", "billing_hard_limit_reached")


def _openai_error(r: httpx.Response) -> None:
    try:
        err = r.json().get("error") or {}
    except ValueError:
        err = {"message": r.text[:200]}
    code, msg = str(err.get("code") or err.get("type") or ""), str(err.get("message") or "")
    log.warning("OpenAI error %s (%s): %s", r.status_code, code, msg[:200])
    if r.status_code == 401:
        raise LLMError("The OpenAI API key was rejected. Check OPENAI_API_KEY in .env.")
    if r.status_code == 403:
        raise LLMError("This OpenAI project is not allowed to use the model (check the project's model access and "
                       "region in the OpenAI dashboard).")
    if r.status_code == 429 and code in _NO_CREDIT:
        raise LLMError("The AI service has no credit left on the OpenAI account, or its monthly budget is reached "
                       "(platform.openai.com, Billing). Ask the administrator; library search and case files still work.")
    if r.status_code == 404 or code == "model_not_found":
        raise LLMError(f"Model not available on this OpenAI account: {msg[:120]}", fallback_ok=True)
    if r.status_code == 429:
        raise LLMError("OpenAI usage limit reached for now. Please wait a minute and try again.", transient=True)
    if r.status_code == 400:
        raise LLMError("The AI service refused the request. Please rephrase it or try again.")
    raise LLMError(f"The language model service returned an error ({r.status_code}).", transient=r.status_code >= 500)


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if _openai():
        _openai_error(r)
    try:
        detail = r.json().get("error", "")
    except ValueError:
        detail = r.text[:200]
    detail = str(detail)
    log.warning("Ollama error %s: %s", r.status_code, detail[:200])
    if r.status_code in (401, 403):
        raise LLMError("The Ollama API key was rejected. Check OLLAMA_API_KEY in .env.")
    if r.status_code == 402:
        raise LLMError("The AI service needs a paid plan or usage credits on the Ollama account (ollama.com/plans). "
                       "Ask the administrator; library search and case files still work.")
    if r.status_code == 404 or "not found" in detail.lower():
        raise LLMError(f"Model not available on your Ollama plan: {detail[:120]}", fallback_ok=True)
    if r.status_code == 429 or "limit" in detail.lower():
        raise LLMError("Ollama usage limit reached for now. Please wait a few minutes and try again.", transient=True)
    raise LLMError(f"The language model service returned an error ({r.status_code}).", transient=r.status_code >= 500)


_RETRY_STATUS = (429, 500, 502, 503, 504)


def _retryable(r: httpx.Response) -> bool:
    if r.status_code not in _RETRY_STATUS:
        return False
    if _openai() and r.status_code == 429:   # an empty account does not recover by waiting
        try:
            return (r.json().get("error") or {}).get("code") not in _NO_CREDIT
        except ValueError:
            return True
    return True


def _chat_path() -> str:
    return "/chat/completions" if _openai() else "/api/chat"


def _note_usage(usage: dict | None) -> None:
    if usage:
        _record(usage={"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                       "cached": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)})


def _chat_once(body: dict, model: str) -> str:
    """One model, bounded retries with jittered back-off."""
    last: LLMError | None = None
    for attempt in range(config.LLM_RETRIES + 1):
        try:
            r = _http().post(_chat_path(), json=_for_model(body, model))
            refused = _refused_setting(r)
            if refused and refused not in _unsupported.get(model, set()):
                _unsupported.setdefault(model, set()).add(refused)
                log.info("Model %s does not accept %r; retrying without it", model, refused)
                r = _http().post(_chat_path(), json=_for_model(body, model))
            if _retryable(r) and attempt < config.LLM_RETRIES:
                _sleep(attempt)
                continue
            _raise_for(r)
            data = r.json()
            if _openai():
                _note_usage(data.get("usage"))
                choice = (data.get("choices") or [{}])[0]
                return (choice.get("message") or {}).get("content") or ""
            return (data.get("message") or {}).get("content", "")
        except LLMError as exc:
            last = exc
            break
        except httpx.TimeoutException:
            last = LLMError("The language model took too long to respond. Please try again.", transient=True)
        except httpx.HTTPError:
            last = LLMError("Could not reach the language model service. Check your internet connection.", transient=True)
        if attempt < config.LLM_RETRIES:
            _sleep(attempt)
    raise last or LLMError("The language model returned no answer.", transient=True)


def chat(messages: list[dict], *, model: str | None = None, json_mode: bool = False, temperature: float = 0.1,
         max_tokens: int | None = None, info: dict | None = None) -> str:
    """`info`, if given, receives which model answered and whether the fallback was used (for traces/labels)."""
    info = {} if info is None else info
    messages, red = privacy.redact_messages(messages)
    body = _payload(messages, model, False, json_mode, temperature, max_tokens)
    order = _models(model)
    last: LLMError | None = None
    for i, m in enumerate(order):
        b = breaker(m)
        if not b.allow():
            last = LLMError("The language model is temporarily unavailable. Please try again shortly.", transient=True)
            _record(model=m, ok=False, fallback=i > 0, skipped="circuit_open")
            continue
        t0 = time.monotonic()
        try:
            out = _chat_once(body, m)
        except LLMError as exc:
            if exc.transient:
                b.failure()
            _record(model=m, ok=False, fallback=i > 0, ms=int(1000 * (time.monotonic() - t0)))
            last = exc
            if not exc.fallback_ok:
                break
            continue
        b.success()
        _record(model=m, ok=True, fallback=i > 0, ms=int(1000 * (time.monotonic() - t0)))
        info.update(model=m, fallback=i > 0, ok=True)
        return red.restore(out)
    info.update(ok=False, models_tried=order)
    raise last or LLMError("The language model returned no answer.", transient=True)


def stream(messages: list[dict], *, model: str | None = None, temperature: float = 0.1,
           max_tokens: int | None = None, info: dict | None = None) -> Iterator[str]:
    """Yield answer tokens as they arrive (reasoning tokens are skipped), with identifiers restored.

    Falls back to the approved fallback model only if the main model fails before producing any text; a failure in
    the middle of an answer is raised so the caller can mark the answer as incomplete."""
    messages, red = privacy.redact_messages(messages)
    yield from red.stream(_stream_with_fallback(messages, model, temperature, max_tokens, {} if info is None else info))


def _stream_with_fallback(messages, model, temperature, max_tokens, info: dict) -> Iterator[str]:
    order = _models(model)
    last: LLMError | None = None
    for i, m in enumerate(order):
        b = breaker(m)
        if not b.allow():
            last = LLMError("The language model is temporarily unavailable. Please try again shortly.", transient=True)
            _record(model=m, ok=False, fallback=i > 0, skipped="circuit_open")
            continue
        produced = False
        t0 = time.monotonic()
        try:
            for tok in _stream(messages, m, temperature, max_tokens):
                produced = True
                yield tok
        except LLMError as exc:
            if exc.transient:
                b.failure()
            _record(model=m, ok=False, fallback=i > 0, partial=produced, ms=int(1000 * (time.monotonic() - t0)))
            info.update(model=m, fallback=i > 0, ok=False, partial=produced)
            if produced or not exc.fallback_ok:
                raise
            last = exc
            continue
        b.success()
        _record(model=m, ok=True, fallback=i > 0, ms=int(1000 * (time.monotonic() - t0)))
        info.update(model=m, fallback=i > 0, ok=True, partial=False)
        return
    info.update(ok=False, models_tried=order)
    raise last or LLMError("The language model returned no answer.", transient=True)


def _stream(messages: list[dict], model: str, temperature: float, max_tokens: int | None) -> Iterator[str]:
    body = _payload(messages, model, True, False, temperature, max_tokens)
    for attempt in range(config.LLM_RETRIES + 2):   # +1: one repeat after dropping a refused setting
        try:
            with _http().stream("POST", _chat_path(), json=_for_model(body, model)) as r:
                if r.status_code >= 400:
                    r.read()
                    refused = _refused_setting(r)
                    if refused and refused not in _unsupported.get(model, set()):
                        _unsupported.setdefault(model, set()).add(refused)
                        log.info("Model %s does not accept %r; retrying without it", model, refused)
                        continue
                    if _retryable(r) and attempt < config.LLM_RETRIES:
                        _sleep(attempt)
                        continue
                    _raise_for(r)
                if _openai():
                    yield from _openai_events(r)
                    return
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except ValueError:
                        continue
                    if evt.get("error"):
                        raise LLMError(f"Model error: {str(evt['error'])[:200]}", transient=True)
                    tok = (evt.get("message") or {}).get("content")
                    if tok:
                        yield tok
                    if evt.get("done"):
                        return
            return
        except httpx.TimeoutException as exc:
            raise LLMError("The language model took too long to respond. Please try again.", transient=True) from exc
        except httpx.HTTPError as exc:
            raise LLMError("Lost connection to the language model service.", transient=True) from exc


def _openai_events(r: httpx.Response) -> Iterator[str]:
    """Server-sent events of the Chat Completions API: `data: {json}` lines, ending with `data: [DONE]`."""
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            evt = json.loads(data)
        except ValueError:
            continue
        if evt.get("error"):
            err = evt["error"]
            raise LLMError(f"Model error: {str(err.get('message', err) if isinstance(err, dict) else err)[:200]}",
                           transient=True)
        _note_usage(evt.get("usage"))
        for ch in evt.get("choices") or []:
            tok = (ch.get("delta") or {}).get("content")
            if tok:
                yield tok


def chat_json(messages: list[dict], *, model: str | None = None, default: dict | None = None,
              info: dict | None = None) -> dict:
    """JSON-mode call with tolerant parsing; returns `default` on any failure (info['ok'] tells which)."""
    try:
        raw = chat(messages, model=model, json_mode=True, temperature=0.0, info=info)
    except LLMError as exc:
        log.warning("JSON call failed: %s", exc)
        return dict(default or {})
    return parse_json(raw, default)


def parse_json(raw: str, default: dict | None = None) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    for candidate in (raw, raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else ""):
        if not candidate:
            continue
        try:
            v = json.loads(candidate)
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    return dict(default or {})


def ping() -> tuple[bool, str]:
    """Reachability and key check without spending tokens (model list)."""
    try:
        r = _http().get("/models" if _openai() else "/api/tags", timeout=10)
        return r.status_code < 400, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, type(exc).__name__
