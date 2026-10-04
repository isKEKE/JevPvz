import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from configs.plant_catalog import plant_info
from jev.client import build_typesafe_state
from jev.decision import JevActionDecision, JevRouterDecision
from jev.loop import JevRuntimeCycle
from jev.questions import (
    COLLECT_STATE_FIELDS,
    DISCARD_OPTION_ID,
    PLANT_STATE_FIELDS,
    PLANT_TARGET_QUESTION_ID,
    SHOVEL_TARGET_QUESTION_ID,
    shovel_option_id,
)
from jev.strategy import BRANCH_PLANT, evaluate_strategy
from jev.trace import (
    DISCARDED_OUTCOME,
    EVENT_ACTION_RESULT,
    EVENT_JOB_END,
    EVENT_JOB_START,
    EVENT_PROPOSAL_DISCARDED,
    EVENT_REQUEST_RESULT,
    EVENT_RUNTIME_STOP,
    EXECUTION_OUTCOMES,
    RUNTIME_EVENT_NAMES,
    SCHEMA_VERSION_V2,
    RuntimeEventBuilder,
    TraceRecorder,
    TraceWriteError,
    build_trace_event,
    summarize_jev_state,
    trace_schema_version,
)


def trace_jev_state(sequence=7):
    return {
        "schema_version": 1,
        "sample_sequence": sequence,
        "observed_at_utc": f"2026-09-27T00:00:{sequence:02d}.000Z",
        "status": "ok",
        "valid": True,
        "decision_ready": True,
        "game": {"phase": "playing", "mode": "adventure", "background": "day", "paused": False, "level": "1-1", "wave": 1},
        "sun_balance": 75,
        "board": {"rows": 5, "cols": 9, "cells": [[None] * 9 for _ in range(5)]},
        "plants": [],
        "zombies": [{"type_code": 0, "type_name": "normal_zombie", "row": 2, "hp": 270, "distance_to_house_cells": 5}],
        "lanes": [{"row": row, "zombie_count": 0, "nearest_zombie_distance_to_house_cells": None} for row in range(5)],
        "items": [{"type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0}],
        "cards": [{"slot": 0, "type_code": 0, "type_name": "peashooter", "usable": True}],
        "raw_snapshot": {"secret": "raw-secret-sentinel"},
        "availability": {"secret": "diagnostic-sentinel"},
    }


def trace_all_state(sequence=8):
    return {
        "schema_version": 1,
        "sample_sequence": sequence,
        "observed_at_utc": f"2026-09-27T00:01:{sequence:02d}.000Z",
        "status": "ok",
        "valid": True,
        "decision_ready": True,
        "source": {"pid": 4242, "root_address": "0xSECRET", "exe_sha256": "sha-secret-sentinel"},
        "raw_snapshot": {"api_key": "api-key-sentinel", "memory": "raw-secret-sentinel"},
        "availability": {"board.occupancy": "provisional"},
        "game": {"phase": "playing", "mode": "adventure", "background": "day", "paused": False, "level": "1-1", "wave": 2},
        "sun_balance": 100,
        "board": {
            "rows": 5,
            "cols": 9,
            "cells": [[None] * 9 for _ in range(5)],
            "plantability": [["unknown"] * 9 for _ in range(5)],
        },
        "plants": [],
        "zombies": [],
        "lanes": [],
        "items": [],
        "cards": [],
    }


def sample_cycle():
    router = JevRouterDecision(
        noul_probabilities={"collect": 0.2, "plant": 0.84, "shovel": 0.1},
        candidates=("plant",),
        choice="plant",
        confidence=0.84,
        probabilities={"wait": 0.05, "collect": 0.05, "plant": 0.84, "shovel": 0.06},
        effective_action="plant",
        fallback_reason=None,
        model="jev-latest",
        usage={"input_tokens": 120, "output_tokens": 24},
        latency_ms=145,
        question_summary={"next_action": {"type": "choice", "criteria": {"wait": "Wait", "plant": "Plant"}}},
        noul_candidate_threshold=0.73,
        confidence_threshold=0.52,
    )
    action = JevActionDecision(
        intent="plant",
        effective_action="plant",
        target={"action": "place_plant", "type_name": "peashooter", "row": 2, "col": 4},
        answers={
            "plant_type": {"choice": "peashooter", "confidence": 0.89, "probabilities": {"peashooter": 1.0}},
            "cell": {"choice": "r2c4", "confidence": 0.78, "probabilities": {"r2c4": 1.0}},
        },
        fallback_reason=None,
        status="selected",
        model="jev-latest",
        usage={"input_tokens": 80, "output_tokens": 16},
        latency_ms=90,
        question_summary={
            "plant_type": {"type": "choice", "criteria": {"peashooter": "Fires peas in a straight line."}},
            "cell": {"type": "choice", "criteria": {"r2c4": "Empty cell."}},
        },
        confidence_threshold=0.81,
    )
    return JevRuntimeCycle(
        cycle=1,
        sample_sequence=7,
        started_at_utc="2026-09-27T00:00:07.000Z",
        finished_at_utc="2026-09-27T00:00:07.235Z",
        outcome="action_success",
        effective_action="plant",
        all_state={"source": {"pid": 4242, "address": "0xSECRET"}, "raw_snapshot": {"api_key": "api-key-sentinel"}},
        jev_state=trace_jev_state(),
        router=router,
        action=action,
        boundary_result={
            "status": "success",
            "action": "place_plant",
            "elapsed_ms": 100,
            "request": {"private": "request-secret-sentinel"},
            "target": {"plant_id": 123456},
        },
        next_observation=trace_all_state(),
    )


RUNTIME_SEQUENCE = 12

_SENTINEL_ALL_STATE = {
    "source": {"pid": 4242, "root_address": "0xSECRET", "exe_sha256": "sha-secret-sentinel"},
    "raw_snapshot": {"api_key": "api-key-sentinel", "memory": "raw-secret-sentinel"},
    "availability": {"board.occupancy": "provisional", "secret": "diagnostic-sentinel"},
}


def _utc(offset_ms: int) -> str:
    base = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(milliseconds=offset_ms)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def runtime_jev_state(sequence: int = RUNTIME_SEQUENCE) -> dict:
    state = trace_jev_state(sequence)
    state["sun_balance"] = 75
    state["cards"] = [
        {"slot": 0, "type_code": 0, "type_name": "sunflower", "usable": True, "cooldown_ready": True, "cost": 50},
        {"slot": 1, "type_code": 1, "type_name": "peashooter", "usable": True, "cooldown_ready": True, "cost": 100},
    ]
    return state


def runtime_plant_cycle(*, cycle=1, start_ms=0, finish_ms=500, latency_ms=210, reranked=False):
    chosen = "peashooter@r2c4"
    selected = "peashooter@r1c0" if reranked else chosen
    merge = {
        "target_choice_rule": "argmax",
        "chosen_option": chosen,
        "selected_option": selected,
        "reranked": reranked,
        "best_available_probability": 0.31 if reranked else 0.36,
        "best_option": chosen,
        "best_probability": 0.36,
        "discard_probability": 0.33,
        "margin": 0.03,
        "confidence": 0.04,
        "status": "selected",
        "fallback_reason": None,
    }
    if reranked:
        merge["rejected_option"] = chosen
        merge["rejected_row"] = 2
    answers = {
        "row_needs_response_r0": {"noul": 0.05},
        "row_needs_response_r1": {"noul": 0.72},
        "row_needs_response_r2": {"noul": 0.91},
        "row_needs_response_r3": {"noul": 0.3},
        "row_needs_response_r4": {"noul": 0.1},
        "plant_target": {
            "choice": chosen,
            "confidence": 0.04,
            "probabilities": {chosen: 0.36, "peashooter@r1c0": 0.31, "none_of_the_above": 0.33},
            "level": 1,
        },
        "merge": merge,
    }
    decision = JevActionDecision(
        intent="plant",
        effective_action="plant",
        target={"action": "place_plant", "type_name": "peashooter", "row": 1 if reranked else 2, "col": 0 if reranked else 4},
        answers=answers,
        fallback_reason=None,
        status="selected",
        model="jev-latest",
        usage={"input_tokens": 800, "output_tokens": 40},
        latency_ms=latency_ms,
        question_summary={"plant_target": {"type": "choice", "criteria": {chosen: "Empty cell."}}},
        # The historical P02 field: schema 2 must never present it as the gate.
        confidence_threshold=0.99,
    )
    return JevRuntimeCycle(
        cycle=cycle,
        sample_sequence=RUNTIME_SEQUENCE,
        started_at_utc=_utc(start_ms),
        finished_at_utc=_utc(finish_ms),
        outcome="selected",
        effective_action="plant",
        all_state=dict(_SENTINEL_ALL_STATE),
        jev_state=runtime_jev_state(),
        action=decision,
        boundary_result=None,
        branch="plant",
    )


def runtime_collect_cycle(*, cycle=1, start_ms=100, finish_ms=600, latency_ms=140):
    decision = JevActionDecision(
        intent="collect",
        effective_action="collect",
        target={"action": "collect_item", "type_code": 4, "type_name": "sun", "x": 100.0, "y": 200.0},
        answers={
            "should_collect_now": {"noul": 0.93},
            "collect_target": {
                "choice": "item_0",
                "confidence": 0.52,
                "probabilities": {"item_0": 0.52, "none_of_the_above": 0.48},
                "level": 1,
            },
            "merge": {
                "should_collect_probability": 0.93,
                "noul_candidate_threshold": 0.6,
                "target_choice_rule": "argmax",
                "discard_option": "none_of_the_above",
                "chosen_option": "item_0",
                "confidence": 0.52,
                "status": "selected",
                "fallback_reason": None,
            },
        },
        fallback_reason=None,
        status="selected",
        model="jev-latest",
        usage={"input_tokens": 300, "output_tokens": 12},
        latency_ms=latency_ms,
        question_summary={},
        confidence_threshold=0.99,
    )
    return JevRuntimeCycle(
        cycle=cycle,
        sample_sequence=RUNTIME_SEQUENCE,
        started_at_utc=_utc(start_ms),
        finished_at_utc=_utc(finish_ms),
        outcome="selected",
        effective_action="collect",
        all_state=dict(_SENTINEL_ALL_STATE),
        jev_state=runtime_jev_state(),
        action=decision,
        boundary_result=None,
        branch="collect",
    )


def runtime_execution_cycle(
    *,
    branch,
    cycle=1,
    start_ms=0,
    finish_ms=50,
    action="collect_item",
    outcome="executed",
    error_code=None,
    evidence=None,
):
    boundary = None
    if outcome == "executed":
        boundary = {
            "status": "success",
            "action": action,
            "elapsed_ms": 30 if action == "collect_item" else 120,
            "request": {"private": "request-secret-sentinel"},
            "target": {"plant_id": 123456},
        }
    return JevRuntimeCycle(
        cycle=cycle,
        sample_sequence=RUNTIME_SEQUENCE,
        started_at_utc=_utc(start_ms),
        finished_at_utc=_utc(finish_ms),
        outcome=outcome,
        effective_action="collect" if branch == "collect" else "plant",
        all_state=dict(_SENTINEL_ALL_STATE),
        jev_state=runtime_jev_state(),
        action=None,
        boundary_result=boundary,
        error_code=error_code,
        branch=branch,
        evidence=evidence,
    )


def runtime_branch_cycle_without_answer(
    *,
    outcome,
    cycle=1,
    error_code=None,
    branch="collect",
    start_ms=1000,
    finish_ms=1010,
):
    return JevRuntimeCycle(
        cycle=cycle,
        sample_sequence=RUNTIME_SEQUENCE,
        started_at_utc=_utc(start_ms),
        finished_at_utc=_utc(finish_ms),
        outcome=outcome,
        effective_action="wait",
        all_state=dict(_SENTINEL_ALL_STATE),
        jev_state=runtime_jev_state(),
        action=None,
        boundary_result=None,
        error_code=error_code,
        branch=branch,
    )


def runtime_stop_cycle(*, cycle=1, at_ms=0, outcome="max_cycles"):
    return JevRuntimeCycle(
        cycle=cycle,
        sample_sequence=RUNTIME_SEQUENCE,
        started_at_utc=_utc(at_ms),
        finished_at_utc=_utc(at_ms),
        outcome=outcome,
        effective_action="wait",
        all_state=dict(_SENTINEL_ALL_STATE),
        jev_state=runtime_jev_state(),
    )


class JevTraceTests(unittest.TestCase):
    def test_cycle_event_records_actual_router_action_boundary_and_next_observation(self):
        event = build_trace_event(sample_cycle(), run_id="run-001")
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["run_id"], "run-001")
        self.assertEqual(event["sample_sequence"], 7)
        self.assertEqual(event["router"]["response"]["noul_probabilities"]["plant"], 0.84)
        self.assertEqual(event["router"]["response"]["noul_candidate_threshold"], 0.73)
        self.assertEqual(event["router"]["response"]["confidence_threshold"], 0.52)
        self.assertEqual(event["router"]["response"]["choice"], "plant")
        self.assertEqual(event["action"]["confidence_threshold"], 0.81)
        self.assertEqual(event["action"]["target"], {"action": "place_plant", "type_name": "peashooter", "row": 2, "col": 4})
        self.assertEqual(event["boundary"], {"status": "success", "action": "place_plant", "elapsed_ms": 100})
        self.assertEqual(event["next_observation"]["sample_sequence"], 8)
        self.assertEqual(event["catalog_context"]["zombie_abilities"][0]["type_name"], "normal_zombie")
        self.assertEqual(
            event["action"]["request"]["questions"]["plant_type"]["criteria"]["peashooter"],
            "Fires peas in a straight line.",
        )

    def test_event_summaries_exclude_secrets_raw_state_and_internal_ids(self):
        event_text = json.dumps(build_trace_event(sample_cycle(), run_id="run-002"), ensure_ascii=False)
        for secret in ("api-key-sentinel", "raw-secret-sentinel", "diagnostic-sentinel", "request-secret-sentinel", "sha-secret-sentinel", "0xSECRET", "plant_id", "4242"):
            self.assertNotIn(secret, event_text)
        self.assertNotIn("raw_snapshot", event_text)
        self.assertNotIn("availability", event_text)
        self.assertNotIn("source", event_text)

    def test_state_summary_is_bounded_and_preserves_review_fields(self):
        summary = summarize_jev_state(trace_jev_state())
        self.assertEqual(summary["sample_sequence"], 7)
        self.assertEqual(summary["counts"]["zombies"], 1)
        self.assertEqual(summary["usable_plant_types"], ["peashooter"])
        self.assertEqual(summary["zombie_types"], [{"type_name": "normal_zombie", "count": 1}])
        self.assertNotIn("zombies", summary)
        self.assertNotIn("items", summary)

    def test_wait_not_ready_api_error_boundary_reject_and_stop_do_not_invent_stages(self):
        base = sample_cycle()
        cases = (
            (replace(base, cycle=2, outcome="wait", effective_action="wait", action=None, boundary_result=None), "wait", True, False),
            (replace(base, cycle=3, outcome="not_ready", effective_action="wait", jev_state=None, router=None, action=None, boundary_result=None), "not_ready", False, False),
            (replace(base, cycle=4, outcome="api_error", effective_action="wait", action=None, boundary_result=None, error_code="JevApiError"), "api_error", True, False),
            (replace(base, cycle=5, outcome="boundary_rejected", effective_action="wait", boundary_result={"status": "rejected", "action": "place_plant"}), "boundary_rejected", True, True),
            (replace(base, cycle=6, outcome="process_disconnected", effective_action="wait", jev_state=None, router=None, action=None, boundary_result=None), "process_disconnected", False, False),
        )
        for cycle, expected_outcome, has_router, has_boundary in cases:
            event = build_trace_event(cycle, run_id="run-paths")
            self.assertEqual(event["outcome"], expected_outcome)
            self.assertEqual(event["router"] is not None, has_router)
            self.assertEqual(event["boundary"] is not None, has_boundary)
            if not has_boundary:
                self.assertIsNone(event["boundary"])

    def test_recorder_replaces_existing_trace_and_writes_a_fresh_jsonl_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            old_event = build_trace_event(sample_cycle(), run_id="run-old")
            with TraceRecorder(path) as recorder:
                recorder.write_event(old_event)
                self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text(encoding="utf-8").splitlines()[0]), old_event)
            new_event = build_trace_event(sample_cycle(), run_id="run-new")
            with TraceRecorder(path) as recorder:
                recorder.write_event(new_event)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0]), new_event)
            self.assertNotIn("run-old", lines[0])

    def test_recorder_refuses_to_replace_a_non_trace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "important.jsonl"
            existing = "user content that is not a JEV trace\n"
            path.write_text(existing, encoding="utf-8")
            with self.assertRaisesRegex(TraceWriteError, "not a recognizable JEV Trace"):
                TraceRecorder(path)
            self.assertEqual(path.read_text(encoding="utf-8"), existing)
            with self.assertRaisesRegex(TraceWriteError, "not a regular file"):
                TraceRecorder(Path(directory))

    def test_recorder_rejects_non_json_event_without_writing_partial_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with TraceRecorder(path) as recorder:
                with self.assertRaises(TraceWriteError):
                    recorder.write_event({"bad": {1, 2, 3}})
                self.assertEqual(path.read_bytes(), b"")


