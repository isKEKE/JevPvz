"""Validate TypeSafe typed answers and merge them into one code-side decision.

Two families live here. :func:`combine_plant_decision` and
:func:`combine_collect_decision` merge the T4 fan-out answers with explicit,
unit-testable rules. The plant merge has no absolute gate (OD-41): the placement
Choice is taken as the model's argmax and the model's own discard option decides
whether to wait. The collect merge compares its single Noul with the pinned
:data:`jev.questions.COLLECT_ACT_THRESHOLD` (OD-42). In both, a Choice
``confidence`` is recorded for audit but never compared with a threshold --
official guidance is explicit that choosing the best option means taking the
highest option, not setting a confidence threshold.

:func:`reconcile_router` and :func:`validate_action_answers` are the P02
historical global-router/action contracts. The asynchronous Runtime no longer
calls them; they are kept as P02 evidence and for the synchronous ``JevClient``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .config import (
    DEFAULT_ACTION_CONFIDENCE_THRESHOLD,
    DEFAULT_NOUL_CANDIDATE_THRESHOLD,
    DEFAULT_ROUTER_CONFIDENCE_THRESHOLD,
)
from .questions import (
    COLLECT_ACT_THRESHOLD,
    COLLECT_NOW_QUESTION_ID,
    DISCARD_OPTION_ID,
    PLANT_LANE_QUESTION_ID,
    PLANT_TARGET_QUESTION_ID,
    SHOVEL_TARGET_QUESTION_ID,
    DecisionQuestionSet,
    plant_lane_target_question_id,
)


ROUTER_CHOICES = frozenset({"wait", "collect", "plant", "shovel"})
ACTION_CONFIDENCE_THRESHOLD = DEFAULT_ACTION_CONFIDENCE_THRESHOLD
ROUTER_CONFIDENCE_THRESHOLD = DEFAULT_ROUTER_CONFIDENCE_THRESHOLD
NOUL_CANDIDATE_THRESHOLD = DEFAULT_NOUL_CANDIDATE_THRESHOLD

_EFFECTIVE_ACTION_BY_TARGET: dict[str, str] = {"place_plant": "plant", "shovel_cell": "shovel"}
"""The plant branch's target action -> effective action; anything else waits."""

_PLANT_LEVEL_QUESTION_IDS: tuple[str, ...] = (PLANT_TARGET_QUESTION_ID, PLANT_LANE_QUESTION_ID)
"""The question ids that make up the placement layer, never the shovel layer."""


class JevDecisionError(ValueError):
    """Raised when a typed response does not match the declared questions."""


@dataclass(frozen=True)
class JevRouterDecision:
    noul_probabilities: dict[str, float]
    candidates: tuple[str, ...]
    choice: str
    confidence: float
    probabilities: dict[str, float]
    effective_action: str
    fallback_reason: str | None
    model: str | None
    usage: dict[str, int | None]
    latency_ms: int
    question_summary: dict[str, Any]
    noul_candidate_threshold: float = NOUL_CANDIDATE_THRESHOLD
    confidence_threshold: float = ROUTER_CONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class JevActionDecision:
    intent: str
    effective_action: str
    target: dict[str, Any] | None
    answers: dict[str, dict[str, Any]]
    fallback_reason: str | None
    status: str
    model: str | None
    usage: dict[str, int | None]
    latency_ms: int
    question_summary: dict[str, Any]
    confidence_threshold: float = ACTION_CONFIDENCE_THRESHOLD
    cohort: tuple[dict[str, Any], ...] = ()
    management: dict[str, Any] | None = None
    request_state: dict[str, Any] | None = None
    source_intent_version: int | None = None
    source_intent: dict[str, Any] | None = None
    source_cycle: int | None = None
    component_errors: tuple[str, ...] = ()


