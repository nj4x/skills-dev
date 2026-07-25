"""Tests for AnthproxyClient."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from vectors.anthproxy_client import AnthproxyClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_httpx_mock(response_json: dict, status_code: int = 200):
    """Return a patched httpx.AsyncClient context manager with a canned response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = {}
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = response_json

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    return mock_ctx, mock_client


def _make_error_resp(status_code: int, retry_after: str | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Retry-After": retry_after} if retry_after else {}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"{status_code}",
        request=httpx.Request("POST", "http://test"),
        response=MagicMock(),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generate_response_builds_correct_messages():
    """generate_response wraps context+query into the expected message format."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    response_json = {"content": [{"type": "text", "text": "42"}]}
    mock_ctx, mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            return await client.generate_response(
                "What is the answer?", "The answer is 42.", max_tokens=50
            )

    result = asyncio.run(_run())
    assert result == "42"

    call_args = mock_http.post.call_args
    payload = call_args[1]["json"]

    assert "system" in payload
    assert "helpful assistant" in payload["system"].lower()

    user_msg = next(m for m in payload["messages"] if m["role"] == "user")
    assert "Context:\nThe answer is 42." in user_msg["content"]
    assert "Question: What is the answer?" in user_msg["content"]
    assert "Answer based on the context above:" in user_msg["content"]


def test_generate_response_custom_system_prompt():
    """generate_response uses the caller-supplied system prompt when provided."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    response_json = {"content": [{"type": "text", "text": "yes"}]}
    mock_ctx, mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            return await client.generate_response(
                "Is it true?", "context text", system_prompt="Custom sys", max_tokens=10
            )

    asyncio.run(_run())

    payload = mock_http.post.call_args[1]["json"]
    assert payload.get("system") == "Custom sys"


def test_generate_response_with_history_happy_path():
    """Mock httpx, verify correct URL + payload construction + text extraction."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku", timeout=30)

    response_json = {"content": [{"type": "text", "text": "Hello from anthproxy"}]}
    mock_ctx, mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            messages = [{"role": "user", "content": "Hello"}]
            return await client.generate_response_with_history(messages, max_tokens=100)

    result = asyncio.run(_run())

    assert result == "Hello from anthproxy"

    # Verify the POST was called with the right URL
    call_args = mock_http.post.call_args
    url = call_args[0][0]
    assert url == "http://test:8082/v1/messages"

    # Verify payload fields
    payload = call_args[1]["json"]
    assert payload["model"] == "haiku"
    assert payload["max_tokens"] == 100
    assert payload["messages"] == [{"role": "user", "content": "Hello"}]


def test_system_prompt_extracted():
    """System message goes into payload['system'], not the messages list."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    response_json = {"content": [{"type": "text", "text": "answer"}]}
    mock_ctx, mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2?"},
            ]
            return await client.generate_response_with_history(messages, max_tokens=50)

    result = asyncio.run(_run())

    assert result == "answer"

    call_args = mock_http.post.call_args
    payload = call_args[1]["json"]

    # System prompt should be at top-level key, not in messages
    assert payload.get("system") == "You are a helpful assistant."
    for msg in payload["messages"]:
        assert msg["role"] != "system", "system role must not appear in messages list"
    assert any(msg["role"] == "user" for msg in payload["messages"])


def test_empty_content_returns_empty_string():
    """When no text block is present in content, returns empty string."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    # Content has blocks but none with type=="text"
    response_json = {"content": [{"type": "image", "source": {}}]}
    mock_ctx, _mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            return await client.generate_response_with_history(
                [{"role": "user", "content": "hi"}]
            )

    result = asyncio.run(_run())
    assert result == ""


def test_embeddings_raise_not_implemented():
    """Both embedding methods raise NotImplementedError."""
    client = AnthproxyClient()

    async def _run_embed():
        await client.get_embedding("hello")

    async def _run_batch():
        await client.get_embeddings_batch(["hello", "world"])

    with pytest.raises(NotImplementedError):
        asyncio.run(_run_embed())

    with pytest.raises(NotImplementedError):
        asyncio.run(_run_batch())


def test_anthproxy_override_header_and_metadata_body():
    """X-Anthproxy-Override must be in headers; metadata.user_id must be in body payload."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    response_json = {"content": [{"type": "text", "text": "ok"}]}
    mock_ctx, mock_http = _make_httpx_mock(response_json)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            return await client.generate_response_with_history(
                [{"role": "user", "content": "hi"}]
            )

    asyncio.run(_run())

    call_args = mock_http.post.call_args
    headers = call_args[1]["headers"]
    payload = call_args[1]["json"]

    assert headers["X-Anthproxy-Override"] == "no-classifier"
    assert "X-Anthproxy-Metadata" not in headers
    assert "metadata" in payload
    assert "user_id" in payload["metadata"]
    assert "device_id" not in payload["metadata"], "device_id causes 400 from Anthropic API"
    uuid.UUID(payload["metadata"]["user_id"])  # raises ValueError if not a valid UUID