class RuntimeTraceV2Tests(unittest.TestCase):
    """Schema-2 events: causality, bounded fields, and no invented thresholds."""

    def setUp(self):
        self.builder = RuntimeEventBuilder(run_id="run-v2")

    def emit(self, cycle):
        return self.builder.events_for(cycle)

    def test_one_plant_request_becomes_causal_events_with_atomic_answers_and_merge(self):
        events = self.emit(runtime_plant_cycle())
        self.assertEqual(
            [event["event"] for event in events],
            [EVENT_JOB_START, EVENT_REQUEST_RESULT, EVENT_JOB_END],
        )
        self.assertEqual([event["event_sequence"] for event in events], [1, 2, 3])
        self.assertEqual({event["run_id"] for event in events}, {"run-v2"})
        self.assertEqual({event["job_id"] for event in events}, {"job-000001"})
        self.assertEqual({event["branch_id"] for event in events}, {"plant"})
        self.assertEqual({event["stage_id"] for event in events}, {"plant-decision"})
        self.assertTrue({event["event"] for event in events} <= RUNTIME_EVENT_NAMES)
        self.assertEqual(events[1]["request_id"], "job-000001-request-1")
        self.assertIsNone(events[0]["request_id"])
        self.assertIsNone(events[1]["execution_id"])

        start, request, end = events
        self.assertEqual(start["sample_sequence"], RUNTIME_SEQUENCE)
        self.assertEqual(start["sample_age_ms"], 290)
        self.assertEqual(start["elapsed_ms"], 500)
        self.assertIs(start["request_issued"], True)
        self.assertEqual(request["latency_ms"], 210)
        self.assertEqual(request["usage"], {"input_tokens": 800, "output_tokens": 40})
        self.assertEqual(request["model"], "jev-latest")
        self.assertIsNone(request["noul_candidate_threshold"])
        self.assertEqual(request["target_choice_rule"], "argmax")
        self.assertEqual(end["outcome"], "selected")
        self.assertIs(end["reliable"], True)

        answers = request["typed_answers"]
        self.assertEqual(
            sorted(answers),
            [
                "plant_target",
                "row_needs_response_r0",
                "row_needs_response_r1",
                "row_needs_response_r2",
                "row_needs_response_r3",
                "row_needs_response_r4",
            ],
        )
        self.assertEqual(answers["row_needs_response_r2"], {"noul": 0.91})
        self.assertEqual(answers["plant_target"]["confidence"], 0.04)
        self.assertNotIn("merge", answers)
        self.assertEqual(request["merge"]["best_option"], "peashooter@r2c4")
        self.assertEqual(request["merge"]["best_probability"], 0.36)
        self.assertEqual(request["merge"]["discard_probability"], 0.33)
        self.assertEqual(request["merge"]["margin"], 0.03)
        for key in (
            "best_option",
            "best_probability",
            "discard_probability",
            "margin",
            "chosen_option",
            "selected_option",
            "reranked",
            "rejected_option",
            "target_choice_rule",
        ):
            self.assertIn(key, request["merge"])

    def test_events_are_bounded_per_job_and_never_carry_raw_state_or_credentials(self):
        events = self.emit(runtime_plant_cycle())
        # One decision job writes a bounded start/result/end group, never one
        # record per observation.
        self.assertLessEqual(len(events), 3)
        text = json.dumps(events, ensure_ascii=False)
        for secret in (
            "raw-secret-sentinel",
            "api-key-sentinel",
            "diagnostic-sentinel",
            "sha-secret-sentinel",
            "0xSECRET",
            "plant_id",
            "4242",
        ):
            self.assertNotIn(secret, text)
        for forbidden in ("raw_snapshot", "availability", "all_state", "confidence_threshold"):
            self.assertNotIn(forbidden, text)
        start = events[0]
        # OD-33/V44: job_start.state is the exact request state, not the v1 summary.
        self.assertEqual(
            start["state"], build_typesafe_state(runtime_jev_state(), branch=BRANCH_PLANT)
        )
        self.assertEqual(set(start["state"]), set(PLANT_STATE_FIELDS))
        self.assertNotEqual(start["state"], summarize_jev_state(runtime_jev_state()))
        self.assertEqual(sorted(start["strategy"]), sorted(evaluate_strategy(runtime_jev_state()).to_dict()))
        self.assertEqual(start["strategy"]["sun"], 75)
        self.assertEqual(start["strategy"]["affordable"], ["sunflower"])

    def test_job_start_records_the_exact_request_state_per_branch(self):
        """V44 — "what the model was shown" is checkable from the Trace itself."""
        plant = self.emit(runtime_plant_cycle())[0]
        self.assertEqual(set(plant["state"]), set(PLANT_STATE_FIELDS))
        self.assertEqual(
            plant["state"], build_typesafe_state(runtime_jev_state(), branch=BRANCH_PLANT)
        )
        self.assertEqual(plant["state"]["sun"], 75)

        collect = self.emit(runtime_collect_cycle())[0]
        self.assertEqual(set(collect["state"]), set(COLLECT_STATE_FIELDS))
        self.assertEqual(
            collect["state"]["items"],
            [{"type_code": 4, "type_name": "sun", "count": 1}],
        )
        # V64/OD-49/OD-50: the recorded input the model actually saw carries the
        # lane composition, the column-direction fact, and a role fact per card.
        # (This fixture's card codes do not resolve to catalog names, so its card
        # list is empty; the concrete role values are pinned in the client and
        # strategy checks.)
        self.assertEqual(
            plant["state"]["lane_composition"],
            [{"row": row, "resource": 0, "attacker": 0, "defender": 0} for row in range(5)],
        )
        self.assertEqual(plant["state"]["board"]["column_direction"]["house_side_col"], 0)
        self.assertEqual(plant["state"]["board"]["column_direction"]["zombie_side_col"], 8)
        for card in plant["state"]["cards"]:
            self.assertIn("role", card)
        for banned in ("recommend", "quota", "ideal", "priority", "advice"):
            self.assertNotIn(banned, json.dumps(plant["state"]))
        # The resource group is a computed fact group, never a recommendation.
        self.assertIn("band", plant["state"]["economy"])

    def test_a_job_that_sent_no_request_records_no_model_input(self):
        events = self.emit(runtime_branch_cycle_without_answer(outcome="await_resource", cycle=2))
        start = [event for event in events if event["event"] == EVENT_JOB_START][0]
        self.assertEqual(start["request_issued"], False)
        self.assertIsNone(start["state"])

    def test_await_plan_is_a_reliable_local_conclusion(self):
        """Case A: saving is a recorded conclusion of the key, not a lost cycle."""
        events = self.emit(runtime_branch_cycle_without_answer(outcome="await_plan", cycle=2, branch="plant"))
        start = [event for event in events if event["event"] == EVENT_JOB_START][0]
        end = [event for event in events if event["event"] == EVENT_JOB_END][0]
        self.assertEqual(start["request_issued"], False)
        self.assertIsNone(start["state"])
        self.assertEqual(end["outcome"], "await_plan")
        self.assertTrue(end["reliable"])

    def test_a_declared_goal_round_trips_through_the_request_state_whitelist(self):
        from types import SimpleNamespace
        from jev.trace import _actual_request_state
        state = runtime_jev_state()
        actual = build_typesafe_state(state, branch=BRANCH_PLANT, plan={"type_name": "peashooter"})
        recorded = _actual_request_state(SimpleNamespace(request_state=actual), state, BRANCH_PLANT, True)
        self.assertEqual(recorded, actual)
        self.assertEqual(
            recorded["economy"],
            {
                "sun": 75,
                "band": "normal",
                "cheapest_cost": 50,
                "highest_cost": 100,
                "sun_above_plan": None,
                "plan": {"type_name": "peashooter", "cost": 100, "payable": False, "shortfall": 25},
            },
        )

    def test_the_recorded_request_state_carries_no_identity_and_no_raw_state(self):
        events = self.emit(runtime_collect_cycle())
        start = [event for event in events if event["event"] == EVENT_JOB_START][0]
        item = start["state"]["items"][0]
        for banned in ("id", "item_id", "item_index", "x", "y"):
            self.assertNotIn(banned, item)
        text = json.dumps(events, ensure_ascii=False)
        for forbidden in ("raw_snapshot", "availability", "all_state", "diagnostic-sentinel"):
            self.assertNotIn(forbidden, text)

    def test_decision_completion_order_and_execution_order_stay_separate(self):
        emitted = []
        for cycle in (
            runtime_plant_cycle(cycle=1, start_ms=0, finish_ms=500),
            runtime_collect_cycle(cycle=2, start_ms=100, finish_ms=900),
            runtime_execution_cycle(branch="collect", cycle=3, start_ms=1000, finish_ms=1050, action="collect_item"),
            runtime_execution_cycle(branch="plant", cycle=4, start_ms=1400, finish_ms=1600, action="place_plant"),
        ):
            emitted.extend(self.emit(cycle))
        self.assertEqual([event["event_sequence"] for event in emitted], list(range(1, len(emitted) + 1)))

        completions = [event for event in emitted if event["event"] == EVENT_JOB_END]
        self.assertEqual(
            [(event["job_id"], event["branch_id"]) for event in completions],
            [("job-000001", "plant"), ("job-000002", "collect")],
        )
        executions = [event for event in emitted if event["event"] == EVENT_ACTION_RESULT]
        self.assertEqual(
            [(event["execution_id"], event["job_id"], event["branch_id"]) for event in executions],
            [("exec-000001", "job-000002", "collect"), ("exec-000002", "job-000001", "plant")],
        )
        # The collect decision completed second but was executed first, and each
        # execution is linked back to the job that produced its proposal.
        self.assertEqual([event["queue_delay_ms"] for event in executions], [100, 900])
        self.assertEqual([event["execution_elapsed_ms"] for event in executions], [50, 200])
        self.assertEqual(
            [event["boundary"] for event in executions],
            [
                {"status": "success", "action": "collect_item", "elapsed_ms": 30},
                {"status": "success", "action": "place_plant", "elapsed_ms": 120},
            ],
        )

    def test_replaced_and_expired_proposals_link_to_the_job_that_created_them(self):
        emitted = []
        for cycle in (
            runtime_plant_cycle(cycle=1, start_ms=0, finish_ms=500),
            runtime_plant_cycle(cycle=2, start_ms=600, finish_ms=1000),
            runtime_execution_cycle(
                branch="plant", cycle=3, start_ms=1000, finish_ms=1000,
                outcome=DISCARDED_OUTCOME, error_code="proposal_replaced",
            ),
            runtime_execution_cycle(
                branch="plant", cycle=4, start_ms=1000, finish_ms=6000,
                outcome=DISCARDED_OUTCOME, error_code="proposal_expired",
            ),
        ):
            emitted.extend(self.emit(cycle))
        discards = [event for event in emitted if event["event"] == EVENT_PROPOSAL_DISCARDED]
        self.assertEqual(
            [(event["job_id"], event["discard_reason"], event["queue_delay_ms"]) for event in discards],
            [
                ("job-000001", "proposal_replaced", 500),
                ("job-000002", "proposal_expired", 5000),
            ],
        )
        for event in discards:
            self.assertIsNone(event["execution_id"])
            self.assertEqual(event["branch_id"], "plant")

    def test_cancelled_and_api_error_jobs_never_claim_an_invented_answer(self):
        cancelled = self.emit(runtime_branch_cycle_without_answer(outcome="cancelled", cycle=1))
        self.assertEqual([event["event"] for event in cancelled], [EVENT_JOB_START, EVENT_JOB_END])
        self.assertIsNone(cancelled[0]["request_issued"])
        self.assertEqual(cancelled[1]["outcome"], "cancelled")
        self.assertIs(cancelled[1]["reliable"], False)

        local_wait = self.emit(runtime_branch_cycle_without_answer(outcome="await_resource", cycle=2))
        self.assertEqual([event["event"] for event in local_wait], [EVENT_JOB_START, EVENT_JOB_END])
        self.assertIs(local_wait[0]["request_issued"], False)
        self.assertIs(local_wait[1]["reliable"], True)

        api_error = self.emit(runtime_branch_cycle_without_answer(
            outcome="api_error", cycle=3, error_code="JevApiError"
        ))
        self.assertEqual(
            [event["event"] for event in api_error],
            [EVENT_JOB_START, EVENT_REQUEST_RESULT, EVENT_JOB_END],
        )
        self.assertIs(api_error[0]["request_issued"], True)
        self.assertIsNone(api_error[0]["sample_age_ms"])
        self.assertIsNone(api_error[1]["latency_ms"])
        self.assertEqual(api_error[1]["typed_answers"], {})
        self.assertIsNone(api_error[1]["merge"])
        self.assertIsNone(api_error[1]["noul_candidate_threshold"])
        self.assertEqual(api_error[1]["status"], "api_error")
        self.assertEqual(api_error[1]["error_code"], "JevApiError")
        self.assertIs(api_error[2]["reliable"], False)

    def test_a_stopped_decision_job_is_told_apart_from_a_discarded_proposal(self):
        stopped = self.emit(runtime_branch_cycle_without_answer(outcome=DISCARDED_OUTCOME, cycle=1))
        self.assertEqual([event["event"] for event in stopped], [EVENT_JOB_START, EVENT_JOB_END])
        self.assertIsNone(stopped[0]["request_issued"])

        discarded = self.emit(runtime_execution_cycle(
            branch="collect", cycle=2, start_ms=0, finish_ms=10,
            outcome=DISCARDED_OUTCOME, error_code="epoch_changed",
        ))
        self.assertEqual([event["event"] for event in discarded], [EVENT_PROPOSAL_DISCARDED])
        self.assertEqual(discarded[0]["discard_reason"], "epoch_changed")

    def test_member_evidence_projects_only_the_category_and_client_coordinates(self):
        """V67/R41: the OD-53 evidence is bounded and can never carry an item id."""
        evidence = {
            "reason_category": "outside_region",
            "client_x": 10.0,
            "client_y": 200.0,
            "item_id": 999,
            "object_id": 999,
        }
        discarded = self.emit(runtime_execution_cycle(
            branch="collect", cycle=1, start_ms=0, finish_ms=10,
            outcome=DISCARDED_OUTCOME, error_code="cohort_member_deferred_never_executable",
            evidence=evidence,
        ))
        self.assertEqual([event["event"] for event in discarded], [EVENT_PROPOSAL_DISCARDED])
        self.assertEqual(
            discarded[0]["evidence"],
            {"reason_category": "outside_region", "client_x": 10.0, "client_y": 200.0},
        )
        executed = self.emit(runtime_execution_cycle(branch="collect", cycle=2, evidence=evidence))
        self.assertEqual(
            executed[0]["evidence"],
            {"reason_category": "outside_region", "client_x": 10.0, "client_y": 200.0},
        )
        # A cycle that carries no member evidence records the field as null rather
        # than inventing an all-null evidence object.
        none = self.emit(runtime_execution_cycle(branch="collect", cycle=3))
        self.assertIsNone(none[0]["evidence"])
        text = json.dumps([*discarded, *executed, *none], ensure_ascii=False)
        self.assertNotIn("999", text)
        self.assertNotIn("item_id", text)
        self.assertNotIn("object_id", text)

    def test_runtime_stop_closes_the_run_and_reports_what_was_still_queued(self):
        self.emit(runtime_plant_cycle(cycle=1, start_ms=0, finish_ms=500))
        stop = self.emit(runtime_stop_cycle(cycle=2, at_ms=700))
        self.assertEqual([event["event"] for event in stop], [EVENT_RUNTIME_STOP])
        self.assertEqual(stop[0]["stop_reason"], "max_cycles")
        # The stop event states the game phase the last sample observed, so a Trace
        # distinguishes a cleared level from a lost one.
        self.assertEqual(stop[0]["final_phase"], "playing")
        self.assertEqual(stop[0]["event_sequence"], 4)
        self.assertIsNone(stop[0]["branch_id"])
        self.assertEqual(
            stop[0]["pending_proposals"],
            [{"branch_id": "plant", "job_id": "job-000001", "created_at_utc": _utc(500)}],
        )

    def test_target_choice_is_recorded_as_argmax_instead_of_a_confidence_threshold(self):
        request = self.emit(runtime_plant_cycle())[1]
        self.assertNotIn("confidence_threshold", request)
        self.assertEqual(request["target_choice_rule"], "argmax")
        # The plant branch has no Noul gate any more, so no threshold is recorded.
        self.assertIsNone(request["noul_candidate_threshold"])
        # The Choice confidence is still audited even though it never gated.
        self.assertEqual(request["typed_answers"]["plant_target"]["confidence"], 0.04)

        reranked = self.emit(runtime_plant_cycle(reranked=True))[1]
        self.assertEqual(reranked["target_choice_rule"], "argmax")
        self.assertEqual(reranked["merge"]["best_option"], "peashooter@r2c4")
        self.assertIs(reranked["merge"]["reranked"], True)
        self.assertEqual(reranked["merge"]["chosen_option"], "peashooter@r2c4")
        self.assertEqual(reranked["merge"]["selected_option"], "peashooter@r1c0")
        self.assertEqual(reranked["merge"]["rejected_option"], "peashooter@r2c4")

    def test_runtime_event_vocabulary_matches_the_scheduler_outcomes(self):
        from jev.scheduler import OUTCOME_DISCARDED, OUTCOME_EXECUTED, OUTCOME_REJECTED

        self.assertEqual(DISCARDED_OUTCOME, OUTCOME_DISCARDED)
        self.assertEqual(EXECUTION_OUTCOMES, frozenset({OUTCOME_EXECUTED, OUTCOME_REJECTED}))
        self.assertEqual(
            RUNTIME_EVENT_NAMES,
            frozenset({
                EVENT_JOB_START,
                EVENT_REQUEST_RESULT,
                EVENT_PROPOSAL_DISCARDED,
                EVENT_ACTION_RESULT,
                EVENT_JOB_END,
                EVENT_RUNTIME_STOP,
            }),
        )

    def test_legacy_v1_cycles_and_v2_events_are_recognized_by_version_only(self):
        legacy = build_trace_event(sample_cycle(), run_id="run-legacy")
        self.assertEqual(trace_schema_version(legacy), 1)
        self.assertEqual(legacy["schema_version"], 1)
        self.assertNotIn("event", legacy)
        self.assertNotIn("branch_id", legacy)
        self.assertNotIn("execution_id", legacy)

        for runtime_event in self.emit(runtime_plant_cycle()):
            self.assertEqual(trace_schema_version(runtime_event), SCHEMA_VERSION_V2)
            self.assertNotIn("cycle", runtime_event)

        self.assertIsNone(trace_schema_version({**legacy, "cycle": "1"}))
        self.assertIsNone(trace_schema_version({"schema_version": 1, "cycle": 2}))
        self.assertIsNone(trace_schema_version({"schema_version": 2, "run_id": "r", "event": "unknown", "event_sequence": 1}))
        self.assertIsNone(trace_schema_version({"schema_version": 2, "run_id": "r", "event": EVENT_JOB_END}))
        self.assertIsNone(trace_schema_version({"schema_version": 3, "run_id": "r", "cycle": 1}))

    def test_single_writer_keeps_the_sequence_monotonic_and_every_line_whole(self):
        events = [
            event
            for index in range(1, 6)
            for event in self.emit(runtime_plant_cycle(cycle=index))
        ]
        self.assertEqual([event["event_sequence"] for event in events], list(range(1, len(events) + 1)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.jsonl"
            with TraceRecorder(path) as recorder:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(recorder.write_event, events))
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(events))
        records = [json.loads(line) for line in lines]
        self.assertEqual(sorted(record["event_sequence"] for record in records), list(range(1, len(events) + 1)))
        self.assertEqual({record["run_id"] for record in records}, {"run-v2"})

    def test_recorder_recognizes_an_existing_v2_run_before_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with TraceRecorder(path) as recorder:
                for event in RuntimeEventBuilder(run_id="run-old").events_for(runtime_plant_cycle()):
                    recorder.write_event(event)
            replacement = RuntimeEventBuilder(run_id="run-new").events_for(runtime_collect_cycle())
            with TraceRecorder(path) as recorder:
                for event in replacement:
                    recorder.write_event(event)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(replacement))
        self.assertEqual({json.loads(line)["run_id"] for line in lines}, {"run-new"})


