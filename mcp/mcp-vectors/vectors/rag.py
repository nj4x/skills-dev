"""RAG pipeline for document indexing and retrieval."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import random as _random
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from .community_detector import DetectorUnavailableError, CommunityCandidate
from .community_orchestrator import CommunityOrchestrator, CommunityBuildResult
from .community_results import (
    CommunitiesReady, CommunitiesRebuilding, CommunitiesError,
    CommunitiesQueryResult, CommunityReportReady, CommunityReportRebuilding,
    CommunityReportError, CommunityReportResult,
)
from .config import Config, resolve_path, sanitize_for_log
from .entity_extractor import EntityExtractor, annotate_chunks
from .errors import (
    NoGitRepository,
    RootResolutionError,
    UnknownResolution,
    UnsupportedBareRepository,
    UnsupportedLinkedWorktree,
)
from .extraction_cache import ExtractionCache
from .git_resolver import GitResolution, GitResolver
from .gitignore import GitignoreMatcher
from .graph_store import GraphStore, GraphSnapshot, entity_id
from .lm_studio import LMStudioClient
from .locks import PathLockConflict, PathLockManager
from .paths import PathPolicy
from .parser import DocumentParser
from .protocols import VectorStoreProtocol, CommunityVectorStoreProtocol
from .reconciliation import ReconciliationEpoch, RegistryReconciler
from .qdrant import QdrantVectorStore, QdrantCommunities, QdrantEntities, CollectionMissingError
from .qdrant_autostart import ensure_qdrant_running
from .safety import ExclusionPolicy

logger = logging.getLogger(__name__)

_SUPPORTED_STATUSES = frozenset({"supported_working_tree", "allowlisted_non_git"})


def _raise_resolution_error(probe: Path, resolution: GitResolution) -> None:
    """Raise the typed RootResolutionError matching the resolution status."""
    status = resolution.status
    if status == "unsupported_linked_worktree":
        raise UnsupportedLinkedWorktree(probe)
    if status == "unsupported_bare_repository":
        raise UnsupportedBareRepository(probe)
    if status == "no_repository":
        raise NoGitRepository(probe)
    raise UnknownResolution(probe, resolution.error_detail)


# ---------------------------------------------------------------------------
# Graph / entity-extraction module-level configuration
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION = os.getenv("ENTITY_EXTRACTION", "true").lower() == "true"
MAX_GLEANINGS = int(os.getenv("MAX_GLEANINGS", "0"))
MAX_CHUNKS_PER_EXTRACT = int(os.getenv("MAX_CHUNKS_PER_EXTRACT", "100"))
GRAPH_DB_DIR = os.path.expanduser(os.getenv("GRAPH_DB_DIR", "~/.mcp-vectors/graphs"))
# B6: hook weight for entity-graph re-ranking (0.0 = disabled)
ENTITY_RERANK_ALPHA = float(os.getenv("ENTITY_RERANK_ALPHA", "0.15"))

_targeting_logger = logging.getLogger("mcp_vectors.search_global.targeting")


def _entity_embedding_text(name: str, description: Optional[str]) -> str:
    """Build embedding text for an entity."""
    if description:
        desc = description[:256].replace("\n", " ").replace("\r", " ").strip()
        return f"{name}: {desc}"
    return f"{name}: (no description)"

# Hard character ceiling before embedding.
# nomic-embed-text has a 2048-token context window; code averages ~3-4 chars/token
# so 1800 chars ≈ 450-600 tokens — well within the limit.  This is an intentional
# last-resort safety net at the embedding call-site; the parser's chunking logic is
# NOT changed.
_EMBED_MAX_CHARS = 1800


def _truncate_for_embed(text: str) -> str:
    """Truncate *text* to ``_EMBED_MAX_CHARS`` characters before embedding.

    Silently truncated inputs from the model are worse than an explicit crop here,
    so we crop and log at DEBUG level to avoid spamming production logs.
    """
    if len(text) > _EMBED_MAX_CHARS:
        logger.debug(
            "Embedding input truncated from %d to %d chars", len(text), _EMBED_MAX_CHARS
        )
        return text[:_EMBED_MAX_CHARS]
    return text


if ENTITY_EXTRACTION:
    os.makedirs(GRAPH_DB_DIR, exist_ok=True)


@dataclass
class IndexResult:
    """Result of indexing operation."""

    success: bool
    file_path: str
    file_name: str
    chunks_indexed: int = 0
    error: Optional[str] = None
    skipped: bool = False
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class SearchResultWithSummary:
    """Search result with optional LLM-generated summary."""

    file_path: str
    file_name: str
    score: float
    chunks: list[dict]
    summary: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGResponse:
    """Complete RAG response with search results."""

    success: bool
    query: str
    results: list[SearchResultWithSummary] = field(default_factory=list)
    total_results: int = 0
    error: Optional[str] = None
    formatted_results: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    filtering_mode: str = "metadata"
    confidence: Optional[dict] = None


@dataclass
class GraphificationStats:
    """Tracks the progress of graph building (entity extraction + community detection)."""

    files_extracted: int = 0
    files_pending_extraction: int = 0     # files queued but not yet done
    chunks_extracted: int = 0
    entities_found: int = 0               # extracted entities only
    entities_embedded: int = 0            # entities + stubs successfully embedded to Qdrant
    entities_total: int = 0               # extracted entities + edge-stub entities
    entities_embed_failed: int = 0        # total failures (entities + stubs)
    entity_embedding_enabled: bool = False  # whether _qdrant_entities is initialized
    batches_sent: int = 0
    extraction_started_at: Optional[float] = None
    last_extraction_completed_at: Optional[float] = None
    community_build_phase: str = "idle"   # "idle"|"detecting"|"reporting"|"embedding"|"ready"|"failed"
    community_build_started_at: Optional[float] = None
    community_last_built_at: Optional[float] = None
    community_build_duration_s: Optional[float] = None
    graph_version: int = 0


@dataclass
class FileScanPlan:
    """Bounded filesystem scan result."""

    root: str
    files: list[Path]
    skipped: list[dict]
    files_scanned: int
    dirs_scanned: int
    partial: bool
    limit_hit: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "files": [str(path) for path in self.files],
            "files_count": len(self.files),
            "skipped": self.skipped,
            "files_scanned": self.files_scanned,
            "dirs_scanned": self.dirs_scanned,
            "partial": self.partial,
            "limit_hit": self.limit_hit,
        }


class RAGPipeline:
    """Orchestrates document indexing and retrieval with RAG."""

    def __init__(
        self,
        config: Config,
        lm_client: Optional[LMStudioClient] = None,
        vector_store: Optional[VectorStoreProtocol] = None,
        parser: Optional[DocumentParser] = None,
        communities: Optional[CommunityVectorStoreProtocol] = None,
    ):
        self.config = config
        self.lm_client = lm_client or LMStudioClient(
            base_url=config.lm_studio_url,
            embedding_model=config.embedding_model,
            llm_model=config.llm_model,
            embedding_batch_size=config.embedding_batch_size,
            ttl=config.lm_studio_ttl,
        )
        self.vector_store = vector_store or QdrantVectorStore(
            url=config.qdrant_url,
            collection_name=config.qdrant_collection,
            max_scroll_points=config.max_scroll_points,
            scroll_page_size=config.scroll_page_size,
        )
        self.safety = ExclusionPolicy(
            excluded_extensions=config.excluded_extensions,
            excluded_directories=config.excluded_directories,
            excluded_filenames=config.excluded_filenames,
            secret_filenames=config.secret_filenames,
            secret_path_patterns=config.secret_path_patterns,
        )
        self.parser = parser or DocumentParser(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            excluded_extensions=config.excluded_extensions,
            excluded_directories=config.excluded_directories,
            excluded_filenames=config.excluded_filenames,
        )
        self.lock_manager = PathLockManager()
        self._initialized = False
        self._extraction_cache = ExtractionCache()
        self._graph_store: Optional[GraphStore] = None
        self._communities: Optional[CommunityVectorStoreProtocol] = communities
        self._qdrant_entities: Optional[QdrantEntities] = None
        self._community_orchestrator: Optional[CommunityOrchestrator] = None
        self._closing: bool = False
        # Startup reconciliation epoch (ADR-0008); None until reconcile_registry runs.
        self._reconciliation: Optional[ReconciliationEpoch] = None
        # Graphification observability
        self._graph_stats: dict[str, GraphificationStats] = {}
        # Per-root reports-incomplete flag (last committed reports build had at
        # least one cluster with no prose). Used by the coverage predicate.
        self._reports_incomplete: dict[str, bool] = {}
        # Background extraction task set — kept so GC doesn't collect running tasks
        self._extraction_tasks: set[asyncio.Task] = set()
        # LLM client: separate from lm_client when LLM_PROVIDER=anthproxy.
        # Stored as _llm_client_obj; the llm_client property falls back to lm_client
        # when this attribute is missing (supports tests that bypass __init__).
        if config.llm_provider == "anthproxy":
            from .anthproxy_client import AnthproxyClient as _AnthproxyClient
            self._llm_client_obj = _AnthproxyClient(
                base_url=config.anthproxy_url,
                model=config.anthproxy_model,
            )
        else:
            self._llm_client_obj = self.lm_client  # same LMStudioClient for both

    @property
    def llm_client(self):
        """LLM-only client (AnthproxyClient or LMStudioClient).

        Falls back to lm_client when _llm_client_obj is not set — this keeps
        tests that build the pipeline via RAGPipeline.__new__() working without
        having to mock llm_client explicitly.
        """
        return getattr(self, "_llm_client_obj", self.lm_client)

    @llm_client.setter
    def llm_client(self, value) -> None:
        self._llm_client_obj = value

    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return
        logger.info("Initializing RAG pipeline...")
        await asyncio.to_thread(ensure_qdrant_running, self.config.qdrant_url)
        await self.lm_client.initialize()
        if self.llm_client is not self.lm_client:
            await self.llm_client.initialize()
        self.vector_store.update_vector_size(self.lm_client.embedding_dimension)
        await self.vector_store.initialize()
        if ENTITY_EXTRACTION:
            self._graph_store = GraphStore(db_dir=GRAPH_DB_DIR)
            if self._communities is None:
                self._communities = QdrantCommunities(url=self.config.qdrant_url)
            await self._communities.initialize(
                embedding_dimension=self.lm_client.embedding_dimension
            )
            self._qdrant_entities = QdrantEntities(url=self.config.qdrant_url)
            await self._qdrant_entities.initialize(
                embedding_dimension=self.lm_client.embedding_dimension
            )
            self._community_orchestrator = CommunityOrchestrator(
                graph_store=self._graph_store,
                communities=self._communities,
                lm_client=self.lm_client,
                llm_client=self.llm_client,
                progress_callback=self._on_community_progress,
                on_result=self._on_community_build_result,
            )
            self._community_orchestrator.schedule_dirty_roots()
        if self.config.reconcile_on_startup:
            await self.reconcile_registry()
        self._initialized = True
        logger.info("RAG pipeline initialized")

    async def reconcile_registry(self) -> dict:
        """Run durable startup reconciliation of legacy roots (ADR-0008).

        Serves only ``active`` roots afterward; remapped/quarantined/retained/
        transient roots are excluded from rootless enumeration. Failures never
        block startup, but are surfaced as ``status="failed"`` and logged at
        ERROR: the reconcile mutates vector data destructively, so a mid-run
        exception may have left partial remap/purge work behind and must not be
        reported as a benign skip.
        """
        try:
            reconciler = RegistryReconciler(
                GRAPH_DB_DIR, self.config, self.vector_store,
                graph_store=self._graph_store,
                qdrant_entities=getattr(self, "_qdrant_entities", None),
            )
            epoch = await reconciler.reconcile()
            self._reconciliation = epoch
            summary = reconciler.summary(epoch)
            logger.warning("startup reconciliation: %s", summary)
            return summary
        except Exception as exc:  # noqa: BLE001 - startup must not hard-fail on reconcile
            logger.error(
                "startup reconciliation FAILED (destructive work may be partially applied): %s",
                exc,
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def _active_root_filter(self) -> Optional[set[str]]:
        """Active-root allowlist for rootless APIs, or None when no filtering applies.

        Returns None (no filtering) unless a completed reconciliation epoch with
        at least one classified legacy root exists, so pre-reconciliation and
        empty-registry deployments enumerate normally.
        """
        epoch = self._reconciliation
        if epoch is None or not epoch.is_complete() or not epoch.classifications:
            return None
        return epoch.active_roots()

    def schedule_detection(self, root_id: str) -> None:
        """Fire-and-forget community *detection* (cluster structure only, no LLM).

        Cheap, eager phase — safe to call on every graph mutation. Delegates to
        the orchestrator's detection single-flight.
        """
        if not ENTITY_EXTRACTION or self._closing or not self._community_orchestrator:
            return
        self._community_orchestrator.schedule_detection(root_id)

    def schedule_reports(
        self, root_id: str, target_clusters: Optional[list[str]] = None
    ) -> None:
        """Fire-and-forget lazy report generation for a root's committed build.

        LLM-driven phase — only triggered by consumers (search_global,
        list_communities, get_community_report) when report text is needed. A
        no-op until a detection build has committed. Delegates to the
        orchestrator's report single-flight (with TTL-recovery).

        target_clusters: when set, only generate reports for those community IDs
        (targeted path); the full build-level slot is not claimed.
        """
        if not ENTITY_EXTRACTION or self._closing or not self._community_orchestrator:
            return
        self._community_orchestrator.schedule_reports(root_id, target_clusters=target_clusters)

    def schedule_community_rebuild(self, root_id: str) -> None:
        """Deprecated alias — schedules *detection* only (reports are now lazy).

        Retained for backward compatibility during the two-phase migration;
        delegates to :meth:`schedule_detection`. New call sites should use
        :meth:`schedule_detection` (eager) and :meth:`schedule_reports` (lazy).
        """
        self.schedule_detection(root_id)

    async def list_communities(
        self,
        root_path: str,
        level: "Optional[int]" = None,
        limit: int = 50,
    ) -> "CommunitiesQueryResult":
        """Return communities for a root, or rebuilding/error status.

        Owns the complete Readiness Protocol for the list_communities use case:
        - Dirty detection: CommunitiesRebuilding (triggers rebuild)
        - Missing committed build: CommunitiesRebuilding (triggers rebuild)
        - Missing root: CommunitiesError (root not indexed)
        - Committed communities exist: CommunitiesReady with data
        - Collection missing: CommunitiesRebuilding (triggers report rebuild)
        """
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store.has_root(root_id):
            return CommunitiesError(
                error={"code": "root_not_indexed", "message": f"Root not indexed: {root_path}"}
            )

        is_dirty = self._graph_store.are_communities_dirty(root_id)
        if is_dirty:
            self.schedule_detection(root_id)
            return CommunitiesRebuilding(reason="Communities are being rebuilt")

        generation = self._graph_store.get_committed_generation(root_id)
        if not generation or not generation[1]:
            self.schedule_detection(root_id)
            return CommunitiesRebuilding(reason="Communities are being built for the first time")

        communities_version, committed_build_id = generation
        self.schedule_reports(root_id)
        try:
            communities = await self._communities.list_by_root(
                root_id=root_id,
                committed_version=communities_version,
                committed_build_id=committed_build_id,
                level=level,
                limit=limit,
            )
        except CollectionMissingError:
            self.schedule_detection(root_id)
            return CommunitiesRebuilding(reason="Community collection missing; rebuilding")

        return CommunitiesReady(communities=communities)

    async def get_community_report(
        self,
        root_path: str,
        community_id: str,
    ) -> "CommunityReportResult":
        """Return a single community report, or rebuilding/error status.

        Owns the complete Readiness Protocol for the get_community_report use case.
        """
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store.has_root(root_id):
            return CommunityReportError(
                error={"code": "root_not_indexed", "message": f"Root not indexed: {root_path}"}
            )

        is_dirty = self._graph_store.are_communities_dirty(root_id)
        if is_dirty:
            self.schedule_detection(root_id)
            return CommunityReportRebuilding(reason="Communities are being rebuilt")

        generation = self._graph_store.get_committed_generation(root_id)
        if not generation or not generation[1]:
            self.schedule_detection(root_id)
            return CommunityReportRebuilding(reason="Communities are being built for the first time")

        communities_version, committed_build_id = generation
        self.schedule_reports(root_id)
        coverage = self._reports_coverage(root_id, committed_build_id)
        if coverage == "rebuilding":
            return CommunityReportRebuilding(reason="Community reports are being generated")

        try:
            report = await self._communities.get_by_id(
                root_id=root_id,
                community_id=community_id,
                committed_version=communities_version,
                committed_build_id=committed_build_id,
            )
        except CollectionMissingError:
            self.schedule_reports(root_id)
            return CommunityReportRebuilding(reason="Community collection missing; rebuilding")

        if report is None:
            if coverage == "failed":
                return CommunityReportError(
                    error={
                        "code": "report_generation_failed",
                        "message": f"Report generation for community {community_id} failed",
                    }
                )
            return CommunityReportError(
                error={"code": "community_not_found", "message": f"Community {community_id} not found"}
            )

        return CommunityReportReady(report=report)

    def _get_reports_incomplete_map(self) -> dict:
        """Return (creating if needed) the per-root reports-incomplete flag map.

        Guarded with ``getattr`` so pipelines built via ``__new__`` in tests work
        without running ``__init__``.
        """
        store = getattr(self, "_reports_incomplete", None)
        if store is None:
            self._reports_incomplete = {}
            store = self._reports_incomplete
        return store

    def _reports_coverage(self, root_id: str, committed_build_id: "Optional[str]") -> str:
        """Classify report coverage for the current committed detection build.

        Returns one of:
            "complete"   – every cluster has a committed report embedding.
            "partial"    – reports committed, but at least one cluster produced none.
            "failed"     – reports permanently parked; nothing committed for this build.
            "rebuilding" – reports for this build are still pending or retrying.
        """
        status = self._graph_store.report_build_status(root_id)
        committed_for_current = (
            committed_build_id is not None
            and status.committed_build_id == committed_build_id
            and not status.dirty
        )
        if committed_for_current:
            incomplete = self._get_reports_incomplete_map().get(root_id, False)
            return "partial" if incomplete else "complete"
        orch = self._community_orchestrator
        if orch is not None and orch.reports_permanently_failed(root_id):
            return "failed"
        return "rebuilding"

    # ------------------------------------------------------------------
    # Graph query seam (ADR-0002)
    # ------------------------------------------------------------------

    def find_entities(self, root_path: str, query: str, limit: int = 10) -> list[dict]:
        """Return entities matching query in root_path; raises if graph features are off or root not indexed."""
        if not ENTITY_EXTRACTION:
            raise RuntimeError("Graph features require ENTITY_EXTRACTION=true")
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store or not self._graph_store.has_root(root_id):
            raise KeyError(f"root_not_indexed:{root_path}")
        return self._graph_store.find_entities(query, root_id, limit=limit)

    async def search_entities_semantic(self, root_path: str, query: str, limit: int = 10) -> list[dict]:
        """Semantic ANN search over entity embeddings with substring-match fallback.

        Returns a list of entity dicts (keys: entity_id, name, type, score where
        available). Falls back to find_entities when embeddings are unavailable.
        Returns [] when ENTITY_EXTRACTION is disabled.
        """
        if not ENTITY_EXTRACTION:
            return []
        root_id = PathPolicy.path_key(root_path)
        _qe = getattr(self, "_qdrant_entities", None)
        if _qe is not None:
            try:
                query_embedding = await self.lm_client.get_embedding(_truncate_for_embed(query))
                hits = await _qe.search(root_id=root_id, query_embedding=query_embedding, limit=limit)
                if hits:
                    return hits
            except Exception as exc:
                logger.debug("search_entities_semantic ANN failed, using substring fallback: %s", exc)
        # Substring fallback
        try:
            return self.find_entities(root_path, query, limit=limit)
        except (KeyError, RuntimeError):
            return []

    def get_neighbors(
        self,
        root_path: str,
        entity_name: str,
        max_depth: int = 2,
        edge_types: list[str] | None = None,
    ) -> dict:
        """Return entity and BFS neighbors for entity_name in root_path."""
        if not ENTITY_EXTRACTION:
            raise RuntimeError("Graph features require ENTITY_EXTRACTION=true")
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store or not self._graph_store.has_root(root_id):
            raise KeyError(f"root_not_indexed:{root_path}")
        matches = self._graph_store.find_entities(entity_name, root_id, limit=5)
        if not matches:
            return {"entity": None, "neighbors": [], "message": f"Entity '{entity_name}' not found"}
        entity = matches[0]
        neighbors = self._graph_store.get_neighbors(entity["id"], max_depth=max_depth, edge_types=edge_types)
        return {"entity": entity, "neighbors": neighbors}

    def get_callers(self, root_path: str, entity_name: str) -> list[dict]:
        """Return callers of entity_name in root_path."""
        if not ENTITY_EXTRACTION:
            raise RuntimeError("Graph features require ENTITY_EXTRACTION=true")
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store or not self._graph_store.has_root(root_id):
            raise KeyError(f"root_not_indexed:{root_path}")
        return self._graph_store.get_callers(entity_name, root_id)

    def _on_community_progress(self, root_id: str, phase: str) -> None:
        """Called by orchestrator at each phase transition to update graph stats."""
        stats = self._get_or_create_stats(root_id)
        if phase == "detecting" and stats.community_build_started_at is None:
            stats.community_build_started_at = time.time()
        stats.community_build_phase = phase

    def _on_community_build_result(self, result: CommunityBuildResult) -> None:
        """Called by orchestrator when a build attempt completes."""
        stats = self._get_or_create_stats(result.root_id)
        if result.success:
            now = time.time()
            stats.community_last_built_at = now
            stats.graph_version = result.graph_version
            stats.community_build_duration_s = result.duration_s
            # Reports-phase commit (possibly partial): record the coverage flag so
            # settled consumers can report incomplete=true without a full re-fetch.
            if result.phase_reached == "reports-ready":
                self._get_reports_incomplete_map()[result.root_id] = result.incomplete
        stats.community_build_phase = result.phase_reached

    def _get_or_create_stats(self, root_id: str) -> GraphificationStats:
        """Return (creating if needed) the GraphificationStats for a root."""
        store = getattr(self, "_graph_stats", None)
        if store is None:
            self._graph_stats = {}
            store = self._graph_stats
        if root_id not in store:
            store[root_id] = GraphificationStats()
        return store[root_id]

    async def index_file(self, file_path: str | Path, root_path: str | Path | None = None) -> IndexResult:
        """Index a single file with replace-safe ordering."""
        if not self._initialized:
            await self.initialize()

        file_path = PathPolicy.resolve(file_path)
        path_key = PathPolicy.path_key(file_path)

        try:
            with self.lock_manager.lock(path_key, "index_file"):
                if not file_path.exists():
                    return IndexResult(False, str(file_path), file_path.name, error=f"File not found: {file_path}")

                decision = self.safety.should_index_path(file_path)
                if decision.action != "index":
                    return IndexResult(
                        False,
                        str(file_path),
                        file_path.name,
                        error=f"Skipped by exclusion policy: {', '.join(decision.reason_codes)}",
                        skipped=True,
                        reason_codes=decision.reason_codes,
                    )

                # Git root enforcement (ADR-0006/0007): resolve canonical root.
                resolution = GitResolver.resolve_root(file_path, self.config)
                if resolution.status not in _SUPPORTED_STATUSES:
                    _raise_resolution_error(file_path, resolution)
                canonical_root = resolution.canonical_root
                if canonical_root is not None:
                    # Canonical root always wins; caller-supplied root_path is advisory only (Fix 2).
                    root_path = canonical_root

                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                if file_size_mb > self.config.max_file_size_mb:
                    return IndexResult(
                        False,
                        str(file_path),
                        file_path.name,
                        error=f"File too large: {file_size_mb:.1f}MB > {self.config.max_file_size_mb}MB",
                    )

                if not self.parser.is_supported(file_path):
                    return IndexResult(False, str(file_path), file_path.name, error=f"Unsupported file type: {file_path.suffix}")

                logger.info(f"Indexing: {sanitize_for_log(file_path.name)}")
                doc = self.parser.parse_file(file_path)
                if not doc.chunks:
                    return IndexResult(False, str(file_path), file_path.name, error="No content to index")

                # Compute graph root_id even though extraction is now background
                root_id_for_graph = None
                if ENTITY_EXTRACTION and self._graph_store:
                    root_id_for_graph = (
                        PathPolicy.path_key(root_path)
                        if root_path
                        else PathPolicy.path_key(file_path.parent)
                    )

                # 1. Embed chunks first → file becomes searchable immediately
                chunk_texts = [_truncate_for_embed(chunk["text"]) for chunk in doc.chunks]
                embeddings = await self.lm_client.get_embeddings_batch(chunk_texts)
                stat = file_path.stat()
                index_run_id = uuid.uuid4().hex

                chunks_stored = await self.vector_store.upsert_chunks(
                    file_path=doc.file_path,
                    file_name=doc.file_name,
                    chunks=doc.chunks,
                    embeddings=embeddings,
                    root_path=str(root_path) if root_path else None,
                    index_run_id=index_run_id,
                    file_metadata={
                        "file_hash": doc.file_hash,
                        "file_size": doc.file_size,
                        "file_type": doc.file_type,
                        "modified_time": doc.modified_time,
                        "mtime_ns": stat.st_mtime_ns,
                        "indexed_time": time.time(),
                        "chunk_count": len(doc.chunks),
                    },
                )

                # Delete only surplus old chunks after new replacement chunks are present.
                await self.vector_store.delete_document_chunks_from(path_key, len(doc.chunks))

                # 2. Fire entity extraction as a background task (non-blocking)
                if ENTITY_EXTRACTION and self._graph_store and root_id_for_graph:
                    _task = asyncio.ensure_future(
                        self._extract_and_merge(file_path, doc, root_id_for_graph, path_key)
                    )
                    _tasks_set = getattr(self, "_extraction_tasks", None)
                    if _tasks_set is not None:
                        _tasks_set.add(_task)
                        _task.add_done_callback(_tasks_set.discard)

                logger.info(f"Indexed {sanitize_for_log(file_path.name)}: {chunks_stored} chunks")
                return IndexResult(True, doc.file_path, doc.file_name, chunks_indexed=chunks_stored)

        except RootResolutionError:
            raise
        except PathLockConflict as e:
            return IndexResult(False, str(file_path), file_path.name, error=str(e))
        except Exception as e:
            logger.error(f"Failed to index {sanitize_for_log(str(file_path))}: {e}")
            return IndexResult(False, str(file_path), file_path.name, error=str(e))

    async def _embed_entities_and_stubs(
        self,
        entities: list,
        stubs: list[dict],
        root_id: str,
        file_name: str,
        stats: GraphificationStats,
    ) -> None:
        """Embed entity vectors and edge-stub vectors into QdrantEntities; accumulate stats.

        No-op when _qdrant_entities is not configured. Gates entity and stub embedding
        independently so zero-entity files with stubs still get their stubs embedded.
        """
        if getattr(self, "_qdrant_entities", None) is None:
            return
        if getattr(self, "_closing", False):
            return

        stats.entity_embedding_enabled = True
        embed_sem = asyncio.Semaphore(self.config.entity_extraction_concurrency)
        seen_sigs: set[str] = set()
        embed_failures = 0
        embeds_succeeded = 0

        async def _embed_entity(entity) -> None:
            nonlocal embed_failures, embeds_succeeded
            try:
                etype = getattr(entity, "type", "") or ""
                eid = entity_id(entity.name, etype, root_id)
                text = _entity_embedding_text(
                    entity.name,
                    getattr(entity, "description", None),
                )
                async with embed_sem:
                    emb = await self.lm_client.get_embedding(_truncate_for_embed(text))
                await self._qdrant_entities.upsert(
                    entity_id=eid,
                    root_id=root_id,
                    name=entity.name,
                    type_=etype,
                    embedding=emb,
                )
                embeds_succeeded += 1
            except Exception as exc:
                embed_failures += 1
                sig = type(exc).__name__
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    # Guard the diagnostic path itself: it must never raise
                    # (and thereby cancel sibling embeds via gather).
                    try:
                        attr_keys = sorted(getattr(entity, "__dict__", {}).keys())
                        logger.warning(
                            "Entity embedding upsert failed for %s | "
                            "entity=%s type=%s attrs=%s",
                            sanitize_for_log(file_name),
                            sanitize_for_log(str(getattr(entity, "name", "<unknown>"))),
                            type(entity).__name__,
                            attr_keys,
                            exc_info=True,
                        )
                    except Exception:
                        pass

        async def _embed_stub(stub_dict) -> None:
            nonlocal embed_failures, embeds_succeeded
            try:
                stub_name = stub_dict.get("name", "<unknown>")
                stub_type = (stub_dict.get("type") or "")
                stub_id = stub_dict["id"]
                text = _entity_embedding_text(stub_name, None)
                async with embed_sem:
                    emb = await self.lm_client.get_embedding(_truncate_for_embed(text))
                await self._qdrant_entities.upsert(
                    entity_id=stub_id,
                    root_id=root_id,
                    name=stub_name,
                    type_=stub_type,
                    embedding=emb,
                )
                embeds_succeeded += 1
            except Exception as exc:
                embed_failures += 1
                sig = type(exc).__name__
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    try:
                        logger.warning(
                            "Edge-stub embedding upsert failed for %s | "
                            "stub=%s type=%s",
                            sanitize_for_log(file_name),
                            sanitize_for_log(stub_name),
                            stub_type,
                            exc_info=exc,
                        )
                    except Exception:
                        pass

        if entities:
            await asyncio.gather(*[_embed_entity(e) for e in entities])
        if stubs:
            await asyncio.gather(*[_embed_stub(s) for s in stubs])

        if embed_failures:
            logger.warning(
                "Entity embedding: %d/%d failures for %s",
                embed_failures,
                len(entities) + len(stubs),
                sanitize_for_log(file_name),
            )
            stats.entities_embed_failed += embed_failures
        stats.entities_embedded += embeds_succeeded
        stats.entities_total += len(entities) + len(stubs)

    async def _extract_and_merge(
        self,
        file_path: Path,
        doc,
        root_id_for_graph: str,
        path_key: str,
    ) -> None:
        """Background coroutine: extract entities and merge into graph store.

        Never propagates exceptions — failures are logged as warnings so a
        broken LLM backend cannot crash the indexing pipeline.
        """
        stats = self._get_or_create_stats(root_id_for_graph)
        stats.files_pending_extraction += 1
        if stats.extraction_started_at is None:
            stats.extraction_started_at = time.time()
        try:
            chunk_semaphore = asyncio.Semaphore(2)
            extractor = EntityExtractor(
                self.llm_client,
                self._extraction_cache,
                max_gleanings=MAX_GLEANINGS,
                **({"batch_size": self.config.anthproxy_llm_batch_size,
                    "max_prompt_chars": self.config.anthproxy_llm_max_prompt_chars}
                   if self.config.llm_provider == "anthproxy" else {}),
            )
            entity_map = await extractor.extract_file(
                str(file_path), doc, root_id_for_graph, chunk_semaphore
            )
            annotate_chunks(doc, entity_map)
            _version, stubs, _deleted_ids = await asyncio.to_thread(
                self._graph_store.replace_file_entity_map,
                entity_map, root_id_for_graph, path_key,
            )
            # Back-fill entity_names into stored Qdrant payloads so that
            # entity-graph reranking works without a full re-index.
            try:
                await self.vector_store.update_chunk_entities(str(file_path), doc.chunks)
            except Exception as backfill_exc:
                logger.warning(
                    f"Failed to back-fill entity_names for "
                    f"{sanitize_for_log(str(file_path))}: {backfill_exc}"
                )
            logger.debug(
                f"Background extracted {len(entity_map.entities)} entities from "
                f"{sanitize_for_log(file_path.name)}"
            )
            await self._embed_entities_and_stubs(
                entity_map.entities, stubs, root_id_for_graph, file_path.name, stats
            )
            self.schedule_detection(root_id_for_graph)
            stats.files_extracted += 1
            stats.chunks_extracted += len(doc.chunks)
            stats.entities_found += len(entity_map.entities)
            stats.last_extraction_completed_at = time.time()
        except Exception as exc:
            logger.warning(
                f"Background entity extraction failed for "
                f"{sanitize_for_log(str(file_path))}: {exc}"
            )
        finally:
            stats.files_pending_extraction -= 1

    async def index_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
        respect_gitignore: Optional[bool] = None,
    ) -> list[IndexResult]:
        """Index all supported files in a directory, with parallelized embedding."""
        if not self._initialized:
            await self.initialize()
        directory = PathPolicy.resolve(directory)
        if not directory.exists():
            return [IndexResult(False, str(directory), directory.name, error=f"Directory not found: {directory}")]
        traverse_decision = self.safety.should_traverse_path(directory)
        if traverse_decision.action != "index":
            return [
                IndexResult(
                    False,
                    str(directory),
                    directory.name,
                    error=f"Skipped by exclusion policy: {', '.join(traverse_decision.reason_codes)}",
                    skipped=True,
                    reason_codes=traverse_decision.reason_codes,
                )
            ]

        # Git root enforcement (ADR-0006/0007): raise early for unsupported roots.
        dir_resolution = GitResolver.resolve_root(directory, self.config)
        if dir_resolution.status not in _SUPPORTED_STATUSES:
            _raise_resolution_error(directory, dir_resolution)
        plan = self.collect_indexable_files(directory, recursive=recursive, respect_gitignore=respect_gitignore)
        logger.info(f"Found {len(plan.files)} files to index in {directory}")

        # Persist under the canonical git root, not the caller-supplied directory
        # (ADR-0006): indexing a subdirectory must not create a subdir-scoped root.
        canonical_root = dir_resolution.canonical_root or directory

        # Use semaphore to parallelize embedding calls (but not Qdrant upserts)
        # Only parallelize if QDRANT_URL is set (async client available)
        if self.config.qdrant_url:
            return await self._index_directory_parallel(plan.files, canonical_root)
        else:
            # In-memory Qdrant: keep serial (sync client blocks event loop)
            return [await self.index_file(file_path, root_path=canonical_root) for file_path in plan.files]

    async def _index_directory_parallel(self, files: list[Path], root_path: Path) -> list[IndexResult]:
        """Index files with bounded parallel embedding (up to 4 concurrent LM Studio calls)."""
        semaphore = asyncio.Semaphore(4)

        async def index_with_semaphore(file_path: Path) -> IndexResult:
            async with semaphore:
                return await self.index_file(file_path, root_path=root_path)

        tasks = [index_with_semaphore(file_path) for file_path in files]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _index_files_parallel(self, files: list[Path], root_path: Path) -> list[IndexResult]:
        """Helper to index a list of files in parallel (for sync_directory)."""
        if not files:
            return []
        semaphore = asyncio.Semaphore(4)

        async def index_with_semaphore(file_path: Path) -> IndexResult:
            async with semaphore:
                return await self.index_file(file_path, root_path=root_path)

        tasks = [index_with_semaphore(file_path) for file_path in files]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def sync_directory(
        self,
        root: str | Path,
        recursive: bool = True,
        respect_gitignore: Optional[bool] = None,
    ) -> dict:
        """Reconcile an indexed directory against the current filesystem.

        Compares on-disk files (by ``st_mtime_ns``) against the persisted index and
        applies the minimal set of changes: index new files, re-index changed files,
        and remove files that no longer exist. Unchanged files are skipped without
        being read.

        Safety: when either scan is incomplete (the bounded on-disk walk or the
        indexed listing was truncated), deletions are skipped so a partial view never
        removes live files.
        """
        if not self._initialized:
            await self.initialize()

        root_path = PathPolicy.resolve(root)
        if not root_path.is_dir():
            return {"success": False, "error": f"Directory not found: {root_path}", "root": str(root_path)}
        traverse_decision = self.safety.should_traverse_path(root_path)
        if traverse_decision.action != "index":
            return {
                "success": False,
                "error": f"Skipped by exclusion policy: {', '.join(traverse_decision.reason_codes)}",
                "root": str(root_path),
                "skipped": True,
                "reason_codes": traverse_decision.reason_codes,
            }

        # On-disk indexable set: path_key -> (Path, mtime_ns)
        plan = self.collect_indexable_files(root_path, recursive=recursive, respect_gitignore=respect_gitignore)
        on_disk: dict[str, tuple[Path, int]] = {}
        for file_path in plan.files:
            try:
                on_disk[PathPolicy.path_key(file_path)] = (file_path, file_path.stat().st_mtime_ns)
            except OSError:
                continue

        # Persisted set: path_key -> record (carries mtime_ns, file_path)
        listing = await self.vector_store.list_indexed_files(
            skip=0,
            limit=self.config.max_files_per_scan,
            base_dirs=[str(root_path)],
        )
        indexed: dict[str, dict] = {}
        for record in listing["files"]:
            key = record.get("path_key")
            if key:
                indexed[key] = record

        scan_incomplete = bool(listing.get("partial") or listing.get("scan_truncated") or plan.partial)

        # Diff on-disk against indexed: mtime fast-path, hash on mtime-change.
        # This two-stage check avoids re-embedding on touch, git checkout, etc.
        to_index_new: list[Path] = []
        to_index_changed: list[Path] = []
        unchanged = 0
        for key, (file_path, mtime_ns) in on_disk.items():
            record = indexed.get(key)
            if record is None:
                to_index_new.append(file_path)
                continue
            stored = record.get("mtime_ns")
            # Fast path: mtime unchanged → definitely unchanged
            if stored is not None and int(stored) == mtime_ns:
                unchanged += 1
                continue
            # mtime changed or missing: check content hash to detect true changes
            # (vs false positives like touch, git checkout, worktree operations)
            stored_hash = record.get("file_hash")
            if stored_hash:
                try:
                    current_hash = self.parser.compute_file_hash(file_path)
                    if current_hash == stored_hash:
                        # Content unchanged; skip re-embed but update stored mtime for next scan
                        unchanged += 1
                        continue
                except Exception as e:
                    logger.warning(f"Hash comparison failed for {sanitize_for_log(file_path.name)}: {e}; falling back to re-index")
            # Hash mismatch or unavailable: content truly changed or can't verify
            to_index_changed.append(file_path)

        to_remove: list[str] = []
        # When recursive=False the on-disk scan covers only the top level of the
        # directory, so any subdirectory files would appear "missing" and get
        # incorrectly removed.  Restrict deletions to recursive scans only.
        if not recursive:
            to_remove = []
        elif not scan_incomplete:
            for key, record in indexed.items():
                if key not in on_disk:
                    to_remove.append(record.get("file_path") or record.get("display_path") or key)

        # Apply: additions/updates first (in parallel if async Qdrant), then deletions.
        new_count = updated_count = removed_count = failed = 0

        # Parallelize indexing if QDRANT_URL is set (async client safe)
        if self.config.qdrant_url and (to_index_new or to_index_changed):
            results_new = await self._index_files_parallel(to_index_new, root_path)
            results_changed = await self._index_files_parallel(to_index_changed, root_path)
            for result in results_new:
                if result.success:
                    new_count += 1
                elif not result.skipped:
                    failed += 1
            for result in results_changed:
                if result.success:
                    updated_count += 1
                elif not result.skipped:
                    failed += 1
        else:
            # In-memory Qdrant or nothing to index: keep serial
            for file_path in to_index_new:
                result = await self.index_file(file_path, root_path=root_path)
                if result.success:
                    new_count += 1
                elif not result.skipped:
                    failed += 1
            for file_path in to_index_changed:
                result = await self.index_file(file_path, root_path=root_path)
                if result.success:
                    updated_count += 1
                elif not result.skipped:
                    failed += 1

        for path in to_remove:
            result = await self.remove_document(path)
            if result.get("success"):
                removed_count += 1
            else:
                failed += 1

        logger.info(
            f"Sync {sanitize_for_log(str(root_path))}: "
            f"+{new_count} new, ~{updated_count} updated, -{removed_count} removed, "
            f"{unchanged} unchanged, {failed} failed"
            + (" (deletions skipped: incomplete scan)" if scan_incomplete else "")
        )
        return {
            "success": True,
            "root": str(root_path),
            "new": new_count,
            "updated": updated_count,
            "removed": removed_count,
            "unchanged": unchanged,
            "failed": failed,
            "scan_incomplete": scan_incomplete,
            "deletions_skipped": scan_incomplete,
        }

    def collect_indexable_files(
        self,
        root: str | Path,
        recursive: bool = True,
        max_files: Optional[int] = None,
        max_dirs: Optional[int] = None,
        max_seconds: Optional[float] = None,
        respect_gitignore: Optional[bool] = None,
    ) -> FileScanPlan:
        """Collect indexable files with bounds and skip reasons."""
        root_path = PathPolicy.resolve(root)
        max_files = max_files or self.config.max_files_per_scan
        max_dirs = max_dirs or self.config.max_dirs_per_scan
        effective_gitignore = (
            respect_gitignore if respect_gitignore is not None else self.config.respect_gitignore
        )
        matcher = GitignoreMatcher.for_path(root_path) if effective_gitignore else None
        started = time.monotonic()
        files: list[Path] = []
        skipped: list[dict] = []
        dirs_scanned = 0
        files_scanned = 0
        partial = False
        limit_hit = None

        def hit_limit(kind: str) -> bool:
            nonlocal partial, limit_hit
            if len(files) >= max_files:
                partial = True
                limit_hit = "max_files"
                return True
            if dirs_scanned >= max_dirs:
                partial = True
                limit_hit = "max_dirs"
                return True
            if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
                partial = True
                limit_hit = "max_seconds"
                return True
            return False

        def visit(directory: Path) -> None:
            nonlocal dirs_scanned, files_scanned
            if hit_limit("pre"):
                return
            dirs_scanned += 1
            if matcher:
                matcher.preload(directory)
            try:
                for item in directory.iterdir():
                    if hit_limit("loop"):
                        return
                    if item.is_symlink() and item.is_dir():
                        skipped.append({"path": str(item), "reason_codes": ["symlink_directory"]})
                        continue
                    if item.is_dir():
                        decision = self.safety.should_traverse_path(item)
                        if decision.action != "index":
                            skipped.append(decision.to_dict())
                            continue
                        if matcher and matcher.is_ignored(item):
                            skipped.append({"path": str(item), "reason_codes": ["gitignore"]})
                            continue
                        if recursive:
                            visit(item)
                        continue
                    if item.is_file():
                        files_scanned += 1
                        if matcher and matcher.is_ignored(item):
                            skipped.append({"path": str(item), "reason_codes": ["gitignore"]})
                            continue
                        decision = self.safety.should_index_path(item)
                        if decision.action == "index":
                            files.append(item)
                        else:
                            skipped.append(decision.to_dict())
            except PermissionError as e:
                skipped.append({"path": str(directory), "reason_codes": ["permission_denied"], "error": str(e)})
            except Exception as e:
                skipped.append({"path": str(directory), "reason_codes": ["scan_error"], "error": str(e)})

        if root_path.is_file():
            files_scanned = 1
            decision = self.safety.should_index_path(root_path)
            if decision.action == "index":
                files.append(root_path)
            else:
                skipped.append(decision.to_dict())
        elif root_path.is_dir():
            decision = self.safety.should_traverse_path(root_path)
            if decision.action == "index":
                visit(root_path)
            else:
                skipped.append(decision.to_dict())
        else:
            skipped.append({"path": str(root_path), "reason_codes": ["path_not_found"]})

        return FileScanPlan(str(root_path), files, skipped, files_scanned, dirs_scanned, partial, limit_hit)

    async def search(
        self,
        query: str,
        limit: int = 10,
        include_summary: bool = False,
        base_dirs: Optional[list[str]] = None,
        exclude_files: Optional[list[str]] = None,
        min_score: Optional[float] = None,
        root_path: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        file_types: Optional[list[str]] = None,
        max_chunks_per_file: Optional[int] = None,
        max_chunk_chars: Optional[int] = None,
        include_chunk_text: bool = True,
        include_metadata: bool = False,
    ) -> RAGResponse:
        """Search for relevant documents and optionally generate summaries."""
        if not self._initialized:
            await self.initialize()
        try:
            query_embedding = await self.lm_client.get_embedding(_truncate_for_embed(query))
            search_results = await self.vector_store.search(
                query_vector=query_embedding,
                limit=limit * 3,
                base_dirs=base_dirs,
                exclude_files=exclude_files,
                min_score=min_score,
                root_path=root_path,
                extensions=extensions,
                file_types=file_types,
            )
            _root_id = PathPolicy.path_key(root_path) if root_path else None
            if not search_results:
                return RAGResponse(
                    True,
                    query,
                    results=[],
                    total_results=0,
                    confidence=self._compute_confidence(_root_id) if _root_id is not None else None,
                )

            search_results = await self._maybe_rerank_by_entity_graph(search_results, query, _root_id)

            files_dict: dict[str, SearchResultWithSummary] = {}
            max_chunks_per_file = max_chunks_per_file or 5
            for result in search_results:
                if result.file_path not in files_dict:
                    files_dict[result.file_path] = SearchResultWithSummary(
                        file_path=result.file_path,
                        file_name=result.file_name,
                        score=result.score,
                        chunks=[],
                        metadata=result.metadata if include_metadata else {},
                    )
                if len(files_dict[result.file_path].chunks) >= max_chunks_per_file:
                    continue
                text = result.chunk_text if include_chunk_text else ""
                if max_chunk_chars is not None and len(text) > max_chunk_chars:
                    text = text[:max_chunk_chars].rstrip() + "…"
                files_dict[result.file_path].chunks.append(
                    {
                        "chunk_id": result.chunk_id,
                        "text": text,
                        "start_char": result.start_char,
                        "end_char": result.end_char,
                        "score": result.score,
                    }
                )

            sorted_files = sorted(files_dict.values(), key=lambda x: x.score, reverse=True)
            if min_score is not None:
                sorted_files = [f for f in sorted_files if f.score >= min_score]
            sorted_files = sorted_files[:limit]

            if include_summary:
                for file_result in sorted_files:
                    context = "\n\n".join(chunk["text"] for chunk in file_result.chunks[:3])
                    file_hash = file_result.metadata.get("file_hash")
                    try:
                        file_result.summary = await self.lm_client.generate_summary(
                            context, max_length=200, file_hash=file_hash
                        )
                    except Exception as e:
                        logger.warning(f"Failed to generate summary: {e}")
                        file_result.summary = None

            formatted = self._format_search_results(sorted_files)
            return RAGResponse(
                True,
                query,
                results=sorted_files,
                total_results=len(sorted_files),
                formatted_results=formatted,
                filtering_mode="metadata_with_component_safe_post_filter" if base_dirs else "metadata",
                confidence=self._compute_confidence(_root_id) if _root_id is not None else None,
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return RAGResponse(False, query, error=str(e))

    def _format_search_results(self, results: list[SearchResultWithSummary]) -> list[dict]:
        formatted = []
        for index, result in enumerate(results, start=1):
            snippets = []
            for chunk in result.chunks:
                text = " ".join((chunk.get("text") or "").split())
                snippets.append(
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "score": round(chunk.get("score", 0), 4),
                        "range": f"chars {chunk.get('start_char', 0)}-{chunk.get('end_char', 0)}",
                        "snippet": text[:500] + ("…" if len(text) > 500 else ""),
                    }
                )
            formatted.append(
                {
                    "rank": index,
                    "file_path": result.file_path,
                    "score": round(result.score, 4),
                    "snippets": snippets,
                }
            )
        return formatted

    def _compute_confidence(self, root_id: Optional[str]) -> dict:
        """Return a confidence dict indicating how complete graph data is for a root."""
        if not ENTITY_EXTRACTION:
            return {"level": "full", "reason": "graph_disabled"}
        graph_stats = getattr(self, "_graph_stats", None)
        if graph_stats is None:
            return {"level": "full", "reason": "no_graph_data"}
        stats = graph_stats.get(root_id or "")
        if stats is None:
            return {"level": "full", "reason": "no_graph_data"}
        pending = stats.files_pending_extraction
        phase = stats.community_build_phase
        if pending > 0:
            return {"level": "partial", "reason": f"entity_extraction_pending:{pending}_files"}
        if phase in ("detecting", "reporting", "embedding"):
            return {"level": "partial", "reason": f"community_build_{phase}"}
        return {"level": "full", "reason": "graph_ready"}

    def get_graph_stats(self, root_id: Optional[str]) -> Optional[dict]:
        """Return serializable graph stats for a root, or None if no data exists."""
        if not root_id:
            return None
        stats = self._graph_stats.get(root_id)
        if stats is None:
            return None
        # Compute extraction rate
        extraction_rate = None
        if stats.files_extracted > 0 and stats.extraction_started_at is not None:
            elapsed_minutes = (time.time() - stats.extraction_started_at) / 60.0
            if elapsed_minutes > 0:
                extraction_rate = round(stats.files_extracted / elapsed_minutes, 2)
        # Format timestamps as ISO 8601 UTC strings
        def _ts(t: Optional[float]) -> Optional[str]:
            if t is None:
                return None
            return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "files_extracted": stats.files_extracted,
            "files_pending_extraction": stats.files_pending_extraction,
            "chunks_extracted": stats.chunks_extracted,
            "entities_found": stats.entities_found,
            "entities_embed_failed": stats.entities_embed_failed,
            "entity_embedding_enabled": getattr(self, "_qdrant_entities", None) is not None,
            "entities_embedded": stats.entities_embedded,
            "entities_total": stats.entities_total,
            "community_build_phase": stats.community_build_phase,
            "community_last_built_at": _ts(stats.community_last_built_at),
            "community_build_duration_s": stats.community_build_duration_s,
            "graph_version": stats.graph_version,
            "extraction_rate_files_per_min": extraction_rate,
        }

    async def search_with_response(self, query: str, limit: int = 5, base_dirs: Optional[list[str]] = None) -> dict:
        """Search and generate a response using RAG."""
        if not self._initialized:
            await self.initialize()
        try:
            search_response = await self.search(query, limit=limit, include_summary=False, base_dirs=base_dirs)
            if not search_response.success:
                return {"success": False, "error": search_response.error}
            if not search_response.results:
                return {
                    "success": True,
                    "query": query,
                    "response": "No relevant documents found for your query.",
                    "sources": [],
                    "confidence": self._compute_confidence(None),
                }
            context_parts = []
            sources = []
            for file_result in search_response.results:
                context_parts.append(f"### {file_result.file_name}\n")
                for chunk in file_result.chunks[:2]:
                    context_parts.append(chunk["text"])
                sources.append({"file_path": file_result.file_path, "file_name": file_result.file_name, "score": file_result.score})
            response = await self.llm_client.generate_response(query=query, context="\n\n".join(context_parts))
            return {
                "success": True,
                "query": query,
                "response": response,
                "sources": sources,
                "confidence": self._compute_confidence(None),
            }
        except Exception as e:
            logger.error(f"RAG response failed: {e}")
            return {"success": False, "error": str(e)}

    async def remove_document(self, file_path: str, dry_run: bool = False) -> dict:
        """Remove a document from the index using canonical path matching."""
        if not self._initialized:
            await self.initialize()
        try:
            resolved_path = str(resolve_path(file_path))
            path_key = PathPolicy.path_key(resolved_path)
            existing_count = await self.vector_store.get_document_chunk_count_by_path_key(path_key)
            if dry_run:
                return {"success": True, "dry_run": True, "file_path": resolved_path, "chunks_matched": existing_count}
            with self.lock_manager.lock(path_key, "remove_document"):
                deleted_count = await self.vector_store.delete_document_by_path_key(path_key)
            # Graph cleanup: find all roots that contain this file and delete/reschedule
            if ENTITY_EXTRACTION and self._graph_store:
                import sqlite3 as _sqlite3
                affected_roots: list[str] = []
                try:
                    if os.path.isdir(GRAPH_DB_DIR):
                        for fname in sorted(os.listdir(GRAPH_DB_DIR)):
                            if not fname.endswith("_graph.sqlite"):
                                continue
                            db_path = os.path.join(GRAPH_DB_DIR, fname)
                            try:
                                conn = _sqlite3.connect(db_path, timeout=2.0)
                                conn.row_factory = _sqlite3.Row
                                rows = conn.execute(
                                    "SELECT root_id FROM meta"
                                ).fetchall()
                                conn.close()
                                for row in rows:
                                    affected_roots.append(row["root_id"])
                            except Exception:
                                pass
                except Exception:
                    pass
                for rid in affected_roots:
                    try:
                        n = await asyncio.to_thread(
                            self._graph_store.delete_file_entities, path_key, rid
                        )
                        if n:
                            self.schedule_detection(rid)
                    except Exception as _ge:
                        logger.debug(
                            f"Graph file entity cleanup failed for root {rid}: {_ge}"
                        )
            return {"success": True, "file_path": resolved_path, "chunks_removed": deleted_count}
        except Exception as e:
            logger.error(f"Failed to remove document: {e}")
            return {"success": False, "error": str(e)}

    async def clear_index(
        self,
        path: str,
        confirm: bool = False,
        expected_files: Optional[int] = None,
        expected_chunks: Optional[int] = None,
        allow_large_scan: bool = False,
    ) -> dict:
        """Preview or clear exact indexed files under a path."""
        target = PathPolicy.resolve(path)
        listing = await self.vector_store.list_indexed_files(
            skip=0,
            limit=100_000,
            base_dirs=[str(target)] if target.is_dir() or not target.suffix else None,
            max_scan_points=None if allow_large_scan else self.config.max_scroll_points,
        )
        matched = []
        for file in listing["files"]:
            file_path = file.get("file_path") or file.get("path_key")
            if not file_path:
                continue
            if PathPolicy.path_key(file_path) == PathPolicy.path_key(target) or PathPolicy.is_within(file_path, target):
                matched.append(file)
        chunks = sum(file.get("chunk_count", 0) for file in matched)
        preview = {
            "success": True,
            "dry_run": not confirm,
            "path": str(target),
            "matched_files": len(matched),
            "matched_chunks": chunks,
            "scan_truncated": listing.get("scan_truncated", False),
            "files": matched[:100],
        }
        if not confirm:
            preview["confirmation_required"] = "Re-run with confirm=true and matching expected_files/expected_chunks."
            return preview
        if listing.get("scan_truncated") and not allow_large_scan:
            return {"success": False, "error": "Refusing clear_index because scan was truncated", **preview}
        if expected_files != len(matched) or expected_chunks != chunks:
            return {"success": False, "error": "Expected counts do not match preview", **preview}
        with self.lock_manager.lock(str(target), "clear_index"):
            removed = 0
            for file in matched:
                removed += await self.vector_store.delete_document_by_path_key(file.get("path_key") or file.get("file_path"))
            # Tier 2: purge entity embeddings and graph when clearing a whole root.
            root_id = PathPolicy.path_key(target)
            if (
                self._graph_store is not None
                and self._graph_store.has_root(root_id)
            ):
                if self._qdrant_entities is not None:
                    try:
                        await self._qdrant_entities.delete_by_root_id(root_id)
                    except Exception as exc:
                        logger.warning(f"clear_index: entity embedding cleanup failed: {exc}")
                try:
                    await asyncio.to_thread(self._graph_store.drop_root, root_id)
                except Exception as exc:
                    logger.warning(f"clear_index: graph store drop_root failed: {exc}")
        return {"success": True, "path": str(target), "files_removed": len(matched), "chunks_removed": removed}

    async def list_indexed_files(self, skip: int = 0, limit: int = 100, base_dirs: Optional[list[str]] = None) -> dict:
        """List all indexed files."""
        if not self._initialized:
            await self.initialize()
        try:
            listing = await self.vector_store.list_indexed_files(skip=skip, limit=limit, base_dirs=base_dirs)
            active = self._active_root_filter()
            if active is not None:
                listing = dict(listing)
                listing["files"] = [f for f in listing["files"] if f.get("root_id") in active]
            return {"success": True, "count": len(listing["files"]), **listing}
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return {"success": False, "error": str(e)}

    async def reset_index(self) -> dict:
        """Reset the vector index, removing all indexed data."""
        if not self._initialized:
            await self.initialize()
        return await self.vector_store.reset_collection()

    async def audit_indexed_secrets(self, include_content_scan: bool = False, max_scan_points: Optional[int] = None) -> dict:
        """Find already-indexed secret-like paths or chunks without returning values."""
        if not self._initialized:
            await self.initialize()
        result = await self.vector_store.audit_payloads_for_secrets(
            self.safety,
            include_content_scan=include_content_scan,
            max_scan_points=max_scan_points,
        )
        result["success"] = True
        result["recommendation"] = "Use purge_indexed_secret_files with exact file paths and confirm_secret_cleanup=true."
        return result

    async def purge_indexed_secret_files(self, file_paths: list[str], confirm_secret_cleanup: bool = False) -> dict:
        """Delete exact secret-like files from Qdrant only."""
        if not confirm_secret_cleanup:
            return {"success": False, "error": "confirm_secret_cleanup=true is required"}
        removed = []
        for file_path in file_paths:
            secret, reasons = self.safety.is_secret_path(file_path)
            if not secret:
                return {"success": False, "error": f"Refusing to purge non-secret-like path without audit evidence: {file_path}"}
            with self.lock_manager.lock(file_path, "purge_secret"):
                chunks = await self.vector_store.delete_document_by_path_key(file_path)
            removed.append({"file_path": PathPolicy.path_key(file_path), "chunks_removed": chunks, "reason_codes": reasons})
        return {"success": True, "files_removed": len(removed), "removed": removed}

    async def preview_reindex(
        self, paths: list[str], recursive: bool = True, respect_gitignore: Optional[bool] = None
    ) -> dict:
        """Dry-run planned indexing for paths."""
        plans = [
            self.collect_indexable_files(
                path, recursive=recursive, respect_gitignore=respect_gitignore
            ).to_dict()
            for path in paths
        ]
        return {
            "success": True,
            "plans": plans,
            "total_files_to_index": sum(plan["files_count"] for plan in plans),
            "partial": any(plan["partial"] for plan in plans),
        }

    async def get_indexing_status(self, root_path: Optional[str] = None) -> dict:
        """Report index and metadata status for a root path."""
        if not self._initialized:
            await self.initialize()
        metadata = await self.vector_store.get_file_metadata_summary(root_path)
        status = "not_found" if metadata["file_count"] == 0 else "indexed"
        if metadata["legacy_file_count"]:
            status = "legacy_metadata" if metadata["legacy_file_count"] == metadata["file_count"] else "partially_indexed"
        secret_audit = await self.audit_indexed_secrets(include_content_scan=False, max_scan_points=min(self.config.max_scroll_points, 10_000))
        result = {
            "success": True,
            "root_path": str(PathPolicy.resolve(root_path)) if root_path else None,
            "status": status,
            "metadata": metadata,
            "secret_audit_warning": {
                "secret_like_file_count": secret_audit["file_count"],
                "scan_truncated": secret_audit["scan_truncated"],
            },
            "next_action": "index_codebase" if metadata["file_count"] == 0 else "search_root",
        }
        if root_path is None:
            active = self._active_root_filter()
            if active is not None:
                result["active_roots"] = sorted(active)
                result["reconciliation"] = {
                    "epoch_id": self._reconciliation.epoch_id,
                    "generation": self._reconciliation.generation,
                    "counts": dict(self._reconciliation.counts),
                }
        return result

    async def get_stats(self) -> dict:
        """Get pipeline statistics."""
        if not self._initialized:
            await self.initialize()
        try:
            store_stats = await self.vector_store.get_stats()
            secret_audit = await self.audit_indexed_secrets(include_content_scan=False, max_scan_points=5_000)
            return {
                "success": True,
                "vector_store": store_stats,
                "embedding_model": self.lm_client.embedding_model,
                "llm_model": self.lm_client.llm_model,
                "embedding_dimension": self.lm_client.embedding_dimension,
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
                "secret_audit_warning": {
                    "secret_like_file_count": secret_audit["file_count"],
                    "scan_truncated": secret_audit["scan_truncated"],
                },
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"success": False, "error": str(e)}

    async def extract_entities_from_file(
        self,
        file_path: "str | Path",
        graph_root_path: "str | Path | None" = None,
    ) -> dict:
        """Extract entities from a file and schedule community rebuild."""
        if not ENTITY_EXTRACTION:
            return {
                "success": False,
                "error": {
                    "code": "feature_disabled",
                    "message": "Entity extraction is disabled",
                },
            }
        if not self._initialized:
            await self.initialize()
        path = PathPolicy.resolve(file_path)
        if not path.exists():
            return {
                "success": False,
                "error": {
                    "code": "invalid_root",
                    "message": f"File not found: {file_path}",
                },
            }
        root_id = (
            PathPolicy.path_key(graph_root_path)
            if graph_root_path
            else PathPolicy.path_key(path.parent)
        )
        path_key = PathPolicy.path_key(path)
        doc = self.parser.parse_file(path)
        if not doc.chunks:
            return {
                "success": False,
                "error": {
                    "code": "invalid_root",
                    "message": "No content to extract",
                },
            }
        extractor = EntityExtractor(
            self.llm_client,
            self._extraction_cache,
            max_gleanings=MAX_GLEANINGS,
            **({"batch_size": self.config.anthproxy_llm_batch_size}
               if self.config.llm_provider == "anthproxy" else {}),
        )
        chunk_semaphore = asyncio.Semaphore(2)
        stats = self._get_or_create_stats(root_id)
        try:
            entity_map = await extractor.extract_file(
                str(path), doc, root_id, chunk_semaphore
            )
            annotate_chunks(doc, entity_map)
            _version, stubs, _deleted_ids = await asyncio.to_thread(
                self._graph_store.replace_file_entity_map, entity_map, root_id, path_key
            )
            await self._embed_entities_and_stubs(
                entity_map.entities, stubs, root_id, path.name, stats
            )
            self.schedule_detection(root_id)
        except Exception as e:
            logger.exception(f"Extract entities failed for {file_path}")
            return {
                "success": False,
                "error": {"code": "invalid_root", "message": str(e)},
            }
        return {
            "success": True,
            "file_path": str(path),
            "entities_extracted": len(entity_map.entities),
            "edges_extracted": len(entity_map.edges),
        }

    async def _maybe_rerank_by_entity_graph(
        self,
        results: list,
        query: str,
        root_id: Optional[str],
    ) -> list:
        """Entity-graph reranking hook: blends entity-overlap scores with vector scores.

        Scoring formula: blended = (1 - alpha) * vector_score + alpha * entity_score
        where entity_score = |chunk.entity_names ∩ query_entities| / max(|query_entities|, 1)

        Early exits (returns results unchanged, no I/O):
        - ENTITY_RERANK_ALPHA == 0 (default): pure no-op, no SQLite round-trip.
        - root_id is None or query is blank: no graph scope.
        - ENTITY_EXTRACTION disabled or _graph_store is None: feature off.
        - No graph entities matched query: no reranking signal.

        Alpha behaviour:
        - ENTITY_RERANK_ALPHA=0 (default): results in original vector-score order.
        - ENTITY_RERANK_ALPHA=1: sorted by entity overlap only; vector score is zeroed.
        - ENTITY_RERANK_ALPHA=0.5: equal blend.
        Alpha is read at import time (module constant); changing the env var without
        process restart has no effect.
        """
        if ENTITY_RERANK_ALPHA == 0.0:
            return results
        if not results:
            return results
        if not ENTITY_EXTRACTION or self._graph_store is None:
            return results
        if not root_id or not query.strip():
            return results

        try:
            entity_rows: list[dict] = await asyncio.to_thread(
                self._graph_store.find_entities, query, root_id, 10
            )
        except Exception as e:
            logger.warning(f"entity-graph rerank lookup failed: {e} — returning original ranking")
            return results

        query_entity_names: frozenset[str] = frozenset(
            r["name"].lower() for r in entity_rows
        )
        if not query_entity_names:
            return results

        alpha = ENTITY_RERANK_ALPHA
        scored: list[tuple[float, object]] = []
        for r in results:
            chunk_names = frozenset(
                n.lower() for n in r.metadata.get("entity_names", [])
            )
            overlap = len(chunk_names & query_entity_names)
            entity_score = overlap / max(len(query_entity_names), 1)
            blended = (1.0 - alpha) * r.score + alpha * entity_score
            scored.append((blended, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [replace(r, score=blended) for blended, r in scored]

    async def _try_entity_targeting(
        self,
        query: str,
        query_vector: list[float],
        root_id: str,
        communities_version: int,
        committed_build_id: str,
        limit: int,
    ) -> Optional[dict]:
        """Attempt entity-targeted community summarization.

        Returns a completed search_global response dict on success, or None if
        targeting is not applicable (zero-match, cap exceeded, entities not
        indexed, or any error).  Callers fall through to full summarization when
        None is returned.
        """
        if getattr(self, "_qdrant_entities", None) is None:
            return None
        try:
            entity_hits = await self._qdrant_entities.search(
                root_id=root_id,
                query_embedding=query_vector,
                limit=self.config.entity_search_limit,
            )
        except Exception as exc:
            _targeting_logger.debug(f"entity search failed, skipping targeting: {exc}")
            return None

        if not entity_hits:
            _targeting_logger.debug(
                "targeting: zero entity hits for root_id=%r, falling through", root_id
            )
            return None

        entity_ids = [h["entity_id"] for h in entity_hits]
        targeted_community_ids: set[str] = await asyncio.to_thread(
            self._graph_store.get_community_ids_for_entities, root_id, entity_ids
        )

        if not targeted_community_ids:
            _targeting_logger.debug(
                "targeting: no communities mapped for %d entities, falling through", len(entity_ids)
            )
            return None

        all_community_ids: list[str] = await asyncio.to_thread(
            self._graph_store.get_committed_community_ids, root_id, committed_build_id
        )
        total = len(all_community_ids)
        cap = int(total * self.config.community_cap_ratio)
        if len(targeted_community_ids) > cap:
            _targeting_logger.debug(
                "targeting: %d communities exceeds cap %d/%d (ratio=%.2f), falling through",
                len(targeted_community_ids), cap, total, self.config.community_cap_ratio,
            )
            return None

        targeted_list = list(targeted_community_ids)
        query_for_log = (
            query if self.config.targeting_log_full_query
            else query[: self.config.query_log_max_chars]
        )
        _targeting_logger.info(
            "targeting: root_id=%r entities=%d communities=%d/%d query=%r",
            root_id, len(entity_ids), len(targeted_list), total, query_for_log,
        )

        self.schedule_reports(root_id, target_clusters=targeted_list)

        if self._communities is None:
            return None
        all_fresh = await self._communities.all_points_exist(
            root_id=root_id,
            graph_version=communities_version,
            build_id=committed_build_id,
            community_ids=targeted_list,
        )

        if not all_fresh:
            _targeting_logger.debug(
                "targeting: not all %d community reports are fresh yet, returning rebuilding",
                len(targeted_list),
            )
            _targeting_logger.debug(
                "targeting: entity-targeting fallback is scoped to root_id=%r", root_id
            )
            fallback = await self.search_with_response(query, limit, base_dirs=[root_id])
            return {
                "success": True,
                "mode": "rebuilding",
                "incomplete": True,
                "root_id": root_id,
                "graph_version": communities_version,
                "warning": "Targeted community reports are being generated; returning vector search fallback",
                "fallback_results": fallback,
                "confidence": self._compute_confidence(root_id),
            }

        results = await self._communities.search_filtered(
            root_id=root_id,
            query_vector=query_vector,
            committed_version=communities_version,
            committed_build_id=committed_build_id,
            community_ids=targeted_list,
            limit=limit,
        )

        if not results:
            return None

        synthesis_context = "\n\n".join(
            f"[{r.get('title', '')}] {r.get('summary', '')}" for r in results[:3]
        )
        try:
            synthesis = await self.llm_client.generate_response(
                f"Based on these community reports, answer: {query}\n\n{synthesis_context}"
            )
        except Exception:
            synthesis = ""

        community_results = sorted(
            results, key=lambda r: (-r.get("score", 0), r.get("community_id", ""))
        )
        return {
            "success": True,
            "mode": "ready",
            "incomplete": True,
            "root_id": root_id,
            "graph_version": communities_version,
            "community_results": community_results,
            "synthesis": synthesis,
            "confidence": self._compute_confidence(root_id),
        }

    async def search_global(
        self,
        query: str,
        root_path: "str | Path",
        limit: int = 5,
    ) -> dict:
        """Global community-aware search using GraphRAG."""
        if not ENTITY_EXTRACTION:
            return {
                "success": False,
                "error": {
                    "code": "feature_disabled",
                    "message": "Graph features require ENTITY_EXTRACTION=true",
                },
            }
        if not self._initialized:
            await self.initialize()
        root_id = PathPolicy.path_key(root_path)
        if not self._graph_store.has_root(root_id):
            return {
                "success": False,
                "error": {
                    "code": "root_not_indexed",
                    "message": f"Root not indexed: {root_path}",
                },
            }
        generation = self._graph_store.get_committed_generation(root_id)
        communities_version, committed_build_id = generation if generation else (None, None)
        graph_version = self._graph_store.get_graph_version(root_id)
        is_dirty = self._graph_store.are_communities_dirty(root_id)

        def _rebuilding(warning: str):
            return self._search_global_fallback(
                query, limit, root_path, root_id, graph_version, warning
            )

        # --- Detection phase: cluster structure must exist before reporting. ---
        if is_dirty or not committed_build_id:
            self.schedule_detection(root_id)
            return await _rebuilding(
                "Communities are being rebuilt; returning vector search fallback"
            )

        # --- Entity-targeted path (ADR-0009–0021): try to serve only the
        #     communities relevant to the query, avoiding an O(N) full-build stall.
        #     Falls through to full summarization on zero-match or cap exceeded. ---
        query_vector = await self.lm_client.get_embedding(_truncate_for_embed(query))
        if getattr(self, "_qdrant_entities", None) is not None and communities_version is not None:
            targeting_result = await self._try_entity_targeting(
                query=query,
                query_vector=query_vector,
                root_id=root_id,
                communities_version=communities_version,
                committed_build_id=committed_build_id,
                limit=limit,
            )
            if targeting_result is not None:
                return targeting_result

        # --- Reports phase (lazy): drive generation for the committed build and
        #     classify coverage of the current-build cluster reports. ---
        self.schedule_reports(root_id)
        coverage = self._reports_coverage(root_id, committed_build_id)
        if coverage == "rebuilding":
            return await _rebuilding(
                "Community reports are being generated; returning vector search fallback"
            )

        # Reports settled (complete | partial | failed). Fetch committed embeddings.
        try:
            results = await self._communities.search(
                root_id=root_id,
                query_vector=query_vector,
                committed_version=communities_version,
                committed_build_id=committed_build_id,
                limit=limit,
            )
        except CollectionMissingError:
            self.schedule_reports(root_id)
            return await _rebuilding("Community collection missing; rebuilding")

        # All clusters failed (nothing committed) → vector fallback, flagged incomplete.
        if coverage == "failed" or not results:
            fallback = await self.search_with_response(
                query, limit, base_dirs=[str(root_path)]
            )
            return {
                "success": True,
                "mode": "ready",
                "incomplete": True,
                "root_id": root_id,
                "graph_version": communities_version,
                "warning": "Community reports unavailable; returning vector search fallback",
                "fallback_results": fallback,
                "confidence": self._compute_confidence(root_id),
            }

        # Some (partial) or all (complete) clusters have committed report embeddings.
        synthesis_context = "\n\n".join(
            f"[{r.get('title', '')}] {r.get('summary', '')}" for r in results[:3]
        )
        try:
            synthesis = await self.llm_client.generate_response(
                f"Based on these community reports, answer: {query}\n\n{synthesis_context}"
            )
        except Exception:
            synthesis = ""
        community_results = sorted(
            results, key=lambda r: (-r.get("score", 0), r.get("community_id", ""))
        )
        return {
            "success": True,
            "mode": "ready",
            "incomplete": coverage != "complete",
            "root_id": root_id,
            "graph_version": communities_version,
            "community_results": community_results,
            "synthesis": synthesis,
            "confidence": self._compute_confidence(root_id),
        }

    async def _search_global_fallback(
        self,
        query: str,
        limit: int,
        root_path: "str | Path",
        root_id: str,
        graph_version: "Optional[int]",
        warning: str,
    ) -> dict:
        """Build the ``mode="rebuilding"`` vector-search fallback envelope."""
        fallback = await self.search_with_response(
            query, limit, base_dirs=[str(root_path)]
        )
        return {
            "success": True,
            "mode": "rebuilding",
            "root_id": root_id,
            "graph_version": graph_version or 0,
            "warning": warning,
            "fallback_results": fallback,
            "confidence": self._compute_confidence(root_id),
        }

    async def close(self) -> None:
        """Close all connections, draining community and extraction tasks first."""
        self._closing = True
        if self._community_orchestrator:
            self._community_orchestrator.close()
        # drain background extraction tasks
        extraction_tasks = getattr(self, "_extraction_tasks", None)
        if extraction_tasks:
            tasks = list(extraction_tasks)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        # drain community tasks (all scheduling paths: detection, reports, legacy)
        orchestrator = self._community_orchestrator
        if orchestrator:
            await orchestrator.drain()
        _qe = getattr(self, "_qdrant_entities", None)
        if _qe is not None:
            await _qe.close()
        if self._communities:
            await self._communities.close()
        if self.lm_client:
            await self.lm_client.close()
        if self.vector_store:
            await self.vector_store.close()
        self._initialized = False
