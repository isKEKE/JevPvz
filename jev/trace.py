"""Versioned, secret-safe JSONL events for JEV Runtime cycles.

Two schemas live here. :func:`build_trace_event` is the historical schema-1
record: one line per runtime cycle, written by the P02 serial runtime, still
read by the Dashboard and by the tests that pin the legacy shape. The
schema-2 runtime trace is produced by :class:`RuntimeEventBuilder`, which turns
the asynchronous runtime's ordered cycles into causally linked ``job_start`` /
``request_result`` / ``proposal_discarded`` / ``action_result`` / ``job_end`` /
``runtime_stop`` events.

Schema 2 deliberately differs from schema 1 in three ways. It never copies the raw
All State, the raw SDK response, or credentials: only bounded State facts, the
derived strategy signals, and the request state's own declared field set are kept.
``job_start.state`` is the exact pruned per-branch state the request carried
(:func:`jev.client.build_typesafe_state`) rather than the schema-1 summary, so
"what the model was shown" can be checked from the Trace itself (OD-33); a job
that sent no request records ``None``. And it no longer records a per-entry
confidence threshold as "the gate this decision used": the collect Noul is
gated by the pinned ``COLLECT_ACT_THRESHOLD`` and the plant target Choice is
taken as the model's argmax with no gate at all (OD-41, OD-42), so
``request_result`` records ``target_choice_rule`` and the used Noul threshold.
The plant merge exposes its ``best_option``/``best_probability``/
``discard_probability``/``margin`` facts for review (V57).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from state.projection import project_jev_state

from .client import build_typesafe_state
from .strategy import evaluate_strategy


class TraceWriteError(OSError):
    """Raised when a cycle cannot be durably appended to its explicit trace."""


def summarize_jev_state(state: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return a bounded allowlist summary; never copy the full State into Trace."""
    if not isinstance(state, Mapping):
        return None
    game = state.get("game") if isinstance(state.get("game"), Mapping) else {}
    board = state.get("board") if isinstance(state.get("board"), Mapping) else {}
    cells = board.get("cells") if isinstance(board.get("cells"), list) else []
    occupied_cells = sum(
        1 for row in cells if isinstance(row, list)
        for cell in row if isinstance(cell, str) and cell.startswith("plant:")
    )
    plants = state.get("plants")
    zombies = state.get("zombies")
    items = state.get("items")
    cards = state.get("cards")
    zombie_types = Counter(
        item.get("type_name") for item in zombies
        if isinstance(zombies, list) and isinstance(item, Mapping) and isinstance(item.get("type_name"), str)
    ) if isinstance(zombies, list) else Counter()
    lanes = state.get("lanes")
    lane_summary = [
        {
            "row": _safe_int(lane.get("row")),
            "zombie_count": _safe_int(lane.get("zombie_count")),
            "nearest_zombie_distance_to_house_cells": _safe_int(lane.get("nearest_zombie_distance_to_house_cells")),
        }
        for lane in lanes if isinstance(lanes, list) and isinstance(lane, Mapping)
    ] if isinstance(lanes, list) else []
    return {
        "sample_sequence": _safe_int(state.get("sample_sequence")),
        "observed_at_utc": _safe_text(state.get("observed_at_utc")),
        "status": _safe_text(state.get("status")),
        "valid": state.get("valid") if type(state.get("valid")) is bool else None,
        "decision_ready": state.get("decision_ready") if type(state.get("decision_ready")) is bool else None,
        "game": {
            "phase": _safe_text(game.get("phase")),
            "mode": _safe_text(game.get("mode")),
            "background": _safe_text(game.get("background")),
            "paused": game.get("paused") if type(game.get("paused")) is bool else None,
            "level": _safe_label(game.get("level")),
            "wave": _safe_int(game.get("wave")),
        },
        "sun_balance": _safe_int(state.get("sun_balance")),
        "counts": {
            "plants": len(plants) if isinstance(plants, list) else None,
            "zombies": len(zombies) if isinstance(zombies, list) else None,
            "items": len(items) if isinstance(items, list) else None,
            "cards": len(cards) if isinstance(cards, list) else None,
            "occupied_cells": occupied_cells,
        },
        "usable_plant_types": sorted({
            card.get("type_name") for card in cards
            if isinstance(cards, list) and isinstance(card, Mapping)
            and card.get("usable") is True and isinstance(card.get("type_name"), str)
        }) if isinstance(cards, list) else [],
        "zombie_types": [
            {"type_name": name, "count": count}
            for name, count in sorted(zombie_types.items())
        ],
        "lanes": lane_summary[:5],
    }