def reconcile_router(
    response: Any,
    *,
    noul_candidate_threshold: float = NOUL_CANDIDATE_THRESHOLD,
    confidence_threshold: float = ROUTER_CONFIDENCE_THRESHOLD,
    latency_ms: int = 0,
    question_summary: dict[str, Any] | None = None,
) -> JevRouterDecision:
    _require_threshold(noul_candidate_threshold)
    _require_threshold(confidence_threshold)
    answers = getattr(response, "answers", None)
    if not isinstance(answers, Mapping):
        raise JevDecisionError("TypeSafe response has no typed answer mapping.")

    noul_keys = {
        "should_collect": "collect",
        "should_plant": "plant",
        "should_shovel": "shovel",
    }
    noul_probabilities: dict[str, float] = {}
    for question_id, action in noul_keys.items():
        answer = answers.get(question_id)
        probability = getattr(answer, "noul", None) if getattr(answer, "type", None) == "noul" else None
        if not _probability(probability):
            raise JevDecisionError(f"TypeSafe response has an invalid {question_id} answer.")
        noul_probabilities[action] = float(probability)

    choice_answer = answers.get("next_action")
    if getattr(choice_answer, "type", None) != "choice":
        raise JevDecisionError("TypeSafe response has no typed next_action Choice.")
    choice = getattr(choice_answer, "choice", None)
    confidence = getattr(choice_answer, "confidence", None)
    probabilities = _choice_probabilities(choice_answer, ROUTER_CHOICES)
    if choice not in ROUTER_CHOICES or not _probability(confidence):
        raise JevDecisionError("TypeSafe response has an invalid next_action Choice.")
    if probabilities[choice] + 1e-9 < max(probabilities.values()):
        raise JevDecisionError("TypeSafe next_action Choice is not the highest-probability option.")

    candidates = tuple(
        action for action, probability in noul_probabilities.items()
        if probability >= noul_candidate_threshold
    )
    fallback_reason = None
    if confidence < confidence_threshold:
        effective_action = "wait"
        fallback_reason = "router_confidence_below_threshold"
    elif choice == "wait":
        effective_action = "wait"
    elif choice not in candidates:
        effective_action = "wait"
        fallback_reason = "selected_action_not_a_noul_candidate"
    else:
        effective_action = choice

    return JevRouterDecision(
        noul_probabilities=noul_probabilities,
        candidates=candidates,
        choice=choice,
        confidence=float(confidence),
        probabilities=probabilities,
        effective_action=effective_action,
        fallback_reason=fallback_reason,
        model=_string_or_none(getattr(response, "model", None)),
        usage=_usage_record(getattr(response, "usage", None)),
        latency_ms=max(0, int(latency_ms)),
        question_summary=question_summary or {},
        noul_candidate_threshold=float(noul_candidate_threshold),
        confidence_threshold=float(confidence_threshold),
    )


def validate_action_answers(
    response: Any,
    *,
    intent: str,
    option_targets: Mapping[str, Mapping[str, Mapping[str, Any]]],
    confidence_threshold: float = ACTION_CONFIDENCE_THRESHOLD,
    latency_ms: int = 0,
    question_summary: dict[str, Any] | None = None,
) -> JevActionDecision:
    _require_threshold(confidence_threshold)
    if intent not in {"collect", "plant", "shovel"}:
        raise JevDecisionError("Specialized Action intent is not supported.")
    answers = getattr(response, "answers", None)
    if not isinstance(answers, Mapping) or not option_targets:
        raise JevDecisionError("TypeSafe Action response has no expected typed answers.")

    selected: dict[str, dict[str, Any]] = {}
    answer_records: dict[str, dict[str, Any]] = {}
    fallback_reason = None
    for question_id, targets in option_targets.items():
        answer = answers.get(question_id)
        if getattr(answer, "type", None) != "choice":
            raise JevDecisionError(f"TypeSafe Action response has no typed {question_id} Choice.")
        choice = getattr(answer, "choice", None)
        confidence = getattr(answer, "confidence", None)
        probabilities = _choice_probabilities(answer, frozenset(targets))
        if choice not in targets or not _probability(confidence):
            raise JevDecisionError(f"TypeSafe Action response has an invalid {question_id} Choice.")
        if probabilities[choice] + 1e-9 < max(probabilities.values()):
            raise JevDecisionError(f"TypeSafe Action {question_id} Choice is not the highest-probability option.")
        answer_records[question_id] = {
            "choice": choice,
            "confidence": float(confidence),
            "probabilities": probabilities,
        }
        selected[question_id] = dict(targets[choice])
        if confidence < confidence_threshold:
            fallback_reason = f"{question_id}_confidence_below_threshold"

    if fallback_reason is not None:
        effective_action = "wait"
        target = None
        status = "low_confidence"
    else:
        target = _combine_action_targets(intent, selected)
        effective_action = intent
        status = "selected"

    return JevActionDecision(
        intent=intent,
        effective_action=effective_action,
        target=target,
        answers=answer_records,
        fallback_reason=fallback_reason,
        status=status,
        model=_string_or_none(getattr(response, "model", None)),
        usage=_usage_record(getattr(response, "usage", None)),
        latency_ms=max(0, int(latency_ms)),
        question_summary=question_summary or {},
        confidence_threshold=float(confidence_threshold),
    )


