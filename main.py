"""Single command-line entry point for the local PvZ state reader."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

from actions import ActionExecutor
from configs.pvz_1051 import TARGET_IDENTITY
from game.reader import read_raw_snapshot
from runtime.memory import ReadOnlyMemory
from runtime.process import (
    ProcessDiscoveryError,
    locate_target_process,
    main_module_base,
    verify_target_identity,
)
from state.builder import capture_state
from state.projection import project_jev_state
from dashboard.server import serve_dashboard
from jev.config import JevConfigurationError, load_typesafe_environment
from jev.loop import JevRuntimeCycle, JevRuntimeLoop
from jev.trace import RuntimeEventBuilder, TraceRecorder, TraceWriteError


def run_probe() -> int:
    """Check the configured executable and print one read-only raw sample."""
    try:
        process = locate_target_process(str(TARGET_IDENTITY["path"]))
        identity = verify_target_identity(process, TARGET_IDENTITY)
        module_base = main_module_base(process.pid, TARGET_IDENTITY["path"])
        with ReadOnlyMemory(process.pid) as memory:
            snapshot = read_raw_snapshot(memory, module_base)
        result = {
            "target_identity": identity.as_dict(),
            "snapshot": snapshot,
        }
    except (ProcessDiscoveryError, OSError, RuntimeError, ValueError) as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def run_snapshot(*, once: bool, interval_ms: int, profile: str = "all") -> int:
    """Print one State record or a newline-delimited stream of records."""
    if interval_ms < 50:
        print("snapshot failed: --interval-ms must be at least 50", file=sys.stderr)
        return 2
    try:
        while True:
            sample = capture_state()
            result = project_jev_state(sample) if profile == "jev" else sample
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
            if once:
                return 0
            time.sleep(interval_ms / 1000)
    except KeyboardInterrupt:
        return 130


def run_serve(*, port: int, interval_ms: int, jev_trace_file: str | None = None) -> int:
    try:
        serve_dashboard(port=port, poll_interval_ms=interval_ms, jev_trace_file=jev_trace_file)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"serve failed: {exc}", file=sys.stderr)
        return 2
    return 0


def run_action(*, action_json: str | None) -> int:
    """Execute one semantic JSON request and print exactly one JSON result."""
    executor = ActionExecutor()
    if action_json is None:
        result = executor.rejected_request(None, "--action-json is required for the action command.")
    else:
        try:
            request = json.loads(action_json)
        except json.JSONDecodeError as exc:
            result = executor.rejected_request(
                action_json,
                f"--action-json must contain valid JSON (line {exc.lineno}, column {exc.colno}).",
            )
        else:
            result = executor.execute(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False), flush=True)
    return {"success": 0, "rejected": 2, "unverified": 3}[result.status]


def run_jev_loop(*, interval_ms: int, max_cycles: int | None, trace_file: str) -> int:
    # Reject unusable start options before anything is opened or truncated. A
    # negative observation interval and a non-positive job limit are startup
    # failures, not runtime stop conditions, so they never create a Trace and
    # never enter the bounded error recovery.
    if interval_ms < 0:
        print(
            "jev-loop failed: --interval-ms must be zero or a positive number of milliseconds.",
            file=sys.stderr,
        )
        return 2
    if max_cycles is not None and max_cycles < 1:
        print("jev-loop failed: --max-cycles must be at least 1 when provided.", file=sys.stderr)
        return 2
    try:
        load_typesafe_environment()
    except JevConfigurationError as exc:
        print(f"jev-loop configuration failed: {exc}", file=sys.stderr)
        return 2

    def log_cycle(cycle: JevRuntimeCycle) -> None:
        router = cycle.router
        action = cycle.action
        boundary_result = cycle.boundary_result
        if hasattr(boundary_result, "to_dict"):
            boundary_result = boundary_result.to_dict()
        boundary_status = boundary_result.get("status") if isinstance(boundary_result, dict) else None
        result = {
            "cycle": cycle.cycle,
            "sample_sequence": cycle.sample_sequence,
            "outcome": cycle.outcome,
            "router": None if router is None else {
                "noul_probabilities": router.noul_probabilities,
                "candidates": list(router.candidates),
                "choice": router.choice,
                "confidence": router.confidence,
                "effective_action": router.effective_action,
            },
            "action": None if action is None else {
                "intent": action.intent,
                "answers": action.answers,
                "effective_action": action.effective_action,
                "target": action.target,
            },
            "boundary_status": boundary_status,
            "error_code": cycle.error_code,
            "next_sample_sequence": (
                cycle.next_observation.get("sample_sequence")
                if isinstance(cycle.next_observation, dict) else None
            ),
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False), flush=True)

    run_id = uuid.uuid4().hex
    events = RuntimeEventBuilder(run_id=run_id)

    def record_cycle(cycle: JevRuntimeCycle) -> None:
        # One writer, one monotonic event_sequence: every schema-2 event of this
        # run is produced here and written in order before the cycle summary line.
        for event in events.events_for(cycle):
            recorder.write_event(event)
        log_cycle(cycle)

    try:
        with TraceRecorder(trace_file) as recorder:
            summary = JevRuntimeLoop(interval_ms=interval_ms, on_cycle=record_cycle).run(max_cycles=max_cycles)
    except TraceWriteError as exc:
        print(f"jev-loop failed: {exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"jev-loop failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    # The four runtime counters are reported separately on purpose: observations
    # are samples, requests are JEV calls, actions are real Boundary dispatches,
    # and terminated jobs are the DecisionJobs --max-cycles limits (OD-22).
    print(json.dumps({
        "status": summary.status,
        "observations": summary.observations,
        "requests": summary.requests,
        "actions": summary.actions,
        "terminated_jobs": summary.jobs,
        "final_phase": summary.final_phase,
        "lane_closest": [[row, cells] for row, cells in summary.lane_closest],
    }, separators=(",", ":")), flush=True)
    if summary.status == "interrupted":
        return 130
    if summary.status in {"too_many_errors", "process_disconnected"}:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect PvZ 1.0.0.1051 state and run guarded semantic UI actions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe", help="check target identity and print one raw sample")
    snapshot = subparsers.add_parser("snapshot", help="print normalized State as JSON")
    snapshot.add_argument("--once", action="store_true", help="capture exactly one State record")
    snapshot.add_argument("--interval-ms", type=int, default=200, help="stream interval (minimum 50 ms)")
    snapshot.add_argument("--profile", choices=("all", "jev"), default="all", help="JSON profile (default: all)")
    serve = subparsers.add_parser("serve", help="start the localhost-only browser dashboard")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--interval-ms", type=int, default=200, help="background sampling interval (minimum 50 ms)")
    serve.add_argument("--jev-trace-file", help="optional JSONL Trace path to read in the JEV dashboard page")
    action = subparsers.add_parser("action", help="execute one guarded semantic UI action")
    action.add_argument("--action-json", help="one JSON request with an action and semantic parameters")
    jev_loop = subparsers.add_parser("jev-loop", help="run the guarded TypeSafe JEV decision loop")
    jev_loop.add_argument(
        "--interval-ms",
        type=int,
        default=0,
        help=(
            "optional observation-only minimum interval in milliseconds; omitted or 0 keeps "
            "continuous observation without any added wait, and a positive value only paces "
            "observations (it never paces JEV requests or changes the request timeout)"
        ),
    )
    jev_loop.add_argument(
        "--max-cycles",
        type=int,
        help=(
            "optional limit counted in terminated DecisionJobs; omitted means run until a stop "
            "condition, and observations/requests/actions are counted separately"
        ),
    )
    jev_loop.add_argument("--trace-file", required=True, help="JSONL path for this run; an existing JEV Trace is replaced, other files are preserved")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "probe":
        return run_probe()
    if arguments.command == "snapshot":
        return run_snapshot(once=arguments.once, interval_ms=arguments.interval_ms, profile=arguments.profile)
    if arguments.command == "serve":
        return run_serve(
            port=arguments.port,
            interval_ms=arguments.interval_ms,
            jev_trace_file=arguments.jev_trace_file,
        )
    if arguments.command == "action":
        return run_action(action_json=arguments.action_json)
    if arguments.command == "jev-loop":
        return run_jev_loop(
            interval_ms=arguments.interval_ms,
            max_cycles=arguments.max_cycles,
            trace_file=arguments.trace_file,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
