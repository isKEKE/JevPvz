"""Smoke test for the offline economy evidence tool in ``tools/``.

Locks the two shapes the tool depends on: a plant job whose paired
``request_result`` carries ``source_intent`` (the reported sample) and one that
does not (must stay out of the comparison). The tool must stay read-only.
"""

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "evidence-plan-economy.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("evidence_plan_economy", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()

CELLS = [[None] * 9 for _ in range(5)]
CARDS = [
    {"type_name": "sunflower", "cost": 50, "payable": True, "shortfall": 0, "usable": True, "cooldown_ready": True},
    {"type_name": "peashooter", "cost": 100, "payable": True, "shortfall": 0, "usable": True, "cooldown_ready": True},
    {"type_name": "melon_pult", "cost": 300, "payable": True, "shortfall": 0, "usable": True, "cooldown_ready": True},
]


def trace_events():
    state = {"sun": 400, "cards": CARDS, "board": {"cells": CELLS}}
    return [
        {"schema_version": 2, "event": "job_start", "event_sequence": 1, "job_id": "job-000001",
         "branch_id": "plant", "sample_sequence": 7, "state": state},
        {"schema_version": 2, "event": "request_result", "event_sequence": 2, "job_id": "job-000001",
         "source_intent": {"type_name": "sunflower"}},
        {"schema_version": 2, "event": "job_start", "event_sequence": 3, "job_id": "job-000002",
         "branch_id": "plant", "sample_sequence": 8, "state": state},
        {"schema_version": 2, "event": "request_result", "event_sequence": 4, "job_id": "job-000002"},
    ]


def write_trace(directory, events):
    path = Path(directory) / "trace.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


class EconomyEvidenceToolTests(unittest.TestCase):
    def test_rebuilds_sample_and_compares_old_and_new_rules(self):
        self.assertEqual(TOOL.resolve_trace_path(".log/jev-dashboard.jsonl"),
                         TOOL.ROOT / ".log" / "jev-dashboard.jsonl")
        with tempfile.TemporaryDirectory() as directory:
            events = TOOL.load_events(write_trace(directory, trace_events()))
            hand = TOOL.hand_from(events)
            self.assertEqual([card["type_name"] for card in hand], ["sunflower", "peashooter", "melon_pult"])
            start, result = TOOL.plant_jobs(events)[0]
            state = TOOL.jev_state_from(start, hand)
            self.assertEqual(state["sun_balance"], 400)
            self.assertEqual(state["board"]["cells"], CELLS)
            signals = TOOL.evaluate_strategy(state)
            plan = {"type_name": result["source_intent"]["type_name"]}
            before = TOOL.old_candidates(state, plan)
            after = TOOL.build_plant_candidates(state, signals, plan=plan)
            self.assertEqual((len(before), sorted({e["type_name"] for e in before})), (45, ["sunflower"]))
            self.assertEqual(
                (len(after), sorted({e["type_name"] for e in after})),
                (135, ["melon_pult", "peashooter", "sunflower"]),
            )

    def test_main_skips_goal_less_jobs_and_prints_case_a_without_touching_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_trace(directory, trace_events())
            before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = TOOL.main(["--trace-file", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_digest)
            text = stdout.getvalue()
            self.assertIn("job-000001", text)
            self.assertNotIn("job-000002", text)
            self.assertIn("BEFORE (goal filter) :   45 placements, types=['sunflower']", text)
            self.assertIn("Case A sun   150  goal melon_pult(300): BEFORE    0 placements [] | "
                          "AFTER    0 placements [] hold=await_plan", text)
            self.assertIn("AFTER   45 placements ['melon_pult'] hold=None", text)
            self.assertIn("AFTER  135 placements ['melon_pult', 'peashooter', 'sunflower'] hold=None", text)

    def test_missing_unparseable_and_goal_less_traces_exit_non_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = TOOL.main(["--trace-file", str(Path(directory) / "absent.jsonl")])
            self.assertNotEqual(code, 0)
            self.assertIn("trace file not found", stderr.getvalue())

            broken = Path(directory) / "broken.jsonl"
            broken.write_text('{"event": "job_start"}\nnot json\n', encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = TOOL.main(["--trace-file", str(broken)])
            self.assertNotEqual(code, 0)
            self.assertIn("not valid JSON", stderr.getvalue())

            goal_less = write_trace(directory, trace_events()[2:])
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = TOOL.main(["--trace-file", str(goal_less)])
            self.assertNotEqual(code, 0)
            self.assertIn("no plant decision with source_intent", stderr.getvalue())
