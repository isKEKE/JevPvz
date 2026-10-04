"""Async runtime checks for continuous observation and independent branches."""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Mapping

from jev.client import (
    JevApiError,
    build_collect_questions,
    build_plant_questions,
)
from jev.decision import (
    JevActionDecision,
    combine_collect_decision,
    combine_plant_decision,
)
from jev.questions import (
    COLLECT_NOW_QUESTION_ID,
    COLLECT_TARGET_QUESTION_ID,
    DISCARD_OPTION_ID,
    PLANT_TARGET_QUESTION_ID,
    SHOVEL_TARGET_QUESTION_ID,
)
from jev.loop import (
    API_RETRY_BASE_SECONDS,
    BATCH_AUTHORIZATION_EXPIRED,
    BATCH_SUPERSEDED_BY_NEWER_BATCH,
    COHORT_AUTHORIZATION_EXPIRED,
    COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE,
    COHORT_MEMBER_ID_GONE,
    COHORT_MEMBERS_ALL_FINISHED,
    COHORT_MEMBER_ALREADY_PENDING,
    COHORT_QUEUE_LIMIT,
    BATCH_QUEUE_OVERFLOW,
    COHORT_STOPPED_BEFORE_EXECUTION,
    COHORT_AUTHORIZATION_SECONDS,
    COLLECT_REASON_ITEMS_UNAVAILABLE,
    COLLECT_REASON_NOT_FINITE,
    COLLECT_REASON_OUTSIDE_REGION,
    COLLECT_REASON_UNRESOLVED_INTERPRETATION,
    JOB_DEADLINE_SECONDS,
    MAX_API_ATTEMPTS,
    SAMPLE_AGE_LIMIT_SECONDS,
    JevLoopSummary,
    JevRuntimeCycle,
    JevRuntimeLoop,
    RuntimeSnapshot,
    SnapshotStore,
)
from jev.scheduler import (
    DISCARD_TARGET_UNVERIFIABLE,
    OUTCOME_DISCARDED,
    PROPOSAL_TTL_SECONDS,
    REJECTED_VALIDATION_FAILED,
)
from jev.trace import build_trace_event

from actions.boundary import ActionValidationError
from actions.executor import ActionResult