if __name__ == "__main__":
    unittest.main()


def shovel_jev_state() -> dict:
    """One plant sample with a removable occupied cell and a usable hand."""
    state = runtime_jev_state()
    cells = [[None] * 9 for _ in range(5)]
    cells[2][3] = "plant:peashooter"
    state["board"]["cells"] = cells
    state["plants"] = [{"type_code": 0, "type_name": "peashooter", "row": 2, "col": 3}]
    return state


def shovel_decision() -> tuple[JevActionDecision, str]:
    """The real plant merge of one request that selects a placement and a removal."""
    from types import SimpleNamespace
    from jev.client import build_plant_questions
    from jev.decision import combine_plant_decision

    question_set = build_plant_questions(shovel_jev_state())
    placement = next(
        key for key in question_set.questions[PLANT_TARGET_QUESTION_ID].criteria
        if key != DISCARD_OPTION_ID
    )
    answers = {}
    for question_id, question in question_set.questions.items():
        chosen = shovel_option_id(2, 3) if question_id == SHOVEL_TARGET_QUESTION_ID else placement
        remaining = (1.0 - 0.9) / max(1, len(question.criteria) - 1)
        probabilities = {key: remaining for key in question.criteria}
        probabilities[chosen] = 0.9
        answers[question_id] = SimpleNamespace(
            type="choice", choice=chosen, confidence=0.9, probabilities=probabilities
        )
    decision = combine_plant_decision(
        SimpleNamespace(model="jev-latest", usage=None, answers=answers),
        question_set=question_set,
        latency_ms=210,
        question_summary=question_set.summary,
    )
    return decision, placement