def build_trace_event(cycle: Any, *, run_id: str) -> dict[str, Any]:
    """Build one fixed-schema event from a runtime cycle without retaining raw state.

    This is the schema-1 legacy record (one line per cycle) the P02 serial runtime
    wrote and older Traces on disk still contain. Its per-entry
    ``confidence_threshold`` fields are historical: the current branch runtime
    selects a target Choice by argmax and records ``target_choice_rule`` in the
    schema-2 events of :class:`RuntimeEventBuilder` instead. Do not read the
    schema-1 threshold as "the gate this decision used".
    """
    jev_state = getattr(cycle, "jev_state", None)
    all_state = getattr(cycle, "all_state", None)
    if not isinstance(jev_state, Mapping) and isinstance(all_state, Mapping):
        try:
            jev_state = project_jev_state(all_state)
        except (TypeError, ValueError):
            jev_state = None
    try:
        catalog_context = build_typesafe_state(jev_state).get("catalog_context", {}) if isinstance(jev_state, Mapping) else {}
    except (TypeError, ValueError):
        catalog_context = {"zombie_abilities": [], "plant_abilities": []}

    next_state = getattr(cycle, "next_observation", None)
    next_jev_state = None
    if isinstance(next_state, Mapping):
        try:
            next_jev_state = project_jev_state(next_state)
        except (TypeError, ValueError):
            next_jev_state = None

    router = getattr(cycle, "router", None)
    action = getattr(cycle, "action", None)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "cycle": _safe_int(getattr(cycle, "cycle", None)),
        "timestamp_utc": _safe_text(getattr(cycle, "started_at_utc", None)),
        "finished_at_utc": _safe_text(getattr(cycle, "finished_at_utc", None)),
        "sample_sequence": _safe_int(getattr(cycle, "sample_sequence", None)),
        "state": summarize_jev_state(jev_state),
        "catalog_context": catalog_context,
        "router": _router_record(router),
        "action": _action_record(action),
        "effective_decision": _safe_text(getattr(cycle, "effective_action", None)) or "wait",
        "outcome": _safe_text(getattr(cycle, "outcome", None)) or "unknown",
        "boundary": _boundary_record(getattr(cycle, "boundary_result", None)),
        "error_code": _safe_text(getattr(cycle, "error_code", None)),
        "next_observation": summarize_jev_state(next_jev_state),
    }


def _router_record(router: Any) -> dict[str, Any] | None:
    if router is None:
        return None
    return {
        "request": {"model": _safe_text(router.model), "questions": _json_safe(router.question_summary)},
        "response": {
            "noul_probabilities": _json_safe(router.noul_probabilities),
            "candidates": list(router.candidates),
            "noul_candidate_threshold": _safe_float(router.noul_candidate_threshold),
            "choice": _safe_text(router.choice),
            "confidence": _safe_float(router.confidence),
            "confidence_threshold": _safe_float(router.confidence_threshold),
            "probabilities": _json_safe(router.probabilities),
            "model": _safe_text(router.model),
            "usage": _json_safe(router.usage),
            "latency_ms": _safe_int(router.latency_ms),
        },
        "effective_action": _safe_text(router.effective_action),
        "fallback_reason": _safe_text(router.fallback_reason),
    }


def _action_record(action: Any) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "intent": _safe_text(action.intent),
        "status": _safe_text(action.status),
        "request": {"model": _safe_text(action.model), "questions": _json_safe(action.question_summary)},
        "answers": _json_safe(action.answers),
        "confidence_threshold": _safe_float(action.confidence_threshold),
        "target": _target_summary(action.target),
        "effective_action": _safe_text(action.effective_action),
        "fallback_reason": _safe_text(action.fallback_reason),
        "model": _safe_text(action.model),
        "usage": _json_safe(action.usage),
        "latency_ms": _safe_int(action.latency_ms),
    }


def _target_summary(target: Any) -> dict[str, Any] | None:
    if not isinstance(target, Mapping):
        return None
    action = target.get("action")
    result: dict[str, Any] = {"action": _safe_text(action)}
    for key in ("type_name", "row", "col"):
        value = target.get(key)
        result[key] = _safe_text(value) if key == "type_name" else _safe_int(value)
    if action == "collect_item":
        result["type_name"] = _safe_text(target.get("type_name"))
    return result


_WAIT_COUNTER_KEYS = ("polls", "waited_ms", "timeout_ms")
"""The bounded wait counters every Boundary record keeps."""

_LAST_OBSERVATION_REASON_KEY = "reason"
_LAST_OBSERVATION_PRESENCE_KEY = "same_item_present"
"""The only executor per-poll fields the Trace keeps (OD-47, R36).

``ActionExecutor._wait_for_postcondition`` records its last postcondition
observation verbatim, and on the collect path that observation carries the clicked
item's ``item_id`` as well as the raw candidate evidence. Both are identity, and no
v2 Trace event may hold one (R22), so only the human-readable ``reason`` and the
``same_item_present`` boolean survive; every id is dropped instead of recorded.
"""


def _last_observation_summary(value: Any) -> dict[str, Any]:
    """Project one executor observation onto the identity-free allowlist."""
    if not isinstance(value, Mapping):
        return {}
    summary: dict[str, Any] = {}
    reason = _safe_text(value.get(_LAST_OBSERVATION_REASON_KEY))
    if reason is not None:
        summary[_LAST_OBSERVATION_REASON_KEY] = reason
    present = value.get(_LAST_OBSERVATION_PRESENCE_KEY)
    if isinstance(present, bool):
        summary[_LAST_OBSERVATION_PRESENCE_KEY] = present
    return summary


