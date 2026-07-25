"""Per-chunk LRU extraction cache keyed by (model_name, prompt_version, chunk_hash)."""
import hashlib
from collections import OrderedDict
from typing import Optional

# Bump this any time ENTITY_EXTRACTION_SYSTEM_PROMPT changes:
PROMPT_VERSION = "v1"


class ExtractionCache:
    _MAX_SIZE = 2000

    def __init__(self):
        self._cache: OrderedDict[tuple, dict] = OrderedDict()

    def _key(self, model: str, chunk_hash: str) -> tuple:
        return (model, PROMPT_VERSION, chunk_hash)

    def get(self, model: str, chunk_hash: str) -> Optional[dict]:
        k = self._key(model, chunk_hash)
        if k not in self._cache:
            return None
        self._cache.move_to_end(k)
        return self._cache[k]

    def set(self, model: str, chunk_hash: str, result: dict) -> None:
        k = self._key(model, chunk_hash)
        self._cache[k] = result
        self._cache.move_to_end(k)
        if len(self._cache) > self._MAX_SIZE:
            self._cache.popitem(last=False)

    def size(self) -> int:
        return len(self._cache)
