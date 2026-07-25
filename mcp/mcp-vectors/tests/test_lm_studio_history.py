"""Test generate_response_with_history and embedding logging on LMStudioClient."""
import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helper to build a pre-initialized LMStudioClient stub
# ---------------------------------------------------------------------------

def _make_client(model="test-model"):
    from vectors.lm_studio import LMStudioClient, EmbeddingCache, SummaryCache
    client = LMStudioClient.__new__(LMStudioClient)
    client._initialized = True
    client._llm_model = model
    client._embedding_model = model
    client._ttl = -1
    client.embedding_batch_size = 100
    client._embedding_cache = EmbeddingCache(max_size=8)
    client._summary_cache = SummaryCache(max_size=8)
    return client


def _mock_completions(content="Test response"):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_openai


def _mock_embeddings(dim=4):
    def _item(idx):
        m = MagicMock()
        m.index = idx
        m.embedding = [0.1] * dim
        return m

    def _response_for(input_list):
        r = MagicMock()
        r.data = [_item(i) for i in range(len(input_list))]
        return r

    mock_openai = MagicMock()
    mock_openai.embeddings.create = AsyncMock(
        side_effect=lambda **kw: _response_for(kw["input"] if isinstance(kw["input"], list) else ["x"])
    )
    return mock_openai


# ---------------------------------------------------------------------------
# Existing contract tests (unchanged)
# ---------------------------------------------------------------------------

def test_method_exists():
    """generate_response_with_history must be present on LMStudioClient."""
    from vectors.lm_studio import LMStudioClient
    assert hasattr(LMStudioClient, 'generate_response_with_history')


def test_signature():
    """Method must accept messages: list[dict] and max_tokens: int."""
    from vectors.lm_studio import LMStudioClient
    sig = inspect.signature(LMStudioClient.generate_response_with_history)
    params = list(sig.parameters.keys())
    assert 'messages' in params
    assert 'max_tokens' in params


def test_calls_chat_completions():
    """Method must call client.chat.completions.create with the messages list."""
    client = _make_client()
    mock_openai = _mock_completions("Test response")
    client.client = mock_openai

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user",   "content": "Hello"},
    ]
    result = asyncio.run(client.generate_response_with_history(messages, max_tokens=512))

    assert result == "Test response"
    mock_openai.chat.completions.create.assert_called_once()
    call_kwargs = mock_openai.chat.completions.create.call_args
    assert call_kwargs.kwargs.get('messages') == messages or \
           (call_kwargs.args and call_kwargs.args[0] == messages)


def test_returns_empty_string_on_none_content():
    """Method must return '' when message content is None."""
    client = _make_client()
    client.client = _mock_completions(None)

    result = asyncio.run(
        client.generate_response_with_history([{"role": "user", "content": "Hi"}])
    )
    assert result == ""


# ---------------------------------------------------------------------------
# New observability tests: log fields must be safe (no text/vector content)
# ---------------------------------------------------------------------------

def _capture_debug(logger_name, fn, *args, **kwargs):
    """Run async fn and collect all LogRecord.extra dicts emitted at DEBUG+."""
    records = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Cap(level=logging.DEBUG)
    log = logging.getLogger(logger_name)
    original_level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        result = asyncio.run(fn(*args, **kwargs))
    finally:
        log.removeHandler(handler)
        log.setLevel(original_level)
    return records, result


def _extra(record):
    """Return the extra dict fields attached to a LogRecord (excludes std attrs)."""
    STANDARD = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
        'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
        'processName', 'process', 'message', 'taskName',
    }
    return {k: v for k, v in record.__dict__.items() if k not in STANDARD}


def test_generate_response_with_history_logs_message_count():
    """Request log must include message_count, not message contents."""
    client = _make_client()
    client.client = _mock_completions("reply")

    messages = [
        {"role": "system", "content": "secret system prompt"},
        {"role": "user",   "content": "secret user question"},
    ]
    records, result = _capture_debug("vectors.lm_studio", client.generate_response_with_history, messages)

    assert result == "reply"
    # Find the request log record
    req_records = [r for r in records if "request" in r.getMessage().lower() and "history" in r.getMessage().lower()]
    assert req_records, "Expected a request log entry for generate_response_with_history"
    ext = _extra(req_records[0])
    # Must carry message_count (count only, not content)
    assert ext.get("message_count") == 2
    # Must NOT carry any message content
    for record in records:
        for v in _extra(record).values():
            if isinstance(v, str):
                assert "secret" not in v, f"Secret content leaked into log: {v!r}"