_EVIDENCE_KEYS = ("reason_category", "client_x", "client_y")
"""The only member-evidence fields schema 2 keeps (OD-53, R41).

One unexecutable collect member is attributed by an enumerated reason category and
its own two client coordinates. The member's ``item_id`` is identity and never
survives; nothing else from the state travels here either.
"""


def _evidence_record(value: Any) -> dict[str, Any] | None:
    """Project one cycle's member evidence onto its three-key allowlist."""
    if not isinstance(value, Mapping):
        return None
    return {
        "reason_category": _safe_text(value.get("reason_category")),
        "client_x": _safe_float(value.get("client_x")),
        "client_y": _safe_float(value.get("client_y")),
    }


def _boundary_record(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    if hasattr(result, "to_dict"):
        result = result.to_dict()
    if not isinstance(result, Mapping):
        return {"status": "unknown", "action": None, "elapsed_ms": None}
    elapsed = result.get("elapsed_ms")
    record = {
        "status": _safe_text(result.get("status")) or "unknown",
        "action": _safe_text(result.get("action")),
        "elapsed_ms": _safe_int(elapsed),
    }
    details = result.get("details")
    if isinstance(details, Mapping):
        clicks = details.get("input_clicks")
        statuses = [click.get("status") for click in clicks if isinstance(click, Mapping)] if isinstance(clicks, list) else []
        if isinstance(clicks, list) and not clicks:
            record["input_status"] = "not_sent"
        elif any(status in {"pending", "uncertain"} for status in statuses):
            record["input_status"] = "uncertain"
        elif statuses and all(status == "sent" for status in statuses):
            record["input_status"] = "sent"
        confirmation = details.get("postcondition_result")
        if confirmation in {"met", "pending", "ambiguous", "mismatch"}:
            record["confirmation"] = confirmation
        wait = details.get("wait", details)
        if isinstance(wait, Mapping) and any(key in wait for key in _WAIT_COUNTER_KEYS):
            record["wait"] = {key: _safe_int(wait.get(key)) for key in _WAIT_COUNTER_KEYS}
            observation = _last_observation_summary(wait.get("last_observation"))
            if observation:
                record["wait"]["last_observation"] = observation
        evidence = tuple(key for key in ("item_coordinate_evidence", "observed_client_rect", "observed_dpi", "display", "observed_source", "input_delivery_error") if key in details)
        if evidence: record["rejection_evidence"] = list(evidence)
    return record



def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items() if isinstance(key, (str, int))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return None


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _safe_label(value: Any) -> str | int | None:
    if isinstance(value, str):
        return value
    return _safe_int(value)


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


# ------------------------------------------------------- schema-2 runtime events

SCHEMA_VERSION_V2 = 2
"""The schema version of every event :class:`RuntimeEventBuilder` writes."""

EVENT_JOB_START = "job_start"
EVENT_REQUEST_RESULT = "request_result"
EVENT_PROPOSAL_DISCARDED = "proposal_discarded"
EVENT_ACTION_RESULT = "action_result"
EVENT_JOB_END = "job_end"
EVENT_RUNTIME_STOP = "runtime_stop"

RUNTIME_EVENT_NAMES: frozenset[str] = frozenset(
    {
        EVENT_JOB_START,
        EVENT_REQUEST_RESULT,
        EVENT_PROPOSAL_DISCARDED,
        EVENT_ACTION_RESULT,
        EVENT_JOB_END,
        EVENT_RUNTIME_STOP,
    }
)
"""Every schema-2 event name; readers validate against exactly this set."""

DISCARDED_OUTCOME = "discarded"
"""The scheduler's discard outcome, mirrored for event classification.

It equals :data:`jev.scheduler.OUTCOME_DISCARDED`; ``tests/test_jev_trace.py``
asserts the two stay equal so a rename cannot split the vocabulary silently.
"""

RELIABLE_OUTCOMES: frozenset[str] = frozenset(
    {"selected", "model_wait", "low_confidence", "no_target", "await_resource", "await_cooldown"}
)
"""Conclusions the Runtime records as the branch's answer for that key (OD-22).

A reliable conclusion is never retried; ``api_error``/``invalid_response`` are
unreliable and ``await_change``/``discarded``/``superseded``/``expired`` are
terminal for the job instead of being a conclusion about the key.
"""

_REQUEST_ATTEMPTED_OUTCOMES: frozenset[str] = frozenset({"api_error", "invalid_response"})
"""Outcomes that prove a request left the Runtime even though no decision came back."""

_UNCERTAIN_REQUEST_OUTCOMES: frozenset[str] = frozenset({"cancelled", DISCARDED_OUTCOME})
"""Outcomes where the Runtime cannot tell whether a request was already in flight."""

EXECUTION_OUTCOMES: frozenset[str] = frozenset({"executed", "action_rejected"})
"""The scheduler's dispatch outcomes, mirrored for event classification.

They equal :data:`jev.scheduler.OUTCOME_EXECUTED` / ``OUTCOME_REJECTED``; the
trace tests assert that equality, and ``DISCARDED_OUTCOME`` above covers the
third one -- a discarded proposal is told apart from a discarded decision job by
its scheduler discard reason.
"""


def _model_input_state(
    jev_state: Any,
    branch: str,
    request_issued: bool | None,
) -> dict[str, Any] | None:
    """The exact pruned state one request carried, or ``None`` if none was sent.

    ``job_start.state`` has to let a reader check the decision's real input (OD-33),
    so it is the same per-branch projection the client sends
    (:func:`jev.client.build_typesafe_state`) instead of the schema-1 summary: a
    collect job records its items and their coordinates, a plant job the computed
    signals it was given. ``availability``, ``source``, ``raw_snapshot``, credentials,
    and every field a branch's declared state omits stay out by construction, since
    the builder returns only the declared fields of that branch (V31/V44).

    A job that sent no request records ``None``: the field means "what the model was
    shown", and recording a state the model never saw would be evidence of something
    that did not happen.
    """
    if request_issued is not True or not isinstance(jev_state, Mapping):
        return None
    try:
        return build_typesafe_state(jev_state, branch=branch)
    except (TypeError, ValueError):
        return None


def summarize_strategy(
    jev_state: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the bounded derived-strategy summary of one JEV State, or None.

    Only the four signal groups :class:`jev.strategy.StrategySignals` derives are
    kept; the summary never carries a predicted income, a reservation, or a raw
    State field, and an unreadable projection yields ``None`` instead of a guess.
    """
    if not isinstance(jev_state, Mapping):
        return None
    try:
        return evaluate_strategy(jev_state).to_dict()
    except (TypeError, ValueError):
        return None


class RuntimeEventBuilder:
    """Turn the Runtime's ordered cycles into causal schema-2 events.

    One builder is one writer: it owns the only ``event_sequence`` counter, hands
    out one ``run_id``, and links each job's events through
    ``job_id``/``stage_id``/``request_id``/``execution_id`` and ``branch_id``.
    Cycles arrive in *completion* order, because that is how the runtime records
    them, so a decision that completes second still keeps its own events in
    sequence while an ``action_result`` records the actual execution order.

    Events are only produced per decision job and per dispatch attempt, never per
    observation, so continuous sampling does not turn into a per-sample log. An
    uncertain stop (``cancelled``/``discarded`` without an answer) reports
    ``request_issued: null`` rather than claiming a request did or did not happen.
    """

    def __init__(self, *, run_id: str):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("A Trace run_id is required.")
        self._run_id = run_id
        self._sequence = 0
        self._jobs = 0
        self._executions = 0
        # job_id of the newest decision of each branch, and the proposals that
        # a decided job created but no dispatch attempt has consumed yet, oldest
        # first (a branch keeps at most one, so a replacement removes one).
        self._last_job_id: dict[str, str] = {}
        self._source_jobs: dict[int, tuple[str | None, str]] = {}
        self._unhandled: dict[str, list[tuple[str | None, str]]] = {}

    @property
    def run_id(self) -> str:
        """The single run identifier every event of this writer carries."""
        return self._run_id

    @property
    def event_sequence(self) -> int:
        """How many events this writer has produced; strictly increasing."""
        return self._sequence

    def events_for(self, cycle: Any) -> list[dict[str, Any]]:
        """Return the schema-2 events for one runtime cycle, in sequence order."""
        branch = _safe_text(getattr(cycle, "branch", None))
        if branch is None:
            # Only the terminal runtime cycle has no branch; it is the stop event.
            return [self._stop_event(cycle)]
        if getattr(cycle, "action", None) is not None:
            return self._decision_events(cycle, branch)
        if _is_execution_record(cycle):
            return [self._execution_event(cycle, branch)]
        # A decision job that ended without an answer (a stop cancelled it, or its
        # local conclusion was voided) still has a start and an end event.
        return self._decision_events(cycle, branch)

    # ------------------------------------------------------------ envelope

    def _event(
        self,
        name: str,
        *,
        timestamp_utc: str | None,
        branch_id: str | None = None,
        job_id: str | None = None,
        stage_id: str | None = None,
        request_id: str | None = None,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        return {
            "schema_version": SCHEMA_VERSION_V2,
            "event": name,
            "event_sequence": self._sequence,
            "run_id": self._run_id,
            "timestamp_utc": timestamp_utc,
            "job_id": job_id,
            "branch_id": branch_id,
            "stage_id": stage_id,
            "request_id": request_id,
            "execution_id": execution_id,
        }

    # --------------------------------------------------------- decision job

    def _decision_events(self, cycle: Any, branch: str) -> list[dict[str, Any]]:
        decision = getattr(cycle, "action", None)
        outcome = _safe_text(getattr(cycle, "outcome", None)) or "unknown"
        started_at_utc = _safe_text(getattr(cycle, "started_at_utc", None))
        finished_at_utc = _safe_text(getattr(cycle, "finished_at_utc", None))
        sample_sequence = _safe_int(getattr(cycle, "sample_sequence", None))

        self._jobs += 1
        job_id = f"job-{self._jobs:06d}"
        stage_id = f"{branch}-decision"
        self._last_job_id[branch] = job_id
        self._source_jobs[getattr(cycle, "cycle", self._jobs)] = (finished_at_utc, job_id)
        if len(self._source_jobs) > 256: self._source_jobs.pop(next(iter(self._source_jobs)))

        request_issued = _request_issued(outcome, decision)
        latency_ms = _safe_int(getattr(decision, "latency_ms", None)) if decision is not None else None
        elapsed_ms = _elapsed_ms(started_at_utc, finished_at_utc)
        sample_age_ms = _sample_age_ms(elapsed_ms, latency_ms, request_issued)
        jev_state = getattr(cycle, "jev_state", None)

        events = [
            {
                **self._event(
                    EVENT_JOB_START,
                    timestamp_utc=started_at_utc,
                    branch_id=branch,
                    job_id=job_id,
                    stage_id=stage_id,
                ),
                "sample_sequence": sample_sequence,
                "sample_observed_at_utc": started_at_utc,
                "sample_age_ms": sample_age_ms,
                "elapsed_ms": elapsed_ms,
                "request_issued": request_issued,
                "state": _actual_request_state(decision, jev_state, branch, request_issued),
                "strategy": summarize_strategy(jev_state),
            }
        ]
        if request_issued is True:
            events.append(self._request_result_event(
                cycle,
                branch=branch,
                job_id=job_id,
                stage_id=stage_id,
                sample_sequence=sample_sequence,
                latency_ms=latency_ms,
                outcome=outcome,
            ))
        events.append(
            {
                **self._event(
                    EVENT_JOB_END,
                    timestamp_utc=finished_at_utc,
                    branch_id=branch,
                    job_id=job_id,
                    stage_id=stage_id,
                ),
                "outcome": outcome,
                "effective_action": _safe_text(getattr(cycle, "effective_action", None)),
                "reliable": outcome in RELIABLE_OUTCOMES,
                "error_code": _safe_text(getattr(cycle, "error_code", None)),
                "sample_sequence": sample_sequence,
                "elapsed_ms": elapsed_ms,
            }
        )
        if outcome == "selected" and getattr(decision, "target", None) is not None and getattr(decision, "source_cycle", None) is None:
            # The scheduler now holds this branch's only pending proposal, created
            # at exactly this record's time. A later dispatch attempt consumes it.
            self._unhandled.setdefault(branch, []).append((finished_at_utc, job_id))
        return events

    def _request_result_event(
        self,
        cycle: Any,
        *,
        branch: str,
        job_id: str,
        stage_id: str,
        sample_sequence: int | None,
        latency_ms: int | None,
        outcome: str,
    ) -> dict[str, Any]:
        decision = getattr(cycle, "action", None)
        answers = getattr(decision, "answers", None) if decision is not None else None
        merge = _merge_record(answers)
        return {
            **self._event(
                EVENT_REQUEST_RESULT,
                timestamp_utc=_safe_text(getattr(cycle, "finished_at_utc", None)),
                branch_id=branch,
                job_id=job_id,
                stage_id=stage_id,
                request_id=f"{job_id}-request-1",
            ),
            "intent": _safe_text(getattr(decision, "intent", None)) if decision is not None else None,
            "status": _safe_text(getattr(decision, "status", None)) if decision is not None else outcome,
            "effective_action": _safe_text(getattr(decision, "effective_action", None)) if decision is not None else None,
            "fallback_reason": _safe_text(getattr(decision, "fallback_reason", None)) if decision is not None else None,
            "error_code": _safe_text(getattr(cycle, "error_code", None)),
            "model": _safe_text(getattr(decision, "model", None)) if decision is not None else None,
            "usage": _json_safe(getattr(decision, "usage", None)) if decision is not None else None,
            "latency_ms": latency_ms,
            "sample_sequence": sample_sequence,
            "noul_candidate_threshold": None if merge is None else _safe_float(merge.get("noul_candidate_threshold")),
            "target_choice_rule": None if merge is None else _safe_text(merge.get("target_choice_rule")),
            "typed_answers": _typed_answers(answers),
            "source_intent_version": _safe_int(getattr(decision, "source_intent_version", None)),
            "source_intent": _intent_record(getattr(decision, "source_intent", None)),
            "management": _select_scalars(getattr(decision, "management", None), ("operation", "type_name")),
            "component_errors": list(getattr(decision, "component_errors", ())),
            "target": _target_summary(getattr(decision, "target", None)),
            "merge": merge,
        }

    # ------------------------------------------------------- execution record

    def _execution_event(self, cycle: Any, branch: str) -> dict[str, Any]:
        outcome = _safe_text(getattr(cycle, "outcome", None)) or "unknown"
        started_at_utc = _safe_text(getattr(cycle, "started_at_utc", None))
        finished_at_utc = _safe_text(getattr(cycle, "finished_at_utc", None))
        sample_sequence = _safe_int(getattr(cycle, "sample_sequence", None))
        source_cycle = getattr(cycle, "source_cycle", None)
        created_at_utc, job_id = self._source_jobs.get(source_cycle, (None, None)) if source_cycle is not None else self._take_unhandled(branch)
        if outcome == DISCARDED_OUTCOME:
            # A discarded proposal never reached an execution, so it gets no
            # execution_id; the queue delay is the wait it spent before the stop.
            return {
                **self._event(
                    EVENT_PROPOSAL_DISCARDED,
                    timestamp_utc=finished_at_utc,
                    branch_id=branch,
                    job_id=job_id,
                ),
                "effective_action": _safe_text(getattr(cycle, "effective_action", None)),
                "discard_reason": _safe_text(getattr(cycle, "error_code", None)),
                "queue_delay_ms": _elapsed_ms(created_at_utc, finished_at_utc),
                "sample_sequence": sample_sequence,
                "evidence": _evidence_record(getattr(cycle, "evidence", None)),
            }
        self._executions += 1
        execution_id = f"exec-{self._executions:06d}"
        return {
            **self._event(
                EVENT_ACTION_RESULT,
                timestamp_utc=started_at_utc,
                branch_id=branch,
                job_id=job_id,
                execution_id=execution_id,
            ),
            "outcome": outcome,
            "effective_action": _safe_text(getattr(cycle, "effective_action", None)),
            "error_code": _safe_text(getattr(cycle, "error_code", None)),
            "boundary": _boundary_record(getattr(cycle, "boundary_result", None)),
            "source_intent_version": _safe_int(getattr(cycle, "source_intent_version", None)),
            "source_intent": _intent_record(getattr(cycle, "source_intent", None)),
            "target": _target_summary(getattr(cycle, "executed_target", None)),
            "execution_elapsed_ms": _elapsed_ms(started_at_utc, finished_at_utc),
            "queue_delay_ms": _elapsed_ms(created_at_utc, started_at_utc),
            "sample_sequence": sample_sequence,
            "evidence": _evidence_record(getattr(cycle, "evidence", None)),
        }

    def _take_unhandled(self, branch: str) -> tuple[str | None, str | None]:
        """Pop the oldest proposal of this branch that no attempt consumed yet."""
        pending = self._unhandled.get(branch)
        if pending:
            return pending.pop(0)
        return None, self._last_job_id.get(branch)

    # -------------------------------------------------------------- terminal

    def _stop_event(self, cycle: Any) -> dict[str, Any]:
        pending = [
            {"branch_id": branch, "job_id": job_id, "created_at_utc": created_at_utc}
            for branch, entries in sorted(self._unhandled.items())
            for created_at_utc, job_id in entries
        ]
        return {
            **self._event(
                EVENT_RUNTIME_STOP,
                timestamp_utc=_safe_text(getattr(cycle, "finished_at_utc", None)),
            ),
            "stop_reason": _safe_text(getattr(cycle, "outcome", None)) or "stopped",
            "sample_sequence": _safe_int(getattr(cycle, "sample_sequence", None)),
            "final_phase": _final_phase(getattr(cycle, "jev_state", None)),
            "pending_proposals": pending,
        }


def _final_phase(jev_state: Any) -> str | None:
    """The game phase the stopping sample observed, so a Trace states win or loss.

    ``stop_reason`` alone collapses ``level_complete`` and ``zombies_win`` into
    ``level_finished``; this fact keeps the difference without changing the stop
    semantics.
    """
    game = jev_state.get("game") if isinstance(jev_state, Mapping) else None
    phase = game.get("phase") if isinstance(game, Mapping) else None
    return phase if isinstance(phase, str) and phase else None


def _is_execution_record(cycle: Any) -> bool:
    """Whether one branch-less-decision cycle is a scheduler execution record.

    Both a dispatch attempt and a stop-cancelled decision job arrive with
    ``action=None``. A dispatch attempt is either an ``executed``/
    ``action_rejected`` outcome or a discard that carries the scheduler's discard
    reason; a decision job always leaves ``error_code`` empty.
    """
    outcome = _safe_text(getattr(cycle, "outcome", None))
    if outcome in EXECUTION_OUTCOMES:
        return True
    return outcome == DISCARDED_OUTCOME and _safe_text(getattr(cycle, "error_code", None)) is not None


def _typed_answers(answers: Any) -> dict[str, Any]:
    """Return the per-question typed answers, without the code merge record."""
    if not isinstance(answers, Mapping):
        return {}
    return {
        question_id: _json_safe(record)
        for question_id, record in answers.items()
        if isinstance(question_id, str) and question_id != "merge"
    }


MERGE_REVIEW_KEYS: tuple[str, ...] = (
    "authorized_count",
    "should_collect_probability",
    "noul_candidate_threshold",
    "target_choice_rule",
    "chosen_option",
    "selected_option",
    "reranked",
    "rejected_option",
    "rejected_row",
    "best_available_probability",
    "best_option",
    "best_probability",
    "discard_probability",
    "margin",
    "confidence",
    "status",
    "fallback_reason",
)
"""The merge fields a reviewer needs to see why one row was not chosen.

They are always present in a schema-2 ``merge`` record -- with ``null`` when the
code-side merge did not set them, as it does not for a target that was never
re-ranked -- so a reviewer can tell "nothing was rejected" from "not recorded".
"""


def _merge_record(answers: Any) -> dict[str, Any] | None:
    """Copy the code-side merge conclusion with its review keys always present."""
    if not isinstance(answers, Mapping):
        return None
    merge = answers.get("merge")
    if not isinstance(merge, Mapping):
        return None
    record = {key: _json_safe(merge.get(key)) for key in MERGE_REVIEW_KEYS}
    return record


def _request_issued(outcome: str, decision: Any) -> bool | None:
    """Whether one request left the Runtime for this job, or None when unknown."""
    if outcome in _REQUEST_ATTEMPTED_OUTCOMES:
        return True
    if decision is None:
        # A local decision (no_target / await_resource / await_cooldown / ...)
        # never sent a request, but a stop can cancel a job mid-flight.
        return None if outcome in _UNCERTAIN_REQUEST_OUTCOMES else False
    return getattr(decision, "status", None) != "skipped_no_targets"


def _sample_age_ms(elapsed_ms: int | None, latency_ms: int | None, request_issued: bool | None) -> int | None:
    """Age of the source sample when the job's work began (OD-22, 500 ms gate).

    ``elapsed_ms`` runs from the sample's observation to the job record and
    ``latency_ms`` is the API round trip inside it, so subtracting it leaves how
    long the sample waited before the request left the Runtime. A job that sent
    no request has no latency to subtract and reports the age at the moment it
    concluded, and a job whose request failed has no measured latency at all, so
    its age is reported as ``None`` instead of being guessed.
    """
    if elapsed_ms is None:
        return None
    if request_issued is True and latency_ms is None:
        return None
    return max(0, elapsed_ms - (latency_ms or 0))


def _elapsed_ms(started_at_utc: str | None, finished_at_utc: str | None) -> int | None:
    """Milliseconds between two UTC timestamps, or None when either is unusable."""
    start = _parse_utc(started_at_utc)
    finish = _parse_utc(finished_at_utc)
    if start is None or finish is None:
        return None
    return max(0, int(round((finish - start).total_seconds() * 1000)))


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def trace_schema_version(event: Any) -> int | None:
    """Return the schema version of one Trace record, or None when it is not one.

    Version 1 is the historical one-record-per-cycle schema and version 2 is the
    runtime event schema; each is validated against its own shape and the two are
    never converted into each other, so a legacy cycle is never read as a branch
    event. Both the reader and the writer's "may I replace this file" check use
    this single definition.
    """
    if not isinstance(event, Mapping) or type(event.get("schema_version")) is not int:
        return None
    if not isinstance(event.get("run_id"), str):
        return None
    version = event["schema_version"]
    if version == 1:
        cycle = event.get("cycle")
        return 1 if isinstance(cycle, int) and not isinstance(cycle, bool) else None
    if version == SCHEMA_VERSION_V2:
        if event.get("event") not in RUNTIME_EVENT_NAMES:
            return None
        sequence = event.get("event_sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1:
            return SCHEMA_VERSION_V2
    return None


class TraceRecorder:
    """Create a new JSONL file exclusively and flush each complete event."""

    def __init__(self, path: str | Path):
        if not path:
            raise ValueError("A Trace path is required.")
        self.path = Path(path)
        self._lock = Lock()
        try:
            if self.path.is_symlink():
                raise TraceWriteError("Trace path is a symbolic link; choose a direct file path.")
            if self.path.exists():
                self._validate_existing_trace()
                self._file = self.path.open("w", encoding="utf-8", newline="\n")
            else:
                try:
                    self._file = self.path.open("x", encoding="utf-8", newline="\n")
                except FileExistsError:
                    self._validate_existing_trace()
                    self._file = self.path.open("w", encoding="utf-8", newline="\n")
        except TraceWriteError:
            raise
        except OSError as exc:
            raise TraceWriteError(_safe_file_error(exc, operation="create")) from exc

    def _validate_existing_trace(self) -> None:
        if not self.path.is_file():
            raise TraceWriteError("Trace path exists but is not a regular file; existing content was left unchanged.")
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                first_line = stream.readline()
        except (OSError, UnicodeError) as exc:
            raise TraceWriteError(_safe_file_error(exc, operation="read existing")) from exc
        if not first_line.strip():
            return
        try:
            event = json.loads(first_line)
        except json.JSONDecodeError as exc:
            raise TraceWriteError("Existing file is not a recognizable JEV Trace; existing content was left unchanged.") from exc
        if trace_schema_version(event) is None:
            raise TraceWriteError("Existing file is not a recognizable JEV Trace; existing content was left unchanged.")

    def write_event(self, event: Mapping[str, Any]) -> None:
        if not isinstance(event, Mapping):
            raise TraceWriteError("Trace event must be an object.")
        try:
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise TraceWriteError("Trace event is not valid JSON data.") from exc
        try:
            with self._lock:
                self._file.write(line + "\n")
                self._file.flush()
        except OSError as exc:
            raise TraceWriteError(_safe_file_error(exc, operation="write")) from exc

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                try:
                    self._file.close()
                except OSError as exc:
                    raise TraceWriteError(_safe_file_error(exc, operation="close")) from exc

    def __enter__(self) -> "TraceRecorder":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def _safe_file_error(error: OSError, *, operation: str) -> str:
    if isinstance(error, FileExistsError):
        return "Trace file already exists; choose a new path. Existing content was not overwritten."
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return "Trace folder does not exist or the path is invalid; choose a file inside an existing folder."
    if isinstance(error, PermissionError):
        return f"Permission denied while trying to {operation} the Trace file."
    if isinstance(error, IsADirectoryError):
        return "Trace path names a folder, not a file; choose a new file path."
    return f"Could not {operation} the Trace file ({type(error).__name__}); check file access and available disk space."


__all__ = [
    "DISCARDED_OUTCOME",
    "EVENT_ACTION_RESULT",
    "EVENT_JOB_END",
    "EVENT_JOB_START",
    "EVENT_PROPOSAL_DISCARDED",
    "EVENT_REQUEST_RESULT",
    "EVENT_RUNTIME_STOP",
    "EXECUTION_OUTCOMES",
    "MERGE_REVIEW_KEYS",
    "RELIABLE_OUTCOMES",
    "RUNTIME_EVENT_NAMES",
    "SCHEMA_VERSION_V2",
    "RuntimeEventBuilder",
    "TraceRecorder",
    "TraceWriteError",
    "build_trace_event",
    "summarize_jev_state",
    "summarize_strategy",
    "trace_schema_version",
]


def _select_scalars(value, keys):
    if not isinstance(value, Mapping): return None
    return {key: _json_safe(value.get(key)) if value.get(key) is None or isinstance(value.get(key), (str, bool, int, float)) else None for key in keys}


def _intent_record(value):
    return _select_scalars(value, ("type_name",))


def _actual_request_state(decision, jev_state, branch, issued):
    actual = getattr(decision, "request_state", None)
    if not isinstance(actual, Mapping): actual = _model_input_state(jev_state, branch, issued)
    if not isinstance(actual, Mapping): return None
    result = {"sun": _safe_int(actual.get("sun"))}
    record_fields = {
        "cards": ("type_name", "cost", "payable", "shortfall", "usable", "cooldown_ready", "description_en", "production_currency", "role"),
        "plants": ("type_name", "row", "col", "hp", "role", "description_en"),
        "zombies": ("type_name", "row", "proximity", "armor"),
        "items": ("type_code", "type_name", "count"),
        "observed_lanes": ("row", "threat", "crowd", "composition", "attacker_count", "has_defender"),
        "lane_composition": ("row", "resource", "attacker", "defender"),
    }
    for field, keys in record_fields.items():
        if field in actual:
            value = actual[field]
            result[field] = [_select_scalars(record, keys) for record in value if isinstance(record, Mapping)] if isinstance(value, list) else None
    counts = actual.get("plant_counts")
    from configs.plant_catalog import PLANTS
    names = {plant.name for plant in PLANTS}
    result["plant_counts"] = {key: _safe_int(value) for key, value in counts.items() if key in names} if isinstance(counts, Mapping) else None
    board = actual.get("board")
    cells = board.get("cells") if isinstance(board, Mapping) else None
    direction = board.get("column_direction") if isinstance(board, Mapping) else None
    result["board"] = {
        "cells": [[cell if cell is None or isinstance(cell, bool) or isinstance(cell, str) and (cell == "unknown" or cell.startswith("plant:") and cell[6:] in names) else "unknown" for cell in row] for row in cells if isinstance(row, list)] if isinstance(cells, list) else None,
        "column_direction": {
            "house_side_col": _safe_int(direction.get("house_side_col")),
            "zombie_side_col": _safe_int(direction.get("zombie_side_col")),
            "increasing_col_moves_toward_zombies": direction.get("increasing_col_moves_toward_zombies") if isinstance(direction.get("increasing_col_moves_toward_zombies"), bool) else None,
            "geometry": _safe_text(direction.get("geometry")),
        } if isinstance(direction, Mapping) else None,
    } if isinstance(board, Mapping) else None
    result["waves"] = _select_scalars(actual.get("waves"), ("wave", "total_waves"))
    catalog = actual.get("catalog_context")
    abilities = catalog.get("zombie_abilities") if isinstance(catalog, Mapping) else None
    plant_abilities = catalog.get("plant_abilities") if isinstance(catalog, Mapping) else None
    result["catalog_context"] = {
        "zombie_abilities": [_select_scalars(record, ("type_name", "description_en")) for record in abilities if isinstance(record, Mapping)] if isinstance(abilities, list) else [],
        "plant_abilities": [_select_scalars(record, ("type_name", "description_en", "role")) for record in plant_abilities if isinstance(record, Mapping)] if isinstance(plant_abilities, list) else [],
    }
    if "current_intent" in actual: result["current_intent"] = _intent_record(actual.get("current_intent"))
    if "last_actual_result" in actual: result["last_actual_result"] = _select_scalars(actual.get("last_actual_result"), ("action", "type_name", "row", "col", "outcome", "status"))
    return result
