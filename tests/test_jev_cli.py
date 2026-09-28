import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from jev.client import REQUEST_TIMEOUT_SECONDS
from jev.config import JevConfigurationError
from jev.loop import JevLoopSummary, JevRuntimeCycle
from main import build_parser, main, run_jev_loop
from dashboard.runtime_control import RuntimeProcessLock


def runtime_summary(**overrides):
    fields = {
        "status": "stopped",
        "observation_cycles": 5,
        "router_cycles": 2,
        "consecutive_error_cycles": 0,
        "observations": 5,
        "jobs": 2,
        "requests": 3,
        "actions": 1,
        "skips": 4,
        "errors": 0,
        "cancelled_jobs": 0,
    }
    fields.update(overrides)
    return JevLoopSummary(**fields)


def local_wait_cycle(*, sequence=9):
    return JevRuntimeCycle(
        cycle=1,
        sample_sequence=sequence,
        started_at_utc="2026-09-27T10:00:00.000Z",
        finished_at_utc="2026-09-27T10:00:00.010Z",
        outcome="await_resource",
        effective_action="wait",
        all_state={"decision_ready": True},
        jev_state={"cards": [], "board": {"cells": [[None] * 9 for _ in range(5)]}},
        branch="plant",
    )


class JevCliTests(unittest.TestCase):
    def test_existing_loop_lock_rejects_second_cli_before_trace_open(self):
        lock = RuntimeProcessLock()
        self.assertTrue(lock.acquire())
        try:
            with patch("main.TraceRecorder") as recorder, redirect_stderr(io.StringIO()) as stderr:
                result = run_jev_loop(interval_ms=0, max_cycles=None, trace_file="unused.jsonl")
            self.assertEqual(result, 2)
            self.assertIn("another JEV Loop", stderr.getvalue())
            recorder.assert_not_called()
        finally:
            lock.release()

    def test_lock_is_held_across_python_processes(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "from dashboard.runtime_control import RuntimeProcessLock; import sys; lock=RuntimeProcessLock(); print(lock.acquire(), flush=True); sys.stdin.readline(); lock.release()"],
            cwd=".", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "True")
            self.assertTrue(RuntimeProcessLock.occupied())
        finally:
            child.stdin.write("\n")
            child.stdin.flush()
            child.wait(timeout=3)
            child.stdout.close()
            child.stderr.close()
            child.stdin.close()
        self.assertFalse(RuntimeProcessLock.occupied())

    def run_cli(self, argv, *, cycles=(), summary=None):
        """Run ``main`` with a fake Trace recorder, runtime loop, and environment."""
        summary = summary or runtime_summary()
        captured: dict[str, object] = {}

        class Recorder:
            def __init__(self, path):
                self.path = path
                self.events = []
                captured["recorder"] = self

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def write_event(self, event):
                self.events.append(event)

        class Loop:
            def __init__(self, **kwargs):
                captured["kwargs"] = kwargs

            def run(self, *, max_cycles=None, stop_requested=None):
                captured["max_cycles"] = max_cycles
                for cycle in cycles:
                    captured["kwargs"]["on_cycle"](cycle)
                return summary

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("main.TraceRecorder", Recorder),
            patch("main.JevRuntimeLoop", Loop),
            patch("main.load_typesafe_environment") as environment,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main(argv)
        captured["stdout"] = stdout.getvalue()
        captured["stderr"] = stderr.getvalue()
        return exit_code, captured

    def final_line(self, output):
        return json.loads(output.strip().splitlines()[-1])

    def test_configuration_error_fails_before_trace_or_loop_starts(self):
        stderr = io.StringIO()
        with (
            patch("main.load_typesafe_environment", side_effect=JevConfigurationError(
                "JEV_ROUTER_CONFIDENCE_THRESHOLD must be a number from 0 through 1."
            )),
            patch("main.TraceRecorder") as trace_recorder,
            patch("main.JevRuntimeLoop") as runtime_loop,
            redirect_stderr(stderr),
        ):
            exit_code = run_jev_loop(interval_ms=5000, max_cycles=None, trace_file="unused.jsonl")

        self.assertEqual(exit_code, 2)
        self.assertIn("jev-loop configuration failed", stderr.getvalue())
        self.assertIn("JEV_ROUTER_CONFIDENCE_THRESHOLD", stderr.getvalue())
        trace_recorder.assert_not_called()
        runtime_loop.assert_not_called()

    def test_help_documents_observation_only_interval_and_terminated_job_limit(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["jev-loop", "--help"])
        self.assertEqual(raised.exception.code, 0)
        help_text = " ".join(stdout.getvalue().split())
        self.assertIn("optional observation-only minimum interval in milliseconds", help_text)
        self.assertIn("omitted or 0 keeps continuous observation without any added wait", help_text)
        self.assertIn("positive value only paces observations", help_text)
        self.assertIn("optional limit counted in terminated DecisionJobs", help_text)
        self.assertIn("observations/requests/actions are counted separately", help_text)
        self.assertNotIn("minimum interval between observations (minimum 50 ms)", help_text)

    def test_interval_ms_is_optional_and_defaults_to_no_added_observation_wait(self):
        arguments = build_parser().parse_args(["jev-loop", "--trace-file", "run.jsonl"])
        self.assertEqual(arguments.interval_ms, 0)
        self.assertIsNone(arguments.max_cycles)

        exit_code, captured = self.run_cli(["jev-loop", "--trace-file", "run.jsonl"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["kwargs"]["interval_ms"], 0)
        self.assertNotEqual(captured["kwargs"]["interval_ms"], 5000)
        self.assertIsNone(captured["max_cycles"])

    def test_a_positive_interval_only_paces_observations(self):
        exit_code, captured = self.run_cli(
            ["jev-loop", "--interval-ms", "250", "--trace-file", "run.jsonl"]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["kwargs"]["interval_ms"], 250)
        # Observation pacing is handed to the runtime and nothing else: the CLI
        # never rewrites the network timeout with it.
        self.assertEqual(set(captured["kwargs"]), {"interval_ms", "on_cycle"})
        self.assertEqual(REQUEST_TIMEOUT_SECONDS, 15.0)

    def test_negative_or_invalid_interval_fails_before_creating_a_trace(self):
        exit_code, captured = self.run_cli(
            ["jev-loop", "--interval-ms=-1", "--trace-file", "unused.jsonl"]
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("--interval-ms must be zero or a positive number", captured["stderr"])
        self.assertNotIn("recorder", captured)
        self.assertNotIn("kwargs", captured)

        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["jev-loop", "--interval-ms", "abc", "--trace-file", "unused.jsonl"])
        self.assertEqual(raised.exception.code, 2)
        self.assertNotEqual(stderr.getvalue(), "")

    def test_non_positive_max_cycles_fails_before_creating_a_trace(self):
        exit_code, captured = self.run_cli(
            ["jev-loop", "--max-cycles", "0", "--trace-file", "unused.jsonl"]
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("--max-cycles must be at least 1", captured["stderr"])
        self.assertNotIn("recorder", captured)
        self.assertNotIn("kwargs", captured)

    def test_max_cycles_is_forwarded_and_counts_terminated_decision_jobs(self):
        summary = runtime_summary(status="max_cycles", observations=7, jobs=2, requests=3, actions=1)
        exit_code, captured = self.run_cli(
            ["jev-loop", "--max-cycles", "2", "--trace-file", "run.jsonl"], summary=summary
        )
        self.assertEqual(captured["max_cycles"], 2)
        self.assertEqual(self.final_line(captured["stdout"]), {
            "status": "max_cycles",
            "observations": 7,
            "requests": 3,
            "actions": 1,
            "terminated_jobs": 2,
            "final_phase": None,
            "lane_closest": [],
        })
        self.assertEqual(exit_code, 0)

    def test_stdout_reports_the_four_runtime_counts_separately(self):
        summary = runtime_summary(status="stopped", observations=11, jobs=4, requests=6, actions=2)
        exit_code, captured = self.run_cli(["jev-loop", "--trace-file", "run.jsonl"], summary=summary)
        final = self.final_line(captured["stdout"])
        self.assertEqual(final, {
            "status": "stopped",
            "observations": 11,
            "requests": 6,
            "actions": 2,
            "terminated_jobs": 4,
            "final_phase": None,
            "lane_closest": [],
        })
        self.assertEqual(exit_code, 0)

    def test_every_cycle_is_written_as_v2_events_by_one_writer(self):
        exit_code, captured = self.run_cli(
            ["jev-loop", "--trace-file", "run.jsonl"], cycles=[local_wait_cycle(), local_wait_cycle(sequence=10)]
        )
        self.assertEqual(exit_code, 0)
        recorder = captured["recorder"]
        self.assertEqual(
            [event["event"] for event in recorder.events],
            ["job_start", "job_end", "job_start", "job_end"],
        )
        self.assertEqual([event["event_sequence"] for event in recorder.events], [1, 2, 3, 4])
        self.assertEqual({event["schema_version"] for event in recorder.events}, {2})
        self.assertEqual(len({event["run_id"] for event in recorder.events}), 1)
        # The per-cycle stdout line still prints one JSON object per cycle.
        self.assertEqual(len(captured["stdout"].strip().splitlines()), 3)

    def test_run_jev_loop_rejects_invalid_start_options_directly(self):
        with (
            patch("main.load_typesafe_environment") as environment,
            patch("main.TraceRecorder") as trace_recorder,
            patch("main.JevRuntimeLoop") as runtime_loop,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(run_jev_loop(interval_ms=-5, max_cycles=None, trace_file="unused.jsonl"), 2)
            self.assertEqual(run_jev_loop(interval_ms=0, max_cycles=0, trace_file="unused.jsonl"), 2)
        environment.assert_not_called()
        trace_recorder.assert_not_called()
        runtime_loop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
