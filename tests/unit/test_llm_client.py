import json

import httpx

from contra.config.models import LlmConfig
from contra.debate.llm_client import LlmClient
from contra.debate.types import Message

SSE = (
    b'data: {"choices":[{"delta":{"content":"Product"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":"ivity"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":" gains"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    b"data: [DONE]\n\n"
)


def _mock_client(body: bytes = SSE) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_streams_token_deltas_in_order():
    client = LlmClient(LlmConfig(), http_client=_mock_client())
    tokens = [t async for t in client.stream([Message(role="user", content="hi")])]
    assert tokens == ["Product", "ivity", " gains"]
    await client.aclose()


async def test_skips_malformed_frames_without_dying():
    body = (
        b"data: {not json}\n\n"
        b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
        b"data: [DONE]\n\n"
    )
    client = LlmClient(LlmConfig(), http_client=_mock_client(body))
    tokens = [t async for t in client.stream([Message(role="user", content="hi")])]
    assert tokens == ["ok"]
    await client.aclose()


async def test_ignores_frames_with_no_choices():
    body = (
        b'data: {"choices":[]}\n\n'
        b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
        b"data: [DONE]\n\n"
    )
    client = LlmClient(LlmConfig(), http_client=_mock_client(body))
    tokens = [t async for t in client.stream([Message(role="user", content="hi")])]
    assert tokens == ["ok"]
    await client.aclose()


async def test_cancel_stops_iteration():
    client = LlmClient(LlmConfig(), http_client=_mock_client())
    tokens = []
    async for t in client.stream([Message(role="user", content="hi")]):
        tokens.append(t)
        await client.cancel()
    assert tokens == ["Product"]
    await client.aclose()


async def test_request_body_carries_required_params():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, content=SSE, headers={"content-type": "text/event-stream"})

    client = LlmClient(
        LlmConfig(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    async for _ in client.stream([Message(role="user", content="hi")]):
        pass
    assert captured["stream"] is True
    assert captured["presence_penalty"] == 1.5
    assert captured["max_tokens"] == 220
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    await client.aclose()


async def test_health_returns_false_when_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = LlmClient(
        LlmConfig(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await client.health() is False
    await client.aclose()
