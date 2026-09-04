"""Tests for CommunityOrchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vectors.community_orchestrator import CommunityOrchestrator, CommunityBuildResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator(on_result=None):
    graph_store = MagicMock()
    graph_store.get_graph_version.return_value = 1
    graph_store.claim_community_build.return_value = True
    graph_store.complete_community_build.return_value = True
    graph_store.fail_community_build.return_value = (True, False)
    graph_store.list_dirty_roots.return_value = []
    # Report CAS ops: a successful claim mints a token by default.
    graph_store.claim_report_build.return_value = "test-claim-token"
    graph_store.commit_report_build.return_value = True
    graph_store.clear_report_claim.return_value = True

    progress_calls: list[tuple[str, str]] = []

    def _progress(root_id: str, phase: str) -> None:
        progress_calls.append((root_id, phase))

    orchestrator = CommunityOrchestrator(
        graph_store=graph_store,
        communities=AsyncMock(),
        lm_client=AsyncMock(),
        llm_client=AsyncMock(),
        progress_callback=_progress,
        on_result=on_result,
    )
    return orchestrator, progress_calls


def _make_snapshot(root_id="root1", graph_version=1, entities=None, edges=None):
    from vectors.graph_store import GraphSnapshot

    snap = MagicMock(spec=GraphSnapshot)
    snap.root_id = root_id
    snap.graph_version = graph_version
    snap.entities = (
        entities
        if entities is not None
        else [{"id": "e1", "name": "A", "type": "func", "degree": 1, "file_paths": '["f1"]'}]
    )
    snap.edges = edges if edges is not None else []
    return snap


# ---------------------------------------------------------------------------
# 1. schedule() single-flight + coalescing
# ---------------------------------------------------------------------------


def test_schedule_single_flight_second_call_sets_flag():
    """Second schedule() while worker is live sets reschedule flag; no 2nd task created."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        block = asyncio.Event()

        async def blocking_attempt(root_id, claimed_version, build_id):
            await block.wait()

        with patch.object(orchestrator, "_run_one_attempt", side_effect=blocking_attempt):
            orchestrator.schedule("r1")
            assert len(orchestrator._tasks) == 1
            first_task = orchestrator._tasks["r1"]

            orchestrator.schedule("r1")
            assert len(orchestrator._tasks) == 1
            assert orchestrator._tasks["r1"] is first_task
            assert orchestrator._reschedule_flags.get("r1") is True

        block.set()
        await asyncio.gather(*list(orchestrator._tasks.values()), return_exceptions=True)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. Successor launched when reschedule flag is set
# ---------------------------------------------------------------------------


def test_schedule_successor_when_reschedule_flag():
    """After first task finishes, a successor is launched when the reschedule flag was set."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        call_count = 0
        started = asyncio.Event()
        unblock = asyncio.Event()

        async def counted_attempt(root_id, claimed_version, build_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                started.set()
                await unblock.wait()

        with patch.object(orchestrator, "_run_one_attempt", side_effect=counted_attempt):
            orchestrator.schedule("r1")
            await started.wait()
            orchestrator._reschedule_flags["r1"] = True
            unblock.set()
            for _ in range(20):
                await asyncio.sleep(0.01)
                if call_count >= 2:
                    break

        assert call_count >= 2, f"Successor not launched; call_count={call_count}"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. No successor when _closing=True
# ---------------------------------------------------------------------------


def test_no_successor_when_closing():
    """When _closing is True at done-callback time, no successor task is spawned."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        call_count = 0

        async def fast_attempt(root_id, claimed_version, build_id):
            nonlocal call_count
            call_count += 1

        with patch.object(orchestrator, "_run_one_attempt", side_effect=fast_attempt):
            orchestrator.schedule("r1")
            orchestrator._reschedule_flags["r1"] = True
            orchestrator._closing = True
            await asyncio.sleep(0.05)

        assert call_count == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. CAS loss: fail_community_build called, candidate deleted
# ---------------------------------------------------------------------------


