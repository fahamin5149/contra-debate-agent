from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from contra.config.models import LlmConfig
from contra.debate.types import Message

__all__ = ["LlmClient"]


class LlmClient:
    """Streaming client for llama-server's OpenAI-compatible API.

    Uses httpx directly rather than the openai SDK so that cancel() can abort
    the underlying HTTP request. Merely abandoning the iterator is not enough:
    llama-server keeps generating until the connection closes, occupying the
    slot the NEXT turn needs. The visible symptom is that interrupting the
    agent makes the following response slower — the opposite of the intent.
    """

    def __init__(self, config: LlmConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self._cfg = config
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=config.timeout_s)
        self._cancelled = False
        self._response: httpx.Response | None = None

    def _payload(self, messages: list[Message]) -> dict[str, Any]:
        s = self._cfg.sampling
        return {
            "model": self._cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": s.temperature,
            "top_p": s.top_p,
            "top_k": s.top_k,
            "min_p": s.min_p,
            "presence_penalty": s.presence_penalty,
            "repeat_penalty": s.repeat_penalty,
            "max_tokens": self._cfg.max_response_tokens,
            "chat_template_kwargs": {"enable_thinking": self._cfg.enable_thinking},
        }

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        self._cancelled = False
        url = f"{self._cfg.base_url.rstrip('/')}/chat/completions"
        async with self._http.stream("POST", url, json=self._payload(messages)) as response:
            self._response = response
            response.raise_for_status()
            async for line in response.aiter_lines():
                if self._cancelled:
                    break
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue  # malformed frame: skip it, keep the stream alive
                choices = parsed.get("choices") or []
                if not choices:
                    continue
                content = (choices[0].get("delta") or {}).get("content")
                if content:
                    yield content
        self._response = None

    async def cancel(self) -> None:
        """Abort generation. Must close the connection, not just stop reading."""
        self._cancelled = True
        if self._response is not None:
            await self._response.aclose()
            self._response = None

    async def health(self) -> bool:
        root = self._cfg.base_url.rstrip("/").removesuffix("/v1")
        try:
            r = await self._http.get(f"{root}/health", timeout=2.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()