def combine_plant_decision(
    response: Any,
    *,
    question_set: DecisionQuestionSet,
    latency_ms: int = 0,
    question_summary: dict[str, Any] | None = None,
) -> JevActionDecision:
    """Merge one plant fan-out response into a single consistent target or wait.

    There is no absolute plant gate (OD-41, R31): the model itself decides
    whether to act, by choosing a placement or its own discard option. The rules,
    all implemented here so they can be unit-tested in one place:

    1. Relative choice (Choice, argmax): the selected option is the model's own
       argmax, which must be offered and must not be the discard option. Its
       ``confidence`` is recorded for Trace/audit but is never compared with a
       threshold: a 130-option Choice distribution is flat by construction, so a
       confidence gate would turn nearly every planting decision into a local
       wait, and the official guidance for choosing the best option is to take
       the highest option rather than to set a threshold.
    2. The discard option is the only local wait: when its argmax is
       ``none_of_the_above`` (or no placement was selected), the branch waits.
       The model's own ``best``/``discard`` probabilities and their ``margin``
       are recorded as facts for review (V41, V57) and are never gated. The wait
       is strict: a placement is taken only when its ``best`` probability is
       *greater* than the discard option's, so a flat tie (``margin == 0``) waits
       instead of dispatching (R31, OD-41).
    3. One action per decision (CD-08): the request carries at most one shovel
       layer next to the placement layer, and when both layers resolve to a target
       the removal wins -- the placement is dropped, and ``merge`` records
       ``shovel_overrode_placement`` plus the dropped option id instead of losing
       it silently. The shovel layer obeys the very same strict rule as the
       placement layer: its own argmax must not be its discard option and must be
       *strictly* above that discard option's probability (δ=0). The intent stays
       ``plant`` (the proposal and its branch do not change, and the scheduler
       re-reviews the target's action); only ``effective_action`` reads
       ``shovel``.
    """
    if question_set.intent != "plant":
        raise JevDecisionError("combine_plant_decision requires a plant question set.")
    answers = getattr(response, "answers", None)
    if not isinstance(answers, Mapping):
        raise JevDecisionError("TypeSafe response has no typed answer mapping.")

    choice_records, probabilities, candidates_by_option = _read_choice_levels(answers, question_set)
    records: dict[str, dict[str, Any]] = {}
    records.update(choice_records)

    merge: dict[str, Any] = {
        "target_choice_rule": "argmax",
        "chosen_option": None,
        "selected_option": None,
        "reranked": False,
        "best_available_probability": None,
        "best_option": None,
        "best_probability": None,
        "discard_probability": None,
        "margin": None,
        "shovel_option": None,
        "shovel_selected": False,
        "shovel_discarded": None,
        "shovel_overrode_placement": False,
        "overridden_placement_option": None,
        "shovel_best_option": None,
        "shovel_best_probability": None,
        "shovel_discard_probability": None,
        "shovel_margin": None,
    }
    records["merge"] = merge

    def _decision(
        status: str, fallback_reason: str | None, target: dict[str, Any] | None
    ) -> JevActionDecision:
        merge["status"] = status
        merge["fallback_reason"] = fallback_reason
        action = None if target is None else target.get("action")
        return JevActionDecision(
            intent="plant",
            effective_action=_EFFECTIVE_ACTION_BY_TARGET.get(action, "wait"),
            target=target,
            answers=records,
            fallback_reason=fallback_reason,
            status=status,
            model=_string_or_none(getattr(response, "model", None)),
            usage=_usage_record(getattr(response, "usage", None)),
            latency_ms=max(0, int(latency_ms)),
            question_summary=question_summary or {},
        )

    chosen_option, confidence, deciding = _chosen_plant_option(question_set, choice_records)
    best_probability: float | None = None
    discard_probability: float | None = None
    if deciding is not None:
        option_probabilities = deciding["probabilities"]
        best_option = max(option_probabilities, key=option_probabilities.get)
        best_probability = option_probabilities[best_option]
        discard_probability = option_probabilities.get(DISCARD_OPTION_ID, 0.0)
        merge["best_option"] = best_option
        merge["best_probability"] = best_probability
        merge["discard_probability"] = discard_probability
        merge["margin"] = best_probability - discard_probability
    merge["chosen_option"] = chosen_option
    merge["confidence"] = confidence

    placement: Mapping[str, Any] | None = None
    placement_reason = "no_placement_option_was_selected"
    if chosen_option is None:
        placement_reason = "no_placement_option_was_selected"
    elif chosen_option == DISCARD_OPTION_ID:
        placement_reason = "model_selected_the_discard_option"
    elif (
        best_probability is not None
        and discard_probability is not None
        and best_probability <= discard_probability + 1e-9
    ):
        placement_reason = "discard_option_tied_or_won"
    else:
        placement = candidates_by_option.get(chosen_option)
        if placement is None:
            placement_reason = "selected_option_has_no_placement"

    shovel_option, shovel_target = _shovel_selection(choice_records, candidates_by_option, merge)
    if shovel_target is not None:
        merge["selected_option"] = shovel_option
        merge["best_available_probability"] = probabilities.get(shovel_option)
        if placement is not None:
            merge["shovel_overrode_placement"] = True
            merge["overridden_placement_option"] = chosen_option
        return _decision("selected", None, dict(shovel_target))
    if placement is not None:
        merge["selected_option"] = chosen_option
        merge["best_available_probability"] = probabilities.get(chosen_option)
        return _decision("selected", None, _plant_target(placement))
    return _decision("model_wait", placement_reason, None)