PEASHOOTER_CARD = {
    "slot": 0,
    "type_code": 0,
    "type_name": "peashooter",
    "cost": 100,
    "cooldown_ready": True,
    "usable": True,
}
SUNFLOWER_CARD = {
    "slot": 1,
    "type_code": 1,
    "type_name": "sunflower",
    "cost": 50,
    "cooldown_ready": True,
    "usable": True,
}
SNOW_PEA_CARD = {
    "slot": 2,
    "type_code": 5,
    "type_name": "snow_pea",
    "cost": 175,
    "cooldown_ready": True,
    "usable": True,
}
MELON_PULT_CARD = {
    "slot": 3,
    "type_code": 39,
    "type_name": "melon_pult",
    "cost": 300,
    "cooldown_ready": True,
    "usable": True,
}
SUN_ITEM = {"type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0}
SUN_ITEM_ADDRESSED = {**SUN_ITEM, "coordinate_interpretation": "f32_pixel_candidate"}


def all_state(
    sequence: int,
    *,
    ready: bool = True,
    phase: str = "playing",
    paused: bool = False,
    level_complete: bool = False,
    sun: int = 100,
    cards: list | None = None,
    items: list | None = None,
    zombies: list | None = None,
    cells: list | None = None,
    plantability: list | None = None,
    latency_ms: int = 3,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "sample_sequence": sequence,
        "observed_at_utc": f"2026-09-27T00:00:{sequence % 60:02d}.000Z",
        "status": "ok",
        "valid": True,
        "decision_ready": ready,
        "identity_verified_at_utc": f"2026-09-27T00:00:{sequence % 60:02d}.500Z",
        "capture_latency_ms": latency_ms,
        "availability": {"board.occupancy": "provisional"},
        "game": {
            "phase": phase,
            "mode": "adventure",
            "background": "day",
            "paused": paused,
            "level_complete": level_complete,
        },
        "sun_balance": sun,
        "board": {
            "rows": 5,
            "cols": 9,
            "cells": cells if cells is not None else [[None] * 9 for _ in range(5)],
            "plantability": plantability if plantability is not None else [["unknown"] * 9 for _ in range(5)],
        },
        "plants": [],
        "zombies": zombies if zombies is not None else [],
        "lanes": [],
        "items": [
            {"id": index + 1, **dict(entry)}
            for index, entry in enumerate(items or [])
        ],
        "cards": cards if cards is not None else [],
    }


def dispatchable_all_state(
    sequence: int,
    *,
    plants: list | None = None,
    items: list | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """An All State whose plant and item facts the Boundary can actually prove.

    ``all_state`` is the legacy fixture: it publishes no plant or item position
    availability, so a dispatch against it is discarded as unprovable before the
    Boundary. This variant declares the availability the real capture publishes and
    marks every cell plantable. Both fixtures give every visible item the entity id
    a real capture always reports (OD-32).
    """
    state = all_state(sequence, plantability=[[True] * 9 for _ in range(5)], items=items, **kwargs)
    state["availability"] = {
        "board.occupancy": "provisional",
        "plants": "available",
        "cards": "available",
        "items": "available",
        "items.position": "available",
    }
    state["plants"] = list(plants or [])
    state["items"] = [
        {"id": index + 1, **dict(entry)} for index, entry in enumerate(state["items"])
    ]
    return state


def boundary_result(request: Mapping[str, Any], status: str = "success") -> ActionResult:
    """A real ActionResult, exactly the shape the Boundary returns in production."""
    action = request.get("action") if isinstance(request, Mapping) else None
    return ActionResult(
        status=status,
        action=action,
        message=(
            "State confirmed the requested action."
            if status == "success"
            else "Input was sent, but the requested State change was not confirmed."
        ),
        request=dict(request),
        target={"window": "fake", "hwnd": 1},
        before_state=None,
        after_state=None,
        details={"input_clicks": [{"x": 10, "y": 20}]},
        started_at_utc="2026-09-27T00:00:00.000Z",
        finished_at_utc="2026-09-27T00:00:00.100Z",
        elapsed_ms=100,
    )


def removal_all_state(
    sequence: int,
    *,
    occupied: tuple[int, int] = (2, 3),
    plantable: bool = True,
    sun: int = 100,
    cards: list | None = None,
) -> dict[str, Any]:
    """An All State whose raw board cell the Boundary can prove is occupied.

    The raw occupied cell is the plant entity the projection compacts into
    ``plant:peashooter``; ``plantable=False`` leaves every other cell
    un-plantable, so the plant branch has a removable cell and no placement
    candidate. The availability set is the one the real capture publishes, without
    which the proposal is discarded as unprovable before the Boundary.
    """
    row, col = occupied
    cells: list[list[Any]] = [[None] * 9 for _ in range(5)]
    cells[row][col] = {
        "type_code": PEASHOOTER_CARD["type_code"],
        "type_name": PEASHOOTER_CARD["type_name"],
    }
    state = all_state(
        sequence,
        sun=sun,
        cards=cards,
        cells=cells,
        plantability=[[plantable] * 9 for _ in range(5)],
    )
    state["plants"] = [
        {
            "type_code": PEASHOOTER_CARD["type_code"],
            "type_name": PEASHOOTER_CARD["type_name"],
            "row": row,
            "col": col,
            "hp": 300,
        }
    ]
    state["availability"] = {
        "board.occupancy": "provisional",
        "plants": "available",
        "cards": "available",
        "items": "available",
        "items.position": "available",
    }
    return state


class FakeBoundary:
    """Stand-in for ActionBoundary: same signature, recorded, no game access."""

    def __init__(
        self,
        *,
        status: str = "success",
        error: Exception | None = None,
        gate: threading.Event | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.gate = gate
        self.requests: list[dict[str, Any]] = []
        self.states: list[tuple[Any, Any]] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self.lock = threading.Lock()

    def dispatch(self, request: Any, *, jev_state: Mapping[str, Any], all_state: Mapping[str, Any]) -> Any:
        with self.lock:
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            self.requests.append(dict(request))
            self.states.append((jev_state, all_state))
        try:
            if self.gate is not None:
                self.gate.wait(5)
            if self.error is not None:
                raise self.error
            return boundary_result(request, self.status)
        finally:
            with self.lock:
                self.in_flight -= 1

    def actions(self) -> list[str | None]:
        return [request.get("action") for request in self.requests]


def zombie(row: int, distance: int) -> dict[str, Any]:
    return {
        "type_code": 0,
        "type_name": "normal_zombie",
        "row": row,
        "hp": 270,
        "distance_to_house_cells": distance,
    }


def noul_answer(probability: float) -> SimpleNamespace:
    return SimpleNamespace(type="noul", noul=probability)


def choice_answer(selected: str, probabilities: Mapping[str, float], confidence: float) -> SimpleNamespace:
    return SimpleNamespace(
        type="choice",
        choice=selected,
        confidence=confidence,
        probabilities=dict(probabilities),
    )


def choice_answer_for(
    question: Any, *, selected: str | None = None, confidence: float = 0.9
) -> SimpleNamespace:
    """Answer one offered Choice with a concentrated but complete distribution."""
    option_ids = [key for key in question.criteria if key != DISCARD_OPTION_ID]
    chosen = selected or option_ids[0]
    remaining = (1.0 - confidence) / max(1, len(question.criteria) - 1)
    probabilities = {key: remaining for key in question.criteria}
    probabilities[chosen] = confidence
    return choice_answer(chosen, probabilities, confidence)


def plant_response(
    questions: Mapping[str, Any],
    *,
    confidence: float = 0.9,
    selected: str | None = None,
) -> SimpleNamespace:
    """One whole plant answer set: the offered placement Choice (or the lane chain)."""
    answers: dict[str, Any] = {}
    for question_id, question in questions.items():
        if question_id == PLANT_TARGET_QUESTION_ID:
            answers[question_id] = choice_answer_for(question, selected=selected, confidence=confidence)
        else:
            answers[question_id] = choice_answer_for(question, confidence=confidence)
    return SimpleNamespace(answers=answers, model="jev-latest", usage=None)


def collect_response(
    questions: Mapping[str, Any],
    *,
    should_collect: float = 0.9,
    confidence: float = 0.9,
    selected: str | None = None,
) -> SimpleNamespace:
    """One whole collect answer set: the absolute gate and the target Choice."""
    return SimpleNamespace(answers={COLLECT_NOW_QUESTION_ID: noul_answer(should_collect)}, model="jev-latest", usage=None)


def branch_responder(plant=plant_response, collect=collect_response):
    def responder(kind: str, state: Mapping[str, Any], questions: Mapping[str, Any], index: int) -> Any:
        if kind == "collect":
            return collect(questions)
        return plant(questions)

    return responder


def local_wait(intent: str) -> JevActionDecision:
    """The decision a branch reaches in code when there is nothing to ask."""
    return JevActionDecision(
        intent=intent,
        effective_action="wait",
        target=None,
        answers={},
        fallback_reason="no_valid_action_targets",
        status="skipped_no_targets",
        model=None,
        usage={"input_tokens": None, "output_tokens": None},
        latency_ms=0,
        question_summary={},
    )


class TickingClock:
    """Clock that advances on every read, so a sample is stale when it is evaluated."""

    def __init__(self, step: float) -> None:
        self.step = step
        self.now = 0.0
        self.reads = 0

    def monotonic(self) -> float:
        self.reads += 1
        self.now += self.step
        return self.now


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


class SleepSpy:
    """Async sleeper that advances the fake clock and records every request."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.now += seconds
        await asyncio.sleep(0)


class GatedCapture:
    """Async capture that yields one scripted sample per released permit."""

    def __init__(self) -> None:
        self.permits: asyncio.Queue = asyncio.Queue()
        self.states: list[dict[str, Any]] = []
        self.index = 0
        self.calls = 0

    def script(self, *states: dict[str, Any]) -> None:
        self.states.extend(states)

    def push(self, state: dict[str, Any]) -> None:
        self.states.append(state)

    def release(self, count: int = 1) -> None:
        for _ in range(count):
            self.permits.put_nowait(None)

    async def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        await self.permits.get()
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return state


class ScriptedCapture:
    """Async capture that keeps sampling the scripted list without a gate."""

    def __init__(self, states: list[dict[str, Any]], *, advance_seconds: float = 0.0, clock: FakeClock | None = None):
        self.states = list(states)
        self.advance_seconds = advance_seconds
        self.clock = clock
        self.index = 0
        self.calls = 0

    async def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        if self.advance_seconds and self.clock is not None:
            self.clock.now += self.advance_seconds
        return state


class FakeAsyncClient:
    """Manually gated branch client recording calls and in-flight peaks.

    Each branch entry builds the real T4 question set and merges the scripted
    answer with the real code-side merge, so the loop exercises the same
    one-request-per-decision wiring that :class:`AsyncJevClient` produces.
    """

    def __init__(self, responder=None, *, clock: FakeClock | None = None):
        self.responder = responder or branch_responder()
        self.clock = clock
        self.calls: list[dict[str, Any]] = []
        self.gate: asyncio.Queue = asyncio.Queue()
        self.blocked: dict[str, int] = {}
        self.in_flight = 0
        self.peak_in_flight = 0
        self.kind_in_flight: dict[str, int] = {}
        self.peak_by_kind: dict[str, int] = {}
        self.closed = False

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self.closed = True
        return False

    def block(self, kind: str) -> None:
        self.blocked[kind] = self.blocked.get(kind, 0) + 1

    def release(self, count: int = 1) -> None:
        for _ in range(count):
            self.gate.put_nowait(None)

    def kinds(self) -> list[str]:
        return [call["kind"] for call in self.calls]

    def calls_of(self, kind: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["kind"] == kind]

    async def decide_plant(self, jev_state: Mapping[str, Any], *, signals=None):
        question_set = build_plant_questions(jev_state, signals=signals)
        if not question_set.questions:
            return local_wait("plant")
        response = await self._decide("plant", jev_state, question_set.questions)
        return combine_plant_decision(response, question_set=question_set)

    async def decide_collect(self, jev_state: Mapping[str, Any], *, all_state=None):
        question_set = build_collect_questions(jev_state, all_state=all_state)
        if not question_set.questions:
            return local_wait("collect")
        response = await self._decide("collect", jev_state, question_set.questions)
        return combine_collect_decision(response, question_set=question_set)

    async def _decide(self, kind: str, jev_state: Mapping[str, Any], questions: Mapping[str, Any]):
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.kind_in_flight[kind] = self.kind_in_flight.get(kind, 0) + 1
        self.peak_by_kind[kind] = max(self.peak_by_kind.get(kind, 0), self.kind_in_flight[kind])
        self.calls.append(
            {
                "kind": kind,
                "sample_sequence": jev_state.get("sample_sequence"),
                "clock": None if self.clock is None else self.clock(),
                "questions": tuple(questions),
            }
        )
        try:
            if self.blocked.get(kind, 0) > 0:
                self.blocked[kind] -= 1
                await self.gate.get()
            return self.responder(kind, jev_state, questions, len(self.calls))
        finally:
            self.kind_in_flight[kind] -= 1
            self.in_flight -= 1


class RuntimeCase(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        task = getattr(self, "task", None)
        if task is not None and not task.done():
            self.loop.stop_dispatch("test_cleanup")
            task.cancel()
            try:
                await asyncio.wait_for(task, 1)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def start(self, *, capture, client, interval_ms=0, clock=None, sleep=None, max_cycles=None,
                    on_cycle=None, on_proposal=None, stop_requested=None, max_consecutive_error_cycles=3,
                    boundary=None):
        self.clock = clock if clock is not None else FakeClock()
        self.sleep = sleep if sleep is not None else SleepSpy(self.clock)
        self.capture = capture
        self.client = client
        self.boundary = boundary if boundary is not None else FakeBoundary()
        self.records: list[JevRuntimeCycle] = []
        self.proposals: list[Mapping[str, Any]] = []
        self.loop = JevRuntimeLoop(
            capture_async=capture,
            client=client,
            boundary=self.boundary,
            interval_ms=interval_ms,
            clock=self.clock.monotonic,
            sleep=self.sleep,
            on_cycle=on_cycle or self.records.append,
            on_proposal=on_proposal or self.proposals.append,
            max_consecutive_error_cycles=max_consecutive_error_cycles,
        )
        self.task = asyncio.create_task(
            self.loop.run_async(max_cycles=max_cycles, stop_requested=stop_requested)
        )
        return self.loop

    async def stop(self, reason: str = "interrupted") -> JevLoopSummary:
        self.loop.stop_dispatch(reason)
        return await asyncio.wait_for(self.task, 5)

    async def wait_until(self, predicate, *, timeout: float = 3.0) -> None:
        async def poll() -> None:
            while not predicate():
                await asyncio.sleep(0)

        try:
            await asyncio.wait_for(poll(), timeout)
        except asyncio.TimeoutError:
            client = getattr(self, "client", None)
            self.fail(f"condition was never met; calls={None if client is None else client.kinds()}")

    def store_version(self) -> int:
        try:
            return self.loop.snapshot_store.version
        except RuntimeError:
            return 0

    def outcomes(self, branch: str | None = None) -> list[str]:
        return [record.outcome for record in self.records if branch is None or record.branch == branch]

    def action_records(self, outcome: str, branch: str | None = None) -> list[JevRuntimeCycle]:
        return [
            record for record in self.records
            if record.outcome == outcome
            and (branch is None or record.branch == branch)
            and record.boundary_result is not None
        ]

    def discard_reasons(self) -> list[str | None]:
        return [
            record.error_code for record in self.records
            if record.outcome == "discarded"
        ]

    def sample_sequences(self, kind: str) -> list[int | None]:
        return [call["sample_sequence"] for call in self.client.calls_of(kind)]

    # ------------------------------------------------------------ V25: change

    async def test_each_plant_decision_is_exactly_one_fan_out_request(self):
        capture = ScriptedCapture(
            [all_state(1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 3)])]
        )
        client = FakeAsyncClient(branch_responder())
        await self.start(capture=capture, client=client)
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        await self.stop()
        plant_calls = client.calls_of("plant")
        self.assertEqual(len(plant_calls), 1)
        self.assertEqual(
            set(plant_calls[0]["questions"]),
            {PLANT_TARGET_QUESTION_ID},
        )

    async def test_no_plant_candidate_waits_locally_without_any_request(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=25, cards=[PEASHOOTER_CARD]))
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: self.outcomes("plant") == ["await_resource"])
        await asyncio.sleep(0)
        self.assertEqual(self.client.calls, [])
        summary = await self.stop()
        self.assertEqual(summary.requests, 0)
        self.assertEqual(self.proposals, [])

    async def test_observation_and_collect_branch_continue_while_plant_request_is_gated(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(branch_responder(), clock=None)
        client.block("plant")
        await self.start(capture=capture, client=client)
        capture.release(1)
        await self.wait_until(lambda: client.kinds().count("plant") == 1)
        published = self.store_version()

        capture.release(2)
        await self.wait_until(lambda: self.store_version() >= published + 2)
        self.assertEqual(self.outcomes("plant"), [])

        capture.push(all_state(2, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM]))
        capture.release(1)
        await self.wait_until(lambda: "selected" in self.outcomes("collect"))
        self.assertEqual(len(client.calls_of("plant")), 1)
        self.assertEqual(client.peak_in_flight, 2)

        client.release()
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        summary = await self.stop()
        self.assertEqual(summary.requests, 2)
        self.assertEqual([proposal["branch"] for proposal in self.proposals], ["collect", "plant"])

    async def test_metadata_only_changes_never_submit_again(self):
        capture = GatedCapture()
        base = all_state(1, sun=100, cards=[PEASHOOTER_CARD])
        capture.script(base)
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 1)
        for sequence in (2, 3, 4):
            variant = deepcopy(base)
            variant["sample_sequence"] = sequence
            variant["observed_at_utc"] = f"2026-09-27T00:10:{sequence:02d}.000Z"
            variant["identity_verified_at_utc"] = f"2026-09-27T00:11:{sequence:02d}.000Z"
            variant["capture_latency_ms"] = 400 + sequence
            capture.push(variant)
            capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 4)
        await asyncio.sleep(0)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.sample_sequences("plant"), [1])
        summary = await self.stop()
        self.assertEqual(summary.requests, 1)
        self.assertGreaterEqual(summary.observations, 4)

    async def test_band_internal_distance_change_is_ignored_and_cross_band_change_submits(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 5)]))
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 1)

        capture.push(all_state(2, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 4)]))
        capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 2)
        await asyncio.sleep(0)
        self.assertEqual(len(self.client.calls), 1)

        capture.push(all_state(3, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 3)]))
        capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 3)
        await self.wait_until(lambda: len(self.client.calls) == 2)
        self.assertEqual(self.sample_sequences("plant"), [1, 3])
        await self.stop()

    async def test_each_semantic_change_kind_submits_exactly_one_more_evaluation(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 1)

        capture.push(all_state(2, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM]))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 2)

        capture.push(all_state(3, sun=150, cards=[PEASHOOTER_CARD, SUNFLOWER_CARD]))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 3)

        occupied = [[None] * 9 for _ in range(5)]
        occupied[0][0] = {"type_code": 0, "type_name": "peashooter"}
        capture.push(all_state(4, sun=150, cards=[PEASHOOTER_CARD, SUNFLOWER_CARD], cells=occupied))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 4)
        counts: dict[str, int] = {}
        for kind in self.client.kinds():
            counts[kind] = counts.get(kind, 0) + 1
        self.assertEqual(counts, {"plant": 3, "collect": 1})
        await self.stop()

    async def test_sun_change_without_affordable_change_never_submits(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=50, cards=[PEASHOOTER_CARD]))
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: self.outcomes("plant") == ["await_resource"])
        capture.push(all_state(2, sun=75, cards=[PEASHOOTER_CARD]))
        capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 2)
        await asyncio.sleep(0)
        self.assertEqual(self.client.calls, [])
        await self.stop()

    async def test_multiple_changes_during_one_request_collapse_to_one_latest_evaluation(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(branch_responder())
        client.block("plant")
        await self.start(capture=capture, client=client)
        capture.release(1)
        await self.wait_until(lambda: len(client.calls_of("plant")) == 1)

        for sequence, distance in ((2, 5), (3, 3), (4, 1)):
            capture.push(all_state(sequence, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, distance)]))
            capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 4)

        client.release()
        await self.wait_until(lambda: len(client.calls) == 2)
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        self.assertEqual(self.outcomes("plant"), ["superseded", "selected"])
        self.assertEqual(self.sample_sequences("plant"), [1, 4])
        self.assertEqual(self.sleep.calls, [0.0] * len(self.sleep.calls))
        await self.stop()

    async def test_default_interval_never_waits_between_observations(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: len(self.client.calls) == 1)
        await self.stop()
        self.assertTrue(self.sleep.calls)
        self.assertEqual(set(self.sleep.calls), {0.0})

    async def test_positive_interval_only_paces_observations(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        clock = FakeClock()
        await self.start(
            capture=capture,
            client=FakeAsyncClient(branch_responder()),
            interval_ms=100,
            clock=clock,
            stop_requested=lambda: clock.now > 0.35,
        )
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.status, "interrupted")
        self.assertGreaterEqual(summary.observations, 4)
        self.assertGreaterEqual(len(self.client.calls), 1)
        for seconds in self.sleep.calls:
            self.assertAlmostEqual(seconds, 0.1, delta=0.02)

    def test_invalid_limits_fail_startup(self):
        with self.assertRaises(ValueError):
            JevRuntimeLoop(interval_ms=-1)
        with self.assertRaises(ValueError):
            JevRuntimeLoop(interval_ms=None)
        with self.assertRaises(ValueError):
            JevRuntimeLoop(max_consecutive_error_cycles=0)
        with self.assertRaises(ValueError):
            JevRuntimeLoop().run(max_cycles=0)

    # -------------------------------------------------- V28: bounded resources

    async def test_global_and_branch_in_flight_limits_and_no_queue(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM])])
        client = FakeAsyncClient(branch_responder())
        await self.start(capture=capture, client=client)
        await self.wait_until(lambda: len(self.records) >= 2)
        await self.stop()
        self.assertLessEqual(client.peak_in_flight, 2)
        self.assertLessEqual(client.peak_by_kind.get("plant", 0), 1)
        self.assertLessEqual(client.peak_by_kind.get("collect", 0), 1)
        self.assertEqual(client.closed, True)

    async def test_reliable_model_wait_is_not_rewoken_by_the_clock(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        clock = FakeClock()

        def responder(kind, state, questions, index):
            if kind == "collect":
                return collect_response(questions)
            return plant_response(questions, selected=DISCARD_OPTION_ID)

        client = FakeAsyncClient(responder)
        await self.start(capture=capture, client=client, clock=clock)
        capture.release(1)
        await self.wait_until(lambda: self.outcomes("plant") == ["model_wait"])
        for sequence in (2, 3, 4):
            clock.now += 120.0
            capture.push(all_state(sequence, sun=100, cards=[PEASHOOTER_CARD]))
            capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 4)
        await asyncio.sleep(0)
        self.assertEqual(len(client.calls), 1)
        summary = await self.stop()
        self.assertEqual(summary.errors, 0)
        self.assertEqual(summary.consecutive_error_cycles, 0)

    # ------------------------------------------------ V37: invalidation order

    async def test_stop_gate_discards_a_late_answer_without_accepting_it(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        holder: dict[str, Any] = {}

        def responder(kind, state, questions, index):
            holder["loop"].stop_dispatch("paused")
            return plant_response(questions)

        client = FakeAsyncClient(responder)
        loop = await self.start(capture=capture, client=client)
        holder["loop"] = loop
        capture.release(1)
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.status, "paused")
        self.assertEqual(self.outcomes("plant"), ["discarded"])
        self.assertEqual(self.proposals, [])
        self.assertEqual(summary.requests, 1)
        self.assertEqual(len(client.calls), 1)

    async def test_stop_gate_cancels_in_flight_jobs_and_stops_new_requests(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(branch_responder())
        client.block("plant")
        await self.start(capture=capture, client=client)
        capture.release(1)
        await self.wait_until(lambda: len(client.calls_of("plant")) == 1)
        capture.push(all_state(2, sun=100, cards=[PEASHOOTER_CARD], paused=True))
        capture.release(1)
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.status, "paused")
        self.assertEqual(self.outcomes("plant"), ["cancelled"])
        self.assertEqual(summary.cancelled_jobs, 1)
        self.assertEqual(summary.requests, 1)
        self.assertEqual(self.proposals, [])

    async def test_sequence_only_change_never_expires_the_result(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(branch_responder())
        client.block("plant")
        await self.start(capture=capture, client=client)
        capture.release(1)
        await self.wait_until(lambda: len(client.calls_of("plant")) == 1)
        for sequence in (2, 3, 4):
            clock_variant = all_state(sequence, sun=100, cards=[PEASHOOTER_CARD])
            capture.push(clock_variant)
            capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 4)
        client.release()
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        self.assertEqual(self.outcomes("plant"), ["selected"])
        await asyncio.sleep(0)
        await self.wait_until(lambda: len(client.calls) == 1)
        await self.stop()

    async def test_job_deadline_expires_only_while_the_key_is_unchanged(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        clock = FakeClock()
        client = FakeAsyncClient(branch_responder(), clock=clock.monotonic)
        client.block("plant")
        await self.start(capture=capture, client=client, clock=clock)
        capture.release(1)
        await self.wait_until(lambda: len(client.calls_of("plant")) == 1)
        clock.now += JOB_DEADLINE_SECONDS + 1
        capture.push(all_state(2, sun=100, cards=[PEASHOOTER_CARD]))
        capture.release(1)
        client.release()
        await self.wait_until(lambda: "expired" in self.outcomes("plant"))
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        self.assertEqual(self.outcomes("plant"), ["expired", "selected"])
        self.assertEqual(self.sample_sequences("plant"), [1, 2])
        await self.stop()

    async def test_sample_older_than_the_age_limit_never_starts_a_job(self):
        clock = TickingClock(SAMPLE_AGE_LIMIT_SECONDS + 0.1)
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])], clock=clock)
        client = FakeAsyncClient(branch_responder())
        await self.start(capture=capture, client=client, clock=clock)
        await self.wait_until(lambda: capture.calls >= 3)
        summary = await self.stop()
        self.assertGreaterEqual(summary.observations, 3)
        self.assertEqual(summary.requests, 0)
        self.assertEqual(summary.jobs, 0)
        self.assertEqual(client.calls, [])

    async def test_a_fresh_sample_is_admitted_and_started(self):
        clock = TickingClock(0.0)
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])], clock=clock)
        client = FakeAsyncClient(branch_responder())
        await self.start(capture=capture, client=client, clock=clock)
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        self.assertEqual(self.sample_sequences("plant"), [1])
        await self.stop()

    # --------------------------------------------------------- V38: recovery

    async def test_reliable_conclusions_are_recorded_once_and_never_retried(self):
        cases = (
            (
                "model_wait",
                all_state(1, sun=100, cards=[PEASHOOTER_CARD]),
                1,
                lambda kind, state, questions, index: plant_response(questions, selected=DISCARD_OPTION_ID),
            ),
            (
                "selected",
                all_state(1, sun=100, cards=[PEASHOOTER_CARD]),
                1,
                lambda kind, state, questions, index: plant_response(questions, confidence=0.5),
            ),
            (
                "model_wait",
                all_state(1, sun=100, cards=[PEASHOOTER_CARD]),
                1,
                lambda kind, state, questions, index: plant_response(questions, selected=DISCARD_OPTION_ID),
            ),
            ("await_resource", all_state(1, sun=25, cards=[PEASHOOTER_CARD]), 0, None),
            (
                "await_cooldown",
                all_state(1, sun=100, cards=[dict(PEASHOOTER_CARD, cooldown_ready=False)]),
                0,
                None,
            ),
        )
        for expected, state, expected_requests, responder in cases:
            with self.subTest(expected=expected, requests=expected_requests):
                await self._run_reliable_case(expected, state, expected_requests, responder)

    async def _run_reliable_case(self, expected, state, expected_requests, responder) -> None:
        capture = GatedCapture()
        capture.script(state)
        clock = FakeClock()
        client = FakeAsyncClient(responder or branch_responder(), clock=clock.monotonic)
        records: list[JevRuntimeCycle] = []
        loop = JevRuntimeLoop(
            capture_async=capture,
            client=client,
            boundary=FakeBoundary(),
            interval_ms=0,
            clock=clock.monotonic,
            sleep=SleepSpy(clock),
            on_cycle=records.append,
        )
        task = asyncio.create_task(loop.run_async())
        capture.release(1)
        await self.wait_until(lambda: expected in [record.outcome for record in records])
        self.assertEqual(len(client.calls), expected_requests)
        for sequence in (2, 3):
            clock.now += 90.0
            capture.push(all_state(sequence, sun=state["sun_balance"], cards=state["cards"]))
            capture.release(1)
        await self.wait_until(lambda: loop.snapshot_store.version >= 3)
        await asyncio.sleep(0)
        self.assertEqual(len(client.calls), expected_requests)
        loop.stop_dispatch("interrupted")
        summary = await asyncio.wait_for(task, 5)
        self.assertEqual(summary.errors, 0)

    async def test_api_error_backoff_is_bounded_then_waits_for_a_change(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        clock = FakeClock()
        sleeper = SleepSpy(clock)

        def responder(kind, state, questions, index):
            raise JevApiError("TimeoutException")

        client = FakeAsyncClient(responder, clock=clock.monotonic)
        await self.start(capture=capture, client=client, clock=clock, sleep=sleeper)
        await self.wait_until(lambda: "await_change" in self.outcomes("plant"))
        self.assertEqual(len(client.calls), MAX_API_ATTEMPTS)
        call_times = [call["clock"] for call in client.calls]
        self.assertAlmostEqual(call_times[0], 0.0, delta=0.02)
        self.assertAlmostEqual(call_times[1], API_RETRY_BASE_SECONDS, delta=0.11)
        self.assertAlmostEqual(call_times[2], API_RETRY_BASE_SECONDS * 3, delta=0.11)
        self.assertEqual(self.outcomes("plant"), ["api_error", "api_error", "await_change"])
        clock.now += 60.0
        await self.wait_until(lambda: capture.calls >= 4)
        await asyncio.sleep(0)
        self.assertEqual(len(client.calls), MAX_API_ATTEMPTS)
        summary = await self.stop()
        self.assertEqual(summary.errors, MAX_API_ATTEMPTS)
        self.assertEqual(summary.consecutive_error_cycles, 1)
        self.assertEqual(summary.jobs, 2)

    async def test_consecutive_error_cycles_reach_the_stop_gate(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        clock = FakeClock()

        def responder(kind, state, questions, index):
            raise JevApiError("ConnectError")

        client = FakeAsyncClient(responder, clock=clock.monotonic)
        await self.start(
            capture=capture,
            client=client,
            clock=clock,
            sleep=SleepSpy(clock),
            max_consecutive_error_cycles=1,
        )
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.status, "too_many_errors")
        self.assertEqual(summary.consecutive_error_cycles, 1)
        self.assertEqual(len(client.calls), MAX_API_ATTEMPTS)
        self.assertEqual(self.outcomes("plant").count("api_error"), MAX_API_ATTEMPTS - 1)

    # --------------------------------------- T6: dispatch, review, fairness

    async def test_an_executed_action_records_the_real_boundary_result(self):
        state = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD])
        boundary = FakeBoundary()
        await self.start(
            capture=ScriptedCapture([state]),
            client=FakeAsyncClient(branch_responder()),
            boundary=boundary,
        )
        await self.wait_until(lambda: self.action_records("executed"))
        summary = await self.stop()

        self.assertEqual(summary.actions, 1)
        self.assertEqual(len(self.proposals), 1)
        executed = self.action_records("executed")[0]
        self.assertIsInstance(executed.boundary_result, ActionResult)
        self.assertEqual(executed.boundary_result.status, "success")
        self.assertEqual(executed.branch, "plant")
        self.assertEqual(executed.effective_action, "plant")
        self.assertEqual(executed.sample_sequence, 1)
        # The model's own target, unchanged: no type, row, or col was rewritten.
        self.assertEqual(boundary.requests, [dict(self.proposals[0]["target"])])
        self.assertEqual(set(boundary.requests[0]), {"action", "type_name", "row", "col"})
        self.assertEqual(executed.boundary_result.request, boundary.requests[0])
        event = build_trace_event(executed, run_id="t6")
        self.assertEqual(
            event["boundary"],
            {"status": "success", "action": "place_plant", "elapsed_ms": 100},
        )
        json.dumps(event)

    async def test_an_unprovable_target_is_discarded_without_any_boundary_call(self):
        # The legacy fixture publishes no plant availability, so occupancy cannot be
        # proven and the plant proposal is thrown away instead of clicked.
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        boundary = FakeBoundary()
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()), boundary=boundary)
        await self.wait_until(lambda: self.outcomes("plant") == ["selected", "discarded"])
        summary = await self.stop()

        self.assertEqual(boundary.requests, [])
        self.assertEqual(summary.actions, 0)
        self.assertEqual(self.discard_reasons(), [DISCARD_TARGET_UNVERIFIABLE])

    async def test_a_rejected_action_is_recorded_and_never_resent(self):
        state = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD])
        boundary = FakeBoundary(error=ActionValidationError("the request is not provable"))
        await self.start(
            capture=ScriptedCapture([state]),
            client=FakeAsyncClient(branch_responder()),
            boundary=boundary,
        )
        await self.wait_until(lambda: self.outcomes("plant") == ["selected", "action_rejected"])
        summary = await self.stop()

        self.assertEqual(summary.actions, 1)
        self.assertEqual(len(boundary.requests), 1)
        rejected = next(record for record in self.records if record.outcome == "action_rejected")
        self.assertEqual(rejected.error_code, REJECTED_VALIDATION_FAILED)
        self.assertIsNone(rejected.boundary_result)

    async def test_an_unverified_result_is_recorded_and_retryable_with_a_new_authorization(self):
        """OD-54/R42-R43: an unconfirmed click never blacklists a visible item.

        The result is the production shape, not a simplified one: the Executor reports
        ``unverified`` exactly when ``_input_may_have_been_sent`` is true, and
        ``_send_left_click`` marks a delivered click ``status: "sent"``, so a real
        unverified result always carries a sent click plus ``postcondition_result:
        "pending"`` and ``wait.last_observation.same_item_present: true``. That is the
        exact result that blacklisted the visible sun in run e6c84636.

        The single unverified click used to mark the id finished for as long as that
        item stayed visible, so every later answer for it was filtered into an empty
        batch. The item now stays collectable and the branch decides again to earn a
        new authorization; the retry is bounded by the model's own answers, so the
        check stops after the second click and the third answer authorizes nothing.
        """
        from dataclasses import replace
        state = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM])
        boundary = FakeBoundary(status="unverified")
        original_dispatch = boundary.dispatch

        def production_dispatch(request, **kwargs):
            return replace(
                original_dispatch(request, **kwargs),
                details={
                    "input_clicks": [{"x": 10.0, "y": 20.0, "status": "sent"}],
                    "postcondition_result": "pending",
                    "wait": {"last_observation": {"same_item_present": True}},
                },
            )

        boundary.dispatch = production_dispatch
        answers = []

        def collect(questions):
            answers.append(len(answers) + 1)
            return collect_response(questions, should_collect=0.9 if len(answers) <= 2 else 0.1)

        client = FakeAsyncClient(
            branch_responder(
                collect=collect,
                plant=lambda questions: plant_response(questions, selected=DISCARD_OPTION_ID),
            )
        )
        await self.start(capture=ScriptedCapture([state]), client=client, boundary=boundary)
        await self.wait_until(lambda: len(boundary.requests) == 2)
        await self.wait_until(lambda: "model_wait" in self.outcomes("collect"))
        for _ in range(20):
            await asyncio.sleep(0)
        finished = set(self.loop._finished_ids)
        executions = self.action_records("executed", "collect")
        calls = len(client.calls_of("collect"))
        requests = [dict(request) for request in boundary.requests]
        summary = await self.stop()

        # The unverified results are recorded and the item stays collectable.
        self.assertEqual(
            [record.boundary_result.status for record in executions],
            ["unverified", "unverified"],
        )
        # The click really was sent, so this is the production case, not a local one.
        self.assertEqual(
            [
                [click["status"] for click in record.boundary_result.details["input_clicks"]]
                for record in executions
            ],
            [["sent"], ["sent"]],
        )
        self.assertNotIn(1, finished)
        # Two clicks of the same id, each from its own decision: the second one is a
        # new authorization, never a replay of the first proposal.
        self.assertEqual([request["item_id"] for request in requests], [1, 1])
        self.assertNotEqual(executions[0].source_cycle, executions[1].source_cycle)
        # Two affirmative answers, two clicks, and then the model itself withdraws:
        # the retry rate is the model's, so nothing is clicked after that.
        self.assertEqual(calls, 3)
        self.assertEqual(summary.actions, 2)

    async def test_a_confirmed_collect_ends_the_member_and_is_never_asked_again(self):
        """V68/R42: only the Executor's confirmed postcondition ends a member.

        This Boundary result carries no click status, so nothing but the confirmed
        ``success`` may end the member; once it is, the same still-visible id is
        neither authorized nor clicked again.
        """
        state = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM])
        boundary = FakeBoundary()
        client = FakeAsyncClient(
            branch_responder(plant=lambda questions: plant_response(questions, selected=DISCARD_OPTION_ID))
        )
        await self.start(capture=ScriptedCapture([state]), client=client, boundary=boundary)
        await self.wait_until(lambda: self.action_records("executed", "collect"))
        for _ in range(40):
            await asyncio.sleep(0)
        finished = set(self.loop._finished_ids)
        called = len(client.calls_of("collect"))
        requests = [dict(request) for request in boundary.requests]
        summary = await self.stop()

        self.assertEqual([request["action"] for request in requests], ["collect_item"])
        self.assertEqual([request["item_id"] for request in requests], [1])
        self.assertEqual(
            [record.boundary_result.status for record in self.action_records("executed", "collect")],
            ["success"],
        )
        self.assertIn(1, finished)
        self.assertEqual(called, 1)
        self.assertEqual(summary.actions, 1)

    async def test_two_ready_proposals_are_never_dispatched_at_the_same_time(self):
        state = dispatchable_all_state(
            1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 2)], items=[SUN_ITEM]
        )
        gate = threading.Event()
        boundary = FakeBoundary(gate=gate)
        client = FakeAsyncClient(
            branch_responder(plant=lambda questions: plant_response(questions, selected="peashooter@r2c0"))
        )
        client.block("collect")
        await self.start(capture=ScriptedCapture([state]), client=client, boundary=boundary)
        await self.wait_until(lambda: len(boundary.requests) == 1)
        client.release()
        await self.wait_until(lambda: len(self.loop._cohort) == 1)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())

        # The plant action is already in flight; the local cohort waits, and while the
        # complete plant action runs no collect input can interleave.
        self.assertEqual(boundary.actions(), ["place_plant"])
        self.assertEqual(boundary.peak_in_flight, 1)
        self.assertEqual(boundary.requests[0]["row"], 2)

        gate.set()
        await self.wait_until(lambda: len(boundary.requests) == 2)
        summary = await self.stop()
        self.assertEqual(boundary.actions(), ["place_plant", "collect_item"])
        self.assertEqual(boundary.peak_in_flight, 1)
        self.assertEqual(summary.actions, 2)
        self.assertEqual([record.branch for record in self.action_records("executed")], ["plant", "collect"])

    async def test_a_falling_sun_does_not_supersede_the_collect_decision(self):
        """V42/V43 — the live livelock, from .log/test.jsonl (run f6a0b97a4a514ceeba06bd3ba15be3e1).

        Measured on one real sun: x held at 546.0 while y went 241.5695037841797 ->
        261.6695861816406 during a single 263-507 ms JEV round trip. With coordinates
        in the collect branch key that motion alone voided every already answered
        decision (46 of 48 selected decisions were superseded, one action total), so
        the branch re-asked forever and never clicked. The key no longer sees motion,
        and the target's identity is the item id bound in its own sample, so the
        decision survives and the click follows the sun to where it is now.
        """
        before = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM])
        before["items"][0]["x"] = 546.0
        before["items"][0]["y"] = 241.5695037841797
        after = deepcopy(before)
        after["sample_sequence"] = 2
        after["observed_at_utc"] = "2026-09-27T00:00:02.000Z"
        after["items"][0]["y"] = 261.6695861816406

        capture = GatedCapture()
        capture.script(before)
        # Only the collect branch may act here: the plant branch answers with
        # its own discard option, so the single dispatched action is the collect one.
        client = FakeAsyncClient(
            branch_responder(
                plant=lambda questions: plant_response(questions, selected=DISCARD_OPTION_ID)
            )
        )
        client.block("collect")
        boundary = FakeBoundary()
        await self.start(capture=capture, client=client, boundary=boundary)

        capture.release(1)
        await self.wait_until(lambda: client.kinds().count("collect") == 1)
        # The sun keeps falling while the model is still answering.
        published = self.store_version()
        capture.push(after)
        capture.release(1)
        await self.wait_until(lambda: self.store_version() > published)
        client.release()
        await self.wait_until(
            lambda: any(request["action"] == "collect_item" for request in boundary.requests)
        )
        summary = await self.stop()

        self.assertEqual(len(client.calls_of("collect")), 1)
        self.assertNotIn("superseded", self.outcomes("collect"))
        collect_requests = [r for r in boundary.requests if r["action"] == "collect_item"]
        self.assertEqual(len(collect_requests), 1)
        self.assertEqual(collect_requests[0]["item_id"], 1)
        self.assertNotIn("x", collect_requests[0])
        self.assertNotIn("y", collect_requests[0])
        self.assertEqual(summary.actions, 1)

    async def test_the_stop_gate_starts_no_new_dispatch_and_voids_pending_proposals(self):
        state = dispatchable_all_state(
            1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 2)], items=[SUN_ITEM]
        )
        gate = threading.Event()
        boundary = FakeBoundary(gate=gate)
        client = FakeAsyncClient(
            branch_responder(plant=lambda questions: plant_response(questions, selected="peashooter@r2c0"))
        )
        client.block("collect")
        await self.start(capture=ScriptedCapture([state]), client=client, boundary=boundary)
        await self.wait_until(lambda: len(boundary.requests) == 1)
        client.release()
        await self.wait_until(lambda: len(self.loop._cohort) == 1)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())

        summary = await self.stop("paused")
        gate.set()
        for _ in range(20):
            await asyncio.sleep(0)

        self.assertEqual(summary.status, "paused")
        # Only the action that was already in flight reached the Boundary; the
        # local collect authorization was voided by the stop gate and never clicked.
        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(boundary.actions(), ["place_plant"])
        self.assertEqual(summary.actions, 1)
        # OD-51/R39: the stop gate records the unexecuted authorization before it
        # clears the batch, so the tail of a run leaves a reason instead of nothing.
        self.assertEqual(self.outcomes("collect"), ["selected", "discarded"])
        stopped = [record for record in self.records if record.error_code == COHORT_STOPPED_BEFORE_EXECUTION]
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0].branch, "collect")
        self.assertIsNone(stopped[0].boundary_result)

    async def test_a_proposal_past_its_ttl_is_discarded_and_its_branch_decides_again(self):
        state = dispatchable_all_state(
            1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 2)], items=[SUN_ITEM]
        )
        clock = FakeClock()
        gate = threading.Event()
        boundary = FakeBoundary(gate=gate)
        client = FakeAsyncClient(
            branch_responder(plant=lambda questions: plant_response(questions, selected="peashooter@r2c0"))
        )
        client.block("collect")
        await self.start(
            capture=ScriptedCapture([state], clock=clock),
            client=client,
            clock=clock,
            boundary=boundary,
        )
        await self.wait_until(lambda: len(boundary.requests) == 1)
        client.release()
        await self.wait_until(lambda: len(self.loop._cohort) == 1)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())

        clock.now += PROPOSAL_TTL_SECONDS + 0.1
        gate.set()
        # OD-51: the OD-35 window that expired here is recorded per member under the
        # batch's own reason, and the branch decides the same key again.
        await self.wait_until(lambda: COHORT_AUTHORIZATION_EXPIRED in self.discard_reasons())
        await self.wait_until(lambda: len(boundary.requests) == 2)
        summary = await self.stop()

        self.assertEqual(boundary.actions(), ["place_plant", "collect_item"])
        self.assertEqual(summary.actions, 2)
        discarded = next(record for record in self.records if record.outcome == "discarded")
        self.assertEqual(discarded.branch, "collect")
        self.assertIsNone(discarded.boundary_result)
        # The discarded proposal was handed back: the branch re-decided the same key.
        self.assertEqual(len(client.calls_of("collect")), 2)

    async def test_the_summary_counts_observations_requests_actions_and_jobs(self):
        state = dispatchable_all_state(1, sun=100, cards=[PEASHOOTER_CARD], items=[SUN_ITEM])
        boundary = FakeBoundary()
        await self.start(
            capture=ScriptedCapture([state]),
            client=FakeAsyncClient(branch_responder()),
            boundary=boundary,
        )
        await self.wait_until(lambda: len(boundary.requests) == 2)
        summary = await self.stop()

        self.assertEqual(summary.requests, 2)
        self.assertEqual(summary.actions, 2)
        self.assertGreaterEqual(summary.jobs, summary.requests)
        self.assertEqual(len(self.action_records("executed")), summary.actions)
        self.assertEqual(summary.jobs, sum(record.branch is not None and record.source_cycle is None for record in self.records))
        self.assertEqual(summary.errors, 0)
        self.assertGreaterEqual(summary.observations, 2)
        self.assertEqual(summary.observations, summary.observation_cycles)
        self.assertEqual(sorted(boundary.actions()), ["collect_item", "place_plant"])

    # ---------------------------------------------- counts and compatibility

    async def test_max_cycles_counts_terminated_jobs_not_observations(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(
            lambda kind, state, questions, index: plant_response(questions, selected=DISCARD_OPTION_ID)
        )
        client.block("plant")
        await self.start(capture=capture, client=client, max_cycles=2)
        capture.release(1)
        await self.wait_until(lambda: len(client.calls) == 1)
        await self.wait_until(lambda: self.outcomes("collect") == ["no_target"])
        capture.release(3)
        await self.wait_until(lambda: self.store_version() >= 4)
        client.release()
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.status, "max_cycles")
        self.assertEqual(summary.jobs, 2)
        self.assertEqual(summary.router_cycles, 2)
        self.assertGreaterEqual(summary.observation_cycles, 4)
        self.assertEqual(summary.observations, summary.observation_cycles)
        self.assertEqual(summary.requests, 1)
        self.assertEqual(summary.actions, 0)
        self.assertEqual(summary.cancelled_jobs, 0)

    async def test_cycle_records_keep_every_recorder_field(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: "selected" in self.outcomes("plant"))
        await self.stop()
        # This fixture publishes no plant availability, so its dispatch is discarded
        # as unprovable: every legacy record still has no Boundary result, and the
        # real ActionResult shape is covered by the T6 dispatch cases.
        for record in self.records:
            for field in (
                "cycle",
                "sample_sequence",
                "started_at_utc",
                "finished_at_utc",
                "outcome",
                "effective_action",
                "all_state",
                "jev_state",
                "router",
                "action",
                "boundary_result",
                "error_code",
                "next_observation",
            ):
                self.assertTrue(hasattr(record, field), field)
            self.assertIsNone(record.boundary_result)
        event = build_trace_event(
            next(record for record in self.records if record.outcome == "selected"), run_id="t5"
        )
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["sample_sequence"], 1)
        self.assertEqual(event["outcome"], "selected")
        self.assertEqual(event["boundary"], None)
        json.dumps(event)

    async def test_summary_keeps_legacy_fields(self):
        capture = ScriptedCapture([all_state(1, sun=100, cards=[PEASHOOTER_CARD])])
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: self.store_version() >= 1)
        summary = await self.stop()
        self.assertIsInstance(summary, JevLoopSummary)
        for field in ("status", "observation_cycles", "router_cycles", "consecutive_error_cycles"):
            self.assertTrue(hasattr(summary, field), field)

    # ----------------------------------------- V71: run-level fact fields (OD-57)

    async def test_lane_closest_keeps_the_run_minimum_per_row_and_omits_empty_lanes(self):
        # Row 2 approaches then retreats; row 4 never shows a zombie. The run
        # result is each row's minimum over the run, so the retreat does not raise
        # it, and the never-observed row is absent entirely.
        capture = ScriptedCapture(
            [
                all_state(1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 5)]),
                all_state(2, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 3)]),
                all_state(3, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 4)]),
            ]
        )
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: self.loop._observations >= 3)
        summary = await self.stop()
        self.assertEqual(summary.lane_closest, ((2, 3),))

    async def test_final_phase_keeps_the_last_observed_phase_and_status_is_unchanged(self):
        capture = ScriptedCapture(
            [
                all_state(1, phase="playing", sun=100, cards=[PEASHOOTER_CARD]),
                all_state(2, phase="zombies_win", sun=100, cards=[PEASHOOTER_CARD]),
            ]
        )
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        summary = await asyncio.wait_for(self.task, 5)
        self.assertEqual(summary.final_phase, "zombies_win")
        self.assertEqual(summary.status, "level_finished")

    async def test_run_facts_never_enter_a_model_request_state(self):
        seen: list[frozenset[str]] = []
        inner = branch_responder()

        def responder(kind, state, questions, index):
            seen.append(frozenset(state.keys()))
            return inner(kind, state, questions, index)

        capture = ScriptedCapture(
            [all_state(1, sun=100, cards=[PEASHOOTER_CARD], zombies=[zombie(2, 3)])]
        )
        await self.start(capture=capture, client=FakeAsyncClient(responder))
        await self.wait_until(lambda: len(seen) > 0)
        await self.stop()
        self.assertTrue(seen)
        for keys in seen:
            self.assertNotIn("lane_closest", keys)
            self.assertNotIn("final_phase", keys)

    async def test_recorder_failure_closes_the_gate_and_stops_new_requests(self):
        capture = GatedCapture()
        capture.script(all_state(1, sun=100, cards=[PEASHOOTER_CARD]))
        client = FakeAsyncClient(branch_responder())

        def failing_recorder(_cycle):
            raise OSError("trace disk failure")

        await self.start(capture=capture, client=client, on_cycle=failing_recorder)
        capture.release(1)
        with self.assertRaises(OSError):
            await asyncio.wait_for(self.task, 5)
        issued = len(client.calls)
        capture.release(2)
        for _ in range(50):
            await asyncio.sleep(0)
        self.assertEqual(len(client.calls), issued)
        self.assertEqual(self.loop.snapshot_store.version, 1)

    # --------------------------------------------------------- helper units

    async def test_snapshot_store_publishes_the_latest_pair_only(self):
        store = SnapshotStore()
        self.assertIsNone(store.read())
        first = store.publish(
            RuntimeSnapshot(all_state={"sample_sequence": 1}, jev_state={"items": []}, sample_sequence=1, observed_at_utc="t", observed_monotonic=0.0)
        )
        second = store.publish(
            RuntimeSnapshot(all_state={"sample_sequence": 2}, jev_state={"items": []}, sample_sequence=2, observed_at_utc="t", observed_monotonic=0.0)
        )
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(store.read().sample_sequence, 2)

        waiter = asyncio.create_task(store.wait_for_publish(2))
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())
        stored = store.publish(
            RuntimeSnapshot(all_state={"sample_sequence": 3}, jev_state={"items": []}, sample_sequence=3, observed_at_utc="t", observed_monotonic=0.0)
        )
        self.assertEqual(stored.version, 3)
        self.assertEqual(await asyncio.wait_for(waiter, 1), stored)

    async def test_not_ready_samples_are_observed_without_any_request(self):
        capture = GatedCapture()
        capture.script(all_state(1, ready=False, sun=100, cards=[PEASHOOTER_CARD]))
        await self.start(capture=capture, client=FakeAsyncClient(branch_responder()))
        capture.release(1)
        await self.wait_until(lambda: self.store_version() >= 1)
        await asyncio.sleep(0)
        self.assertEqual(self.client.calls, [])
        capture.push(all_state(2, ready=True, sun=100, cards=[PEASHOOTER_CARD]))
        capture.release(1)
        await self.wait_until(lambda: len(self.client.calls) == 1)
        await self.stop()

    # ---------------------------------------------------- removal (CD-08/CD-09)

    async def test_a_selected_removal_dispatches_one_shovel_cell_and_records_its_action(self):
        state = removal_all_state(1, plantable=False, cards=[PEASHOOTER_CARD])
        await self.start(capture=ScriptedCapture([state]), client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: self.action_records("executed"))
        self.assertEqual(self.boundary.actions(), ["shovel_cell"])
        self.assertEqual((self.boundary.requests[0]["row"], self.boundary.requests[0]["col"]), (2, 3))
        # A board with no plantable cell asks the removal layer alone, in one request.
        self.assertEqual(self.client.calls_of("plant")[0]["questions"], (SHOVEL_TARGET_QUESTION_ID,))
        self.assertEqual(self.loop._last_result["action"], "shovel_cell")
        self.assertIsNone(self.loop._last_result["type_name"])
        self.assertEqual((self.loop._last_result["row"], self.loop._last_result["col"]), (2, 3))
        await self.stop()

    async def test_two_selected_layers_dispatch_only_the_removal_and_record_the_drop(self):
        state = removal_all_state(1, plantable=True, cards=[PEASHOOTER_CARD])
        await self.start(capture=ScriptedCapture([state]), client=FakeAsyncClient(branch_responder()))
        await self.wait_until(lambda: self.action_records("executed"))
        self.assertEqual(self.boundary.actions(), ["shovel_cell"])
        self.assertEqual(
            set(self.client.calls_of("plant")[0]["questions"]),
            {PLANT_TARGET_QUESTION_ID, SHOVEL_TARGET_QUESTION_ID},
        )
        decisions = [
            record.action
            for record in self.records
            if record.branch == "plant" and record.action is not None
        ]
        merge = decisions[0].answers["merge"]
        self.assertIs(merge["shovel_selected"], True)
        self.assertIs(merge["shovel_overrode_placement"], True)
        self.assertEqual(merge["overridden_placement_option"], "peashooter@r0c0")
        await self.stop()

    async def test_local_wait_reason_asks_whenever_a_placement_or_a_removal_exists(self):
        from jev.loop import BRANCH_PLANT
        from jev.strategy import evaluate_strategy
        from state.projection import project_jev_state

        def reason(loop: JevRuntimeLoop, raw: Mapping[str, Any]) -> str | None:
            jev_state = project_jev_state(raw)
            return loop._local_wait_reason(
                BRANCH_PLANT, jev_state, evaluate_strategy(jev_state), raw
            )

        loop = JevRuntimeLoop(client=FakeAsyncClient(), boundary=FakeBoundary())
        # No plantable cell and no removable cell: the pre-existing conclusion stands.
        blocked = all_state(1, sun=100, cards=[PEASHOOTER_CARD], plantability=[[False] * 9 for _ in range(5)])
        self.assertEqual(reason(loop, blocked), "no_target")
        unaffordable = dispatchable_all_state(1, sun=25, cards=[PEASHOOTER_CARD])
        self.assertEqual(reason(loop, unaffordable), "await_resource")
        cooling = dispatchable_all_state(
            1, sun=100, cards=[{**PEASHOOTER_CARD, "cooldown_ready": False}]
        )
        self.assertEqual(reason(loop, cooling), "await_cooldown")
        removable = removal_all_state(1, plantable=False, sun=25, cards=[PEASHOOTER_CARD])
        self.assertIsNone(reason(loop, removable))

        class SharedAsyncClient(FakeAsyncClient):
            """Its ``decide_shared`` presence alone marks the saving runtime; it sends nothing."""

            async def decide_shared(self, *_args, **_kwargs):
                raise AssertionError("a saving branch must not send a request")

        saving = JevRuntimeLoop(client=SharedAsyncClient(), boundary=FakeBoundary())
        saving._intent = {"type_name": "snow_pea"}
        declared = removal_all_state(1, plantable=False, sun=25, cards=[SNOW_PEA_CARD])
        # CD-09: an unpayable declared goal still outranks a removable cell.
        self.assertEqual(reason(saving, declared), "await_plan")


class JevRuntimeLoopSyncTests(unittest.TestCase):
    def test_run_keeps_a_synchronous_entry_point(self):
        records: list[JevRuntimeCycle] = []
        loop = JevRuntimeLoop(
            capture=lambda: all_state(1, sun=100, cards=[PEASHOOTER_CARD]),
            client=FakeAsyncClient(
                lambda kind, state, questions, index: plant_response(questions, selected=DISCARD_OPTION_ID)
            ),
            interval_ms=0,
            on_cycle=records.append,
        )
        result: dict[str, Any] = {}

        def target() -> None:
            result["summary"] = loop.run(max_cycles=2)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "JevRuntimeLoop.run did not return")
        summary = result["summary"]
        self.assertEqual(summary.status, "max_cycles")
        self.assertEqual(summary.jobs, 2)
        self.assertEqual(summary.requests, 1)
        self.assertEqual(summary.actions, 0)
        self.assertTrue(records)

    def test_short_interval_is_now_allowed_and_invalid_inputs_raise(self):
        loop = JevRuntimeLoop(capture=lambda: all_state(1), interval_ms=10)
        self.assertIsNotNone(loop)
        with self.assertRaises(ValueError):
            JevRuntimeLoop(interval_ms=0.5)


if __name__ == "__main__":
    unittest.main()


class SharedSourceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setup_runtime(self, *, result=None):
        from jev.loop import _BranchState
        from jev.scheduler import ActionScheduler
        from state.projection import project_jev_state
        self.records = []
        self.now = 0.0
        class Boundary:
            def __init__(self): self.requests = []
            def dispatch(boundary, request, **kwargs):
                boundary.requests.append(dict(request))
                return result or {"status": "success", "details": {"input_clicks": [{"status": "sent"}]}}
        self.boundary = Boundary()
        self.loop = JevRuntimeLoop(client=SimpleNamespace(decide_shared=True), boundary=self.boundary, clock=lambda: self.now, on_cycle=self.records.append)
        self.loop._branches = {"collect": _BranchState(), "plant": _BranchState()}
        self.loop._proposal_event = asyncio.Event()
        self.loop._store = SnapshotStore()
        self.loop._scheduler = ActionScheduler(self.boundary, clock=lambda: self.now, source_guard=self.loop._proposal_source_guard)
        raw = dispatchable_all_state(1, cards=[SUNFLOWER_CARD], items=[{**SUN_ITEM, "id": identity, "coordinate_interpretation": "f32_pixel_candidate"} for identity in (101, 102, 103)])
        self.source = self.loop._store.publish(RuntimeSnapshot(raw, project_jev_state(raw), 1, raw["observed_at_utc"], 0.0))
        return self.loop

    def decision(self, operation="replace", type_name="sunflower", affirmative=True):
        targets = tuple({"action": "collect_item", "item_id": item["id"], "type_code": 4, "type_name": "sun"} for item in self.source.all_state["items"])
        return JevActionDecision("collect", "collect" if affirmative else "wait", targets[0] if affirmative else None, {}, None, "selected" if affirmative else "model_wait", "offline", {}, 1, {}, cohort=targets if affirmative else (), management={"operation": operation, "type_name": type_name})

    async def submit(self, decision, *, during=None):
        from jev.loop import _Attempt
        from jev.strategy import evaluate_strategy
        async def attempt(*args):
            if during: during()
            return _Attempt(decision.status, True, decision=decision)
        self.loop._attempt = attempt
        key = self.loop._branch_key("collect", self.source)
        await self.loop._submit("collect", self.loop._branches["collect"], self.loop._store, self.source, key, evaluate_strategy(self.source.jev_state))

    async def test_same_keep_content_does_not_publish_new_version(self):
        self.setup_runtime()
        await self.submit(self.decision())
        version = self.loop._intent_version
        await self.submit(self.decision(operation="keep", affirmative=False))
        self.assertEqual(self.loop._intent_version, version)

    async def test_stale_management_context_does_not_replace_current_intent(self):
        self.setup_runtime()
        def changed():
            self.loop._intent = {"type_name": "peashooter"}
            self.loop._intent_version += 1
        await self.submit(self.decision(), during=changed)
        self.assertEqual(self.loop._intent["type_name"], "peashooter")
        self.assertEqual(len(self.loop._cohort), 3)

    async def test_one_affirmative_consumes_three_ids_sequentially_and_preserves_provenance(self):
        from jev.trace import RuntimeEventBuilder
        self.setup_runtime()
        await self.submit(self.decision())
        source_cycle = self.records[0].cycle
        for _ in range(3):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102, 103])
        self.assertEqual(self.loop._cohort, [])
        self.assertTrue(all(record.source_cycle == source_cycle for record in self.records[1:]))
        builder = RuntimeEventBuilder(run_id="offline")
        events = [event for record in self.records for event in builder.events_for(record)]
        executions = [event for event in events if event["event"] == "action_result"]
        self.assertEqual({event["job_id"] for event in executions}, {"job-000001"})
        self.assertNotIn("item_id", json.dumps(events))

    async def test_stale_plant_intent_is_rejected_before_boundary(self):
        from jev.strategy import evaluate_strategy
        from dataclasses import replace
        self.setup_runtime()
        self.loop._intent = {"type_name": "sunflower"}
        decision = replace(self.decision(), intent="plant", effective_action="plant", target={"action": "place_plant", "type_name": "sunflower", "row": 0, "col": 0}, source_intent_version=0, source_intent=dict(self.loop._intent))
        self.loop._propose("plant", self.source, (), evaluate_strategy(self.source.jev_state), decision, "2026-09-27T00:00:00Z")
        self.loop._intent_version = 1
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual(self.boundary.requests, [])
        self.assertEqual(self.records[-1].error_code, "intent_changed")

    async def test_possible_input_rejection_never_replays(self):
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": [{"status": "uncertain"}]}})
        await self.submit(self.decision())
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertIn(101, self.loop._finished_ids)
        self.assertNotIn(101, self.loop._blocked_collect)

    async def test_temporary_rejection_only_recovers_when_discrete_condition_changes(self):
        from dataclasses import replace
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        await self.submit(self.decision())
        await self.loop._dispatch(self.loop._scheduler, self.source)
        # OD-52/R40: the deferred head no longer holds the slot while its discrete
        # condition is unchanged, so its sibling gets the turn instead.
        self.loop._pump_cohort(self.source)
        self.assertEqual([proposal.target["item_id"] for proposal in self.loop._scheduler.pending("collect")], [102])
        # Drain the siblings; each is rejected for the same reason, so once every
        # member is disproved nothing is proposed again (no repeated loop).
        for _ in range(2):
            await self.loop._dispatch(self.loop._scheduler, self.source)
            self.loop._pump_cohort(self.source)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())
        # A changed discrete condition lets the first member back into the slot.
        raw = deepcopy(self.source.all_state)
        raw["items"][0]["coordinate_interpretation"] = "unknown"
        changed = replace(self.source, all_state=raw)
        self.loop._pump_cohort(changed)
        self.assertEqual([proposal.target["item_id"] for proposal in self.loop._scheduler.pending("collect")], [101])

    async def test_cohort_expiry_and_stop_clear_pending_authorization(self):
        self.setup_runtime()
        await self.submit(self.decision())
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.now = 5.01
        self.loop._pump_cohort(self.source)
        self.assertEqual(self.loop._cohort, [])
        self.loop.stop_dispatch("paused")
        self.assertIsNone(self.loop._intent)
        self.assertFalse(self.loop._scheduler.has_pending())

    async def test_no_intent_allows_typed_local_fallback(self):
        from jev.strategy import evaluate_strategy
        self.setup_runtime()
        self.assertIsNone(self.loop._local_wait_reason("plant", self.source.jev_state, evaluate_strategy(self.source.jev_state), self.source.all_state))

    async def test_management_worker_remains_live_during_active_cohort(self):
        from jev.loop import _Attempt
        from dataclasses import replace
        from state.projection import project_jev_state
        self.setup_runtime()
        await self.submit(self.decision())
        answered = asyncio.Event()
        async def attempt(*args):
            answered.set()
            return _Attempt("model_wait", True, decision=self.decision(type_name="peashooter", affirmative=False))
        self.loop._attempt = attempt
        raw = deepcopy(self.source.all_state)
        raw["zombies"] = [{"type_code": 0, "type_name": "normal_zombie", "row": 0, "distance_to_house_cells": 3}]
        self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        task = asyncio.create_task(self.loop._branch_loop("collect", self.loop._store))
        try:
            await asyncio.wait_for(answered.wait(), 1)
            await asyncio.sleep(0)
            self.assertEqual(self.loop._intent["type_name"], "peashooter")
            self.assertEqual(len(self.loop._cohort), 3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_item_only_change_keeps_management_but_new_id_cannot_borrow_grant(self):
        from dataclasses import replace
        from state.projection import project_jev_state
        self.setup_runtime()
        def changed():
            raw = deepcopy(self.source.all_state)
            raw["items"] = [{**raw["items"][0], "id": 999}]
            self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        await self.submit(self.decision(), during=changed)
        self.assertEqual(self.loop._intent["type_name"], "sunflower")
        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(self.boundary.requests, [])

    async def test_ttl_does_not_mark_unstarted_member_finished(self):
        self.setup_runtime()
        await self.submit(self.decision())
        self.now = 5.01
        # Publish a fresh sample so the only failure is authorization age.
        from dataclasses import replace
        fresh = self.loop._store.publish(replace(self.source, observed_monotonic=self.now))
        await self.loop._dispatch(self.loop._scheduler, fresh)
        self.assertEqual(self.boundary.requests, [])
        self.assertNotIn(101, self.loop._finished_ids)

    async def test_in_flight_member_cannot_be_requeued(self):
        self.setup_runtime()
        await self.submit(self.decision())
        entered = threading.Event(); release = threading.Event()
        original = self.boundary.dispatch
        def gated(request, **kwargs):
            entered.set(); release.wait(1)
            return original(request, **kwargs)
        self.boundary.dispatch = gated
        task = asyncio.create_task(self.loop._dispatch(self.loop._scheduler, self.source))
        try:
            await asyncio.to_thread(entered.wait, 1)
            self.loop._pump_cohort(self.source)
            self.assertEqual(self.loop._scheduler.pending("collect"), ())
        finally:
            release.set()
            await task
        self.loop._pump_cohort(self.source)
        self.assertEqual(self.loop._scheduler.pending("collect")[0].target["item_id"], 102)


class ManagementAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    setup_runtime = SharedSourceLifecycleTests.setup_runtime
    decision = SharedSourceLifecycleTests.decision
    submit = SharedSourceLifecycleTests.submit
    async def test_model_can_wait_change_and_cancel_without_cheaper_substitute(self):
        from dataclasses import replace
        from jev.strategy import evaluate_strategy
        from state.projection import project_jev_state
        self.setup_runtime()
        raw = deepcopy(self.source.all_state)
        raw["cards"] = [PEASHOOTER_CARD, SUNFLOWER_CARD]
        raw["sun_balance"] = 75
        source = self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        self.source = source
        await self.submit(self.decision(type_name="peashooter", affirmative=False))
        self.assertEqual(self.loop._intent["type_name"], "peashooter")
        # Case A: the declared goal still needs 25 sun and no lane is close, so the
        # branch keeps saving instead of spending the 75 on a cheaper plant.
        self.assertEqual(self.loop._local_wait_reason("plant", source.jev_state, evaluate_strategy(source.jev_state), raw), "await_plan")
        self.assertEqual(self.boundary.requests, [])
        old_key = self.loop._branch_key("collect", source)
        raw = deepcopy(raw); raw["sun_balance"] = 100
        payable = replace(source, all_state=raw, jev_state=project_jev_state(raw))
        self.assertNotEqual(self.loop._branch_key("collect", payable), old_key)
        self.assertIsNone(self.loop._local_wait_reason("plant", payable.jev_state, evaluate_strategy(payable.jev_state), raw))
        await self.submit(self.decision(type_name="sunflower", affirmative=False))
        self.assertEqual(self.loop._intent["type_name"], "sunflower")
        await self.submit(self.decision(operation="cancel", affirmative=False))
        self.assertIsNone(self.loop._intent)

    async def test_case_a_a_goal_above_the_balance_saves_and_then_reopens_on_payment(self):
        from dataclasses import replace
        from jev.strategy import build_plant_candidates, evaluate_strategy
        from state.projection import project_jev_state
        self.setup_runtime()
        raw = deepcopy(self.source.all_state)
        raw["cards"] = [SUNFLOWER_CARD, PEASHOOTER_CARD, MELON_PULT_CARD]
        raw["sun_balance"] = 150
        source = self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        self.source = source
        await self.submit(self.decision(type_name="melon_pult", affirmative=False))
        self.assertEqual(self.loop._intent["type_name"], "melon_pult")
        signals = evaluate_strategy(source.jev_state)
        self.assertEqual(self.loop._local_wait_reason("plant", source.jev_state, signals, raw), "await_plan")
        self.assertEqual(build_plant_candidates(source.jev_state, signals, plan=self.loop._intent), [])
        self.assertEqual(self.boundary.requests, [])
        for sun, expected in ((150, set()), (320, {"melon_pult"}), (400, {"melon_pult", "sunflower", "peashooter"})):
            raw = deepcopy(raw); raw["sun_balance"] = sun
            sample = replace(source, all_state=raw, jev_state=project_jev_state(raw))
            offered = {
                entry["type_name"]
                for entry in build_plant_candidates(sample.jev_state, evaluate_strategy(sample.jev_state), plan=self.loop._intent)
            }
            self.assertEqual(offered, expected, sun)

    async def test_a_lane_that_cannot_stop_what_is_in_it_overrides_the_save(self):
        from dataclasses import replace
        from jev.strategy import build_plant_candidates, evaluate_strategy
        from state.projection import project_jev_state
        self.setup_runtime()
        raw = deepcopy(self.source.all_state)
        raw["cards"] = [SUNFLOWER_CARD, PEASHOOTER_CARD, MELON_PULT_CARD]
        raw["sun_balance"] = 150
        raw["zombies"] = [
            {"type_code": 0, "type_name": "normal_zombie", "row": 0, "distance_to_house_cells": 2}
        ]
        source = self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        self.source = source
        await self.submit(self.decision(type_name="melon_pult", affirmative=False))
        signals = evaluate_strategy(source.jev_state)
        self.assertEqual(signals.rows[0].urgency, "high")
        self.assertIsNone(self.loop._local_wait_reason("plant", source.jev_state, signals, raw))
        self.assertEqual(
            {entry["type_name"] for entry in build_plant_candidates(source.jev_state, signals, plan=self.loop._intent)},
            {"sunflower", "peashooter"},
        )

    async def test_case_b_an_abundant_balance_offers_the_high_cost_hand_under_a_cheap_goal(self):
        from dataclasses import replace
        from jev.strategy import evaluate_strategy
        from state.projection import project_jev_state
        self.setup_runtime()
        raw = deepcopy(self.source.all_state)
        raw["cards"] = [SUNFLOWER_CARD, PEASHOOTER_CARD, SNOW_PEA_CARD, MELON_PULT_CARD]
        raw["sun_balance"] = 8175
        source = self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        self.source = source
        await self.submit(self.decision(type_name="sunflower", affirmative=False))
        self.assertEqual(self.loop._intent["type_name"], "sunflower")
        signals = evaluate_strategy(source.jev_state)
        self.assertIsNone(self.loop._local_wait_reason("plant", source.jev_state, signals, raw))
        questions = build_plant_questions(source.jev_state, signals=signals, plan=self.loop._intent).questions
        self.assertIn("melon_pult@r0c0", questions[PLANT_TARGET_QUESTION_ID].criteria)
        self.assertIn("snow_pea@r0c0", questions[PLANT_TARGET_QUESTION_ID].criteria)

    async def test_a_target_outside_the_declared_goal_is_context_not_a_conflict(self):
        from dataclasses import replace
        from jev.strategy import evaluate_strategy
        from state.projection import project_jev_state
        self.setup_runtime()
        raw = deepcopy(self.source.all_state)
        raw["cards"] = [SUNFLOWER_CARD, MELON_PULT_CARD]
        raw["sun_balance"] = 500
        self.source = self.loop._store.publish(replace(self.source, all_state=raw, jev_state=project_jev_state(raw)))
        self.loop._intent = {"type_name": "sunflower"}
        decision = replace(
            self.decision(),
            intent="plant",
            effective_action="plant",
            target={"action": "place_plant", "type_name": "melon_pult", "row": 0, "col": 0},
            source_intent_version=0,
            source_intent=dict(self.loop._intent),
        )
        self.loop._propose("plant", self.source, (), evaluate_strategy(self.source.jev_state), decision, "2026-09-27T00:00:00Z")
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["action"] for request in self.boundary.requests], ["place_plant"])

    async def test_epoch_changed_shared_result_cannot_authorize_any_input(self):
        self.setup_runtime()
        await self.submit(self.decision(), during=lambda: self.loop.stop_dispatch("paused"))
        self.assertEqual(self.loop._cohort, [])
        self.assertIsNone(self.loop._intent)
        self.assertEqual(self.boundary.requests, [])


class LatestUnauthorizedBatchTests(unittest.IsolatedAsyncioTestCase):
    """V63/OD-48/R37 — one held collect batch, and no silent authorization loss."""

    setup_runtime = SharedSourceLifecycleTests.setup_runtime

    def source_with_ids(self, *ids):
        from dataclasses import replace
        from state.projection import project_jev_state
        raw = deepcopy(self.source.all_state)
        raw["items"] = [{**raw["items"][0], "id": identity} for identity in ids]
        self.source = self.loop._store.publish(
            replace(self.source, all_state=raw, jev_state=project_jev_state(raw))
        )
        return self.source

    def batch(self, *ids):
        targets = tuple(
            {"action": "collect_item", "item_id": identity, "type_code": 4, "type_name": "sun"}
            for identity in ids
        )
        return JevActionDecision(
            "collect", "collect", targets[0], {}, None, "selected", "offline", {}, 1, {}, cohort=targets
        )

    async def submit_batch(self, *ids):
        from jev.loop import _Attempt
        from jev.strategy import evaluate_strategy
        decision = self.batch(*ids)

        async def attempt(*args):
            return _Attempt("selected", True, decision=decision)

        self.loop._attempt = attempt
        key = self.loop._branch_key("collect", self.source)
        await self.loop._submit(
            "collect",
            self.loop._branches["collect"],
            self.loop._store,
            self.source,
            key,
            evaluate_strategy(self.source.jev_state),
        )

    def covered_source_cycles(self):
        return {
            record.source_cycle
            for record in self.records
            if record.outcome in {"executed", OUTCOME_DISCARDED}
        }

    def advance_to(self, now):
        """Move the frozen clock and republish the same sample as freshly observed."""
        from dataclasses import replace
        self.now = now
        self.source = self.loop._store.publish(replace(self.source, observed_monotonic=now))

    async def test_an_answer_arriving_during_an_active_batch_is_consumed_or_recorded(self):
        self.setup_runtime()
        self.source_with_ids(101, 102, 103, 104, 105)
        await self.submit_batch(101, 102, 103)
        self.assertEqual([target["item_id"] for target in self.loop._cohort], [101, 102, 103])

        # Both later answers arrive while the first batch is still being consumed.
        await self.submit_batch(104)
        self.assertEqual([target["item_id"] for target in self.loop._cohort_queue[0][0]], [104])
        await self.submit_batch(105)
        # OD-59: both later answers wait in arrival order; the older one is kept.
        self.assertEqual(
            [[target["item_id"] for target in batch[0]] for batch in self.loop._cohort_queue],
            [[104], [105]],
        )
        self.assertEqual(
            [record.error_code for record in self.records if record.error_code == BATCH_SUPERSEDED_BY_NEWER_BATCH],
            [],
        )
        # A new id never joins the batch that is already running.
        self.assertEqual([target["item_id"] for target in self.loop._cohort], [101, 102, 103])

        for _ in range(3):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual(self.loop._cohort, [])

        # The active batch is exhausted, so the queued batches start in arrival order.
        for _ in range(2):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102, 103, 104, 105])
        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(self.loop._cohort_queue, [])

        # Conservation: every affirmative decision has at least one downstream
        # action or recorded discard -- there is no third, silent outcome.
        selected = [record.cycle for record in self.records if record.outcome == "selected"]
        self.assertEqual(len(selected), 3)
        self.assertEqual(set(selected) - self.covered_source_cycles(), set())
        # Already consumed ids are never selected again.
        self.assertTrue({101, 102, 103, 105} <= self.loop._finished_ids)
        # Red line: a batch discard must not put an item id into any v2 event.
        from jev.trace import RuntimeEventBuilder
        builder = RuntimeEventBuilder(run_id="offline")
        events = [event for record in self.records for event in builder.events_for(record)]
        self.assertNotIn("item_id", json.dumps(events))

    async def test_a_held_batch_that_is_still_fresh_is_consumed_after_the_active_batch(self):
        self.setup_runtime()
        self.source_with_ids(101, 102, 103, 104)
        await self.submit_batch(101, 102, 103)
        self.advance_to(4.0)
        await self.submit_batch(104)  # accepted at t=4.0, while the first batch ran
        for _ in range(3):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual(self.loop._cohort, [])
        self.advance_to(4.9)  # 0.9 s after acceptance: still inside the OD-35 window
        self.loop._pump_cohort(self.source)
        self.assertEqual([target["item_id"] for target in self.loop._cohort], [104])
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102, 103, 104])

    async def test_a_held_batch_expires_five_seconds_after_acceptance_not_at_dequeue(self):
        self.setup_runtime()
        self.source_with_ids(101, 102, 103, 104)
        await self.submit_batch(101, 102, 103)
        self.advance_to(0.5)
        await self.submit_batch(104)  # accepted at t=0.5
        for _ in range(3):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual(self.loop._cohort, [])
        # Dequeued at t=5.6, i.e. 5.1 s after acceptance: the window is anchored on
        # acceptance, so the batch is dropped and recorded instead of being renewed.
        self.advance_to(0.5 + COHORT_AUTHORIZATION_SECONDS + 0.1)
        self.loop._pump_cohort(self.source)
        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(self.loop._cohort_queue, [])
        self.assertEqual(
            [record.error_code for record in self.records if record.error_code == BATCH_AUTHORIZATION_EXPIRED],
            [BATCH_AUTHORIZATION_EXPIRED],
        )
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102, 103])

    async def test_a_stop_clears_the_held_batch(self):
        self.setup_runtime()
        self.source_with_ids(101, 102, 103, 104)
        await self.submit_batch(101, 102, 103)
        await self.submit_batch(104)
        self.assertEqual(len(self.loop._cohort_queue), 1)
        self.loop.stop_dispatch("paused")
        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(self.loop._cohort_queue, [])
        self.assertIsNone(self.loop._cohort_source)


class CohortMemberLedgerTests(unittest.IsolatedAsyncioTestCase):
    """V65/V66/V67 (OD-51-OD-53, R39-R41): no authorized member disappears.

    A collect batch is the only place where one decision authorizes several
    actions; these checks pin that every authorized member ends as ``executed``
    or ``discarded(reason)`` (including across the stop gate), that a deferred
    member never starves its siblings or loops, and that the record of an
    unexecutable member says why and where without ever naming its id.
    """

    setup_runtime = SharedSourceLifecycleTests.setup_runtime

    def publish_items(self, items, *, availability=None):
        from dataclasses import replace
        from state.projection import project_jev_state
        raw = deepcopy(self.source.all_state)
        raw["items"] = [{"id": identity, **dict(entry)} for identity, entry in items]
        if availability is not None:
            raw["availability"] = {**raw.get("availability", {}), **availability}
        self.source = self.loop._store.publish(
            replace(self.source, all_state=raw, jev_state=project_jev_state(raw), observed_monotonic=self.now)
        )
        return self.source

    def sun_items(self, *ids):
        return [(identity, dict(SUN_ITEM_ADDRESSED)) for identity in ids]

    def batch(self, *ids):
        targets = tuple(
            {"action": "collect_item", "item_id": identity, "type_code": 4, "type_name": "sun"}
            for identity in ids
        )
        return JevActionDecision("collect", "collect", targets[0], {}, None, "selected", "offline", {}, 1, {}, cohort=targets)

    async def submit_batch(self, *ids):
        from jev.loop import _Attempt
        from jev.strategy import evaluate_strategy
        decision = self.batch(*ids)

        async def attempt(*args):
            return _Attempt("selected", True, decision=decision)

        self.loop._attempt = attempt
        key = self.loop._branch_key("collect", self.source)
        await self.loop._submit(
            "collect",
            self.loop._branches["collect"],
            self.loop._store,
            self.source,
            key,
            evaluate_strategy(self.source.jev_state),
        )

    def ledger(self, reason):
        return [record for record in self.records if record.outcome == OUTCOME_DISCARDED and record.error_code == reason]

    def confirmed_executions(self):
        """Collect actions the Boundary confirmed, i.e. the members that really ran.

        A member the Boundary rejected without sending input is dispatched too, but
        it stays deferred in the batch and is only terminal when the batch records
        it as discarded, so counting it here would double-count it.
        """
        confirmed = []
        for record in self.records:
            if record.outcome != "executed" or record.branch != "collect":
                continue
            result = record.boundary_result
            status = result.get("status") if isinstance(result, Mapping) else getattr(result, "status", None)
            if status == "success":
                confirmed.append(record)
        return confirmed

    def advance_to(self, now):
        from dataclasses import replace
        self.now = now
        self.source = self.loop._store.publish(replace(self.source, observed_monotonic=now))

    # ------------------------------------------------------------------ V65

    async def test_a_batch_past_its_window_records_every_unrun_member(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102, 103)
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.advance_to(COHORT_AUTHORIZATION_SECONDS + 0.1)
        self.loop._pump_cohort(self.source)

        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(len(self.ledger(COHORT_AUTHORIZATION_EXPIRED)), 2)
        self.assertEqual(len(self.confirmed_executions()), 1)
        # Conservation: 3 authorized = 1 executed + 2 discarded + nothing left over.
        self.assertEqual(3, len(self.confirmed_executions()) + len(self.ledger(COHORT_AUTHORIZATION_EXPIRED)) + len(self.loop._cohort))

    async def test_newer_answers_queue_behind_the_running_batch_instead_of_replacing_it(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103, 104, 105, 106))
        await self.submit_batch(101, 102, 103)
        await self.submit_batch(104, 105)
        await self.submit_batch(106)

        # OD-59: every answer waits in arrival order and nothing is replaced, so the
        # six authorized members are all still accounted for.
        self.assertEqual(
            [[target["item_id"] for target in batch[0]] for batch in self.loop._cohort_queue],
            [[104, 105], [106]],
        )
        self.assertEqual(self.ledger(BATCH_SUPERSEDED_BY_NEWER_BATCH), [])
        self.assertEqual(len(self.confirmed_executions()), 0)
        self.assertEqual(6, len(self.loop._cohort) + sum(len(batch[0]) for batch in self.loop._cohort_queue))

    async def test_a_member_already_pending_is_recorded_instead_of_dispatched_twice(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102)
        # The same id arrives again while 101/102 are still pending: the repeat is a
        # recorded discard, and only the genuinely new member joins the batch.
        await self.submit_batch(102, 103)

        duplicates = self.ledger(COHORT_MEMBER_ALREADY_PENDING)
        self.assertEqual([record.cycle for record in duplicates], [duplicates[0].cycle])
        self.assertEqual(len(duplicates), 1)
        self.assertEqual([target["item_id"] for target in self.loop._cohort], [101, 102])
        self.assertEqual([target["item_id"] for target in self.loop._cohort_queue[0][0]], [103])

    async def test_a_fourth_queued_batch_is_recorded_as_queue_overflow(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103, 104, 105, 106, 107))
        await self.submit_batch(101, 102, 103)
        for member in (104, 105, 106, 107):
            await self.submit_batch(member)

        # OD-59: the queue is bounded, and the batch pushed past the limit is
        # recorded rather than silently dropped.
        self.assertEqual(len(self.loop._cohort_queue), COHORT_QUEUE_LIMIT)
        overflow = self.ledger(BATCH_QUEUE_OVERFLOW)
        self.assertEqual(len(overflow), 1)
        self.assertEqual(7, len(self.confirmed_executions()) + len(overflow) + len(self.loop._cohort) + sum(len(batch[0]) for batch in self.loop._cohort_queue))

    async def test_a_member_whose_id_leaves_all_state_is_recorded(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102, 103)
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.publish_items(self.sun_items(101, 103))
        self.loop._pump_cohort(self.source)

        self.assertEqual(len(self.ledger(COHORT_MEMBER_ID_GONE)), 1)
        self.assertEqual([target["item_id"] for target in self.loop._cohort], [103])
        self.assertEqual(3, len(self.confirmed_executions()) + len(self.ledger(COHORT_MEMBER_ID_GONE)) + len(self.loop._cohort))

    async def test_the_stop_gate_records_both_unrun_batches_before_it_clears_them(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103, 104))
        await self.submit_batch(101, 102, 103)
        await self.submit_batch(104)
        self.loop.stop_dispatch("paused")

        self.assertEqual(self.loop._cohort, [])
        self.assertEqual(self.loop._cohort_queue, [])
        stopped = self.ledger(COHORT_STOPPED_BEFORE_EXECUTION)
        self.assertEqual(len(stopped), 4)
        self.assertTrue(all(record.boundary_result is None for record in stopped))
        self.assertEqual(4, len(self.confirmed_executions()) + len(stopped) + len(self.loop._cohort))
        # The synchronous stop records once and only once.
        self.loop.stop_dispatch("paused")
        self.assertEqual(len(self.ledger(COHORT_STOPPED_BEFORE_EXECUTION)), 4)

    async def test_a_stop_during_an_in_flight_member_records_it_exactly_once(self):
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102))
        await self.submit_batch(101, 102)
        entered = threading.Event()
        release = threading.Event()
        original = self.boundary.dispatch

        def gated(request, **kwargs):
            entered.set()
            release.wait(1)
            return original(request, **kwargs)

        self.boundary.dispatch = gated
        task = asyncio.create_task(self.loop._dispatch(self.loop._scheduler, self.source))
        try:
            await asyncio.to_thread(entered.wait, 1)
            self.loop.stop_dispatch("paused")
        finally:
            release.set()
            await task

        # A stop never preempts the action already in flight (OD-24), so 101 is
        # terminal through its own execution record and only the unrun 102 is
        # recorded as stopped; no member is accounted for twice.
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101])
        self.assertEqual(len(self.confirmed_executions()), 1)
        self.assertEqual(len(self.ledger(COHORT_STOPPED_BEFORE_EXECUTION)), 1)

    async def test_members_deferred_until_the_batch_ends_are_recorded_as_never_executable(self):
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102, 103)
        for _ in range(3):
            await self.loop._dispatch(self.loop._scheduler, self.source)
            self.loop._pump_cohort(self.source)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())
        self.advance_to(COHORT_AUTHORIZATION_SECONDS + 0.1)
        self.loop._pump_cohort(self.source)

        deferred = self.ledger(COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE)
        self.assertEqual(len(deferred), 3)
        self.assertEqual(self.ledger(COHORT_AUTHORIZATION_EXPIRED), [])
        self.assertEqual(3, len(self.confirmed_executions()) + len(deferred) + len(self.loop._cohort))

    # ------------------------------------------------------------------ V66

    async def test_a_deferred_head_does_not_starve_its_sibling(self):
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        self.publish_items(self.sun_items(101, 102))
        await self.submit_batch(101, 102)
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertIn(101, self.loop._blocked_collect)
        self.loop._pump_cohort(self.source)

        self.assertEqual([proposal.target["item_id"] for proposal in self.loop._scheduler.pending("collect")], [102])
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102])

    async def test_a_deferred_member_is_not_retried_while_its_condition_is_unchanged(self):
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102, 103)
        for _ in range(3):
            await self.loop._dispatch(self.loop._scheduler, self.source)
            self.loop._pump_cohort(self.source)
        dispatched = len(self.boundary.requests)
        for _ in range(5):
            self.loop._pump_cohort(self.source)
        self.assertEqual(len(self.boundary.requests), dispatched)
        self.assertEqual(self.loop._scheduler.pending("collect"), ())

    async def test_a_deferred_member_is_retried_once_its_discrete_condition_changes(self):
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        self.publish_items(self.sun_items(101, 102))
        await self.submit_batch(101, 102)
        await self.loop._dispatch(self.loop._scheduler, self.source)
        await self.loop._dispatch(self.loop._scheduler, self.source)

        # An item behind the seed-bar UI (y < 80) is outside the click region.
        outside = {**SUN_ITEM_ADDRESSED, "x": 100.0, "y": 20.0}
        self.publish_items([(101, outside), (102, dict(outside))])
        self.loop._pump_cohort(self.source)
        self.assertEqual([proposal.target["item_id"] for proposal in self.loop._scheduler.pending("collect")], [101])

    # ------------------------------------------------------------------ V69

    async def test_a_batch_whose_members_are_all_finished_is_recorded_once(self):
        from jev.trace import RuntimeEventBuilder
        self.setup_runtime()
        self.publish_items(self.sun_items(101, 102, 103))
        await self.submit_batch(101, 102, 103)
        for _ in range(3):
            self.loop._pump_cohort(self.source)
            await self.loop._dispatch(self.loop._scheduler, self.source)
        self.assertEqual([request["item_id"] for request in self.boundary.requests], [101, 102, 103])
        self.assertEqual(self.loop._finished_ids, {101, 102, 103})
        self.assertEqual(self.loop._cohort, [])

        # A second affirmative answer for the same, still visible items authorizes
        # nobody: the filter empties it, and that batch end is recorded instead of
        # being dropped in silence (OD-55/R44).
        await self.submit_batch(101, 102, 103)
        all_finished = self.ledger(COHORT_MEMBERS_ALL_FINISHED)
        self.assertEqual(len(all_finished), 1)
        self.assertEqual(all_finished[0].branch, "collect")
        self.assertIsNone(all_finished[0].boundary_result)
        self.assertEqual(len(self.boundary.requests), 3)
        self.assertEqual(self.loop._cohort, [])

        # Conservation: every affirmative answer is covered by an executed or a
        # discarded record, the emptied batch included.
        covered = {
            record.source_cycle
            for record in self.records
            if record.outcome in {"executed", OUTCOME_DISCARDED}
        }
        selected = {record.cycle for record in self.records if record.outcome == "selected"}
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected - covered, set())

        # Red line: the record of the emptied batch never names an item.
        builder = RuntimeEventBuilder(run_id="offline")
        events = [event for record in self.records for event in builder.events_for(record)]
        recorded = [
            event for event in events if event.get("discard_reason") == COHORT_MEMBERS_ALL_FINISHED
        ]
        self.assertEqual(len(recorded), 1)
        self.assertNotIn("item_id", json.dumps(events))

    # ------------------------------------------------------------------ V67

    async def test_member_evidence_maps_each_reason_category_with_the_items_coordinates(self):
        cases = [
            (COLLECT_REASON_OUTSIDE_REGION, {**SUN_ITEM_ADDRESSED, "x": 100.0, "y": 20.0}, None, 100.0, 20.0),
            (COLLECT_REASON_NOT_FINITE, {**SUN_ITEM_ADDRESSED, "y": float("inf")}, None, 100.0, None),
            (COLLECT_REASON_UNRESOLVED_INTERPRETATION, {**SUN_ITEM_ADDRESSED, "coordinate_interpretation": "unknown"}, None, 100.0, 200.0),
            (COLLECT_REASON_ITEMS_UNAVAILABLE, dict(SUN_ITEM_ADDRESSED), {"items": "unavailable"}, 100.0, 200.0),
        ]
        for category, item, availability, expected_x, expected_y in cases:
            with self.subTest(category=category):
                self.setup_runtime()
                self.publish_items([(101, item)], availability=availability)
                evidence = self.loop._member_evidence(self.source, 101)
                self.assertEqual(evidence, {"reason_category": category, "client_x": expected_x, "client_y": expected_y})
        # An executable member has no fact to blame, so its category is empty and
        # the batch-end reason stands on its own.
        self.setup_runtime()
        self.publish_items([(101, dict(SUN_ITEM_ADDRESSED))])
        self.assertEqual(
            self.loop._member_evidence(self.source, 101),
            {"reason_category": None, "client_x": 100.0, "client_y": 200.0},
        )

    async def test_a_deferred_member_record_carries_the_evidence_without_any_item_id(self):
        from jev.trace import RuntimeEventBuilder
        self.setup_runtime(result={"status": "rejected", "details": {"input_clicks": []}})
        self.publish_items([(101, {**SUN_ITEM_ADDRESSED, "x": 100.0, "y": 20.0})])
        await self.submit_batch(101)
        await self.loop._dispatch(self.loop._scheduler, self.source)
        self.advance_to(COHORT_AUTHORIZATION_SECONDS + 0.1)
        self.loop._pump_cohort(self.source)

        record = self.ledger(COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE)[0]
        self.assertEqual(
            record.evidence,
            {"reason_category": COLLECT_REASON_OUTSIDE_REGION, "client_x": 100.0, "client_y": 20.0},
        )
        builder = RuntimeEventBuilder(run_id="offline")
        events = [event for one in self.records for event in builder.events_for(one)]
        discarded = [
            event
            for event in events
            if event["event"] == "proposal_discarded" and event["discard_reason"] == COHORT_MEMBER_DEFERRED_NEVER_EXECUTABLE
        ]
        self.assertEqual(
            discarded[0]["evidence"],
            {"reason_category": COLLECT_REASON_OUTSIDE_REGION, "client_x": 100.0, "client_y": 20.0},
        )
        text = json.dumps(events)
        self.assertNotIn("item_id", text)
        self.assertNotIn('"id"', text)