def test_cas_loss_calls_fail_and_deletes_candidate():
    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._graph_store.replace_communities_if_current.return_value = False
        orchestrator._communities.upsert_generation = AsyncMock()
        orchestrator._communities.delete_generation = AsyncMock()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((), "singleton"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[])
            await orchestrator._run_one_attempt("r1", 1, "claim-1")

        orchestrator._graph_store.fail_community_build.assert_called_once_with("r1", 1, "claim-1")
        orchestrator._communities.delete_generation.assert_called_once()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Done callback: stale reschedule suppressed by claim gate returning False
# ---------------------------------------------------------------------------


def test_task_done_claim_gate_suppresses_stale_reschedule():
    orchestrator, _ = _make_orchestrator()
    orchestrator._graph_store.claim_community_build.return_value = False

    task = MagicMock()
    task.exception.return_value = None
    task.cancelled.return_value = False
    orchestrator._tasks["r1"] = task
    orchestrator._reschedule_flags["r1"] = True

    orchestrator._task_done("r1", task)

    assert "r1" not in orchestrator._tasks
    orchestrator._graph_store.claim_community_build.assert_called_once()


# ---------------------------------------------------------------------------
# 6. Cancellation before staging: complete_community_build called, no delete
# ---------------------------------------------------------------------------