class ShovelLayerTraceTests(unittest.TestCase):
    """V19/R15: the removal layer and its execution are recorded as facts."""

    def events(self) -> tuple[list[dict], dict]:
        decision, placement = shovel_decision()
        self.assertEqual(decision.target["action"], "shovel_cell")
        self.assertEqual(decision.effective_action, "shovel")
        self.assertEqual(decision.answers["merge"]["overridden_placement_option"], placement)
        builder = RuntimeEventBuilder(run_id="run-shovel")
        events = builder.events_for(
            JevRuntimeCycle(
                cycle=1,
                sample_sequence=RUNTIME_SEQUENCE,
                started_at_utc=_utc(0),
                finished_at_utc=_utc(500),
                outcome="selected",
                effective_action="shovel",
                all_state=dict(_SENTINEL_ALL_STATE),
                jev_state=shovel_jev_state(),
                action=decision,
                boundary_result=None,
                branch="plant",
            )
        )
        events += builder.events_for(
            JevRuntimeCycle(
                cycle=2,
                sample_sequence=RUNTIME_SEQUENCE,
                started_at_utc=_utc(600),
                finished_at_utc=_utc(700),
                outcome="executed",
                effective_action="shovel",
                all_state=dict(_SENTINEL_ALL_STATE),
                jev_state=shovel_jev_state(),
                action=None,
                boundary_result={"status": "success", "action": "shovel_cell", "elapsed_ms": 120},
                branch="plant",
                executed_target={"action": "shovel_cell", "row": 2, "col": 3},
            )
        )
        return events, placement

    def test_the_removal_layer_answers_and_execution_are_recorded(self):
        events, placement = self.events()
        start = next(event for event in events if event["event"] == EVENT_JOB_START)
        result = next(event for event in events if event["event"] == EVENT_REQUEST_RESULT)
        action = next(event for event in events if event["event"] == EVENT_ACTION_RESULT)

        # job_start.state carries the very facts the removal options state.
        self.assertEqual(start["state"]["board"]["cells"][2][3], "plant:peashooter")
        self.assertEqual([plant["type_name"] for plant in start["state"]["plants"]], ["peashooter"])
        self.assertEqual(start["request_issued"], True)

        shovel_answer = result["typed_answers"]["shovel_target"]
        self.assertEqual(shovel_answer["choice"], shovel_option_id(2, 3))
        self.assertEqual(sorted(shovel_answer["probabilities"]), ["none_of_the_above", shovel_option_id(2, 3)])
        self.assertIs(result["merge"]["shovel_selected"], True)
        self.assertIs(result["merge"]["shovel_discarded"], False)
        self.assertIs(result["merge"]["shovel_overrode_placement"], True)
        self.assertEqual(result["merge"]["overridden_placement_option"], placement)
        self.assertEqual(result["target"]["action"], "shovel_cell")
        self.assertEqual(result["effective_action"], "shovel")

        self.assertEqual(action["target"]["action"], "shovel_cell")
        self.assertEqual((action["target"]["row"], action["target"]["col"]), (2, 3))
        self.assertEqual(action["boundary"]["action"], "shovel_cell")
        self.assertEqual(action["boundary"]["status"], "success")

        blob = json.dumps(events, ensure_ascii=False)
        for banned in ("item_id", "plant_id", "raw_snapshot", "api_key", "123456"):
            self.assertNotIn(banned, blob)


