"""Real API client, with the network replaced: error classes, response mapping, request passed through unchanged."""
import asyncio

import anthropic
import httpx2
import pytest

from src.clients import AnthropicModel, FatalError, RetryableError, cost_usd


def _err(cls, status, headers=None):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(status, request=req, headers=headers or {})
    return cls("test error", response=resp, body=None)


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    return AnthropicModel(timeout_s=5)


@pytest.mark.parametrize("cls,status,kind", [
    (anthropic.RateLimitError, 429, RetryableError),
    (anthropic.InternalServerError, 500, RetryableError),
    (anthropic.InternalServerError, 529, RetryableError),
    (anthropic.BadRequestError, 400, FatalError),
    (anthropic.AuthenticationError, 401, FatalError),
    (anthropic.PermissionDeniedError, 403, FatalError),
    (anthropic.NotFoundError, 404, FatalError),
])
def test_error_classes(model, monkeypatch, cls, status, kind):
    async def raise_(**kw):
        raise _err(cls, status, {"retry-after": "7"})

    monkeypatch.setattr(model.client.messages, "create", raise_)
    with pytest.raises(kind) as ei:
        asyncio.run(model.create({"model": "m", "max_tokens": 1, "messages": []}))
    assert ei.value.http_status == status
    if kind is RetryableError and status == 429:
        assert ei.value.retry_after == 7.0


def test_connection_error_is_retryable(model, monkeypatch):
    async def raise_(**kw):
        raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    monkeypatch.setattr(model.client.messages, "create", raise_)
    with pytest.raises(RetryableError):
        asyncio.run(model.create({}))


def test_response_mapping_and_pass_through(model, monkeypatch):
    seen = {}
    msg = anthropic.types.Message.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 3,
                  "cache_read_input_tokens": 600},
    })

    async def create(**kw):
        seen.update(kw)
        return msg

    monkeypatch.setattr(model.client.messages, "create", create)
    req = {"model": "claude-haiku-5-5", "max_tokens": 1024, "system": "s", "messages": [{"role": "user", "content": "x"}],
           "cache_control": {"type": "ephemeral"}, "thinking": {"type": "disabled"}}
    r = asyncio.run(model.create(req))
    assert seen == req
    assert r.text == "Hello world" and r.stop_reason == "end_turn" and r.api_model == "claude-haiku-5-5"
    assert [b["type"] for b in r.content] == ["text", "text"]
    assert r.usage["cache_read_input_tokens"] == 600 and r.usage["input_tokens"] == 10


def test_cost():
    p = {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
         "cache_creation_input_tokens": 1_000_000}
    assert cost_usd(u, p) == pytest.approx(0.735)


def test_sdk_accepts_request_options():
    """The installed SDK names output_config, cache_control and thinking as create() parameters (spec 6.3)."""
    import inspect
    params = inspect.signature(anthropic.resources.messages.AsyncMessages.create).parameters
    assert {"output_config", "cache_control", "thinking"} <= set(params)
