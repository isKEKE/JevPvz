"""Single command-line entry point for the local PvZ state reader."""

from __future__ import annotations

import argparse
import json
import sys
import time

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
from dashboard.server import serve_dashboard


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


def run_snapshot(*, once: bool, interval_ms: int) -> int:
    """Print one State record or a newline-delimited stream of records."""
    if interval_ms < 50:
        print("snapshot failed: --interval-ms must be at least 50", file=sys.stderr)
        return 2
    try:
        while True:
            print(json.dumps(capture_state(), ensure_ascii=False, separators=(",", ":")), flush=True)
            if once:
                return 0
            time.sleep(interval_ms / 1000)
    except KeyboardInterrupt:
        return 130


def run_serve(*, port: int, interval_ms: int) -> int:
    try:
        serve_dashboard(port=port, poll_interval_ms=interval_ms)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect PvZ 1.0.0.1051 state and run guarded semantic UI actions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe", help="check target identity and print one raw sample")
    snapshot = subparsers.add_parser("snapshot", help="print normalized State as JSON")
    snapshot.add_argument("--once", action="store_true", help="capture exactly one State record")
    snapshot.add_argument("--interval-ms", type=int, default=200, help="stream interval (minimum 50 ms)")
    serve = subparsers.add_parser("serve", help="start the localhost-only browser dashboard")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--interval-ms", type=int, default=200, help="background sampling interval (minimum 50 ms)")
    action = subparsers.add_parser("action", help="execute one guarded semantic UI action")
    action.add_argument("--action-json", help="one JSON request with an action and semantic parameters")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "probe":
        return run_probe()
    if arguments.command == "snapshot":
        return run_snapshot(once=arguments.once, interval_ms=arguments.interval_ms)
    if arguments.command == "serve":
        return run_serve(port=arguments.port, interval_ms=arguments.interval_ms)
    if arguments.command == "action":
        return run_action(action_json=arguments.action_json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