def test_429_retries_then_succeeds():
    """429 triggers exponential-backoff retry; succeeds on third attempt."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    fail_resp = _make_error_resp(429)
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {}
    ok_resp.json.return_value = {"content": [{"type": "text", "text": "success"}]}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[fail_resp, fail_resp, ok_resp])

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                return await client.generate_response_with_history(
                    [{"role": "user", "content": "hi"}]
                )

    result = asyncio.run(_run())

    assert result == "success"
    assert mock_client.post.call_count == 3
    assert sleep_calls == [1.0, 2.0]


def test_5xx_retries():
    """5xx server errors trigger the same retry path as 429."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    fail_resp = _make_error_resp(503)
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {}
    ok_resp.json.return_value = {"content": [{"type": "text", "text": "recovered"}]}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[fail_resp, ok_resp])

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                return await client.generate_response_with_history(
                    [{"role": "user", "content": "hi"}]
                )

    result = asyncio.run(_run())

    assert result == "recovered"
    assert mock_client.post.call_count == 2
    assert len(sleep_calls) == 1


def test_no_retry_on_4xx():
    """Non-429 4xx errors raise immediately without any retry."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    bad_resp = _make_error_resp(400)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=bad_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                with pytest.raises(httpx.HTTPStatusError):
                    await client.generate_response_with_history(
                        [{"role": "user", "content": "hi"}]
                    )

    asyncio.run(_run())

    assert mock_client.post.call_count == 1
    assert sleep_calls == []


def test_retry_after_header_respected():
    """Retry-After from server is used as the floor for the sleep delay."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    # Server asks for 10s; our backoff starts at 1s — server value must win
    fail_resp = _make_error_resp(429, retry_after="10")
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {}
    ok_resp.json.return_value = {"content": [{"type": "text", "text": "ok"}]}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[fail_resp, ok_resp])

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                return await client.generate_response_with_history(
                    [{"role": "user", "content": "hi"}]
                )

    result = asyncio.run(_run())

    assert result == "ok"
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 10.0


def test_retry_after_unparseable_falls_back_to_exponential():
    """An HTTP-date Retry-After that can't be parsed as float uses exponential backoff."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    fail_resp = _make_error_resp(429, retry_after="Wed, 21 Oct 2015 07:28:00 GMT")
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {}
    ok_resp.json.return_value = {"content": [{"type": "text", "text": "ok"}]}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[fail_resp, ok_resp])

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                return await client.generate_response_with_history(
                    [{"role": "user", "content": "hi"}]
                )

    result = asyncio.run(_run())

    assert result == "ok"
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 1.0  # fell back to initial exponential delay


def test_raises_after_max_retries_exhausted():
    """After 6 retries (7 total attempts) the last raise_for_status propagates."""
    client = AnthproxyClient(base_url="http://test:8082", model="haiku")

    fail_resp = _make_error_resp(429)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=fail_resp)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    async def _run():
        with patch("vectors.anthproxy_client.httpx.AsyncClient", return_value=mock_ctx):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                with pytest.raises(httpx.HTTPStatusError):
                    await client.generate_response_with_history(
                        [{"role": "user", "content": "hi"}]
                    )

    asyncio.run(_run())

    assert mock_client.post.call_count == 7  # 1 initial + 6 retries
    assert len(sleep_calls) == 6
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