def _shovel_selection(
    choice_records: Mapping[str, Mapping[str, Any]],
    candidates_by_option: Mapping[str, Mapping[str, Any]],
    merge: dict[str, Any],
) -> tuple[str | None, Mapping[str, Any] | None]:
    """Resolve the optional shovel layer into one removal target, or nothing.

    The layer is judged by the placement layer's own strict rule (OD-41, δ=0): its
    argmax must not be the layer's discard option and must be *strictly* above that
    discard option's probability, so a flat tie waits instead of clearing a cell.
    ``merge`` receives the layer's own best/discard facts plus
    ``shovel_selected``/``shovel_discarded``, so a reviewer can tell "no removal
    layer was asked" (``None``) from "the removal layer was discarded".
    """
    record = choice_records.get(SHOVEL_TARGET_QUESTION_ID)
    if record is None:
        return None, None
    option_probabilities = record["probabilities"]
    choice = str(record["choice"])
    best_option = max(option_probabilities, key=option_probabilities.get)
    best_probability = option_probabilities[best_option]
    discard_probability = option_probabilities.get(DISCARD_OPTION_ID, 0.0)
    merge["shovel_option"] = choice
    merge["shovel_best_option"] = best_option
    merge["shovel_best_probability"] = best_probability
    merge["shovel_discard_probability"] = discard_probability
    merge["shovel_margin"] = best_probability - discard_probability
    target = None if choice == DISCARD_OPTION_ID else candidates_by_option.get(choice)
    if (
        target is None
        or target.get("action") != "shovel_cell"
        or best_probability <= discard_probability + 1e-9
    ):
        merge["shovel_discarded"] = True
        return None, None
    merge["shovel_selected"] = True
    merge["shovel_discarded"] = False
    return choice, target