class SharedNestedWhitelistTests(unittest.TestCase):
    def test_actual_input_nested_credentials_ids_and_snapshots_are_removed(self):
        from types import SimpleNamespace
        from jev.trace import _actual_request_state
        hostile = {"sun": 10, "cards": [{"type_name": "sunflower", "cost": 50, "credential": "secret"}],
                   "items": [{"type_name": "sun", "type_code": 4, "count": 1, "item_id": 999, "x": 123, "raw_snapshot": {"credential": "secret"}}],
                   "plants": [{"type_name": "sunflower", "row": 0, "col": 0, "id": 888}], "zombies": [],
                   "current_intent": {"type_name": "sunflower", "token": "secret"},
                   "last_actual_result": {"action": "plant", "status": "success", "source": {"token": "secret"}},
                   "board": {"cells": [[None]], "raw_snapshot": {"token": "secret"}}, "plant_counts": {"sunflower": 1, "credential": 123},
                   "catalog_context": {"zombie_abilities": [{"type_name": "normal_zombie", "description_en": "Walks", "id": 77}]}}
        sanitized = _actual_request_state(SimpleNamespace(request_state=hostile), {}, "collect", True)
        text = json.dumps(sanitized)
        for banned in ("secret", "credential", "item_id", "raw_snapshot", "888", "999", "token"):
            self.assertNotIn(banned, text)
        self.assertEqual(sanitized["items"][0], {"type_code": 4, "type_name": "sun", "count": 1})


