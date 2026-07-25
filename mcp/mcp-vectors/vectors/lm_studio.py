"""LM Studio client for embeddings and LLM generation."""

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """LRU cache for embedding vectors, keyed by (model_name, text_hash)."""

    def __init__(self, max_size: int = 512):
        """
        Initialize embedding cache.

        Args:
            max_size: Maximum number of cached embeddings (LRU eviction)
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, list[float]] = OrderedDict()
        self._model_name: Optional[str] = None

    def set_model(self, model_name: str) -> None:
        """
        Set the active model. Invalidates cache on model change.

        Args:
            model_name: Resolved embedding model name
        """
        if self._model_name and self._model_name != model_name:
            logger.info(f"Embedding model changed from {self._model_name} to {model_name}; clearing cache")
            self.cache.clear()
        self._model_name = model_name

    @staticmethod
    def _make_key(model_name: str, text: str) -> str:
        """Generate cache key from model and text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"{model_name}:{text_hash}"

    def get(self, model_name: str, text: str) -> Optional[list[float]]:
        """
        Retrieve cached embedding.

        Args:
            model_name: Embedding model name
            text: Text that was embedded

        Returns:
            Cached embedding vector, or None if not found
        """
        key = self._make_key(model_name, text)
        if key in self.cache:
            # Move to end (LRU eviction)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, model_name: str, text: str, embedding: list[float]) -> None:
        """
        Store embedding in cache.

        Args:
            model_name: Embedding model name
            text: Text that was embedded
            embedding: Embedding vector
        """
        key = self._make_key(model_name, text)
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # Evict oldest (first) entry
                self.cache.popitem(last=False)
            self.cache[key] = embedding

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self.cache.clear()