def test_generate_response_with_history_logs_response_length():
    """Response log must include response_length (int), not response text."""
    client = _make_client()
    client.client = _mock_completions("hello world")

    records, result = _capture_debug(
        "vectors.lm_studio",
        client.generate_response_with_history,
        [{"role": "user", "content": "hi"}],
    )
    assert result == "hello world"
    resp_records = [r for r in records if "received" in r.getMessage().lower() and "history" in r.getMessage().lower()]
    assert resp_records, "Expected a received log entry for generate_response_with_history"
    ext = _extra(resp_records[0])
    assert ext.get("response_length") == len("hello world")
    # Must NOT log the actual response text
    for record in records:
        for v in _extra(record).values():
            if isinstance(v, str):
                assert "hello world" not in v, f"Response text leaked into log: {v!r}"


def test_get_embedding_logs_dimension_not_vector():
    """get_embedding must log embedding_dimension (int), not the vector itself."""
    client = _make_client()
    client.client = _mock_embeddings(dim=8)

    records, embedding = _capture_debug("vectors.lm_studio", client.get_embedding, "some text")
    assert len(embedding) == 8

    completed_records = [r for r in records if "completed" in r.getMessage().lower() and "single" in r.getMessage().lower()]
    assert completed_records, "Expected a single embedding completed log"
    ext = _extra(completed_records[0])
    assert ext.get("embedding_dimension") == 8

    # Must NOT log the vector values
    for record in records:
        for v in _extra(record).values():
            assert not isinstance(v, list), f"Vector data leaked into log extra: {v!r}"
        # Also check message itself doesn't contain the raw float list
        assert "0.1" not in record.getMessage()


def test_get_embeddings_batch_logs_counts_not_vectors():
    """get_embeddings_batch must log counts only, never vector data."""
    client = _make_client()
    client.client = _mock_embeddings(dim=4)

    texts = ["a", "b", "c"]
    records, embeddings = _capture_debug("vectors.lm_studio", client.get_embeddings_batch, texts)
    assert len(embeddings) == 3
    assert all(len(e) == 4 for e in embeddings)

    batch_records = [r for r in records if "batch" in r.getMessage().lower()]
    assert batch_records, "Expected at least one batch log entry"

    req_record = next(
        (r for r in batch_records if "request" in r.getMessage().lower()), None
    )
    assert req_record, "Expected a batch request log entry"
    ext = _extra(req_record)
    assert ext.get("total_input_count") == 3

    completed_record = next(
        (r for r in batch_records if "completed" in r.getMessage().lower()), None
    )
    assert completed_record, "Expected a batch completed log entry"
    ext_c = _extra(completed_record)
    assert ext_c.get("total_output_count") == 3

    # Must NOT log vector data
    for record in records:
        for v in _extra(record).values():
            assert not isinstance(v, list), f"Vector data leaked into log extra: {v!r}"


def test_generate_response_with_history_logs_error_type_on_failure():
    """On exception, log must include error_type, not exception message details."""
    client = _make_client()
    mock_openai = MagicMock()
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("internal server error with secrets")
    )
    client.client = mock_openai

    records = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Cap(level=logging.DEBUG)
    log = logging.getLogger("vectors.lm_studio")
    original_level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        try:
            asyncio.run(client.generate_response_with_history([{"role": "user", "content": "hi"}]))
        except RuntimeError:
            pass
    finally:
        log.removeHandler(handler)
        log.setLevel(original_level)

    error_records = [r for r in records if r.levelno >= logging.ERROR]
    assert error_records, "Expected at least one ERROR log on failure"
    ext = _extra(error_records[0])
    assert ext.get("error_type") == "RuntimeError"