class ConfirmationEvidenceAcceptanceTests(unittest.TestCase):
    def test_boundary_evidence_is_structured_without_identity_or_error_content(self):
        from jev.trace import _boundary_record
        evidence = _boundary_record({"status": "unverified", "action": "collect_item", "elapsed_ms": 12, "details": {"input_clicks": [{"status": "uncertain", "item_id": 999}], "postcondition_result": "pending", "observed_source": {"pid": 999, "token": "secret"}, "input_delivery_error": "secret", "wait": {"polls": 2, "waited_ms": 12, "timeout_ms": 10, "last_observation": {"item_id": 999}}}})
        self.assertEqual(evidence["input_status"], "uncertain")
        self.assertEqual(evidence["confirmation"], "pending")
        self.assertEqual(evidence["wait"]["polls"], 2)
        # Only the item id was observed, so nothing identity-free is left to record.
        self.assertNotIn("last_observation", evidence["wait"])
        self.assertEqual(evidence["rejection_evidence"], ["observed_source", "input_delivery_error"])
        self.assertNotIn("999", json.dumps(evidence))
        self.assertNotIn("secret", json.dumps(evidence))


class SharedPlantAbilityParityTests(unittest.TestCase):
    """V74/R49: the recorded model input keeps the plant ability facts."""

    def jev_state_with_plants(self, sequence=RUNTIME_SEQUENCE):
        state = runtime_jev_state(sequence)
        state["cards"] = [
            {"slot": 0, "type_code": 0, "type_name": "peashooter", "usable": True, "cooldown_ready": True, "cost": 100},
        ]
        state["plants"] = [
            {"type_code": 1, "type_name": "sunflower", "row": 0, "col": 0, "hp": 300, "id": 987654},
            {"type_code": 999, "type_name": "unknown", "row": 1, "col": 0, "hp": 300, "id": 987655},
        ]
        return state

    def test_job_start_state_shows_plant_abilities_and_each_plant_role(self):
        state = self.jev_state_with_plants()
        events = RuntimeEventBuilder(run_id="run-abilities").events_for(
            replace(runtime_plant_cycle(), jev_state=state)
        )
        start = [event for event in events if event["event"] == EVENT_JOB_START][0]
        self.assertEqual(set(start["state"]), set(PLANT_STATE_FIELDS))
        self.assertEqual(
            start["state"]["catalog_context"]["plant_abilities"],
            [
                {"type_name": "peashooter", "description_en": plant_info(0).description_en, "role": "attacker"},
                {"type_name": "sunflower", "description_en": plant_info(1).description_en, "role": "resource"},
            ],
        )
        self.assertEqual(
            [plant["role"] for plant in start["state"]["plants"]], ["resource", None]
        )
        self.assertEqual(
            [plant["description_en"] for plant in start["state"]["plants"]],
            [plant_info(1).description_en, None],
        )
        self.assertEqual(
            list(start["state"]["plants"][0]),
            ["type_name", "row", "col", "hp", "role", "description_en"],
        )
        recorded = json.dumps(events)
        for identity in ("987654", "987655"):
            self.assertNotIn(identity, recorded)