class SummaryCache:
    """Cache for file summaries, keyed by (model_name, file_hash)."""

    def __init__(self, max_size: int = 1000):
        """
        Initialize summary cache.

        Args:
            max_size: Maximum number of cached summaries (LRU eviction)
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, str] = OrderedDict()
        self._model_name: Optional[str] = None

    def set_model(self, model_name: str) -> None:
        """
        Set the active model. Invalidates cache on model change.

        Args:
            model_name: Resolved LLM model name
        """
        if self._model_name and self._model_name != model_name:
            logger.info(f"LLM model changed from {self._model_name} to {model_name}; clearing cache")
            self.cache.clear()
        self._model_name = model_name

    @staticmethod
    def _make_key(model_name: str, file_hash: str) -> str:
        """Generate cache key from model and file hash."""
        return f"{model_name}:{file_hash}"

    def get(self, model_name: str, file_hash: str) -> Optional[str]:
        """
        Retrieve cached summary.

        Args:
            model_name: LLM model name
            file_hash: File hash (MD5)

        Returns:
            Cached summary, or None if not found
        """
        key = self._make_key(model_name, file_hash)
        if key in self.cache:
            # Move to end (LRU eviction)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, model_name: str, file_hash: str, summary: str) -> None:
        """
        Store summary in cache.

        Args:
            model_name: LLM model name
            file_hash: File hash (MD5)
            summary: Summary text
        """
        key = self._make_key(model_name, file_hash)
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # Evict oldest (first) entry
                self.cache.popitem(last=False)
            self.cache[key] = summary

    def clear(self) -> None:
        """Clear all cached summaries."""
        self.cache.clear()


class LMStudioClient:
    """Client for LM Studio's OpenAI-compatible API."""
    
    # Known embedding model prefixes
    EMBEDDING_PREFIXES = ["text-embedding", "embedding", "nomic", "minilm"]
    
    # Known LLM model prefixes (exclude embedding models)
    LLM_EXCLUDE_PREFIXES = ["text-embedding", "embedding"]
    
    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        embedding_model: str = "auto",
        llm_model: str = "auto",
        embedding_batch_size: int = 100,
        ttl: int = -1,
    ):
        """
        Initialize the LM Studio client.

        Args:
            base_url: LM Studio API URL
            embedding_model: Embedding model name or "auto" for auto-detection
            llm_model: LLM model name or "auto" for auto-detection
            embedding_batch_size: Max texts per embedding RPC (default: 100)
            ttl: Seconds to keep the model loaded after each call (-1 = indefinite,
                 0 = unload immediately). Passed as LM Studio's ``ttl`` extension
                 field on every API request.
        """
        # Clean up the base URL to remove any trailing commas or slashes
        self.base_url = base_url.rstrip("/,")
        self._embedding_model_name = embedding_model
        self._llm_model_name = llm_model
        self.embedding_batch_size = embedding_batch_size
        self._ttl = ttl
        
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key="not-needed"  # LM Studio doesn't require API key
        )
        
        self._available_models: list[str] = []
        self._embedding_model: Optional[str] = None
        self._llm_model: Optional[str] = None
        self._embedding_dimension: Optional[int] = None
        self._initialized = False
        self._embedding_cache = EmbeddingCache(max_size=512)
        self._summary_cache = SummaryCache(max_size=1000)
    
    async def initialize(self) -> None:
        """Initialize the client and detect available models."""
        if self._initialized:
            return
        
        logger.info(f"Connecting to LM Studio at {self.base_url}")
        
        # Get available models
        try:
            models_response = await self.client.models.list()
            # Handle case where models_response.data might be None
            if models_response.data is None:
                logger.error("LM Studio returned None for models list")
                raise ConnectionError(
                    f"LM Studio at {self.base_url} returned invalid response. "
                    "Make sure LM Studio is running with the server enabled and models loaded."
                )
            self._available_models = [m.id for m in models_response.data]
            logger.info(f"Available models: {self._available_models}")
        except Exception as e:
            logger.error(f"Failed to connect to LM Studio: {e}")
            raise ConnectionError(
                f"Cannot connect to LM Studio at {self.base_url}. "
                "Make sure LM Studio is running with the server enabled."
            ) from e
        
        if not self._available_models:
            raise ValueError("No models available in LM Studio. Please load at least one model.")
        
        # Auto-detect or validate embedding model
        if self._embedding_model_name == "auto":
            self._embedding_model = self._detect_embedding_model()
        else:
            if self._embedding_model_name in self._available_models:
                self._embedding_model = self._embedding_model_name
            else:
                raise ValueError(
                    f"Embedding model '{self._embedding_model_name}' not found. "
                    f"Available models: {self._available_models}"
                )
        
        # Auto-detect or validate LLM model
        if self._llm_model_name == "auto":
            self._llm_model = self._detect_llm_model()
        else:
            if self._llm_model_name in self._available_models:
                self._llm_model = self._llm_model_name
            else:
                raise ValueError(
                    f"LLM model '{self._llm_model_name}' not found. "
                    f"Available models: {self._available_models}"
                )
        
        logger.info(f"Selected embedding model: {self._embedding_model}")
        logger.info(f"Selected LLM model: {self._llm_model}")

        # Detect embedding dimension
        await self._detect_embedding_dimension()

        # Set models in caches for key generation
        self._embedding_cache.set_model(self._embedding_model)
        self._summary_cache.set_model(self._llm_model)

        self._initialized = True
    
    def _detect_embedding_model(self) -> str:
        """Auto-detect the best embedding model from available models."""
        # Priority order for embedding models
        preferred_models = [
            "text-embedding-nomic-embed-text-v1.5",
            "text-embedding-all-minilm-l6-v2",
        ]
        
        # Check preferred models first
        for model in preferred_models:
            if model in self._available_models:
                return model
        
        # Look for any model with embedding-related prefix
        for model in self._available_models:
            model_lower = model.lower()
            for prefix in self.EMBEDDING_PREFIXES:
                if prefix in model_lower:
                    return model
        
        # Fall back to first available model
        logger.warning(
            f"No embedding model detected. Using first available model: {self._available_models[0]}"
        )
        return self._available_models[0]
    
    def _detect_llm_model(self) -> str:
        """Auto-detect the best LLM model from available models."""
        # Priority order for LLM models
        preferred_models = [
            "mistralai/mistral-small-3.2",
        ]
        
        # Check preferred models first
        for model in preferred_models:
            if model in self._available_models:
                return model
        
        # Look for any non-embedding model
        for model in self._available_models:
            model_lower = model.lower()
            is_embedding = any(prefix in model_lower for prefix in self.LLM_EXCLUDE_PREFIXES)
            if not is_embedding:
                return model
        
        # Fall back to first available model (even if embedding)
        logger.warning(
            f"No LLM model detected. Using first available model: {self._available_models[0]}"
        )
        return self._available_models[0]
    
    async def _detect_embedding_dimension(self) -> None:
        """Detect the embedding dimension for the selected model.
        
        Includes retry logic with exponential backoff to handle concurrent
        model loading conflicts when multiple MCP server instances start.
        """
        max_retries = 3
        base_delay = 2.0  # seconds
        
        for attempt in range(max_retries):
            try:
                await self._try_detect_embedding_dimension()
                return  # Success
            except ValueError as e:
                # Check if this is a retryable error (model loading conflict)
                error_str = str(e).lower()
                is_retryable = (
                    "canceled" in error_str or
                    "operation canceled" in error_str or
                    "failed to load" in error_str
                )
                
                if is_retryable and attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)  # 2s, 4s, 6s
                    logger.warning(
                        f"Embedding model detection failed (attempt {attempt + 1}/{max_retries}), "
                        f"likely concurrent model loading conflict. Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                
                # Not retryable or last attempt - re-raise
                raise
    
    async def _try_detect_embedding_dimension(self) -> None:
        """Try to detect embedding dimension once. May raise ValueError on failure."""
        # Use the already selected embedding model (configured or auto-detected)
        model = self._embedding_model
        
        logger.info(f"Detecting embedding dimension for model: {model}")
        
        logger.info(
            "LM Studio embedding dimension probe requested",
            extra={"model": model, "input_count": 1, "ttl": self._ttl},
        )
        try:
            response = await self.client.embeddings.create(
                model=model,
                input="test",
                encoding_format="float",  # LM Studio doesn't support base64 (SDK default)
                extra_body={"ttl": self._ttl},
            )
            self._embedding_dimension = len(response.data[0].embedding)
            logger.info(
                "LM Studio embedding dimension probe completed",
                extra={"model": model, "embedding_dimension": self._embedding_dimension},
            )
        except Exception as e:
            logger.exception(
                "LM Studio embedding dimension probe failed",
                extra={"model": model, "error_type": type(e).__name__},
            )
            raise ValueError(
                f"Embedding model '{model}' failed: {e}. "
                f"Make sure the model is loaded in LM Studio."
            ) from e
    
    @property
    def embedding_model(self) -> str:
        """Get the selected embedding model name."""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        return self._embedding_model
    
    @property
    def llm_model(self) -> str:
        """Get the selected LLM model name."""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        return self._llm_model
    
    @property
    def embedding_dimension(self) -> int:
        """Get the embedding vector dimension."""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        return self._embedding_dimension
    
    async def get_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for a single text, with caching.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if not self._initialized:
            await self.initialize()

        # Check cache first
        cached = self._embedding_cache.get(self._embedding_model, text)
        if cached is not None:
            logger.debug(
                "Embedding cache hit",
                extra={"model": self._embedding_model},
            )
            return cached

        logger.debug(
            "LM Studio single embedding request",
            extra={"model": self._embedding_model, "input_count": 1, "ttl": self._ttl},
        )
        response = await self.client.embeddings.create(
            model=self._embedding_model,
            input=text,
            encoding_format="float",  # LM Studio doesn't support base64 (SDK default)
            extra_body={"ttl": self._ttl},
        )
        embedding = response.data[0].embedding
        logger.debug(
            "LM Studio single embedding completed",
            extra={"model": self._embedding_model, "embedding_dimension": len(embedding)},
        )

        # Store in cache
        self._embedding_cache.put(self._embedding_model, text, embedding)
        return embedding
    
    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts, with sub-batching for robustness.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors, in the same order as input
        """
        if not self._initialized:
            await self.initialize()

        if not texts:
            return []

        # Sub-batch to avoid huge single RPCs (which can timeout or OOM on large files)
        total = len(texts)
        num_batches = (total + self.embedding_batch_size - 1) // self.embedding_batch_size
        logger.debug(
            "LM Studio batch embedding request",
            extra={
                "model": self._embedding_model,
                "total_input_count": total,
                "batch_count": num_batches,
                "batch_size": self.embedding_batch_size,
                "ttl": self._ttl,
            },
        )
        all_embeddings = {}
        for batch_start in range(0, total, self.embedding_batch_size):
            batch_end = min(batch_start + self.embedding_batch_size, total)
            batch_texts = texts[batch_start:batch_end]
            batch_num = batch_start // self.embedding_batch_size + 1

            logger.debug(
                "LM Studio embedding sub-batch",
                extra={
                    "model": self._embedding_model,
                    "batch_num": batch_num,
                    "batch_input_count": len(batch_texts),
                    "ttl": self._ttl,
                },
            )
            response = await self.client.embeddings.create(
                model=self._embedding_model,
                input=batch_texts,
                encoding_format="float",  # LM Studio doesn't support base64 (SDK default)
                extra_body={"ttl": self._ttl},
            )

            # Store embeddings by their global index (batch_start + local_index)
            for item in response.data:
                global_index = batch_start + item.index
                all_embeddings[global_index] = item.embedding

        logger.debug(
            "LM Studio batch embedding completed",
            extra={
                "model": self._embedding_model,
                "total_output_count": len(all_embeddings),
            },
        )
        # Return embeddings in original order
        return [all_embeddings[i] for i in range(total)]
    
    async def generate_response(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """
        Generate a response using the LLM with provided context.
        
        Args:
            query: User's question
            context: Retrieved context from documents
            system_prompt: Optional system prompt override
            max_tokens: Maximum tokens in response
            
        Returns:
            Generated response text
        """
        if not self._initialized:
            await self.initialize()
        
        if system_prompt is None:
            system_prompt = (
                "You are a helpful assistant that answers questions based on the provided context. "
                "Use only the information from the context to answer. "
                "If the context doesn't contain relevant information, say so clearly."
            )
        
        user_prompt = f"""Context:
{context}

Question: {query}

Answer based on the context above:"""
        
        logger.debug(
            "LM Studio completion request (generate_response)",
            extra={
                "model": self._llm_model,
                "message_count": 2,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "ttl": self._ttl,
            },
        )
        response = await self.client.chat.completions.create(
            model=self._llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            extra_body={"ttl": self._ttl},
        )
        content = response.choices[0].message.content
        logger.debug(
            "LM Studio completion received (generate_response)",
            extra={
                "model": self._llm_model,
                "response_length": len(content) if content else 0,
            },
        )
        return content

    async def generate_response_with_history(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> str:
        """Multi-turn LLM completion. Caller assembles the full messages list.

        Each message is {"role": "system"|"user"|"assistant", "content": str}.
        Used by entity extraction gleaning loop which needs conversation history.
        """
        if not self._initialized:
            await self.initialize()
        logger.debug(
            "LM Studio completion request (generate_response_with_history)",
            extra={
                "model": self._llm_model,
                "message_count": len(messages),
                "max_tokens": max_tokens,
                "temperature": 0.0,
                "ttl": self._ttl,
            },
        )
        try:
            response = await self.client.chat.completions.create(
                model=self._llm_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
                extra_body={"ttl": self._ttl},
            )
            content = response.choices[0].message.content or ""
            logger.debug(
                "LM Studio completion received (generate_response_with_history)",
                extra={
                    "model": self._llm_model,
                    "response_length": len(content),
                },
            )
            return content
        except Exception as e:
            logger.error(
                "LM Studio completion failed (generate_response_with_history)",
                extra={"model": self._llm_model, "error_type": type(e).__name__},
            )
            raise

    async def generate_summary(
        self,
        text: str,
        max_length: int = 200,
        file_hash: Optional[str] = None,
    ) -> str:
        """
        Generate a summary of the provided text, with caching.

        Args:
            text: Text to summarize
            max_length: Approximate max length of summary
            file_hash: Optional file hash for caching (enables cache hits)

        Returns:
            Summary text
        """
        if not self._initialized:
            await self.initialize()

        # Check cache first (if file_hash provided)
        if file_hash:
            cached = self._summary_cache.get(self._llm_model, file_hash)
            if cached is not None:
                logger.debug(
                    "Summary cache hit",
                    extra={"model": self._llm_model, "file_hash_prefix": file_hash[:8]},
                )
                return cached

        prompt = f"""Summarize the following text in about {max_length} characters:

{text[:4000]}  # Limit input to avoid token limits

Summary:"""

        logger.debug(
            "LM Studio completion request (generate_summary)",
            extra={
                "model": self._llm_model,
                "max_tokens": max_length // 2,
                "temperature": 0.3,
                "input_char_count": min(len(text), 4000),
                "ttl": self._ttl,
            },
        )
        response = await self.client.chat.completions.create(
            model=self._llm_model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_length // 2,  # Rough estimate
            temperature=0.3,
            extra_body={"ttl": self._ttl},
        )

        summary = response.choices[0].message.content.strip()
        logger.debug(
            "LM Studio completion received (generate_summary)",
            extra={
                "model": self._llm_model,
                "response_length": len(summary),
            },
        )

        # Store in cache (if file_hash provided)
        if file_hash:
            self._summary_cache.put(self._llm_model, file_hash, summary)

        return summary
    
    async def close(self) -> None:
        """Close the client connection."""
        await self.client.close()