def test_cancellation_before_staging_calls_complete():
    """CancelledError before candidate staged: complete_community_build called, no delete_generation."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._communities.upsert_generation = AsyncMock()
        orchestrator._communities.delete_generation = AsyncMock()
        orchestrator._communities.delete_all_except = AsyncMock()

        async def cancel_on_upsert(**kwargs):
            raise asyncio.CancelledError()

        orchestrator._communities.upsert_generation.side_effect = cancel_on_upsert

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((), "singleton"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[])
            with pytest.raises((asyncio.CancelledError, RuntimeError)):
                await orchestrator._run_one_attempt("r1", 1, "cancel-claim")

        orchestrator._communities.delete_generation.assert_not_called()
        orchestrator._graph_store.complete_community_build.assert_called_once_with(
            "r1", 1, "cancel-claim"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. Empty graph: short-circuit to ready without detect/report
# ---------------------------------------------------------------------------


def test_empty_graph_publishes_ready_without_detect():
    async def _run():
        orchestrator, progress = _make_orchestrator()
        snapshot = _make_snapshot(entities=[])
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._graph_store.replace_communities_if_current.return_value = True
        orchestrator._communities.delete_all_except = AsyncMock()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities"
            ) as mock_detect,
            patch(
                "vectors.community_orchestrator.generate_all_reports"
            ) as mock_report,
        ):
            await orchestrator._run_one_attempt("r1", 1, "build-empty")
            mock_detect.assert_not_called()
            mock_report.assert_not_called()

        orchestrator._graph_store.replace_communities_if_current.assert_called_once()
        orchestrator._graph_store.complete_community_build.assert_called_once()
        assert any(phase == "ready" for _, phase in progress)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. Version mismatch: fail_community_build called without detect/report
# ---------------------------------------------------------------------------


def test_version_mismatch_calls_fail():
    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot(graph_version=99)
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot

        with (
            patch(
                "vectors.community_orchestrator.detect_communities"
            ) as mock_detect,
        ):
            await orchestrator._run_one_attempt("r1", 1, "build-mismatch")
            mock_detect.assert_not_called()

        orchestrator._graph_store.fail_community_build.assert_called_once()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. CollectionMissingError: ensure_collection called, fail_community_build called
# ---------------------------------------------------------------------------


def test_collection_missing_triggers_ensure_collection_and_fail():
    """CollectionMissingError during upsert_generation calls ensure_collection and fail."""
    from vectors.qdrant import CollectionMissingError

    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._communities.ensure_collection = AsyncMock()

        async def upsert_raises(**kwargs):
            raise CollectionMissingError("r1")

        orchestrator._communities.upsert_generation = AsyncMock(side_effect=upsert_raises)

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((), "singleton"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[])
            await orchestrator._run_one_attempt("r1", 1, "claim-col-missing")

        orchestrator._communities.ensure_collection.assert_awaited_once()
        orchestrator._graph_store.fail_community_build.assert_called_once()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 10. M1 regression: exception handlers wrap finish_failure in asyncio.shield
# ---------------------------------------------------------------------------


def test_exception_handlers_shield_finish_failure():
    """M1 regression: both exception handlers in _run_one_attempt must call
    asyncio.shield(finish_failure(...)) so the claim is released even when
    the outer task is cancelled during cleanup.

    Verifies structurally that asyncio.shield is present in the source,
    then behaviourally that fail_community_build is called on CollectionMissingError.
    """
    import pathlib

    src = (pathlib.Path(__file__).parent.parent / "vectors" / "community_orchestrator.py").read_text()
    # Both except handlers must wrap finish_failure in asyncio.shield
    assert src.count("asyncio.shield(finish_failure(") >= 2, (
        "_run_one_attempt exception handlers must use asyncio.shield(finish_failure(...))"
    )

    # Behavioural: verify fail_community_build is called in the CollectionMissingError path
    from vectors.qdrant import CollectionMissingError

    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._communities.ensure_collection = AsyncMock()
        orchestrator._communities.upsert_generation = AsyncMock(
            side_effect=CollectionMissingError("r1")
        )

        with (
            patch("vectors.community_orchestrator.detect_communities", return_value=((), "singleton")),
            patch("vectors.community_orchestrator.generate_all_reports", new_callable=AsyncMock, return_value=[]),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[])
            await orchestrator._run_one_attempt("r1", 1, "claim-shield")

        orchestrator._graph_store.fail_community_build.assert_called_once()

    asyncio.run(_run())


# ===========================================================================
# Two-phase split: schedule_detection / schedule_reports + TTL recovery
# ===========================================================================


class _FakeCandidate:
    """Minimal CommunityCandidate stand-in for detection tests."""

    def __init__(self, cid: str) -> None:
        self.community_id = cid
        self.level = 0
        self.parent_id = None
        self.entity_ids = ["e1"]
        self.file_ids = ["f1"]


# ---------------------------------------------------------------------------
# 11. Phase separation: schedule_detection runs detection only, no reports
# ---------------------------------------------------------------------------


def test_detection_attempt_runs_detection_only_no_reports():
    """_run_detection_attempt calls detect_communities but never generate_all_reports."""

    async def _run():
        orchestrator, progress = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._graph_store.replace_communities_if_current.return_value = True

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((_FakeCandidate("c1"),), "leiden"),
            ) as mock_detect,
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
            ) as mock_reports,
        ):
            await orchestrator._run_detection_attempt("r1", 1, "build-d1")
            mock_detect.assert_called_once()
            mock_reports.assert_not_called()

        # LLM / embedding clients must not be touched by the detection phase.
        orchestrator._lm_client.get_embeddings_batch.assert_not_called()
        orchestrator._communities.upsert_generation.assert_not_called()

        orchestrator._graph_store.replace_communities_if_current.assert_called_once()
        orchestrator._graph_store.complete_community_build.assert_called_once_with(
            "r1", 1, "build-d1"
        )
        assert any(phase == "ready" for _, phase in progress)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 12. Detection must not touch the report CAS slot
# ---------------------------------------------------------------------------


def test_detection_attempt_does_not_call_report_setters():
    """Detection must not call any report-slot ops (reports use the new CAS ops)."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot
        orchestrator._graph_store.replace_communities_if_current.return_value = True

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((_FakeCandidate("c1"),), "leiden"),
            ),
            patch("vectors.community_orchestrator.generate_all_reports", new_callable=AsyncMock),
        ):
            await orchestrator._run_detection_attempt("r1", 1, "build-d1")

        orchestrator._graph_store.claim_report_build.assert_not_called()
        orchestrator._graph_store.commit_report_build.assert_not_called()
        orchestrator._graph_store.clear_report_claim.assert_not_called()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 13. schedule_reports single-flight coalescing
# ---------------------------------------------------------------------------