def combine_collect_decision(
    response: Any,
    *,
    question_set: DecisionQuestionSet,
    latency_ms: int = 0,
    question_summary: dict[str, Any] | None = None,
) -> JevActionDecision:
    """Merge one collect fan-out response into a single collect target or wait.

    ``should_collect_now`` is compared with the reviewable fixed anchor
    :data:`jev.questions.COLLECT_ACT_THRESHOLD` (OD-42, R32), never with the P02
    ``JEV_NOUL_CANDIDATE_THRESHOLD``, so the collect conclusion cannot drift with
    the P02 gate config. The merge records the probability and the threshold it
    was actually compared with.
    """
    if question_set.intent != "collect":
        raise JevDecisionError("combine_collect_decision requires a collect question set.")
    answers = getattr(response, "answers", None)
    if not isinstance(answers, Mapping):
        raise JevDecisionError("TypeSafe response has no typed answer mapping.")

    should_collect = _noul_probability(answers, COLLECT_NOW_QUESTION_ID)
    records = {COLLECT_NOW_QUESTION_ID: {"noul": should_collect}}
    selected = should_collect >= COLLECT_ACT_THRESHOLD and bool(question_set.candidates)
    records["merge"] = {"should_collect_probability": should_collect, "noul_candidate_threshold": COLLECT_ACT_THRESHOLD,
                        "authorized_count": len(question_set.candidates) if selected else 0}
    return JevActionDecision(
        intent="collect", effective_action="collect" if selected else "wait",
        target=dict(question_set.candidates[0]) if selected else None,
        answers=records, fallback_reason=None if selected else "noul_gate_below_threshold",
        status="selected" if selected else "model_wait", model=_string_or_none(getattr(response, "model", None)),
        usage=_usage_record(getattr(response, "usage", None)), latency_ms=max(0, int(latency_ms)),
        question_summary=question_summary or {}, cohort=tuple(dict(target) for target in question_set.candidates) if selected else (),
    )


def _read_choice_levels(
    answers: Mapping[str, Any], question_set: DecisionQuestionSet
) -> tuple[dict[str, dict[str, Any]], dict[str, float], dict[str, Mapping[str, Any]]]:
    """Validate every offered Choice answer and flatten it for the merge.

    Returns the trace records per question, the option probabilities keyed by
    option id, and the target each option binds to. The discard option binds to
    nothing, and so does a lane option (which names no plant type and no action).
    """
    records: dict[str, dict[str, Any]] = {}
    probabilities: dict[str, float] = {}
    candidates: dict[str, Mapping[str, Any]] = {}
    for level in question_set.choice_levels:
        answer = answers.get(level.question_id)
        if getattr(answer, "type", None) != "choice":
            raise JevDecisionError(f"TypeSafe response has no typed {level.question_id} Choice.")
        choice = getattr(answer, "choice", None)
        confidence = getattr(answer, "confidence", None)
        option_probabilities = _choice_probabilities(answer, frozenset(level.targets))
        if choice not in level.targets or not _probability(confidence):
            raise JevDecisionError(f"TypeSafe response has an invalid {level.question_id} Choice.")
        if option_probabilities[choice] + 1e-9 < max(option_probabilities.values()):
            raise JevDecisionError(
                f"TypeSafe {level.question_id} Choice is not the highest-probability option."
            )
        records[level.question_id] = {
            "choice": choice,
            "confidence": float(confidence),
            "probabilities": option_probabilities,
            "level": level.level,
        }
        for option_id, probability in option_probabilities.items():
            probabilities[option_id] = probability
            target = level.targets[option_id]
            # Only a complete type/row/column placement or a removal cell is a
            # bindable target; the discard option and a lane option (which names no
            # plant type) are not.
            if target and ("type_name" in target or target.get("action") == "shovel_cell"):
                candidates[option_id] = target
    return records, probabilities, candidates


