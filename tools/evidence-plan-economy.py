"""Offline before/after evidence for the plan/economy revision (Case A / Case B).

Reads a frozen schema-2 Trace, rebuilds the exact JEV state of one plant decision
from the Trace's own recorded fields, and prints what the old candidate rule and
the new one offer for the same sample. No game, no network, no model call: only
the two deterministic candidate layers are compared. The tool is read-only and
never writes to the repository.

Run:  uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jev.strategy import (  # noqa: E402  (the repository root is on sys.path above)
    build_plant_candidates,
    economy_facts,
    evaluate_strategy,
    plant_spend_decision,
)

DEFAULT_TRACE_FILE = ".log/jev-dashboard.jsonl"
EXIT_INPUT_ERROR = 2


class EvidenceError(Exception):
    """An unusable input: the caller maps it to a message and a non-zero exit."""


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline BEFORE/AFTER candidate comparison on a frozen JEV Trace.",
    )
    parser.add_argument(
        "--trace-file",
        default=DEFAULT_TRACE_FILE,
        help=f"schema-2 JSONL Trace, relative to the repository root or absolute (default: {DEFAULT_TRACE_FILE})",
    )
    return parser.parse_args(argv)


def resolve_trace_path(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise EvidenceError(f"trace file not found: {path}")
    events: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as error:
            raise EvidenceError(f"{path}: line {number} is not valid JSON: {error}") from error
        if not isinstance(event, dict):
            raise EvidenceError(f"{path}: line {number} is not a JSON object")
        events.append(event)
    return events


def plant_jobs(events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    jobs = []
    for start in (event for event in events if event.get("event") == "job_start" and event.get("branch_id") == "plant"):
        result = next(
            (
                event
                for event in events
                if event.get("event") == "request_result" and event.get("job_id") == start.get("job_id")
            ),
            None,
        )
        jobs.append((start, result))
    return jobs


def hand_from(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The full hand of this run, taken from the first multi-type plant request state."""
    for start in (event for event in events if event.get("event") == "job_start" and event.get("branch_id") == "plant"):
        cards = start["state"]["cards"]
        if len(cards) > 1:
            return [
                {
                    "type_name": card["type_name"],
                    "type_code": 0,
                    "cost": card["cost"],
                    "usable": card["usable"],
                    "cooldown_ready": card["cooldown_ready"],
                }
                for card in cards
            ]
    return []


def jev_state_from(start: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    """The decision's own facts: board, balance, empty zombies, this run's hand."""
    return {
        "sun_balance": start["state"]["sun"],
        "cards": list(cards),
        "board": {"rows": 5, "cols": 9, "cells": start["state"]["board"]["cells"]},
        "plants": [],
        "zombies": [],
    }


def old_candidates(state: dict[str, Any], plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The removed rule: filter the hand down to the declared type first."""
    if plan and plan.get("type_name"):
        state = {
            **state,
            "cards": [card for card in state["cards"] if card["type_name"] == plan["type_name"]],
        }
    return build_plant_candidates(state)


def report(events: list[dict[str, Any]], path: Path) -> None:
    hand = hand_from(events)
    print(f"trace: {path.name}  plant decisions: {len(plant_jobs(events))}  hand: {len(hand)} types")
    print()

    for start, result in plant_jobs(events):
        if result is None or not result.get("source_intent"):
            continue
        plan = {"type_name": result["source_intent"]["type_name"]}
        state = jev_state_from(start, hand)
        signals = evaluate_strategy(state)
        before = old_candidates(state, plan)
        after = build_plant_candidates(state, signals, plan=plan)
        facts = economy_facts(state, plan)
        print(f"--- {start['job_id']}  sample {start['sample_sequence']}  sun {state['sun_balance']}")
        print(
            f"    declared goal        : {plan['type_name']} "
            f"(cost {facts['plan']['cost']}, payable {facts['plan']['payable']})"
        )
        print(f"    balance band         : {facts['band']}   sun_above_plan: {facts['sun_above_plan']}")
        print(
            f"    BEFORE (goal filter) : {len(before):4d} placements, "
            f"types={sorted({entry['type_name'] for entry in before})}"
        )
        print(
            f"    AFTER  (goal context): {len(after):4d} placements, "
            f"types={sorted({entry['type_name'] for entry in after})}"
        )
        print()

    # Case A is a synthetic sample of the same hand: the goal above the balance.
    state = jev_state_from(plant_jobs(events)[0][0], hand)
    state["zombies"] = []
    for sun in (150, 320, 400):
        state["sun_balance"] = sun
        signals = evaluate_strategy(state)
        plan = {"type_name": "melon_pult"}
        before = old_candidates(state, plan)
        after = build_plant_candidates(state, signals, plan=plan)
        decision = plant_spend_decision(signals, state["cards"], plan)
        print(
            f"--- Case A sun {sun:5d}  goal melon_pult(300): "
            f"BEFORE {len(before):4d} placements {sorted({e['type_name'] for e in before})} | "
            f"AFTER {len(after):4d} placements {sorted({e['type_name'] for e in after})} "
            f"hold={decision.hold_reason}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    path = resolve_trace_path(parse_arguments(argv).trace_file)
    try:
        events = load_events(path)
        if not any(
            result is not None and result.get("source_intent") for _, result in plant_jobs(events)
        ):
            raise EvidenceError(f"{path}: no plant decision with source_intent")
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    report(events, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