def test_schedule_reports_single_flight_coalesces():
    """A second schedule_reports() while a task is live coalesces (no 2nd task)."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        block = asyncio.Event()

        async def blocking(root_id):
            await block.wait()

        with patch.object(orchestrator, "_run_reports_attempt", side_effect=blocking):
            orchestrator.schedule_reports("r1")
            assert len(orchestrator._reports_tasks) == 1
            first_task = orchestrator._reports_tasks["r1"]

            orchestrator.schedule_reports("r1")
            assert len(orchestrator._reports_tasks) == 1
            assert orchestrator._reports_tasks["r1"] is first_task
            assert orchestrator._reports_reschedule_flags.get("r1") is True

        block.set()
        await asyncio.gather(
            *list(orchestrator._reports_tasks.values()), return_exceptions=True
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 14. Coverage predicate — success: all clusters covered → not incomplete
# ---------------------------------------------------------------------------


def test_reports_coverage_all_covered_not_incomplete():
    async def _run():
        results: list = []
        orchestrator, _ = _make_orchestrator(on_result=results.append)
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-c1")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )
        orchestrator._communities.upsert_generation = AsyncMock()

        reports = [{"summary": "s1"}, {"summary": "s2"}]
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(), MagicMock()), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=reports,
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(
                return_value=[[0.0], [0.0]]
            )
            await orchestrator._run_reports_attempt("r1")

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].incomplete is False
        orchestrator._graph_store.commit_report_build.assert_called_once_with(
            "r1", "build-c1", "test-claim-token"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 15. Coverage predicate — partial: some clusters empty → incomplete=True
# ---------------------------------------------------------------------------


def test_reports_coverage_partial_is_incomplete():
    async def _run():
        results: list = []
        orchestrator, _ = _make_orchestrator(on_result=results.append)
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-c2")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )
        orchestrator._communities.upsert_generation = AsyncMock()

        # Second cluster produced no prose (LLM failure returns empty title+summary).
        reports = [{"summary": "s1"}, {"summary": "", "title": ""}]
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(), MagicMock()), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=reports,
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(
                return_value=[[0.0], [0.0]]
            )
            await orchestrator._run_reports_attempt("r1")

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].incomplete is True
        # Partial coverage still commits reports for the covered clusters.
        orchestrator._graph_store.commit_report_build.assert_called_once_with(
            "r1", "build-c2", "test-claim-token"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 16. TTL recovery: failed-permanently resets to pending; next TTL doubles
# ---------------------------------------------------------------------------


def _make_reports_orchestrator(clock, **kwargs):
    graph_store = MagicMock()
    graph_store.get_committed_generation.return_value = (1, "build-x")
    graph_store.read_graph_snapshot.return_value = _make_snapshot(graph_version=1)
    orchestrator = CommunityOrchestrator(
        graph_store=graph_store,
        communities=AsyncMock(),
        lm_client=AsyncMock(),
        llm_client=AsyncMock(),
        progress_callback=lambda *a: None,
        clock=clock,
        **kwargs,
    )
    return orchestrator


def test_reports_ttl_recovery_resets_and_doubles():
    async def _run():
        t = {"now": 1000.0}

        orchestrator = _make_reports_orchestrator(
            clock=lambda: t["now"],
            reports_max_attempts=1,
            reports_retry_base_ttl_seconds=100,
            reports_retry_max_ttl_seconds=10_000,
        )

        # First attempt hard-fails → immediately parked failed-permanently.
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom-1"),
            ),
        ):
            await orchestrator._run_reports_attempt("r1")

        state = orchestrator._reports_failures["r1"]
        assert state.permanent is True
        assert state.retry_at == 1000.0 + 100
        assert state.next_ttl_seconds == 200  # doubled for next parking

        # Within TTL: schedule_reports is a no-op (settled), no task spawned.
        orchestrator.schedule_reports("r1")
        assert "r1" not in orchestrator._reports_tasks

        # Advance past TTL: schedule_reports resets to pending and spawns a task.
        t["now"] = 1000.0 + 100 + 1
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom-2"),
            ),
        ):
            t["now"] = 1200.0
            orchestrator.schedule_reports("r1")
            assert "r1" in orchestrator._reports_tasks  # reset allowed a new attempt
            await asyncio.gather(
                *list(orchestrator._reports_tasks.values()), return_exceptions=True
            )

        state2 = orchestrator._reports_failures["r1"]
        assert state2.permanent is True
        # Re-failure applies the DOUBLED TTL (200s), transparent to consumers.
        assert state2.retry_at == 1200.0 + 200
        assert state2.next_ttl_seconds == 400

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 17. In-flight reports with stale build_id abandon; next consumer re-triggers
# ---------------------------------------------------------------------------


def test_stale_build_abandoned_then_next_consumer_retriggers():
    async def _run():
        orchestrator, _ = _make_orchestrator()
        gs = orchestrator._graph_store
        orchestrator._communities.upsert_generation = AsyncMock()
        orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[[0.0]])

        # Detection advanced under the in-flight attempt: committed build is v1/'old'
        # but the snapshot already reads v2 → abandon cleanly, release the claim.
        gs.get_committed_generation.return_value = (1, "old")
        gs.read_graph_snapshot.return_value = _make_snapshot(graph_version=2)
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[{"summary": "s"}],
            ) as mock_reports,
        ):
            await orchestrator._run_reports_attempt("r1")
            mock_reports.assert_not_called()

        gs.commit_report_build.assert_not_called()
        gs.clear_report_claim.assert_called_with("r1", "test-claim-token")  # claim released

        # Next consumer: detection has settled at v2/'new' → generation re-triggers
        # against the new cluster set and commits.
        gs.get_committed_generation.return_value = (2, "new")
        gs.read_graph_snapshot.return_value = _make_snapshot(graph_version=2)
        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[{"summary": "s"}],
            ) as mock_reports2,
        ):
            await orchestrator._run_reports_attempt("r1")
            mock_reports2.assert_called_once()

        gs.commit_report_build.assert_called_once_with("r1", "new", "test-claim-token")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 18. Deprecated alias schedule_community_rebuild delegates to detection
# ---------------------------------------------------------------------------


def test_schedule_community_rebuild_alias_delegates_to_detection():
    orchestrator, _ = _make_orchestrator()
    with patch.object(orchestrator, "schedule_detection") as mock_detect:
        orchestrator.schedule_community_rebuild("r1")
        mock_detect.assert_called_once_with("r1")


# ---------------------------------------------------------------------------
# 19. Raising progress_callback is swallowed; build completes with success=True
# ---------------------------------------------------------------------------


def test_raising_progress_callback_swallowed():
    """A progress_callback that raises must not abort the rebuild (spec ADR-0001)."""
    async def _run():
        results: list = []

        def _raising_progress(root_id: str, phase: str) -> None:
            raise RuntimeError(f"monitoring broken at {phase}")

        orchestrator = CommunityOrchestrator(
            graph_store=MagicMock(
                **{
                    "get_committed_generation.return_value": (1, "build-p"),
                    "read_graph_snapshot.return_value": _make_snapshot(graph_version=1),
                }
            ),
            communities=AsyncMock(),
            lm_client=AsyncMock(),
            llm_client=AsyncMock(),
            progress_callback=_raising_progress,
            on_result=results.append,
        )
        orchestrator._communities.upsert_generation = AsyncMock()
        orchestrator._lm_client.get_embeddings_batch = AsyncMock(return_value=[[0.1]])

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[{"summary": "s"}],
            ),
        ):
            await orchestrator._run_reports_attempt("r1")

        assert len(results) == 1, "on_result must be called despite raising progress_callback"
        assert results[0].success is True, "build must succeed even if progress_callback raised"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 20. on_result is called with success=False on failure path
# ---------------------------------------------------------------------------


def test_on_result_called_with_failure_on_reports_error():
    """on_result(success=False) must be invoked when report generation fails."""
    async def _run():
        results: list = []
        orchestrator, _ = _make_orchestrator(on_result=results.append)
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-f")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                side_effect=RuntimeError("llm down"),
            ),
        ):
            await orchestrator._run_reports_attempt("r1")

        assert len(results) == 1, "on_result must be called on failure"
        assert results[0].success is False, "on_result must receive success=False"
        assert results[0].error is not None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Targeted _run_reports_attempt (ADR-0009–0021, Seam 3)
# ---------------------------------------------------------------------------


def test_targeted_reports_skips_full_build_flags():
    """Targeted run must NOT set reports_committed_build_id (reserved for full sweeps)."""

    async def _run():
        results: list = []
        orchestrator, _ = _make_orchestrator(on_result=results.append)
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-t1")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )
        orchestrator._communities.upsert_generation = AsyncMock()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(), MagicMock()), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[{"summary": "targeted"}],
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(
                return_value=[[0.1, 0.2]]
            )
            await orchestrator._run_reports_attempt("r1", target_clusters={"c-targeted"})

        # Targeted runs never claim or commit the full report slot.
        orchestrator._graph_store.claim_report_build.assert_not_called()
        orchestrator._graph_store.commit_report_build.assert_not_called()
        # But must still upsert the generated reports
        orchestrator._communities.upsert_generation.assert_called_once()

    asyncio.run(_run())


def test_targeted_reports_filters_to_specified_clusters():
    """Targeted run only passes the named clusters to generate_all_reports."""

    async def _run():
        orchestrator, _ = _make_orchestrator()
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-t2")

        # Two clusters available in the snapshot
        c_a = MagicMock()
        c_a.community_id = "cluster-A"
        c_b = MagicMock()
        c_b.community_id = "cluster-B"

        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )
        orchestrator._communities.upsert_generation = AsyncMock()

        captured_clusters: list = []

        async def _capture(clusters, snapshot, llm_client):
            captured_clusters.extend(clusters)
            return [{"summary": "ok"}]

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((c_a, c_b), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                side_effect=_capture,
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(
                return_value=[[0.1]]
            )
            await orchestrator._run_reports_attempt(
                "r1", target_clusters={"cluster-A"}
            )

        assert len(captured_clusters) == 1
        assert captured_clusters[0].community_id == "cluster-A"

    asyncio.run(_run())


def test_full_reports_still_sets_build_flags():
    """Non-targeted run (target_clusters=None) still sets reports_committed_build_id."""

    async def _run():
        results: list = []
        orchestrator, _ = _make_orchestrator(on_result=results.append)
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-full")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )
        orchestrator._communities.upsert_generation = AsyncMock()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                return_value=((MagicMock(),), "leiden"),
            ),
            patch(
                "vectors.community_orchestrator.generate_all_reports",
                new_callable=AsyncMock,
                return_value=[{"summary": "full"}],
            ),
        ):
            orchestrator._lm_client.get_embeddings_batch = AsyncMock(
                return_value=[[0.1]]
            )
            await orchestrator._run_reports_attempt("r1")  # target_clusters=None

        orchestrator._graph_store.commit_report_build.assert_called_once_with(
            "r1", "build-full", "test-claim-token"
        )


def test_targeted_reports_failure_does_not_contaminate_failure_counter():
    """A targeted-path failure must NOT record a failure in _reports_failures.

    Regression test for: targeted exceptions called _record_reports_failure
    unconditionally, which could permanently park the slot after 5 targeted
    failures and block subsequent full-sweep schedule_reports calls.
    """

    async def _run():
        orchestrator, _ = _make_orchestrator()
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-tc")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )

        with patch(
            "vectors.community_orchestrator.detect_communities",
            return_value=((MagicMock(), MagicMock()), "leiden"),
        ), patch(
            "vectors.community_orchestrator.generate_all_reports",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            await orchestrator._run_reports_attempt("r1", target_clusters={"c-targeted"})

        # Failure counter must be empty — targeted failures must not park the slot.
        assert "r1" not in orchestrator._reports_failures

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 21. Timeout handling in _run_reports_attempt (line 512)
# ---------------------------------------------------------------------------


def test_run_reports_attempt_detect_community_timeout_logs_warning_and_releases_claim():
    """TimeoutError during detect_communities in _run_reports_attempt must log warning,
    release claim, and return without failure cascade."""

    async def _run():
        orchestrator, progress = _make_orchestrator()
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-timeout")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )

        def detect_times_out(snapshot):
            raise asyncio.TimeoutError()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                side_effect=detect_times_out,
            ) as mock_detect,
            patch("vectors.community_orchestrator.logger") as mock_logger,
        ):
            await orchestrator._run_reports_attempt("r1")
            mock_detect.assert_called_once()
            # Verify warning was logged with timeout message
            mock_logger.warning.assert_called()
            assert any(
                "timed out" in str(call).lower()
                for call in mock_logger.warning.call_args_list
            )

        # Claim must be released
        orchestrator._graph_store.clear_report_claim.assert_called_with("r1", "test-claim-token")
        # Must NOT commit or record failure (timeout = skip, not fail)
        orchestrator._graph_store.commit_report_build.assert_not_called()
        assert "r1" not in orchestrator._reports_failures
        # Progress must not reach "reporting" phase (stopped at detection)
        assert not any(phase == "reporting" for _, phase in progress)

    asyncio.run(_run())


def test_run_reports_attempt_detect_community_generic_exception_handling():
    """Generic Exception during detect_communities in _run_reports_attempt must log warning,
    release claim, and return without failure cascade."""

    async def _run():
        orchestrator, progress = _make_orchestrator()
        orchestrator._graph_store.get_committed_generation.return_value = (1, "build-exception")
        orchestrator._graph_store.read_graph_snapshot.return_value = _make_snapshot(
            graph_version=1
        )

        def detect_raises(snapshot):
            raise RuntimeError("detection crashed")

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                side_effect=detect_raises,
            ) as mock_detect,
            patch("vectors.community_orchestrator.logger") as mock_logger,
        ):
            await orchestrator._run_reports_attempt("r1")
            mock_detect.assert_called_once()
            # Verify warning was logged
            mock_logger.warning.assert_called()
            assert any(
                "failed" in str(call).lower()
                for call in mock_logger.warning.call_args_list
            )

        # Claim must be released
        orchestrator._graph_store.clear_report_claim.assert_called_with("r1", "test-claim-token")
        # Must NOT commit or record failure
        orchestrator._graph_store.commit_report_build.assert_not_called()
        assert "r1" not in orchestrator._reports_failures

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 22. Timeout handling in _run_one_attempt (line 681)
# ---------------------------------------------------------------------------


def test_run_one_attempt_detect_community_timeout_calls_finish_failure():
    """TimeoutError during detect_communities in _run_one_attempt must call
    finish_failure with detection_timeout error."""

    async def _run():
        orchestrator, progress = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot

        def detect_times_out(snapshot):
            raise asyncio.TimeoutError()

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                side_effect=detect_times_out,
            ) as mock_detect,
            patch("vectors.community_orchestrator.logger") as mock_logger,
        ):
            await orchestrator._run_one_attempt("r1", 1, "build-timeout")
            mock_detect.assert_called_once()
            # Verify warning was logged
            mock_logger.warning.assert_called()
            assert any(
                "timed out" in str(call).lower()
                for call in mock_logger.warning.call_args_list
            )

        # finish_failure must be called with timeout error
        orchestrator._graph_store.fail_community_build.assert_called_once_with(
            "r1", 1, "build-timeout"
        )
        # Progress must not reach "reporting" phase
        assert not any(phase == "reporting" for _, phase in progress)

    asyncio.run(_run())


def test_run_one_attempt_detect_community_generic_exception_handling():
    """Generic Exception during detect_communities in _run_one_attempt must call
    finish_failure with detection_error."""

    async def _run():
        orchestrator, progress = _make_orchestrator()
        snapshot = _make_snapshot()
        orchestrator._graph_store.read_graph_snapshot.return_value = snapshot

        def detect_raises(snapshot):
            raise RuntimeError("detection crashed")

        with (
            patch(
                "vectors.community_orchestrator.detect_communities",
                side_effect=detect_raises,
            ) as mock_detect,
            patch("vectors.community_orchestrator.logger") as mock_logger,
        ):
            await orchestrator._run_one_attempt("r1", 1, "build-exception")
            mock_detect.assert_called_once()
            # Verify warning was logged
            mock_logger.warning.assert_called()
            assert any(
                "failed" in str(call).lower()
                for call in mock_logger.warning.call_args_list
            )

        # finish_failure must be called
        orchestrator._graph_store.fail_community_build.assert_called_once_with(
            "r1", 1, "build-exception"
        )
        # Progress must not reach "reporting" phase
        assert not any(phase == "reporting" for _, phase in progress)

    asyncio.run(_run())
