"""Asynchronous, change-driven JEV runtime loop with two independent branches.

Authorities: OD-21 (global at most two, branch at most one request in flight),
OD-22 (branch keys, sample age, job deadline, bounded API recovery), OD-25
(continuous observation with an optional observation-only interval), OD-26
(change-driven branches with latest-only pending state), OD-27 (collect and
plant stay independent), OD-28/T4 (one fan-out request per branch decision with
atomic questions merged in code) and the T4 task row of P03.

The Observer captures one All/JEV State pair after another on a controlled
worker and publishes the latest immutable pair; the PlantBranch and the
CollectBranch each compare :func:`jev.strategy.build_branch_state_key` against
their own last submitted / last reliable key and only then submit a decision.
Each branch then makes exactly one ``AsyncJevClient`` fan-out call
(``decide_plant`` / ``decide_collect``) whose atomic answers are merged by code
in :mod:`jev.decision`. An accepted target is published through ``on_proposal``
and handed to :mod:`jev.scheduler`, whose single execution worker reviews it
against the newest reliable pair and dispatches it through the unchanged
``ActionBoundary`` entry point, so a cycle now carries a real ``ActionResult``.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Hashable, Mapping

from actions.boundary import ActionBoundary
from state.builder import capture_state
from state.projection import project_jev_state

from .client import (
    AsyncJevClient,
    JevApiError,
    build_collect_questions,
)
from .config import JevConfigurationError
from .decision import JevActionDecision, JevDecisionError, JevRouterDecision
from .scheduler import (
    DISCARD_PROPOSAL_REPLACED,
    DISCARD_TTL_EXPIRED,
    DISCARD_TARGET_UNVERIFIABLE,
    OUTCOME_DISCARDED,
    ActionProposal,
    ActionScheduler,
    proposal_priority,
)
from .strategy import (
    BRANCH_COLLECT,
    BRANCH_PLANT,
    StrategySignals,
    build_branch_state_key,
    build_plant_candidates,
    evaluate_strategy,
)

MAX_CONSECUTIVE_ERROR_CYCLES = 3
SAMPLE_AGE_LIMIT_SECONDS = 0.5
JOB_DEADLINE_SECONDS = 10.0
API_RETRY_BASE_SECONDS = 1.0
API_RETRY_LIMIT_SECONDS = 8.0
MAX_API_ATTEMPTS = 3
BACKOFF_POLL_SECONDS = 0.05

COHORT_AUTHORIZATION_SECONDS = 5.0
COHORT_QUEUE_LIMIT = 3
"""How many accepted-but-unstarted collect batches the FIFO queue keeps (OD-59)."""
"""How long one model-authorized collect batch stays valid (OD-35, R37).

Anchored on the moment the batch was *accepted*, so the window neither starts
nor is renewed when the batch is later dequeued; a batch that waited past it is
discarded and recorded instead of being silently extended.
"""

BATCH_SUPERSEDED_BY_NEWER_BATCH = "batch_superseded_by_newer_batch"
"""Discard reason (OD-48/R37): a newer held batch replaced this one before it ran."""

BATCH_AUTHORIZATION_EXPIRED = "batch_authorization_expired"
"""Discard reason (OD-48/R37): a held batch was already past its OD-35 window."""

COHORT_AUTHORIZATION_EXPIRED = "cohort_authorization_expired"
"""Member reason (OD-51/R39): the running batch passed its OD-35 window unrun."""

COHORT_MEMBER_ID_GONE = "cohort_member_id_gone"
"""Member reason (OD-51/R39): an authorized id left All State before it ran."""

COHORT_STOPPED_BEFORE_EXECUTION = "cohort_stopped_before_execution"
"""Member reason (OD-51/R39): the stop gate cleared a batch that never ran."""

COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE = "cohort_member_deferred_never_executable"
"""Member reason (OD-51/R39): the member stayed disproved until the batch ended."""

COHORT_MEMBERS_ALL_FINISHED = "cohort_members_all_finished"
COHORT_MEMBER_ALREADY_PENDING = "cohort_member_already_pending"
BATCH_QUEUE_OVERFLOW = "batch_queue_overflow"
"""Batch reason (OD-55/R44): an affirmative answer had no collectable member left.

Every member of the answer was already confirmed collected, so the filter emptied
that batch before it could run; one record keeps that terminal state visible
instead of letting the authorization disappear without a trace.
"""

COLLECT_REASON_OUTSIDE_REGION = "outside_region"
COLLECT_REASON_NOT_FINITE = "not_finite"
COLLECT_REASON_UNRESOLVED_INTERPRETATION = "unresolved_interpretation"
COLLECT_REASON_ITEMS_UNAVAILABLE = "items_unavailable"
"""The OD-53 reason categories one unexecutable collect member is attributed to."""

COLLECT_ACCEPTED_AVAILABILITY = frozenset({"available", "provisional"})
"""Availability levels a collect member's item facts must carry to be actionable."""

UNRELIABLE_OUTCOMES = frozenset({"api_error", "invalid_response"})

Branch = str


@dataclass(frozen=True)
class RuntimeSnapshot:
    """One immutable All State / JEV State pair published by the Observer."""

    all_state: Mapping[str, Any]
    jev_state: Mapping[str, Any]
    sample_sequence: int | None
    observed_at_utc: str
    observed_monotonic: float
    version: int = 0


