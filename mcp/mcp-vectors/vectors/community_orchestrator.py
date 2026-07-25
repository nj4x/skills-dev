"""CommunityOrchestrator: owns the full community-rebuild lifecycle."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from .community_detector import detect_communities
from .community_reporter import generate_all_reports
from .config import get_config
from .graph_store import GraphStore, GraphSnapshot
from .protocols import CommunityVectorStoreProtocol
from .qdrant import CollectionMissingError

logger = logging.getLogger(__name__)

# Type aliases for injected client protocols.
LMClient = object  # has: async get_embeddings_batch(texts: list[str]) -> list[list[float]]
LLMClient = object  # has: async generate_response(prompt: str, ...) -> str

_EMBED_MAX_CHARS = 1800


def _truncate_for_embed(text: str) -> str:
    if len(text) > _EMBED_MAX_CHARS:
        logger.debug("Embedding input truncated from %d to %d chars", len(text), _EMBED_MAX_CHARS)
        return text[:_EMBED_MAX_CHARS]
    return text


@dataclass
class CommunityBuildResult:
    """Outcome of one community rebuild attempt."""

    root_id: str
    graph_version: int
    success: bool
    phase_reached: str      # "detecting" | "reporting" | "embedding" | "ready" | "failed"
    duration_s: Optional[float]
    error: Optional[str]
    # Coverage predicate for the reports phase: True when at least one cluster's
    # report could not be produced (e.g. LLM returned empty prose). Detection
    # results always leave this False.
    incomplete: bool = False


@dataclass
class _ReportsRetryState:
    """In-memory retry/TTL bookkeeping for one root's report-generation slot.

    ``next_ttl_seconds`` is the TTL that will be applied the *next* time the slot
    is parked ``failed-permanently``; it doubles on each consecutive parking and
    is capped by ``reports_retry_max_ttl_seconds``.
    """

    attempts: int = 0
    permanent: bool = False
    retry_at: Optional[float] = None
    next_ttl_seconds: Optional[int] = None


class CommunityOrchestrator:
    """Schedules, coalesces, and drives community rebuilds for all known roots.

    Public interface:
        schedule(root_id)         – fire-and-forget, idempotent, coalescing
        schedule_dirty_roots()    – startup sweep over graph_store.list_dirty_roots()
        close()                   – signal shutdown; no new tasks will be spawned

    Constructor parameters:
        graph_store       – the pipeline's initialized GraphStore instance
        communities       – the pipeline's initialized community vector store
        lm_client         – embedding client (get_embeddings_batch)
        llm_client        – report-generation LLM client
        progress_callback – called at each phase transition: (root_id, phase) -> None;
                            exceptions are caught and logged
        on_result         – optional; called with CommunityBuildResult when an
                            attempt finishes
    """

    def __init__(
        self,
        graph_store: GraphStore,
        communities: "CommunityVectorStoreProtocol",
        lm_client: "LMClient",
        llm_client: "LLMClient",
        progress_callback: Callable[[str, str], None],
        on_result: Optional[Callable[[CommunityBuildResult], None]] = None,
        *,
        reports_retry_base_ttl_seconds: Optional[int] = None,
        reports_retry_max_ttl_seconds: Optional[int] = None,
        reports_max_attempts: Optional[int] = None,
        reports_claim_lease_seconds: Optional[int] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._graph_store = graph_store
        self._communities = communities
        self._lm_client = lm_client
        self._llm_client = llm_client
        self._progress_callback = progress_callback
        self._on_result = on_result
        # Legacy combined detect+report path (deprecated; see schedule()).
        self._tasks: dict[str, asyncio.Task] = {}
        self._reschedule_flags: dict[str, bool] = {}
        # Detection phase (cheap, no LLM) — its own single-flight lifecycle.
        self._detection_tasks: dict[str, asyncio.Task] = {}
        self._detection_reschedule_flags: dict[str, bool] = {}
        # Reports phase (LLM-driven, lazy) — single-flight + coalescing per root.
        self._reports_tasks: dict[str, asyncio.Task] = {}
        self._reports_reschedule_flags: dict[str, bool] = {}
        self._reports_failures: dict[str, _ReportsRetryState] = {}
        self._closing = False

        # TTL-recovery configuration (defaults sourced from Config/env when unset).
        cfg = None
        if (
            reports_retry_base_ttl_seconds is None
            or reports_retry_max_ttl_seconds is None
            or reports_max_attempts is None
            or reports_claim_lease_seconds is None
        ):
            cfg = get_config()
        self._reports_base_ttl = (
            reports_retry_base_ttl_seconds
            if reports_retry_base_ttl_seconds is not None
            else cfg.reports_retry_base_ttl_seconds
        )
        self._reports_max_ttl = (
            reports_retry_max_ttl_seconds
            if reports_retry_max_ttl_seconds is not None
            else cfg.reports_retry_max_ttl_seconds
        )
        self._reports_max_attempts = (
            reports_max_attempts
            if reports_max_attempts is not None
            else cfg.reports_max_attempts
        )
        self._reports_claim_lease_seconds = (
            reports_claim_lease_seconds
            if reports_claim_lease_seconds is not None
            else cfg.reports_claim_lease_seconds
        )
        self._clock = clock

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, root_id: str) -> None:
        """Fire-and-forget; idempotent for the running task; coalescing.

        Legacy combined detect+report path retained for backward compatibility.
        New callers should use :meth:`schedule_detection` (cheap, eager) and
        :meth:`schedule_reports` (lazy, LLM-driven) instead.
        """
        if self._closing:
            return
        if root_id in self._tasks:
            self._reschedule_flags[root_id] = True
            return
        graph_version = self._graph_store.get_graph_version(root_id)
        build_id = str(uuid.uuid4())
        if not self._graph_store.claim_community_build(
            root_id, graph_version, build_id, lease_seconds=3600
        ):
            return
        task = asyncio.ensure_future(
            self._run_one_attempt(root_id, graph_version, build_id)
        )
        self._tasks[root_id] = task
        task.add_done_callback(lambda t: self._task_done(root_id, t))

    def schedule_community_rebuild(self, root_id: str) -> None:
        """Deprecated alias — runs detection only (reports are now lazy).

        Kept so existing call sites keep working during the two-phase migration.
        Delegates to :meth:`schedule_detection`.
        """
        self.schedule_detection(root_id)

    def schedule_detection(self, root_id: str) -> None:
        """Fire-and-forget detection phase: cluster structure only, no LLM calls.

        Idempotent for the running detection task; coalescing. On a successful
        publish of a new build it sets the advisory ``reports_dirty`` hint so
        consumers can fast-path to ``mode="rebuilding"``.
        """
        if self._closing:
            return
        if root_id in self._detection_tasks:
            self._detection_reschedule_flags[root_id] = True
            return
        graph_version = self._graph_store.get_graph_version(root_id)
        build_id = str(uuid.uuid4())
        if not self._graph_store.claim_community_build(
            root_id, graph_version, build_id, lease_seconds=3600
        ):
            return
        task = asyncio.ensure_future(
            self._run_detection_attempt(root_id, graph_version, build_id)
        )
        self._detection_tasks[root_id] = task
        task.add_done_callback(lambda t: self._detection_task_done(root_id, t))

    def schedule_reports(
        self, root_id: str, target_clusters: "Optional[set[str]]" = None
    ) -> None:
        """Fire-and-forget report-generation phase with single-flight coalescing.

        Concurrent calls for the same root coalesce onto one in-flight attempt;
        a call arriving while a task runs sets a reschedule flag instead of
        spawning a second task. A root parked ``failed-permanently`` is skipped
        until its TTL expires, at which point the slot resets to pending and a
        fresh attempt runs.

        When *target_clusters* is non-None, only those clusters are generated (a
        targeted partial rebuild). When None (default), all clusters are generated
        (full rebuild, unchanged behavior).
        """
        if self._closing:
            return
        # TTL gate: a parked root stays settled until its retry_at passes.
        state = self._reports_failures.get(root_id)
        if state is not None and state.permanent:
            if state.retry_at is not None and self._clock() < state.retry_at:
                return
            # TTL expired — reset to pending and fall through to a fresh attempt.
            state.permanent = False
            state.attempts = 0
            state.retry_at = None
        # Single-flight: coalesce concurrent calls onto the in-flight task.
        if root_id in self._reports_tasks:
            self._reports_reschedule_flags[root_id] = True
            return
        task = asyncio.ensure_future(
            self._run_reports_attempt(root_id, target_clusters=target_clusters)
        )
        self._reports_tasks[root_id] = task
        task.add_done_callback(lambda t: self._reports_task_done(root_id, t))

    def schedule_dirty_roots(self) -> None:
        """Startup sweep — schedules detection for every root flagged dirty.

        Reports stay lazy: the startup sweep only re-establishes cluster
        structure; report text is (re)generated on the next consumer read.
        """
        for root_id in self._graph_store.list_dirty_roots():
            self.schedule_detection(root_id)

    def close(self) -> None:
        """Prevent new tasks from being scheduled."""
        self._closing = True

    async def drain(self) -> None:
        """Cancel and await all in-flight tasks across all scheduling paths.

        Call this before closing shared resources so that no task can touch
        a client after it has been closed.  Safe to call while ``_closing``
        is already True (set by :meth:`close`).
        """
        all_tasks = [
            *self._tasks.values(),
            *self._detection_tasks.values(),
            *self._reports_tasks.values(),
        ]
        if not all_tasks:
            return
        for t in all_tasks:
            t.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)

    def reports_permanently_failed(self, root_id: str) -> bool:
        """Return True if reports for *root_id* are parked as failed-permanently."""
        state = self._reports_failures.get(root_id)
        return state is not None and state.permanent

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_progress(self, root_id: str, phase: str) -> None:
        try:
            self._progress_callback(root_id, phase)
        except Exception as exc:
            logger.warning("progress_callback raised for %s phase=%s: %s", root_id, phase, exc)

    def _task_done(self, root_id: str, task: asyncio.Task) -> None:
        self._tasks.pop(root_id, None)
        try:
            exc = task.exception()
            if exc is not None:
                logger.error("Community rebuild task for %s raised: %s", root_id, exc)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass
        should_reschedule = self._reschedule_flags.pop(root_id, False)
        if not self._closing and not task.cancelled() and should_reschedule:
            self.schedule(root_id)

    def _detection_task_done(self, root_id: str, task: asyncio.Task) -> None:
        self._detection_tasks.pop(root_id, None)
        try:
            exc = task.exception()
            if exc is not None:
                logger.error("Community detection task for %s raised: %s", root_id, exc)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass
        should_reschedule = self._detection_reschedule_flags.pop(root_id, False)
        if not self._closing and not task.cancelled() and should_reschedule:
            self.schedule_detection(root_id)

    def _reports_task_done(self, root_id: str, task: asyncio.Task) -> None:
        self._reports_tasks.pop(root_id, None)
        try:
            exc = task.exception()
            if exc is not None:
                logger.error("Community reports task for %s raised: %s", root_id, exc)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass
        should_reschedule = self._reports_reschedule_flags.pop(root_id, False)
        if not self._closing and not task.cancelled() and should_reschedule:
            self.schedule_reports(root_id)

    def _record_reports_failure(self, root_id: str) -> None:
        """Advance the retry counter; park the slot failed-permanently at the cap.

        The first parking uses the base TTL; each consecutive parking doubles the
        TTL (capped at ``reports_retry_max_ttl_seconds``). TTL reset back to
        pending happens lazily in :meth:`schedule_reports`.
        """
        state = self._reports_failures.get(root_id)
        if state is None:
            state = _ReportsRetryState(next_ttl_seconds=self._reports_base_ttl)
            self._reports_failures[root_id] = state
        state.attempts += 1
        if state.attempts >= self._reports_max_attempts:
            ttl = state.next_ttl_seconds or self._reports_base_ttl
            state.permanent = True
            state.retry_at = self._clock() + ttl
            state.next_ttl_seconds = min(ttl * 2, self._reports_max_ttl)
            logger.warning(
                "Reports for %s parked failed-permanently after %d attempts; "
                "retry in %ss",
                root_id,
                state.attempts,
                ttl,
            )

    async def _run_detection_attempt(
        self, root_id: str, claimed_version: int, build_id: str
    ) -> None:
        """Drive one detection-only attempt: publish cluster structure, no LLM.

        On a successful publish of a non-empty (or empty) build it marks the
        detection build complete and atomically flags ``reports_dirty=1`` so the
        lazy reports phase (and consumers) know report text is stale.
        """
        started_at = time.time()
        self._emit_progress(root_id, "detecting")

        async def finish_failure(error: str) -> None:
            accepted, warning = await asyncio.shield(
                asyncio.to_thread(
                    self._graph_store.fail_community_build,
                    root_id,
                    claimed_version,
                    build_id,
                )
            )
            if accepted and warning:
                logger.warning(
                    "Community detection for %s v%s exhausted attempts; parking",
                    root_id,
                    claimed_version,
                )
            self._emit_progress(root_id, "failed")
            self._emit_result(root_id, claimed_version, False, "failed", started_at, error)

        try:
            snapshot: GraphSnapshot = self._graph_store.read_graph_snapshot(root_id)
            if snapshot.graph_version != claimed_version:
                await finish_failure("graph_version_mismatch")
                return

            if not snapshot.entities:
                clusters: list = []
            else:
                communities_tuple, _algo = detect_communities(snapshot)
                clusters = [
                    {
                        "community_id": c.community_id,
                        "level": c.level,
                        "parent_id": c.parent_id,
                        "entity_ids": list(c.entity_ids),
                        "file_ids": list(c.file_ids),
                    }
                    for c in communities_tuple
                ]

            published = self._graph_store.replace_communities_if_current(
                root_id, claimed_version, build_id, clusters
            )
            if not published:
                await finish_failure("cas_lost")
                return

            self._graph_store.complete_community_build(root_id, claimed_version, build_id)
            # A fresh detection build invalidates any prior report text. The dirty
            # signal is now implicit via build_id mismatch in the reports slot
            # (commit_report_build clears reports_dirty; a new build resets it).

            # Write entity→community join table rows if entities exist.
            if clusters and self._graph_store.entities_exist(root_id):
                rows = [
                    (eid, c["community_id"])
                    for c in clusters
                    for eid in (c.get("entity_ids") or [])
                ]
                if rows:
                    self._graph_store.upsert_entity_community_rows(root_id, build_id, rows)
                    self._graph_store.delete_entity_community_stale(root_id, build_id)
                    logger.debug(
                        "Wrote %d entity_community rows for %s build=%s",
                        len(rows), root_id, build_id,
                    )

            logger.info("Community structure published for %s v%s", root_id, claimed_version)
            self._emit_progress(root_id, "ready")
            self._emit_result(root_id, claimed_version, True, "ready", started_at, None)

        except CollectionMissingError as exc:
            logger.warning("Community detection collection error for %s: %s", root_id, exc)
            await asyncio.shield(finish_failure(str(exc)))
        except Exception as exc:
            logger.warning("Community detection failed for %s: %s", root_id, exc)
            await asyncio.shield(finish_failure(str(exc)))

    async def _run_reports_attempt(
        self,
        root_id: str,
        target_clusters: "Optional[set[str]]" = None,
    ) -> None:
        """Drive one report-generation attempt against the committed detection build.

        Generates report prose, embeds summaries, publishes report embeddings, and
        marks reports complete via the durable reports_* slot. Hard failures feed
        the TTL-recovery machinery; a partial result (some clusters produced no
        prose) still commits but is flagged ``incomplete``.

        When *target_clusters* is a non-empty set, only those clusters are
        generated and committed; ``reports_committed_build_id`` is NOT updated
        (reserved for full-build sweeps only).  When None (default), all clusters
        are generated and the full-build flag is set.
        """
        started_at = time.time()
        is_targeted = target_clusters is not None and len(target_clusters) > 0
        communities_version, committed_build_id = self._graph_store.get_committed_generation(
            root_id
        )
        if committed_build_id is None:
            # No committed detection build to report on yet.
            return
        build_id = committed_build_id

        claim_token: "Optional[str]" = None
        if not is_targeted:
            # CAS-claim the durable reports slot (single-flight is enforced in-process
            # by _reports_tasks; the lease slot guards against cross-process duplication).
            claim_token = self._graph_store.claim_report_build(
                root_id, build_id, self._reports_claim_lease_seconds
            )
            if claim_token is None:
                # Already committed or a live same-generation claim exists — bail out.
                return

        def _release_claim() -> None:
            if not is_targeted and claim_token is not None:
                self._graph_store.clear_report_claim(root_id, claim_token)

        try:
            snapshot: GraphSnapshot = self._graph_store.read_graph_snapshot(root_id)
            if snapshot.graph_version != communities_version:
                # Detection advanced under us; abandon cleanly so the next consumer
                # re-triggers generation against the new cluster set.
                _release_claim()
                return

            communities_tuple, _algo = detect_communities(snapshot)
            all_clusters = list(communities_tuple)

            # Filter to targeted subset when requested.
            if is_targeted:
                clusters = [c for c in all_clusters if c.community_id in target_clusters]
            else:
                clusters = all_clusters

            self._emit_progress(root_id, "reporting")
            reports = await generate_all_reports(clusters, snapshot, self._llm_client)

            # Coverage predicate: a cluster whose report has neither title nor
            # summary failed prose generation.
            expected = len(clusters)
            covered = sum(1 for r in reports if (r.get("summary") or r.get("title")))
            incomplete = covered < expected

            for report in reports:
                report["report_build_id"] = build_id

            self._emit_progress(root_id, "embedding")
            texts = [
                _truncate_for_embed(report.get("summary", report.get("title", "")))
                for report in reports
            ]
            embeddings = await self._lm_client.get_embeddings_batch(texts) if texts else []
            reports_with_vectors = [
                dict(report, vector=embedding)
                for report, embedding in zip(reports, embeddings)
            ]

            await self._communities.upsert_generation(
                root_id=root_id,
                graph_version=communities_version,
                build_id=build_id,
                community_reports=reports_with_vectors,
            )

            if not is_targeted:
                # Mark reports complete against this detection build (full sweep only).
                # commit_report_build atomically records the committed build, clears
                # reports_dirty, and nulls the claim slot — do NOT call _release_claim().
                self._graph_store.commit_report_build(root_id, build_id, claim_token)
                self._reports_failures.pop(root_id, None)

            self._emit_progress(root_id, "ready")
            self._emit_result(
                root_id,
                communities_version,
                True,
                "reports-ready",
                started_at,
                None,
                incomplete=incomplete,
            )

        except asyncio.CancelledError:
            _release_claim()
            raise
        except CollectionMissingError as exc:
            try:
                await self._communities.ensure_collection()
            except Exception:
                pass
            logger.warning("Reports collection recovery failed for %s: %s", root_id, exc)
            _release_claim()
            if not is_targeted:
                self._record_reports_failure(root_id)
            self._emit_progress(root_id, "failed")
            self._emit_result(
                root_id, communities_version, False, "reports-failed", started_at, str(exc)
            )
        except Exception as exc:
            logger.warning("Report generation failed for %s: %s", root_id, exc)
            _release_claim()
            if not is_targeted:
                self._record_reports_failure(root_id)
            self._emit_progress(root_id, "failed")
            self._emit_result(
                root_id, communities_version, False, "reports-failed", started_at, str(exc)
            )

    def _emit_result(
        self,
        root_id: str,
        graph_version: int,
        success: bool,
        phase_reached: str,
        started_at: float,
        error: Optional[str],
        *,
        incomplete: bool = False,
    ) -> None:
        if not self._on_result:
            return
        try:
            self._on_result(
                CommunityBuildResult(
                    root_id=root_id,
                    graph_version=graph_version,
                    success=success,
                    phase_reached=phase_reached,
                    duration_s=time.time() - started_at,
                    error=error,
                    incomplete=incomplete,
                )
            )
        except Exception as cb_exc:
            logger.warning("on_result raised: %s", cb_exc)

    async def _run_one_attempt(
        self, root_id: str, claimed_version: int, build_id: str
    ) -> None:
        """Drive one durably claimed rebuild attempt."""
        started_at = time.time()
        self._emit_progress(root_id, "detecting")
        candidate_staged = False

        async def finish_failure(error: str) -> None:
            if candidate_staged:
                try:
                    await self._communities.delete_generation(
                        root_id=root_id,
                        graph_version=claimed_version,
                        build_id=build_id,
                    )
                except Exception as exc:
                    logger.warning("Community candidate cleanup failed for %s: %s", root_id, exc)
            accepted, warning = await asyncio.shield(
                asyncio.to_thread(
                    self._graph_store.fail_community_build,
                    root_id,
                    claimed_version,
                    build_id,
                )
            )
            if accepted and warning:
                logger.warning(
                    "Community rebuild for %s v%s exhausted 5 attempts; parking",
                    root_id,
                    claimed_version,
                )
            self._emit_progress(root_id, "failed")
            self._emit_result(root_id, claimed_version, False, "failed", started_at, error)

        try:
            snapshot: GraphSnapshot = self._graph_store.read_graph_snapshot(root_id)
            if snapshot.graph_version != claimed_version:
                await finish_failure("graph_version_mismatch")
                return

            if not snapshot.entities:
                published = self._graph_store.replace_communities_if_current(
                    root_id, claimed_version, build_id, []
                )
                if not published:
                    await finish_failure("cas_lost_empty_graph")
                    return
                self._graph_store.complete_community_build(root_id, claimed_version, build_id)
                await self._communities.delete_all_except(
                    root_id=root_id,
                    keep_version=claimed_version,
                    keep_build_id=build_id,
                )
                self._emit_progress(root_id, "ready")
                self._emit_result(root_id, claimed_version, True, "ready", started_at, None)
                return

            communities_tuple, _algo = detect_communities(snapshot)
            self._emit_progress(root_id, "reporting")
            reports = await generate_all_reports(
                list(communities_tuple), snapshot, self._llm_client
            )
            self._emit_progress(root_id, "embedding")
            texts = [
                _truncate_for_embed(report.get("summary", report.get("title", "")))
                for report in reports
            ]
            embeddings = await self._lm_client.get_embeddings_batch(texts) if texts else []
            reports_with_vectors = [
                dict(report, vector=embedding)
                for report, embedding in zip(reports, embeddings)
            ]

            await self._communities.upsert_generation(
                root_id=root_id,
                graph_version=claimed_version,
                build_id=build_id,
                community_reports=reports_with_vectors,
            )
            candidate_staged = True
            published = self._graph_store.replace_communities_if_current(
                root_id, claimed_version, build_id, reports
            )
            if not published:
                await finish_failure("cas_lost")
                return

            self._graph_store.complete_community_build(root_id, claimed_version, build_id)
            logger.info("Communities published for %s v%s", root_id, claimed_version)
            await self._communities.delete_all_except(
                root_id=root_id,
                keep_version=claimed_version,
                keep_build_id=build_id,
            )
            self._emit_progress(root_id, "ready")
            self._emit_result(root_id, claimed_version, True, "ready", started_at, None)

        except asyncio.CancelledError:
            if candidate_staged:
                try:
                    await asyncio.shield(
                        self._communities.delete_generation(
                            root_id=root_id,
                            graph_version=claimed_version,
                            build_id=build_id,
                        )
                    )
                except Exception:
                    pass
            await asyncio.shield(
                asyncio.to_thread(
                    self._graph_store.complete_community_build,
                    root_id,
                    claimed_version,
                    build_id,
                )
            )
            raise
        except CollectionMissingError as exc:
            try:
                await self._communities.ensure_collection()
            except Exception:
                pass
            logger.warning("Community collection recovery failed for %s: %s", root_id, exc)
            await asyncio.shield(finish_failure(str(exc)))
        except Exception as exc:
            logger.warning("Community rebuild failed for %s: %s", root_id, exc)
            await asyncio.shield(finish_failure(str(exc)))