class SharedActualInputParityAcceptanceTests(unittest.TestCase):
    def test_real_shared_builder_survives_whitelist_with_observed_lanes_and_waves(self):
        from types import SimpleNamespace
        from jev.trace import _actual_request_state
        state = runtime_jev_state()
        source = {"sample_sequence": state.get("sample_sequence"), "observed_at_utc": state.get("observed_at_utc"), "game": state.get("game"), "availability": {"game.wave": "available", "game.total_waves": "provisional"}}
        actual = build_typesafe_state(state, branch="collect", all_state=source)
        actual.update(current_intent={"type_name": "sunflower"}, last_actual_result={"action": "plant", "type_name": "sunflower", "row": 0, "col": 0, "outcome": "executed", "status": "success"})
        recorded = _actual_request_state(SimpleNamespace(request_state=actual), state, "collect", True)
        self.assertEqual(recorded, actual)
        self.assertEqual(len(recorded["observed_lanes"]), 5)
        self.assertNotIn("urgency", json.dumps(recorded))


class BoundaryWaitSummaryRepairTests(unittest.TestCase):
    def test_missing_wait_keys_omit_summary_and_known_values_survive(self):
        from jev.trace import _boundary_record
        base = {"status": "success", "action": "collect_item", "elapsed_ms": 0}
        self.assertNotIn("wait", _boundary_record({**base, "details": {"input_clicks": [{"status": "sent"}]}}))
        for details, expected in (
            ({"polls": 0, "waited_ms": 0, "timeout_ms": 10},
             {"polls": 0, "waited_ms": 0, "timeout_ms": 10}),
            ({"wait": {"polls": 2, "waited_ms": 12, "timeout_ms": 10, "item_id": 999}},
             {"polls": 2, "waited_ms": 12, "timeout_ms": 10}),
            ({"wait": {"polls": 3, "waited_ms": 2_500, "timeout_ms": 2_500,
                       "last_observation": {"item_id": 999, "same_item_present": False}}},
             {"polls": 3, "waited_ms": 2_500, "timeout_ms": 2_500,
              "last_observation": {"same_item_present": False}}),
        ):
            with self.subTest(details=details):
                result = _boundary_record({**base, "details": details})
                # OD-47 adds the identity-free part of the executor's last observation
                # to the bounded counters; every id in it is still dropped.
                self.assertEqual(result["wait"], expected)
                self.assertNotIn("item_id", json.dumps(result))

    def test_unverified_keeps_its_counters_and_the_unconfirmation_reason(self):
        from jev.trace import _boundary_record
        record = _boundary_record({
            "status": "unverified",
            "action": "collect_item",
            "elapsed_ms": 2_501,
            "details": {
                "input_clicks": [{"status": "sent"}],
                "postcondition": "the same item ID disappears",
                "postcondition_result": "pending",
                "polls": 40,
                "waited_ms": 2_500,
                "timeout_ms": 2_500,
                "last_observation": {"reason": "item IDs are unresolved", "item_id": 999},
                "item": {"item_id": 999, "client_point": [40.0, 80.0]},
            },
        })
        self.assertEqual(record["status"], "unverified")
        self.assertEqual(record["confirmation"], "pending")
        self.assertEqual(record["wait"], {
            "polls": 40,
            "waited_ms": 2_500,
            "timeout_ms": 2_500,
            "last_observation": {"reason": "item IDs are unresolved"},
        })
        self.assertNotIn("999", json.dumps(record))
        self.assertNotIn("item_id", json.dumps(record))