def _chosen_plant_option(
    question_set: DecisionQuestionSet, choice_records: Mapping[str, Mapping[str, Any]]
) -> tuple[str | None, float, Mapping[str, Any] | None]:
    """Resolve the selected placement option and the level record it came from.

    The placement layer is found by its own question ids, never by position: a
    request whose placement layer is empty asks the shovel layer alone, and that
    layer must not be read as a placement. The returned record's ``probabilities``
    are the deciding level's own distribution, so its ``best``/``discard`` facts can
    be reviewed without mixing in the other level of a split chain.
    """
    first = next(
        (
            level
            for level in question_set.choice_levels
            if level.question_id in _PLANT_LEVEL_QUESTION_IDS
        ),
        None,
    )
    if first is None:
        return None, 0.0, None
    record = choice_records.get(first.question_id)
    if record is None:
        return None, 0.0, None
    choice = str(record["choice"])
    confidence = float(record["confidence"])
    if not question_set.split or choice == DISCARD_OPTION_ID:
        return choice, confidence, record
    lane = first.targets.get(choice, {}).get("row")
    if not isinstance(lane, int):
        raise JevDecisionError("The plant lane Choice did not map to a lane.")
    deeper = choice_records.get(plant_lane_target_question_id(lane))
    if deeper is None:
        raise JevDecisionError("The plant lane Choice points to a lane that was not asked.")
    return str(deeper["choice"]), float(deeper["confidence"]), deeper


def _noul_probability(answers: Mapping[str, Any], question_id: str) -> float:
    answer = answers.get(question_id)
    probability = getattr(answer, "noul", None) if getattr(answer, "type", None) == "noul" else None
    if not _probability(probability):
        raise JevDecisionError(f"TypeSafe response has an invalid {question_id} answer.")
    return float(probability)


def _plant_target(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action": "place_plant",
        "type_name": candidate["type_name"],
        "row": candidate["row"],
        "col": candidate["col"],
    }


def _combine_action_targets(intent: str, selected: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if intent == "collect":
        target = selected.get("item")
        if target is None or target.get("action") != "collect_item":
            raise JevDecisionError("Collect Choice did not map to a collect target.")
        return dict(target)
    if intent == "plant":
        plant = selected.get("plant_type")
        cell = selected.get("cell")
        if plant is None or cell is None or "type_name" not in plant or "row" not in cell or "col" not in cell:
            raise JevDecisionError("Plant Choices did not map to a complete target.")
        return {"action": "place_plant", "type_name": plant["type_name"], "row": cell["row"], "col": cell["col"]}
    cell = selected.get("cell")
    if cell is None or "row" not in cell or "col" not in cell:
        raise JevDecisionError("Shovel Choice did not map to a cell target.")
    return {"action": "shovel_cell", "row": cell["row"], "col": cell["col"]}


def _choice_probabilities(answer: Any, expected_choices: frozenset[str]) -> dict[str, float]:
    values = getattr(answer, "probabilities", None)
    if not isinstance(values, Mapping) or set(values) != expected_choices:
        raise JevDecisionError("TypeSafe Choice probabilities do not match the declared criteria.")
    normalized = {str(key): float(value) for key, value in values.items() if _probability(value)}
    if len(normalized) != len(values) or abs(sum(normalized.values()) - 1.0) > 0.05:
        raise JevDecisionError("TypeSafe Choice probabilities are invalid.")
    return normalized


def _probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def _require_threshold(value: Any) -> None:
    if not _probability(value):
        raise JevDecisionError("Decision threshold must be a finite number from 0 through 1.")


def _usage_record(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {"input_tokens": None, "output_tokens": None}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, Mapping):
        return {"input_tokens": None, "output_tokens": None}
    result: dict[str, int | None] = {}
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        result[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return result


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "ACTION_CONFIDENCE_THRESHOLD",
    "JevActionDecision",
    "JevDecisionError",
    "JevRouterDecision",
    "NOUL_CANDIDATE_THRESHOLD",
    "ROUTER_CONFIDENCE_THRESHOLD",
    "combine_collect_decision",
    "combine_plant_decision",
    "reconcile_router",
    "validate_action_answers",
]