class SnapshotStore:
    """Hold the latest published snapshot and notify, never queue, waiters."""

    def __init__(self) -> None:
        self._snapshot: RuntimeSnapshot | None = None
        self._version = 0
        self._recheck = 0
        self._published = asyncio.Event()

    @property
    def version(self) -> int:
        return self._version

    @property
    def recheck_generation(self) -> int:
        """How often a branch has been asked to re-evaluate without a new pair."""
        return self._recheck

    def publish(self, snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
        """Publish one immutable pair as the newest snapshot and wake waiters."""
        self._version += 1
        stored = replace(snapshot, version=self._version)
        self._snapshot = stored
        event, self._published = self._published, asyncio.Event()
        event.set()
        return stored

    def request_recheck(self) -> None:
        """Wake parked branch waiters so a discarded proposal is re-evaluated.

        The snapshot itself is untouched: only :meth:`wait_for_change` reads the
        counter, so a branch that was parked on an unchanged key can evaluate that
        key again as OD-22 requires when a proposal passed its TTL and was thrown
        away.
        """
        self._recheck += 1
        event, self._published = self._published, asyncio.Event()
        event.set()

    def read(self) -> RuntimeSnapshot | None:
        """Return the newest published pair, or None before the first sample."""
        return self._snapshot

    async def wait_for_publish(self, since_version: int = -1) -> RuntimeSnapshot | None:
        """Suspend until a snapshot newer than ``since_version`` is published.

        The ``_snapshot is not None`` guard is required: without it a waiter that
        arrives before the first publish would return immediately on the initial
        version and spin instead of suspending.
        """
        while True:
            event = self._published
            if self._snapshot is not None and self._version > since_version:
                return self._snapshot
            await event.wait()

    async def wait_for_change(
        self,
        branch: Branch,
        since_key: Hashable,
        *,
        since_recheck: int = 0,
    ) -> RuntimeSnapshot | None:
        """Suspend until this branch's semantic key differs from ``since_key``.

        ``since_recheck`` also returns when :meth:`request_recheck` ran since that
        generation, which is how a branch whose proposal was discarded gets a
        chance to re-evaluate the same key.
        """
        while True:
            event = self._published
            snapshot = self._snapshot
            if snapshot is not None and build_branch_state_key(branch, snapshot.jev_state) != since_key:
                return snapshot
            if self._recheck != since_recheck:
                return snapshot
            await event.wait()


@dataclass(frozen=True)
class JevRuntimeCycle:
    """One recorded runtime event and only the state references its recorders need."""

    cycle: int
    sample_sequence: int | None
    started_at_utc: str
    finished_at_utc: str
    outcome: str
    effective_action: str
    all_state: Mapping[str, Any] | None
    jev_state: Mapping[str, Any] | None
    router: JevRouterDecision | None = None
    action: JevActionDecision | None = None
    boundary_result: Any = None
    error_code: str | None = None
    next_observation: Mapping[str, Any] | None = None
    branch: str | None = None
    source_cycle: int | None = None
    source_intent_version: int | None = None
    source_intent: dict[str, Any] | None = None
    executed_target: dict[str, Any] | None = None
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class JevLoopSummary:
    status: str
    observation_cycles: int
    router_cycles: int
    consecutive_error_cycles: int
    observations: int = 0
    jobs: int = 0
    requests: int = 0
    actions: int = 0
    skips: int = 0
    errors: int = 0
    cancelled_jobs: int = 0
    lane_closest: tuple[tuple[int, int], ...] = ()
    final_phase: str | None = None


@dataclass(frozen=True)
class _Attempt:
    """The result of one branch evaluation attempt, before invalidation checks.

    ``router`` stays for the v1 cycle/Trace record the P02 baseline writes; the
    T4 fan-out branches leave it ``None`` because there is no router phase.
    """

    outcome: str
    reliable: bool
    router: JevRouterDecision | None = None
    decision: JevActionDecision | None = None
    error_code: str | None = None


@dataclass
class _BranchState:
    """Per-branch dedup, latest-only pending state and bounded API recovery."""

    last_submitted_key: Hashable | None = None
    last_decided_key: Hashable | None = None
    attempt_key: Hashable | None = None
    attempts: int = 0
    backoff_until: float | None = None
    hard_block_key: Hashable | None = None


from .strategy import management_state_key, collect_identity_key


class JevRuntimeLoop:
    """Observe continuously and let two independent branches decide and one act.

    ``run`` keeps the synchronous entry point of the previous serial runtime and
    drives the asynchronous implementation with ``asyncio.run``; ``run_async`` is
    the same runtime for tests that already own an event loop.
    """

    def __init__(
        self,
        *,
        capture: Callable[[], Mapping[str, Any]] | None = None,
        capture_async: Callable[[], Awaitable[Mapping[str, Any]]] | None = None,
        client: Any | None = None,
        boundary: Any | None = None,
        interval_ms: int = 0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        on_cycle: Callable[[JevRuntimeCycle], None] | None = None,
        on_proposal: Callable[[Mapping[str, Any]], None] | None = None,
        max_consecutive_error_cycles: int = MAX_CONSECUTIVE_ERROR_CYCLES,
    ):
        if type(interval_ms) is not int or interval_ms < 0:
            raise ValueError("--interval-ms must be zero or a positive number of milliseconds.")
        if max_consecutive_error_cycles < 1:
            raise ValueError("The consecutive error-cycle limit must be positive.")
        self._capture = capture or capture_state
        self._capture_async = capture_async
        self._client = client or AsyncJevClient()
        self._boundary = boundary if boundary is not None else ActionBoundary()
        self._interval_seconds = interval_ms / 1000
        self._clock = clock
        self._sleep = sleep or asyncio.sleep
        self._on_cycle = on_cycle
        self._on_proposal = on_proposal
        self._error_limit = max_consecutive_error_cycles
        self._store: SnapshotStore | None = None
        self._scheduler: ActionScheduler | None = None
        self._proposal_event: asyncio.Event | None = None
        self._done: asyncio.Event | None = None
        self._branches: dict[Branch, _BranchState] = {}
        self._max_cycles: int | None = None
        self._reset_counters()

    # ------------------------------------------------------------------ entry

    def run(
        self,
        *,
        max_cycles: int | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> JevLoopSummary:
        """Run the asynchronous runtime to a stop condition from synchronous code."""
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("--max-cycles must be at least 1 when provided.")
        try:
            return asyncio.run(self._run_async(max_cycles=max_cycles, stop_requested=stop_requested))
        except KeyboardInterrupt:
            self.stop_dispatch("interrupted")
            return self._summary()

    async def run_async(
        self,
        *,
        max_cycles: int | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> JevLoopSummary:
        """Run the asynchronous runtime inside an existing event loop."""
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("--max-cycles must be at least 1 when provided.")
        return await self._run_async(max_cycles=max_cycles, stop_requested=stop_requested)

    @property
    def snapshot_store(self) -> SnapshotStore:
        """The store of the running (or most recent) runtime; mostly test access."""
        if self._store is None:
            raise RuntimeError("The runtime has not started yet.")
        return self._store

    def stop_dispatch(self, reason: str) -> None:
        """Close the submit gate, invalidate in-flight work, and drop pending state.

        Bumping ``epoch`` makes every already started job discard its answer even
        when it returns instead of being cancelled, and no new request or action can
        start afterwards. Pending proposals are voided here too, so the stop gate
        also covers the execution side. Every authorized-but-unrun collect member is
        recorded first (OD-51/R39), so the tail of a run leaves a terminal reason
        instead of disappearing with the cleared batch; this path stays synchronous.
        """
        if self._stopping:
            return
        self._stopping = True
        self._stop_status = reason
        self._epoch += 1
        self._intent = None
        self._record_stopped_cohorts()
        self._proposed_member = None
        self._cohort = []
        self._cohort_source = None
        self._cohort_started = None
        # OD-59: accepted-but-unstarted batches wait here in arrival order, oldest
        # first; each entry is (targets, source, accepted_monotonic).
        self._cohort_queue: list[tuple[list[dict], tuple, float]] = []
        self._blocked_collect.clear()
        self._finished_ids.clear()
        if self._scheduler is not None:
            self._scheduler.invalidate(reason)
        if self._done is not None:
            self._done.set()

    async def _run_async(
        self,
        *,
        max_cycles: int | None,
        stop_requested: Callable[[], bool] | None,
    ) -> JevLoopSummary:
        self._max_cycles = max_cycles
        pending_stop = self._stop_status if self._stopping else None
        self._reset_counters()
        self._scheduler = ActionScheduler(
            self._boundary, clock=self._clock, on_dispatch=self._count_action, source_guard=self._proposal_source_guard
        )
        self._proposal_event = asyncio.Event()
        self._branches = {BRANCH_PLANT: _BranchState(), BRANCH_COLLECT: _BranchState()}
        self._done = asyncio.Event()
        if pending_stop is not None:
            # The stop gate closed before the runtime started: never submit anything.
            self.stop_dispatch(pending_stop)
        store = SnapshotStore()
        self._store = store
        should_stop = stop_requested or (lambda: False)
        failure: BaseException | None = None

        async with self._client:
            observer = asyncio.create_task(self._observe(store, should_stop), name="jev-observer")
            branches = [
                asyncio.create_task(self._branch_loop(branch, store), name=f"jev-{branch}")
                for branch in (BRANCH_PLANT, BRANCH_COLLECT)
            ]
            executor = asyncio.create_task(
                self._execute_loop(store, self._scheduler), name="jev-executor"
            )
            stop_waiter = asyncio.create_task(self._done.wait(), name="jev-stop")
            tasks = [observer, *branches, executor]
            try:
                done, _pending = await asyncio.wait(
                    [stop_waiter, *tasks], return_when=asyncio.FIRST_COMPLETED
                )
                for task in tasks:
                    if task in done and not task.cancelled():
                        exception = task.exception()
                        if exception is not None:
                            failure = exception
                            break
                if failure is None and not self._stopping:
                    self.stop_dispatch("worker_stopped")
            finally:
                if failure is not None:
                    self.stop_dispatch("worker_failed")
                await _drain([stop_waiter, *tasks])

        if failure is not None:
            raise failure
        self._record_terminal()
        return self._summary()

    # -------------------------------------------------------------- observer

    async def _observe(
        self,
        store: SnapshotStore,
        stop_requested: Callable[[], bool],
    ) -> None:
        while not self._stopping:
            if stop_requested():
                self.stop_dispatch("interrupted")
                return
            started = self._clock()
            if self._capture_async is not None:
                all_state = await self._capture_async()
            else:
                all_state = await asyncio.to_thread(self._capture)
            if self._stopping:
                return
            # Sample age is measured from the moment the data was read, so a slow
            # capture never publishes a pair that already looks stale.
            read_at = self._clock()
            jev_state = project_jev_state(all_state)
            store.publish(
                RuntimeSnapshot(
                    all_state=all_state,
                    jev_state=jev_state,
                    sample_sequence=_sample_sequence(all_state),
                    observed_at_utc=_observed_at_utc(all_state),
                    observed_monotonic=read_at,
                )
            )
            self._observations += 1
            self._record_run_facts(all_state, jev_state)
            reason = self._state_stop_reason(all_state)
            if reason is not None:
                self.stop_dispatch(reason)
                return
            await self._pace(started)

    def _record_run_facts(self, all_state: Mapping[str, Any], jev_state: Mapping[str, Any]) -> None:
        """Accumulate the two run-level fact fields (OD-57, R46) from one sample.

        Facts only: the per-lane closest distance keeps its run-wide minimum and
        the final phase keeps the last observed non-empty value. Both stay on the
        run summary and never enter any decision, model request, or trace record.
        """
        for row in evaluate_strategy(jev_state).rows:
            if row.nearest_cells is None:
                continue
            current = self._lane_closest.get(row.row)
            if current is None or row.nearest_cells < current:
                self._lane_closest[row.row] = row.nearest_cells
        game = all_state.get("game")
        if isinstance(game, Mapping):
            phase = game.get("phase")
            if isinstance(phase, str) and phase:
                self._final_phase = phase

    async def _pace(self, started: float) -> None:
        if self._interval_seconds > 0:
            remaining = self._interval_seconds - (self._clock() - started)
            if remaining > 0:
                await self._sleep(remaining)
            return
        # Continuous observation still yields so the branches and the stop gate run.
        await self._sleep(0)

    def _state_stop_reason(self, all_state: Mapping[str, Any]) -> str | None:
        if all_state.get("status") == "disconnected":
            return "process_disconnected"
        game = all_state.get("game")
        if not isinstance(game, Mapping):
            return None
        phase = game.get("phase")
        if phase == "playing":
            self._seen_playing = True
        if game.get("paused") is True:
            return "paused"
        if game.get("level_complete") is True or phase in {"zombies_win", "level_award"}:
            return "level_finished"
        if self._seen_playing and phase not in {None, "playing"}:
            return "game_left_playing_phase"
        return None

    # --------------------------------------------------------------- branches

    async def _branch_loop(self, branch: Branch, store: SnapshotStore) -> None:
        state = self._branches[branch]
        while not self._stopping:
            # Explicit fairness point: keep the Observer and the stop gate running
            # even when a client implementation never suspends during a request.
            await asyncio.sleep(0)
            snapshot = store.read()
            if snapshot is None:
                await store.wait_for_publish()
                continue
            if not self._admissible(snapshot):
                await store.wait_for_publish(snapshot.version)
                continue
            signals = evaluate_strategy(snapshot.jev_state)
            if branch == BRANCH_COLLECT and (self._cohort or self._cohort_queue):
                self._pump_cohort(snapshot)
            key = self._branch_key(branch, snapshot)
            if state.attempt_key != key:
                state.attempt_key = key
                state.attempts = 0
                state.backoff_until = None
                state.hard_block_key = None
            if key == state.last_decided_key or key == state.hard_block_key:
                # A reliable conclusion already covers this key: hang, never re-ask,
                # unless a discarded proposal handed this same key back.
                self._skips += 1
                await store.wait_for_publish(snapshot.version)
                continue
            if state.backoff_until is not None and self._clock() < state.backoff_until:
                await self._wait_backoff(store, branch, key, state)
                continue
            if key == state.last_submitted_key:
                # In-flight dedup: a serial branch only reaches this while its own
                # request is pending, so it can never enqueue a second identical job.
                await store.wait_for_publish(snapshot.version)
                continue
            await self._submit(branch, state, store, snapshot, key, signals)

    async def _submit(
        self,
        branch: Branch,
        state: _BranchState,
        store: SnapshotStore,
        snapshot: RuntimeSnapshot,
        key: Hashable,
        signals: StrategySignals,
    ) -> None:
        state.last_submitted_key = key
        started = self._clock()
        epoch = self._epoch
        source_intent_version = self._intent_version
        source_intent = None if self._intent is None else dict(self._intent)
        source_result = None if self._last_result is None else dict(self._last_result)
        try:
            attempt = await self._attempt(branch, snapshot, signals)
        except asyncio.CancelledError:
            self._cancelled_jobs += 1
            self._finish_job(
                branch=branch,
                snapshot=snapshot,
                outcome="cancelled",
                attempt=None,
                next_observation=None,
                safe=True,
            )
            raise

        # The attempt returned, so nothing is in flight for this branch any more;
        # a bounded retry may submit the same key again after its backoff expires.
        state.last_submitted_key = None
        if attempt.outcome in UNRELIABLE_OUTCOMES:
            state.attempts += 1
            self._errors += 1
            if state.attempts >= MAX_API_ATTEMPTS:
                # Exhausted the bounded retry budget: stop asking for this key.
                state.hard_block_key = key
                self._mark_error_cycle()
                self._finish_job(
                    branch=branch,
                    snapshot=snapshot,
                    outcome="await_change",
                    attempt=attempt,
                    next_observation=None,
                )
                self._maybe_stop_for_max_cycles()
                return
            state.backoff_until = self._clock() + min(
                API_RETRY_BASE_SECONDS * (2 ** (state.attempts - 1)), API_RETRY_LIMIT_SECONDS
            )
            self._notify_cycle(
                self._record(branch=branch, snapshot=snapshot, outcome=attempt.outcome, attempt=attempt),
                safe=True,
            )
            return

        if attempt.decision is not None:
            from dataclasses import replace
            attempt = replace(attempt, decision=replace(attempt.decision, source_intent_version=source_intent_version, source_intent=source_intent, source_cycle=self._cycle_index + 1))
        outcome, reliable = self._resolve_outcome(branch, store, key, epoch, started, attempt)
        if reliable:
            state.last_decided_key = key
        self._consecutive_errors = 0
        latest = store.read()
        cycle = self._finish_job(
            branch=branch,
            snapshot=snapshot,
            outcome=outcome,
            attempt=attempt,
            next_observation=None if latest is None else latest.all_state,
        )
        decision = attempt.decision
        if branch == BRANCH_COLLECT and outcome not in {"discarded", "expired"} and decision is not None:
            if latest is not None and management_state_key(latest.jev_state, latest.all_state) == management_state_key(snapshot.jev_state, snapshot.all_state) and decision.management is not None and source_intent_version == self._intent_version and source_result == self._last_result:
                previous_intent = self._intent
                management = decision.management
                operation = management["operation"]
                if operation == "cancel": self._intent = None
                elif operation == "replace":
                    self._intent = None if management["type_name"] == "none_of_the_above" else {"type_name": management["type_name"]}
                if self._intent != previous_intent:
                    self._intent_version += 1
                    self._branches[BRANCH_PLANT].last_decided_key = None
                    store.request_recheck()
            if outcome == "selected":
                # OD-35/OD-48: one affirmative answer covers the frozen sample's ids
                # and an answer that arrives while another batch is still being
                # consumed is kept as the single latest unauthorized batch instead
                # of being thrown away.
                targets = [dict(target) for target in (decision.cohort or (decision.target,)) if target is not None and target.get("item_id") not in self._finished_ids]
                if targets:
                    self._accept_latest_cohort(targets, snapshot, key, signals, decision, cycle.finished_at_utc)
                    if latest is not None: self._pump_cohort(latest)
                elif decision.cohort or decision.target is not None:
                    # OD-55/R44: an affirmative answer whose every member is already
                    # confirmed collected is a terminal batch, not a silent one. It is
                    # recorded once for the batch, like every other batch end.
                    self._record_action(
                        proposal=ActionProposal(
                            branch=BRANCH_COLLECT,
                            intent="collect",
                            effective_action="collect",
                            target=dict(decision.target if decision.target is not None else decision.cohort[0]),
                            source_key=key,
                            sample_sequence=snapshot.sample_sequence,
                            epoch=self._epoch,
                            created_monotonic=self._clock(),
                            urgency="collect",
                            source_cycle=decision.source_cycle,
                        ),
                        snapshot=snapshot,
                        outcome=OUTCOME_DISCARDED,
                        reason=COHORT_MEMBERS_ALL_FINISHED,
                        result=None,
                        started_at_utc=cycle.finished_at_utc,
                        finished_at_utc=cycle.finished_at_utc,
                        evidence=None,
                    )
        elif outcome == "selected" and decision is not None and decision.target is not None:
            self._propose(branch, snapshot, key, signals, decision, cycle.finished_at_utc)
        self._maybe_stop_for_max_cycles()

    def _proposal_source_guard(self, proposal):
        if self._stopping or proposal.epoch != self._epoch: return "epoch_changed"
        latest = self._store.read() if self._store is not None else None
        if latest is not None and not self._admissible(latest): return "stale_sample"
        if proposal.branch == BRANCH_PLANT and proposal.source_intent_version is not None:
            if proposal.source_intent_version != self._intent_version or proposal.source_intent != self._intent:
                return "intent_changed"
            if self._intent is not None and proposal.target.get("type_name") != self._intent.get("type_name"):
                return "intent_type_conflict"
        return None

    def _collect_condition(self, snapshot, identity):
        from configs.pvz_1051 import ACTION_WINDOW_PROFILE
        profile = ACTION_WINDOW_PROFILE["item_coordinates"]
        items = [item for item in snapshot.all_state.get("items") or [] if isinstance(item, Mapping) and item.get("id") == identity]
        if len(items) != 1: return (len(items),)
        item = items[0]
        x, y = item.get("x"), item.get("y")
        finite = all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (x, y))
        left, top, right, bottom = profile["bounds"]
        ox, oy = profile["origin"]
        bounded = finite and left <= x + ox < right and top <= y + oy < bottom
        availability = snapshot.all_state.get("availability", {})
        return (bounded, finite, item.get("coordinate_interpretation") in profile["interpretations"], item.get("type_code"), availability.get("items"), availability.get("items.position"))

    def _branch_key(self, branch, snapshot):
        if branch == BRANCH_COLLECT:
            live_ids = {item.get("id") for item in snapshot.all_state.get("items") or [] if isinstance(item, Mapping)}
            self._finished_ids.intersection_update(live_ids)
            identity = self._cohort_source[1][0] if self._cohort and self._cohort_source else collect_identity_key(snapshot.all_state)
            return (identity, management_state_key(snapshot.jev_state, snapshot.all_state), self._intent_version, repr(self._last_result))
        return (build_branch_state_key(branch, snapshot.jev_state), self._intent_version)

    def _accept_latest_cohort(self, targets, snapshot, key, signals, decision, created_at_utc):
        """Queue one arriving ``selected`` batch, merging what is already pending.

        OD-35/OD-48/OD-59: an affirmative answer that arrives while another batch is
        still being consumed is not thrown away *and* no longer replaces the answer
        held before it. A batch whose members are all already pending (running, in
        flight, or queued) is recorded member by member and dropped instead of being
        dispatched twice; a batch that adds work joins the bounded FIFO queue and
        starts when the batches before it have ended. A batch pushed past
        :data:`COHORT_QUEUE_LIMIT` is recorded as ``batch_queue_overflow`` rather
        than silently lost.
        """
        source = (snapshot, key, signals, decision, created_at_utc)
        accepted = self._clock()
        pending = {target.get("item_id") for target in self._cohort}
        for queued_targets, _queued_source, _queued_accepted in self._cohort_queue:
            pending.update(target.get("item_id") for target in queued_targets)
        if self._proposed_member is not None:
            pending.add(self._proposed_member)
        duplicate = [dict(target) for target in targets if target.get("item_id") in pending]
        fresh = [dict(target) for target in targets if target.get("item_id") not in pending]
        if duplicate:
            self._discard_cohort(source=source, targets=duplicate, accepted=accepted, reason=COHORT_MEMBER_ALREADY_PENDING, snapshot=snapshot)
        if fresh:
            self._cohort_queue.append((fresh, source, accepted))
            while len(self._cohort_queue) > COHORT_QUEUE_LIMIT:
                dropped_targets, dropped_source, dropped_accepted = self._cohort_queue.pop(0)
                self._discard_cohort(source=dropped_source, targets=dropped_targets, accepted=dropped_accepted, reason=BATCH_QUEUE_OVERFLOW, snapshot=snapshot)
        if not self._cohort:
            # No batch is being consumed, so the oldest answer starts right away (the
            # dispatch gate below still decides when it runs).
            self._start_latest_cohort(snapshot)

    def _start_latest_cohort(self, snapshot) -> None:
        """Promote the oldest queued batch, or record why it is dropped instead.

        The promoted batch keeps the moment it was accepted, so the OD-35 window is
        never renewed by queueing, by waiting behind another batch, or by starting
        late; a batch already past it is discarded and recorded (OD-48: no silent
        loss) and the next queued batch is tried in the same call.
        """
        while self._cohort_queue:
            targets, source, accepted = self._cohort_queue.pop(0)
            runnable = [target for target in targets if target.get("item_id") not in self._finished_ids]
            if accepted is None or self._clock() - accepted > COHORT_AUTHORIZATION_SECONDS:
                self._discard_cohort(source=source, targets=runnable, accepted=accepted, reason=BATCH_AUTHORIZATION_EXPIRED, snapshot=snapshot)
                state = self._branches.get(BRANCH_COLLECT)
                if state is not None and state.last_decided_key == source[1]:
                    state.last_decided_key = None
                continue
            if not runnable:
                self._record_all_finished_batch(snapshot, source, targets, accepted)
                continue
            self._cohort = runnable
            self._cohort_source = source
            self._cohort_started = accepted
            return

    def _record_all_finished_batch(self, snapshot, source, targets, accepted) -> None:
        """One batch-level record for an affirmative answer with nothing runnable.

        OD-55: an answer whose every member is already confirmed collected is a
        terminal batch, not a silent one, so it is recorded once for the batch like
        every other batch end.
        """
        _source_snapshot, key, _signals, decision, created_at_utc = source
        members = list(targets) or list(decision.cohort or ())
        target = decision.target if decision.target is not None else (members[0] if members else {})
        self._record_action(
            proposal=ActionProposal(
                branch=BRANCH_COLLECT,
                intent="collect",
                effective_action="collect",
                target=dict(target) if isinstance(target, Mapping) else {},
                source_key=key,
                sample_sequence=snapshot.sample_sequence,
                epoch=self._epoch,
                created_monotonic=self._clock() if accepted is None else accepted,
                urgency="collect",
                source_cycle=decision.source_cycle,
            ),
            snapshot=snapshot,
            outcome=OUTCOME_DISCARDED,
            reason=COHORT_MEMBERS_ALL_FINISHED,
            result=None,
            started_at_utc=created_at_utc,
            finished_at_utc=created_at_utc,
            evidence=None,
        )

    def _discard_cohort(self, *, source, targets, accepted, reason, snapshot) -> None:
        """Record every unexecuted member of one ended batch through the action path.

        OD-51/R39: a batch that ends without running records each remaining member
        individually, so no authorized member can vanish without a terminal
        ``executed`` or ``discarded(reason)`` record. A member already deferred by
        an unchanged discrete condition keeps that fact as its reason instead of
        being reported as a plain authorization expiry.
        """
        source_snapshot, key, _signals, decision, created_at_utc = source
        effective = source_snapshot if snapshot is None else snapshot
        for target in targets:
            identity = target.get("item_id")
            member_reason = reason
            if reason == COHORT_AUTHORIZATION_EXPIRED and identity in self._blocked_collect:
                member_reason = COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE
            proposal = ActionProposal(
                branch=BRANCH_COLLECT,
                intent="collect",
                effective_action="collect",
                target=dict(target),
                source_key=key,
                sample_sequence=source_snapshot.sample_sequence,
                epoch=self._epoch,
                created_monotonic=self._clock() if accepted is None else accepted,
                urgency="collect",
                source_cycle=decision.source_cycle,
            )
            self._record_action(
                proposal=proposal,
                snapshot=effective,
                outcome=OUTCOME_DISCARDED,
                reason=member_reason,
                result=None,
                started_at_utc=created_at_utc,
                finished_at_utc=_utc_now(),
                evidence=self._member_evidence(effective, identity),
            )

    def _record_stopped_cohorts(self) -> None:
        """Record both unexecuted batches before the stop gate clears them.

        OD-51/R39: the stop path used to drop the running and held authorizations
        silently, which is where the tail of a run's authorizations disappeared.
        This stays synchronous: it only writes the same action-discard records the
        dispatch path writes, with no IO, retry, or wait.

        The one member already consumed by the Executor is left to its own dispatch
        record -- a stop never preempts an action already in flight (OD-24) -- so a
        member is recorded exactly once either way.
        """
        snapshot = self._store.read() if self._store is not None else None
        pending_collect = self._scheduler.pending(BRANCH_COLLECT) if self._scheduler is not None else ()
        in_flight = self._proposed_member if self._dispatch_busy and not pending_collect else None
        unrun = [target for target in self._cohort if target.get("item_id") != in_flight]
        if unrun and self._cohort_source is not None:
            self._discard_cohort(
                source=self._cohort_source,
                targets=unrun,
                accepted=self._cohort_started,
                reason=COHORT_STOPPED_BEFORE_EXECUTION,
                snapshot=snapshot or self._cohort_source[0],
            )
        for queued_targets, queued_source, queued_accepted in list(self._cohort_queue):
            self._discard_cohort(
                source=queued_source,
                targets=queued_targets,
                accepted=queued_accepted,
                reason=COHORT_STOPPED_BEFORE_EXECUTION,
                snapshot=snapshot or queued_source[0],
            )
        self._cohort_queue = []

    def _member_evidence(self, snapshot, identity) -> Mapping[str, Any] | None:
        """Return the bounded OD-53 evidence for one authorized collect member.

        The reason category comes from the same :meth:`_collect_condition` fact set
        the deferral uses, and the two numbers are the member's own client ``x``/
        ``y`` from that same All State sample. No id, raw field, or credential ever
        travels here (R41/V67).
        """
        if snapshot is None or identity is None:
            return None
        condition = self._collect_condition(snapshot, identity)
        items = [
            item
            for item in snapshot.all_state.get("items") or []
            if isinstance(item, Mapping) and item.get("id") == identity
        ]
        x = y = None
        if len(items) == 1:
            x = _finite_number(items[0].get("x"))
            y = _finite_number(items[0].get("y"))
        return {"reason_category": _collect_condition_reason(condition), "client_x": x, "client_y": y}

    def _pump_cohort(self, snapshot):
        from dataclasses import replace
        if self._dispatch_busy or self._scheduler is None or self._scheduler.pending(BRANCH_COLLECT): return
        if not self._cohort:
            self._start_latest_cohort(snapshot)
            if not self._cohort: return
        if self._clock() - self._cohort_started > COHORT_AUTHORIZATION_SECONDS:
            self._discard_cohort(source=self._cohort_source, targets=self._cohort, accepted=self._cohort_started, reason=COHORT_AUTHORIZATION_EXPIRED, snapshot=snapshot)
            self._cohort = []
            self._cohort_source = None
            self._cohort_started = None
            self._branches[BRANCH_COLLECT].last_decided_key = None
            return
        ids = {item.get("id") for item in snapshot.all_state.get("items") or [] if isinstance(item, Mapping)}
        present = [target for target in self._cohort if target["item_id"] in ids]
        gone = [target for target in self._cohort if target["item_id"] not in ids]
        if gone:
            # OD-51: an id that left All State is a recorded terminal discard, not a
            # silent prune; the rest of the batch keeps its turn.
            self._discard_cohort(source=self._cohort_source, targets=gone, accepted=self._cohort_started, reason=COHORT_MEMBER_ID_GONE, snapshot=snapshot)
        self._cohort = present
        if not self._cohort: return
        if not self._promote_next_collect_member(snapshot): return
        source, key, signals, decision, created = self._cohort_source
        self._proposed_member = self._cohort[0]["item_id"]
        self._propose(BRANCH_COLLECT, source, key, signals, replace(decision, target=self._cohort[0]), created)

    def _promote_next_collect_member(self, snapshot) -> bool:
        """Rotate the batch so the next member that can actually run is its head.

        OD-52/R40: a member whose discrete condition was already disproved must not
        hold the head and starve its siblings, so it moves to the tail; the first
        member that is either unproved or whose condition has changed takes its
        place. An unchanged disproved member is never proposed again, so the batch
        cannot turn into a repeated request loop.
        """
        for index, target in enumerate(self._cohort):
            identity = target["item_id"]
            if identity in self._blocked_collect:
                if self._blocked_collect[identity] == self._collect_condition(snapshot, identity):
                    continue
                del self._blocked_collect[identity]
            if index:
                self._cohort = self._cohort[index:] + self._cohort[:index]
            return True
        return False

    def _resolve_outcome(
        self,
        branch: Branch,
        store: SnapshotStore,
        key: Hashable,
        epoch: int,
        started: float,
        attempt: _Attempt,
    ) -> tuple[str, bool]:
        """Apply the OD-22 invalidation order: epoch, then key, then TTL only."""
        if self._stopping or epoch != self._epoch:
            return "discarded", False
        latest = store.read()
        if branch != BRANCH_COLLECT and latest is not None and self._branch_key(branch, latest) != key:
            return "superseded", False
        if self._clock() - started > JOB_DEADLINE_SECONDS:
            return "expired", False
        return attempt.outcome, attempt.reliable

    async def _wait_backoff(
        self,
        store: SnapshotStore,
        branch: Branch,
        key: Hashable,
        state: _BranchState,
    ) -> None:
        """Wait out the backoff, but never beyond a newly relevant key."""
        while not self._stopping:
            now = self._clock()
            if state.backoff_until is None or now >= state.backoff_until:
                return
            snapshot = store.read()
            if snapshot is not None and self._branch_key(branch, snapshot) != key:
                return
            await self._sleep(min(state.backoff_until - now, BACKOFF_POLL_SECONDS))

    async def _attempt(
        self,
        branch: Branch,
        snapshot: RuntimeSnapshot,
        signals: StrategySignals,
    ) -> _Attempt:
        """Ask one branch's complete decision set in one fan-out request."""
        local = self._local_wait_reason(branch, snapshot.jev_state, signals, snapshot.all_state)
        if local is not None:
            return _Attempt(outcome=local, reliable=True)
        if self._stopping:
            return _Attempt(outcome="discarded", reliable=False)
        # The local check above already proved this branch has something to ask,
        # and the branch entry sends exactly one request for such a key (V29), so
        # the issued request is counted here even if it fails or is cancelled.
        self._requests += 1
        try:
            if branch == BRANCH_PLANT:
                if hasattr(self._client, "decide_shared"):
                    decision = await self._client.decide_plant(snapshot.jev_state, signals=signals, intent=self._intent, last_result=self._last_result, all_state=snapshot.all_state)
                else:
                    decision = await self._client.decide_plant(snapshot.jev_state, signals=signals)
            else:
                if hasattr(self._client, "decide_shared"):
                    decision = await self._client.decide_shared(snapshot.jev_state, all_state=snapshot.all_state, intent=self._intent, last_result=self._last_result)
                else:
                    decision = await self._client.decide_collect(snapshot.jev_state, all_state=snapshot.all_state)
        except (JevApiError, JevConfigurationError) as exc:
            return _Attempt(outcome="api_error", reliable=False, error_code=type(exc).__name__)
        except JevDecisionError as exc:
            return _Attempt(outcome="invalid_response", reliable=False, error_code=type(exc).__name__)
        if decision.status == "selected" and decision.target is not None:
            return _Attempt(outcome="selected", reliable=True, decision=decision)
        outcome = "low_confidence" if decision.status == "low_confidence" else "model_wait"
        return _Attempt(outcome=outcome, reliable=True, decision=decision)

    def _local_wait_reason(
        self,
        branch: Branch,
        jev_state: Mapping[str, Any],
        signals: StrategySignals,
        all_state: Mapping[str, Any],
    ) -> str | None:
        """Decide locally, without a request, when the branch has nothing to ask.

        The collect test uses the same ``all_state`` as the eventual request, so
        "there is something to ask" means exactly "at least one option can be bound
        to a verifiable item id" (OD-32) and never disagrees with the real builder.
        """
        if branch == BRANCH_COLLECT:
            return (
                None
                if hasattr(self._client, "decide_shared") or build_collect_questions(jev_state, all_state=all_state).candidates
                else "no_target"
            )
        if hasattr(self._client, "decide_shared"):
            if self._intent is not None:
                jev_state = {**jev_state, "cards": [card for card in jev_state.get("cards") or [] if card.get("type_name") == self._intent.get("type_name")]}
                signals = evaluate_strategy(jev_state)
        if build_plant_candidates(jev_state, signals):
            return None
        if not signals.empty_plantable_cells:
            return "no_target"
        return "await_cooldown" if _has_cooling_card(jev_state) else "await_resource"

    def _admissible(self, snapshot: RuntimeSnapshot) -> bool:
        if snapshot.all_state.get("decision_ready") is not True:
            return False
        return self._clock() - snapshot.observed_monotonic <= SAMPLE_AGE_LIMIT_SECONDS

    # ---------------------------------------------------------------- records

    def _finish_job(
        self,
        *,
        branch: Branch,
        snapshot: RuntimeSnapshot,
        outcome: str,
        attempt: _Attempt | None,
        next_observation: Mapping[str, Any] | None,
        safe: bool = False,
    ) -> JevRuntimeCycle:
        self._jobs += 1
        cycle = self._record(
            branch=branch,
            snapshot=snapshot,
            outcome=outcome,
            attempt=attempt,
            next_observation=next_observation,
        )
        self._notify_cycle(cycle, safe=safe)
        return cycle

    def _propose(
        self,
        branch: Branch,
        snapshot: RuntimeSnapshot,
        key: Hashable,
        signals: StrategySignals,
        decision: JevActionDecision,
        created_at_utc: str,
    ) -> None:
        """Publish one accepted target and hand it to the single dispatch gate.

        The ``on_proposal`` mapping stays exactly the temporary dict the P02-era
        recorders read. The scheduler additionally receives a typed proposal bound
        to this pair, key, epoch and lane premise; an accepted target never reserves
        a resource and is never rewritten into a different entity.
        """
        target = dict(decision.target or {})
        if self._on_proposal is not None:
            self._on_proposal(
                {
                    "branch": branch,
                    "target": dict(target),
                    "sample_sequence": snapshot.sample_sequence,
                    "created_at_utc": created_at_utc,
                }
            )
        if self._stopping or self._scheduler is None:
            return
        urgency = "low"
        row = None
        proposal = ActionProposal(
            branch=branch,
            intent=decision.intent,
            effective_action=decision.effective_action,
            target=target,
            source_key=key,
            sample_sequence=snapshot.sample_sequence,
            epoch=self._epoch,
            created_monotonic=self._cohort_started if branch == BRANCH_COLLECT and self._cohort_started is not None else self._clock(),
            urgency=urgency,
            row=row,
            source_intent_version=decision.source_intent_version,
            source_intent=decision.source_intent,
            source_cycle=decision.source_cycle,
        )
        replaced = self._scheduler.submit(proposal)
        self._notify_proposal()
        if replaced is not None:
            # Latest-only per branch (OD-26): the newer pair wins and the replaced
            # proposal is never dispatched.
            self._record_action(
                proposal=replaced,
                snapshot=snapshot,
                outcome=OUTCOME_DISCARDED,
                reason=DISCARD_PROPOSAL_REPLACED,
                result=None,
                started_at_utc=created_at_utc,
                finished_at_utc=_utc_now(),
            )

    # --------------------------------------------------------------- executor

    async def _execute_loop(self, store: SnapshotStore, scheduler: ActionScheduler) -> None:
        """Consume at most one reviewed proposal at a time; never preempt an action.

        The Boundary call runs on a worker so the Observer and both branches keep
        running, but this task awaits it to completion before it looks at the next
        proposal: select -> click -> confirmation can never interleave with a second
        action (OD-24).
        """
        while not self._stopping:
            await asyncio.sleep(0)
            if not scheduler.has_pending():
                await self._await_proposal(scheduler)
                continue
            snapshot = store.read()
            if snapshot is None:
                await store.wait_for_publish()
                continue
            if snapshot.all_state.get("decision_ready") is not True:
                # Only a pair the game itself marked decision-ready is a reliable
                # basis for a click; a newer one is always waited for.
                await store.wait_for_publish(snapshot.version)
                continue
            await self._dispatch(scheduler, snapshot)

    async def _await_proposal(self, scheduler: ActionScheduler) -> None:
        """Suspend until a branch submits; the swap-and-set event never loses one."""
        while not self._stopping:
            event = self._proposal_event
            if scheduler.has_pending():
                return
            await event.wait()

    def _notify_proposal(self) -> None:
        event, self._proposal_event = self._proposal_event, asyncio.Event()
        if event is not None:
            event.set()

    async def _dispatch(self, scheduler: ActionScheduler, snapshot: RuntimeSnapshot) -> None:
        """Run one reviewed proposal to its ActionResult on a worker thread.

        A stop that lands while this call is already in flight cannot start a
        second action: the proposal was consumed before the Boundary was entered,
        and the Executor finishes the clicks it already started under its own
        rules without any replay or cleanup click.
        """
        started_at_utc = _utc_now()
        self._dispatch_busy = True
        try:
            dispatch = await asyncio.to_thread(
                scheduler.dispatch_next,
                jev_state=snapshot.jev_state,
                all_state=snapshot.all_state,
                epoch=self._epoch,
            )
        finally:
            self._dispatch_busy = False
        finished_at_utc = _utc_now()
        if dispatch is None:
            return
        evidence = None
        if dispatch.proposal.branch == BRANCH_COLLECT:
            identity = dispatch.proposal.target.get("item_id")
            result = dispatch.result
            status = result.get("status") if isinstance(result, Mapping) else getattr(result, "status", None)
            details = result.get("details", {}) if isinstance(result, Mapping) else getattr(result, "details", {})
            possible_input = isinstance(details, Mapping) and any(click.get("status") in {"sent", "pending", "uncertain"} for click in details.get("input_clicks", []) if isinstance(click, Mapping))
            if not possible_input and status != "unverified" and (status == "rejected" or dispatch.outcome == "action_rejected" or dispatch.outcome == "discarded" and dispatch.reason == DISCARD_TARGET_UNVERIFIABLE):
                self._blocked_collect[identity] = self._collect_condition(snapshot, identity)
                # OD-53/R41: the record of a deferred member carries why it could
                # not run (reason category) and where it was (two coordinates).
                evidence = self._member_evidence(snapshot, identity)
            else:
                if dispatch.reason != DISCARD_TTL_EXPIRED:
                    if status == "success" or (status == "rejected" and possible_input):
                        # OD-54/R42: only a confirmed disappearance ends the member, plus
                        # the one approved §8 exception -- a rejection that may already
                        # have sent input is never retried, so it stays terminal.
                        self._finished_ids.add(identity)
                    else:
                        # OD-54/R42-R43: an unverified click or a scheduler-side discard
                        # (result is None) proved nothing about the item, so it stays
                        # collectable and the branch decides this same key again to earn a
                        # *new* authorization for it instead of replaying this proposal.
                        # A production unverified result always carries a "sent" click
                        # (the Executor reports unverified exactly when input may have been
                        # sent), so it must not be treated as an already spent member.
                        self._rearm_branch(dispatch.proposal.branch, dispatch.proposal.source_key)
                self._cohort = [target for target in self._cohort if target.get("item_id") != identity]
        else:
            result_status = dispatch.result.get("status") if isinstance(dispatch.result, Mapping) else getattr(dispatch.result, "status", None)
            self._last_result = {"action": "plant", "type_name": dispatch.proposal.target.get("type_name"), "row": dispatch.proposal.target.get("row"), "col": dispatch.proposal.target.get("col"), "outcome": dispatch.outcome, "status": result_status}
        if dispatch.outcome == OUTCOME_DISCARDED:
            self._release_branch(dispatch.proposal, dispatch.reason)
        self._record_action(
            proposal=dispatch.proposal,
            snapshot=snapshot,
            outcome=dispatch.outcome,
            reason=dispatch.reason,
            result=dispatch.result,
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            evidence=evidence,
        )
        if dispatch.proposal.branch == BRANCH_COLLECT:
            # The member is terminal now; a later stop must not record it again.
            self._proposed_member = None

    def _count_action(self, proposal: ActionProposal) -> None:
        """Count one real dispatch the moment the Boundary call is entered.

        The count is taken before the call returns, so an action the stop gate
        cancels while it is already in flight is still reported as dispatched; a
        discarded proposal never reaches this point and is never counted. The
        proposal identifies the action for recorders that need more than a count.
        """
        self._actions += 1

    def _release_branch(self, proposal: ActionProposal, reason: str | None) -> None:
        """Hand a proposal that waited past its TTL back to its branch.

        Only the TTL discard needs this hand-back: the TTL is a queue-wait fact, not
        a State fact, so the branch key is unchanged and no other wake-up exists.
        Every other discard reason is a State fact that is already part of that
        branch's key, so the branch wakes by itself when the fact changes, and
        re-asking for an unchanged key would only repeat the same conclusion (OD-22:
        a reliable conclusion is never retried). A collect result that proved nothing
        about its item is armed directly by the dispatch path (OD-54) instead.
        """
        if reason != DISCARD_TTL_EXPIRED:
            return
        self._rearm_branch(proposal.branch, proposal.source_key)

    def _rearm_branch(self, branch: Branch, source_key: Hashable) -> None:
        """Make one branch decide an already answered key once more.

        A reliable conclusion pins ``last_decided_key`` so the same key is never
        re-asked; clearing it is the only way to ask for that unchanged key again.
        The guard keeps a branch that already moved on -- its own new facts made the
        key different -- from repeating a stale conclusion (OD-22).
        """
        state = self._branches.get(branch)
        if state is None or state.last_decided_key != source_key:
            return
        state.last_decided_key = None
        if self._store is not None:
            self._store.request_recheck()

    def _record_action(
        self,
        *,
        proposal: ActionProposal,
        snapshot: RuntimeSnapshot | None,
        outcome: str,
        reason: str | None,
        result: Any,
        started_at_utc: str,
        finished_at_utc: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> None:
        """Record one dispatch attempt, discard, or replacement.

        The reason travels in the cycle's ``error_code`` because the v1 cycle keeps
        exactly the field set its recorders already read, and ``boundary_result`` is
        the real Boundary return value (never a rewriting of the model's target).
        ``evidence`` is the optional OD-53 member evidence (reason category plus the
        member's client coordinates); it is projected to schema 2 through an explicit
        allowlist and never carries an entity id.
        """
        self._notify_cycle(
            JevRuntimeCycle(
                cycle=self._next_cycle(),
                sample_sequence=None if snapshot is None else snapshot.sample_sequence,
                started_at_utc=started_at_utc,
                finished_at_utc=finished_at_utc,
                outcome=outcome,
                effective_action=proposal.effective_action,
                all_state=None if snapshot is None else snapshot.all_state,
                jev_state=None if snapshot is None else snapshot.jev_state,
                boundary_result=result,
                error_code=reason,
                branch=proposal.branch,
                source_cycle=proposal.source_cycle,
                source_intent_version=proposal.source_intent_version,
                source_intent=proposal.source_intent,
                executed_target={key: value for key, value in proposal.target.items() if key in {"action", "type_name", "row", "col"}},
                evidence=evidence,
            )
        )

    def _record(
        self,
        *,
        branch: Branch,
        snapshot: RuntimeSnapshot,
        outcome: str,
        attempt: _Attempt | None,
        next_observation: Mapping[str, Any] | None = None,
    ) -> JevRuntimeCycle:
        decision = None if attempt is None else attempt.decision
        return JevRuntimeCycle(
            cycle=self._next_cycle(),
            sample_sequence=snapshot.sample_sequence,
            started_at_utc=snapshot.observed_at_utc or _utc_now(),
            finished_at_utc=_utc_now(),
            outcome=outcome,
            effective_action=decision.effective_action if decision is not None else "wait",
            all_state=snapshot.all_state,
            jev_state=snapshot.jev_state,
            router=None if attempt is None else attempt.router,
            action=decision,
            boundary_result=None,
            error_code=None if attempt is None else attempt.error_code,
            next_observation=next_observation,
            branch=branch,
        )

    def _record_terminal(self) -> None:
        snapshot = self._store.read() if self._store is not None else None
        if snapshot is None:
            return
        self._notify_cycle(
            JevRuntimeCycle(
                cycle=self._next_cycle(),
                sample_sequence=snapshot.sample_sequence,
                started_at_utc=snapshot.observed_at_utc or _utc_now(),
                finished_at_utc=_utc_now(),
                outcome=self._stop_status or "stopped",
                effective_action="wait",
                all_state=snapshot.all_state,
                jev_state=snapshot.jev_state,
            )
        )

    def _mark_error_cycle(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self._error_limit:
            self.stop_dispatch("too_many_errors")

    def _next_cycle(self) -> int:
        self._cycle_index += 1
        return self._cycle_index

    def _notify_cycle(self, cycle: JevRuntimeCycle, *, safe: bool = False) -> None:
        if self._on_cycle is None:
            return
        if safe:
            try:
                self._on_cycle(cycle)
            except Exception:
                return
            return
        self._on_cycle(cycle)

    def _maybe_stop_for_max_cycles(self) -> bool:
        if self._max_cycles is not None and self._jobs >= self._max_cycles:
            self.stop_dispatch("max_cycles")
            return True
        return False

    # ----------------------------------------------------------------- summary

    def _reset_counters(self) -> None:
        self._stopping = False
        self._stop_status: str | None = None
        self._epoch = 0
        self._intent = None
        self._intent_version = 0
        self._last_result = None
        self._cohort = []
        self._cohort_started = None
        self._cohort_source = None
        self._cohort_queue = []
        self._finished_ids = set()
        self._blocked_collect = {}
        self._proposed_member: Hashable | None = None
        self._dispatch_busy = False
        self._seen_playing = False
        self._cycle_index = 0
        self._observations = 0
        self._lane_closest: dict[int, int] = {}
        self._final_phase: str | None = None
        self._jobs = 0
        self._requests = 0
        self._actions = 0
        self._skips = 0
        self._errors = 0
        self._cancelled_jobs = 0
        self._consecutive_errors = 0

    def _summary(self) -> JevLoopSummary:
        return JevLoopSummary(
            status=self._stop_status or "stopped",
            observation_cycles=self._observations,
            router_cycles=self._jobs,
            consecutive_error_cycles=self._consecutive_errors,
            observations=self._observations,
            jobs=self._jobs,
            requests=self._requests,
            actions=self._actions,
            skips=self._skips,
            errors=self._errors,
            cancelled_jobs=self._cancelled_jobs,
            lane_closest=tuple(sorted(self._lane_closest.items())),
            final_phase=self._final_phase,
        )


async def _drain(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _collect_condition_reason(condition: tuple) -> str | None:
    """Derive the OD-53 reason category from one :meth:`JevRuntimeCollect._collect_condition`.

    An id that is not uniquely present, or an item whose availability is not
    accepted, is ``items_unavailable``; a finite check that fails precedes the
    bound and interpretation checks because an unbounded item is by definition
    outside the clickable region. A member that passes every check has no fact to
    blame, so its category is ``None`` and the batch-end reason stands alone.
    """
    if len(condition) != 6:
        return COLLECT_REASON_ITEMS_UNAVAILABLE
    bounded, finite, interpretation_ok, _type_code, items, items_position = condition
    if not finite:
        return COLLECT_REASON_NOT_FINITE
    if not bounded:
        return COLLECT_REASON_OUTSIDE_REGION
    if not interpretation_ok:
        return COLLECT_REASON_UNRESOLVED_INTERPRETATION
    if items not in COLLECT_ACCEPTED_AVAILABILITY or items_position not in COLLECT_ACCEPTED_AVAILABILITY:
        return COLLECT_REASON_ITEMS_UNAVAILABLE
    return None


def _finite_number(value: Any) -> float | None:
    """Return one finite numeric coordinate, or None for anything else."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _has_cooling_card(jev_state: Mapping[str, Any]) -> bool:
    cards = jev_state.get("cards")
    if not isinstance(cards, list):
        return False
    return any(
        isinstance(card, Mapping)
        and card.get("usable") is True
        and card.get("cooldown_ready") is not True
        for card in cards
    )


def _observed_at_utc(all_state: Mapping[str, Any]) -> str:
    value = all_state.get("observed_at_utc")
    return value if isinstance(value, str) else _utc_now()


def _sample_sequence(state: Mapping[str, Any]) -> int | None:
    value = state.get("sample_sequence")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "BATCH_AUTHORIZATION_EXPIRED",
    "BATCH_SUPERSEDED_BY_NEWER_BATCH",
    "COHORT_AUTHORIZATION_EXPIRED",
    "COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE",
    "COHORT_MEMBER_ID_GONE",
    "COHORT_MEMBERS_ALL_FINISHED",
    "COHORT_MEMBER_ALREADY_PENDING",
    "BATCH_QUEUE_OVERFLOW",
    "COHORT_STOPPED_BEFORE_EXECUTION",
    "COLLECT_REASON_ITEMS_UNAVAILABLE",
    "COLLECT_REASON_NOT_FINITE",
    "COLLECT_REASON_OUTSIDE_REGION",
    "COLLECT_REASON_UNRESOLVED_INTERPRETATION",
    "JevLoopSummary",
    "JevRuntimeCycle",
    "JevRuntimeLoop",
    "RuntimeSnapshot",
    "SnapshotStore",
]
