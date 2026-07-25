"""Async LLM client backed by a local anthproxy router (Anthropic Messages API)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class AnthproxyClient:
    """Thin async wrapper around anthproxy's /v1/messages endpoint.

    Only implements the LLM (chat) interface; embeddings are not supported
    and will raise NotImplementedError. Use alongside LMStudioClient for
    embeddings.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8082",
        model: str = "haiku",
        timeout: int = 120,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._initialized = False
        self._session_id = str(uuid.uuid4())
        # Expose _llm_model for duck-type compatibility with LMStudioClient
        # (community_reporter.py checks hasattr(lm_client, "_llm_model"))
        self._llm_model = model

    async def initialize(self) -> None:
        # No warm-up needed; just mark ready
        self._initialized = True
        logger.info(f"AnthproxyClient ready: {self._base_url}, model={self._model}")

    @property
    def llm_model(self) -> str:
        return self._model

    async def generate_response_with_history(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        payload = self._build_payload(messages, max_tokens)
        return await self._post(payload)

    async def generate_response(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> str:
        if system_prompt is None:
            system_prompt = (
                "You are a helpful assistant that answers questions based on the provided context. "
                "Use only the information from the context to answer. "
                "If the context doesn't contain relevant information, say so clearly."
            )
        user_content = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer based on the context above:"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        return await self.generate_response_with_history(messages, max_tokens)

    def _build_payload(self, messages: list[dict], max_tokens: int) -> dict:
        # Extract system prompt if present as first message
        system = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        payload: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        return payload

    async def _post(self, payload: dict) -> str:
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": "unused",
            "content-type": "application/json",
            "X-Anthproxy-Override": "no-classifier",
        }
        model = payload.get("model", self._model)
        message_count = len(payload.get("messages", []))
        max_tokens = payload.get("max_tokens", 0)
        payload = {**payload, "metadata": {"user_id": self._session_id}}
        delay = 1.0
        max_retries = 6
        op_start = time.monotonic()
        logger.debug(
            "anthproxy.post: starting "
            "reason=generate_completion service=anthproxy "
            "model=%s message_count=%d max_tokens=%d max_retries=%d",
            model, message_count, max_tokens, max_retries,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(max_retries + 1):
                attempt_start = time.monotonic()
                resp = await client.post(url, headers=headers, json=payload)
                attempt_ms = int((time.monotonic() - attempt_start) * 1000)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    content = data.get("content", [])
                    result_text = ""
                    for block in content:
                        if block.get("type") == "text":
                            result_text = block.get("text", "")
                            break
                    total_ms = int((time.monotonic() - op_start) * 1000)
                    logger.debug(
                        "anthproxy.post: done "
                        "service=anthproxy model=%s attempt=%d "
                        "attempt_ms=%d total_ms=%d status=success response_length=%d",
                        model, attempt + 1, attempt_ms, total_ms, len(result_text),
                    )
                    return result_text
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt >= max_retries:
                        resp.raise_for_status()
                    retry_after = resp.headers.get("Retry-After")
                    actual_delay = delay
                    if retry_after:
                        try:
                            actual_delay = max(float(retry_after), delay)
                        except (ValueError, TypeError):
                            pass
                    logger.warning(
                        "anthproxy.post: retry "
                        "service=anthproxy model=%s status_code=%d "
                        "attempt=%d/%d attempt_ms=%d retry_delay_s=%.1f",
                        model, resp.status_code, attempt + 1, max_retries + 1,
                        attempt_ms, actual_delay,
                    )
                    await asyncio.sleep(actual_delay)
                    delay = min(delay * 2, 60.0)
                else:
                    resp.raise_for_status()
        raise RuntimeError("unreachable")

    # Embeddings not supported — callers must use LMStudioClient for these
    async def get_embedding(self, text: str) -> list[float]:
        raise NotImplementedError(
            "AnthproxyClient does not support embeddings; use LMStudioClient"
        )

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "AnthproxyClient does not support embeddings; use LMStudioClient"
        )
