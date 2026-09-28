"""Typed TypeSafe requests: one fan-out request per branch decision."""

from __future__ import annotations

import asyncio
import math
import sys
import time
from collections import defaultdict
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass
from os import PathLike
from typing import Any, Callable, Mapping

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, TypeSafeClient

from configs.item_catalog import item_name
from configs.plant_catalog import plant_info
from configs.zombie_catalog import zombie_info
from .config import (
    DEFAULT_MODEL_NAME,
    DEFAULT_NOUL_CANDIDATE_THRESHOLD,
    RuntimeConfig,
    load_jev_thresholds,
    load_typesafe_environment,
    runtime_environment,
    use_configured_http_proxy_fallback,
)
from .decision import (
    JevActionDecision,
    JevDecisionError,
    JevRouterDecision,
    combine_collect_decision,
    combine_plant_decision,
    reconcile_router,
    validate_action_answers,
)
from .questions import (
    ACTION_CONFIDENCE_THRESHOLD,
    COLLECT_NOW_QUESTION_ID,
    COLLECT_STATE_FIELDS,
    COLLECT_TARGET_QUESTION_ID,
    DISCARD_OPTION_ID,
    MAX_CHOICE_OPTIONS,
    PLANT_LANE_QUESTION_ID,
    PLANT_STATE_FIELDS,
    PLANT_TARGET_QUESTION_ID,
    ROW_COUNT,
    ChoiceLevel,
    DecisionQuestionSet,
    collect_now_question,
    collect_option_criteria,
    collect_option_id,
    collect_target_question,
    discard_option_criteria,
    economy_question,
    lane_option_criteria,
    plant_lane_option_id,
    plant_lane_question,
    plant_lane_target_question,
    plant_lane_target_question_id,
    plant_option_criteria,
    plant_option_id,
    plant_row_question,
    plant_target_options,
    plant_target_question,
    question_summary,
)
from .strategy import (
    BRANCH_COLLECT,
    BRANCH_PLANT,
    StrategySignals,
    build_plant_candidates,
    evaluate_strategy,
)


REQUEST_TIMEOUT_SECONDS = 15.0
GLOBAL_IN_FLIGHT_LIMIT = 2


class JevApiError(RuntimeError):
    """A sanitized TypeSafe request/configuration error."""

    def __init__(self, exception_type: str):
        self.exception_type = exception_type
        super().__init__(f"TypeSafe request failed ({exception_type}); response details were suppressed.")


@dataclass(frozen=True)
class ActionQuestionSet:
    intent: str
    questions: dict[str, Any]
    option_targets: dict[str, dict[str, dict[str, Any]]]
    summary: dict[str, Any]


def build_typesafe_state(
    jev_state: Mapping[str, Any],
    *,
    branch: str | None = None,
    signals: StrategySignals | None = None,
    all_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build only the facts the requested branch's questions need (R20, V31).

    The JEV projection is never sent as a whole: a plant request carries the
    pruned :data:`jev.questions.PLANT_STATE_FIELDS` and a collect request the
    pruned :data:`jev.questions.COLLECT_STATE_FIELDS`. Numbers, counts, and
    comparisons are computed by code (:mod:`jev.strategy`) and placed here as
    fact fields, so no question has to ask the model to arithmetic.

    Called without a branch the function returns the shared observed-ability
    context only; :func:`jev.trace.build_trace_event` reads exactly that key.
    :class:`JevClient` keeps its own P02 legacy state builder.
    """
    if not isinstance(jev_state, Mapping):
        raise ValueError("JEV State must be a mapping.")
    catalog_context = {
        "zombie_abilities": _zombie_ability_context(jev_state),
        "plant_abilities": _plant_ability_context(jev_state),
    }
    if branch is None:
        return {"catalog_context": catalog_context}
    from .strategy import management_facts, threat_label_facts
    state = threat_label_facts(management_facts(jev_state, all_state))
    state["catalog_context"] = catalog_context
    if branch == BRANCH_COLLECT:
        counts = {}
        for item in jev_state.get("items") or []:
            if isinstance(item, Mapping) and item_name(item.get("type_code")) == item.get("type_name"):
                key = (item.get("type_code"), item.get("type_name"))
                counts[key] = counts.get(key, 0) + 1
        state["items"] = [{"type_code": code, "type_name": name, "count": count} for (code, name), count in sorted(counts.items())]
    if branch in (BRANCH_PLANT, BRANCH_COLLECT): return state
    raise ValueError(f"unknown branch: {branch!r}")


def _zombie_ability_context(jev_state: Mapping[str, Any]) -> list[dict[str, str]]:
    """Abilities of the zombie types actually present in this sample (R7).

    Only types that appear in the sample and resolve to a known catalog entry
    with a non-empty English description are described; no ability is inferred
    for a type that is not there.
    """
    zombie_records = jev_state.get("zombies")
    context: list[dict[str, str]] = []
    seen: set[int] = set()
    if not isinstance(zombie_records, list):
        return context
    for zombie in zombie_records:
        if not isinstance(zombie, Mapping):
            continue
        code = zombie.get("type_code")
        info = zombie_info(code)
        if (
            info is None
            or info.name != zombie.get("type_name")
            or code in seen
            or not info.description_en.strip()
        ):
            continue
        seen.add(code)
        context.append({"type_name": info.name, "description_en": info.description_en})
    return context


def _plant_ability_context(jev_state: Mapping[str, Any]) -> list[dict[str, str]]:
    """Catalog abilities of the plant types in hand or already planted (R49).

    Only a type that is present in this sample and resolves to a catalog entry
    whose name equals its projected type name with a non-empty English
    description is described; a type that is not in hand or on the board is
    never inferred, and an unknown mod type is left out instead of invented.
    Entries are deduplicated and sorted by type name so two recordings of the
    same sample read the same.
    """
    context: dict[str, dict[str, str]] = {}
    for field in ("cards", "plants"):
        records = jev_state.get(field)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, Mapping):
                continue
            info = plant_info(record.get("type_code"))
            type_name = record.get("type_name")
            if (
                info is None
                or info.name != type_name
                or not info.description_en.strip()
            ):
                continue
            context[type_name] = {
                "type_name": info.name,
                "description_en": info.description_en,
                "role": info.role,
            }
    return [context[type_name] for type_name in sorted(context)]


def _collect_item_facts(jev_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every collectable visible item as ``index``/``type_name``/``x``/``y``.

    An item is collectable when its type code resolves to the projected type
    name and its coordinates are finite; anything else is not offered.
    """
    items = jev_state.get("items")
    if not isinstance(items, list):
        return []
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        code, name = item.get("type_code"), item.get("type_name")
        x, y = item.get("x"), item.get("y")
        if (
            not _integer(code)
            or code < 0
            or not isinstance(name, str)
            or name == "unknown"
            or item_name(code) != name
            or not _finite_number(x)
            or not _finite_number(y)
        ):
            continue
        facts.append({"index": index, "type_name": name, "x": x, "y": y})
    return facts


def _legacy_projection_state(jev_state: Mapping[str, Any]) -> dict[str, Any]:
    """The P02 historical whole-projection state used by the sync ``JevClient``.

    The asynchronous Runtime never uses this form (T4 replaced it with the
    pruned per-question state above); it is kept so the P02 interface and its
    recorded evidence stay intact.
    """
    if not isinstance(jev_state, Mapping):
        raise ValueError("JEV State must be a mapping.")
    state = deepcopy(dict(jev_state))
    state["catalog_context"] = {
        "zombie_abilities": _zombie_ability_context(state),
        "plant_abilities": _plant_ability_context(state),
    }
    return state


def build_router_questions(
    noul_candidate_threshold: float = DEFAULT_NOUL_CANDIDATE_THRESHOLD,
) -> dict[str, Any]:
    """P02 historical global-router questions; no Runtime branch uses them.

    T4 replaced this phase with the per-branch fan-out sets built by
    :func:`build_plant_questions` and :func:`build_collect_questions`. The
    construct is kept (with :func:`reconcile_router`) as P02 evidence and for the
    synchronous :class:`JevClient` interface.
    """
    threshold_text = f"{noul_candidate_threshold:g}"
    return {
        "should_collect": Noul(
            instructions=f"Is collecting a currently visible item sufficiently useful to be an immediate-action candidate? The runtime treats Noul probabilities of {threshold_text} or higher as candidates.",
            criteria={"true": "Collecting is useful enough to be considered as an immediate action.", "false": "Do not consider collecting an item now."},
        ),
        "should_plant": Noul(
            instructions=f"Is planting a currently usable plant sufficiently useful to be an immediate-action candidate? The runtime treats Noul probabilities of {threshold_text} or higher as candidates.",
            criteria={"true": "Planting is useful enough to be considered as an immediate action.", "false": "Do not consider planting now."},
        ),
        "should_shovel": Noul(
            instructions=f"Is removing a current plant sufficiently useful to be an immediate-action candidate? The runtime treats Noul probabilities of {threshold_text} or higher as candidates.",
            criteria={"true": "Removing a plant is useful enough to be considered as an immediate action.", "false": "Do not consider removing a plant now."},
        ),
        "next_action": Choice(
            instructions=f"Choose one immediate action only when its matching should_collect, should_plant, or should_shovel evaluation would meet the {threshold_text} candidate threshold. Choose wait when none meets that bar. Other actions can be reconsidered after the next observation.",
            criteria={
                "wait": "Take no game action now.",
                "collect": "Collect one currently visible item.",
                "plant": "Place one currently usable plant.",
                "shovel": "Remove plants from one occupied cell.",
            },
        ),
    }


def build_action_questions(intent: str, jev_state: Mapping[str, Any]) -> ActionQuestionSet:
    """P02 historical specialized-action questions; no Runtime branch uses them.

    T4 replaced the parallel plant-type/cell form with one complete placement
    Choice, and collect with one target Choice, both built by the branch builders
    above. The construct is kept (with :func:`validate_action_answers`) as P02
    evidence and for the synchronous :class:`JevClient` interface.
    """
    if intent not in {"collect", "plant", "shovel"}:
        raise ValueError("A specialized Action requires collect, plant, or shovel intent.")
    if intent == "collect":
        return _collect_questions(jev_state)
    if intent == "plant":
        return _plant_questions(jev_state)
    return _shovel_questions(jev_state)


def _collect_questions(jev_state: Mapping[str, Any]) -> ActionQuestionSet:
    items = jev_state.get("items")
    criteria: dict[str, str] = {}
    targets: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            code, name = item.get("type_code"), item.get("type_name")
            x, y = item.get("x"), item.get("y")
            if (
                not _integer(code)
                or code < 0
                or not isinstance(name, str)
                or name == "unknown"
                or item_name(code) != name
                or not _finite_number(x)
                or not _finite_number(y)
            ):
                continue
            key = f"item_{index}"
            criteria[key] = f"Collect the visible {name.replace('_', ' ')} at sample-local item index {index}."
            targets[key] = {"action": "collect_item", "type_code": code, "type_name": name, "x": x, "y": y}
    if not criteria:
        return _empty_action_question_set("collect")
    questions = {
        "item": Choice(
            instructions="Choose one currently visible item to collect.",
            criteria=criteria,
        )
    }
    return ActionQuestionSet("collect", questions, {"item": targets}, question_summary(questions))


def _plant_questions(jev_state: Mapping[str, Any]) -> ActionQuestionSet:
    cards = jev_state.get("cards")
    usable: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, Mapping) or card.get("usable") is not True or card.get("cooldown_ready") is not True:
                continue
            code, name = card.get("type_code"), card.get("type_name")
            info = plant_info(code)
            if info is not None and info.name == name and info.description_en.strip():
                usable[name].append(card)

    type_criteria: dict[str, str] = {}
    type_targets: dict[str, dict[str, Any]] = {}
    for name, matching_cards in usable.items():
        # ActionBoundary requires a plant type to identify exactly one live card.
        if len(matching_cards) != 1:
            continue
        type_criteria[name] = plant_info(matching_cards[0]["type_code"]).description_en
        type_targets[name] = {"type_name": name}

    cells = _jev_cells(jev_state)
    cell_criteria: dict[str, str] = {}
    cell_targets: dict[str, dict[str, int]] = {}
    if cells is not None:
        for row, line in enumerate(cells):
            for col, value in enumerate(line):
                if value is None:
                    key = f"r{row}c{col}"
                    cell_criteria[key] = f"An empty, plantable board cell at zero-based row {row}, column {col}."
                    cell_targets[key] = {"row": row, "col": col}

    if not type_criteria or not cell_criteria:
        return _empty_action_question_set("plant")
    questions = {
        "plant_type": Choice(
            instructions="Choose one currently usable plant whose ability suits the current threat.",
            criteria=type_criteria,
        ),
        "cell": Choice(
            instructions="Choose one currently empty, plantable cell.",
            criteria=cell_criteria,
        ),
    }
    return ActionQuestionSet(
        "plant", questions, {"plant_type": type_targets, "cell": cell_targets}, question_summary(questions)
    )


def _shovel_questions(jev_state: Mapping[str, Any]) -> ActionQuestionSet:
    cells = _jev_cells(jev_state)
    if cells is None:
        return _empty_action_question_set("shovel")
    plants_by_cell: dict[tuple[int, int], list[str]] = defaultdict(list)
    plants = jev_state.get("plants")
    if isinstance(plants, list):
        for plant in plants:
            if not isinstance(plant, Mapping):
                continue
            row, col, name = plant.get("row"), plant.get("col"), plant.get("type_name")
            if _integer(row) and _integer(col) and isinstance(name, str):
                plants_by_cell[(row, col)].append(name.replace("_", " "))
    criteria: dict[str, str] = {}
    targets: dict[str, dict[str, int]] = {}
    for row, line in enumerate(cells):
        for col, value in enumerate(line):
            if isinstance(value, str) and value.startswith("plant:"):
                key = f"r{row}c{col}"
                names = sorted(set(plants_by_cell.get((row, col)) or [value.removeprefix("plant:")]))
                criteria[key] = f"Remove plants in zero-based row {row}, column {col}; present types: {', '.join(names)}."
                targets[key] = {"row": row, "col": col}
    if not criteria:
        return _empty_action_question_set("shovel")
    questions = {
        "cell": Choice(
            instructions="Choose one occupied board cell whose plants should be removed.",
            criteria=criteria,
        )
    }
    return ActionQuestionSet("shovel", questions, {"cell": targets}, question_summary(questions))


def _empty_action_question_set(intent: str) -> ActionQuestionSet:
    return ActionQuestionSet(intent, {}, {}, {})


def build_plant_questions(
    jev_state: Mapping[str, Any],
    *,
    signals: StrategySignals | None = None,
) -> DecisionQuestionSet:
    """Build the whole plant decision as one speculative fan-out question set.

    The set holds a single relative Choice over the complete, already validated
    placement list plus the explicit discard option; the model's own discard
    option is the only thing that decides *whether* to act, so there is no
    absolute plant gate (OD-41, R31). One plant decision costs exactly one
    ``system_one`` call.

    When ``candidates + discard`` would exceed the official
    :data:`jev.questions.MAX_CHOICE_OPTIONS` cap, the placement Choice is chained
    into a lane Choice plus one speculative Choice per lane (each inside the cap)
    instead of being sorted, shortlisted, or truncated. An empty ``questions``
    mapping means the caller must wait locally and send nothing.
    """
    resolved = signals if signals is not None else evaluate_strategy(jev_state)
    candidates = tuple(build_plant_candidates(jev_state, resolved))
    if not candidates:
        return DecisionQuestionSet("plant", {}, (), (), False, {})
    if len(resolved.rows) != ROW_COUNT:
        raise JevDecisionError("The plant request needs the five projected lanes.")
    if plant_target_options(len(candidates)):
        return _split_plant_question_set(jev_state, candidates)
    return _single_plant_question_set(jev_state, candidates)


def _same_sample_item_id(
    all_state: Mapping[str, Any] | None,
    index: int,
    type_code: Any,
    type_name: str,
) -> int | None:
    """The id of the same sample's ``items[index]``, or ``None`` when unverifiable.

    The JEV projection drops item ids on purpose (``state.projection`` picks only
    ``type_code``/``type_name``/``x``/``y``), so a collect target's identity can
    only come from the raw All State of the very sample the decision is made on.

    The record at ``index`` must agree with the projected item on both
    ``type_code`` and ``type_name``. A disagreement means the two lists do not
    line up, and then no id may be bound; the caller must not offer that item at
    all, because a target that cannot be verified here could never be verified
    again at dispatch time (OD-32).
    """
    if not isinstance(all_state, Mapping):
        return None
    items = all_state.get("items")
    if not isinstance(items, list) or not 0 <= index < len(items):
        return None
    record = items[index]
    if not isinstance(record, Mapping):
        return None
    if record.get("type_code") != type_code or record.get("type_name") != type_name:
        return None
    item_id = record.get("id")
    if not _integer(item_id) or item_id <= 0:
        return None
    return item_id


def build_collect_questions(
    jev_state: Mapping[str, Any],
    *,
    all_state: Mapping[str, Any] | None = None,
) -> DecisionQuestionSet:
    """Build the whole collect decision: one absolute gate and one target Choice.

    The Choice lists every currently visible, validated item plus the explicit
    discard option; an empty ``questions`` mapping means there is nothing to
    collect and the caller must conclude locally without a request.

    Every option binds the ``id`` of the same sample's All State item (OD-32), so
    the scheduler can re-verify that identity at dispatch time and aim at wherever
    that item is *then* instead of where it was when the model answered. The id
    stays local: it is in no option text and in no state field sent to the model,
    and the Trace has no field for it either. An item whose id cannot be resolved
    in the same sample is not offered, because such a target could never be
    verified at dispatch and asking about it would only burn a request.
    """
    targets = []
    items = jev_state.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            code, name = item.get("type_code"), item.get("type_name")
            identity = _same_sample_item_id(all_state, index, code, name)
            if identity is not None and item_name(code) == name:
                targets.append({"action": "collect_item", "item_id": identity, "type_code": code, "type_name": name})
    ids = [target["item_id"] for target in targets]
    targets = [target for target in targets if ids.count(target["item_id"]) == 1]
    # No collectable item means no collect sub-question (OD-44, R33): the shared
    # request then carries only the management questions, and the caller concludes
    # the collect component locally instead of asking a question it cannot use.
    questions = {COLLECT_NOW_QUESTION_ID: collect_now_question()} if targets else {}
    return DecisionQuestionSet("collect", questions, tuple(targets), (), False, question_summary(questions))


def _single_plant_question_set(
    jev_state: Mapping[str, Any],
    candidates: tuple[Mapping[str, Any], ...],
) -> DecisionQuestionSet:
    facts_by_type = _plant_type_facts(jev_state, candidates)
    criteria: dict[str, Any] = {}
    targets: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        option_id = plant_option_id(candidate["type_name"], candidate["row"], candidate["col"])
        criteria[option_id] = _placement_criteria(facts_by_type, candidate)
        targets[option_id] = dict(candidate)
    criteria[DISCARD_OPTION_ID] = discard_option_criteria("No placement")
    targets[DISCARD_OPTION_ID] = {}
    questions = {PLANT_TARGET_QUESTION_ID: plant_target_question(criteria)}
    return DecisionQuestionSet(
        "plant",
        questions,
        candidates,
        (ChoiceLevel(PLANT_TARGET_QUESTION_ID, 1, targets),),
        False,
        question_summary(questions),
    )


def _split_plant_question_set(
    jev_state: Mapping[str, Any],
    candidates: tuple[Mapping[str, Any], ...],
) -> DecisionQuestionSet:
    """Chain the placement Choice level by level instead of truncating options."""
    facts_by_type = _plant_type_facts(jev_state, candidates)
    lanes = sorted({candidate["row"] for candidate in candidates})
    lane_criteria: dict[str, Any] = {
        plant_lane_option_id(row): lane_option_criteria(row) for row in lanes
    }
    lane_criteria[DISCARD_OPTION_ID] = discard_option_criteria("No lane")
    lane_targets: dict[str, Mapping[str, Any]] = {
        plant_lane_option_id(row): {"row": row} for row in lanes
    }
    lane_targets[DISCARD_OPTION_ID] = {}
    questions = {PLANT_LANE_QUESTION_ID: plant_lane_question(lane_criteria)}
    levels = [ChoiceLevel(PLANT_LANE_QUESTION_ID, 1, lane_targets)]
    for row in lanes:
        criteria: dict[str, Any] = {}
        targets: dict[str, Mapping[str, Any]] = {}
        for candidate in candidates:
            if candidate["row"] != row:
                continue
            option_id = plant_option_id(candidate["type_name"], candidate["row"], candidate["col"])
            criteria[option_id] = _placement_criteria(facts_by_type, candidate)
            targets[option_id] = dict(candidate)
        if len(criteria) + 1 > MAX_CHOICE_OPTIONS:
            raise JevDecisionError(
                "One lane offers more placements than the official "
                f"{MAX_CHOICE_OPTIONS} option cap; OD-22 records a two-level chain that "
                "assigns at most nine columns times ten plant types to one lane."
            )
        criteria[DISCARD_OPTION_ID] = discard_option_criteria(f"No placement in lane {row}")
        targets[DISCARD_OPTION_ID] = {}
        question_id = plant_lane_target_question_id(row)
        questions[question_id] = plant_lane_target_question(row, criteria)
        levels.append(ChoiceLevel(question_id, 2, targets))
    return DecisionQuestionSet(
        "plant",
        questions,
        candidates,
        tuple(levels),
        True,
        question_summary(questions),
    )


def _placement_criteria(
    facts_by_type: Mapping[str, Mapping[str, Any]], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    facts = facts_by_type.get(candidate["type_name"], {})
    return plant_option_criteria(
        type_name=candidate["type_name"],
        row=candidate["row"],
        col=candidate["col"],
        cost=facts.get("cost"),
        role=facts.get("role"),
        description_en=facts.get("description_en"),
        engagement=facts.get("engagement"),
    )


def _plant_type_facts(
    jev_state: Mapping[str, Any],
    candidates: tuple[Mapping[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    """Catalog cost/role/ability/engagement facts for the offered plant types (R6, V15)."""
    offered = {candidate["type_name"] for candidate in candidates}
    facts: dict[str, dict[str, Any]] = {name: {} for name in offered}
    cards = jev_state.get("cards")
    if not isinstance(cards, list):
        return facts
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        type_name = card.get("type_name")
        if type_name not in offered or facts.get(type_name):
            continue
        info = plant_info(card.get("type_code"))
        cost = card.get("cost")
        facts[type_name] = {
            "cost": cost if _finite_number(cost) else None,
            "role": None if info is None else info.role,
            "description_en": None if info is None or info.name != type_name else info.description_en,
            "engagement": None if info is None or info.name != type_name else info.engagement,
        }
    return facts


def _jev_cells(jev_state: Mapping[str, Any]) -> list[list[Any]] | None:
    board = jev_state.get("board")
    cells = board.get("cells") if isinstance(board, Mapping) else None
    if (
        not isinstance(cells, list)
        or len(cells) != 5
        or any(not isinstance(row, list) or len(row) != 9 for row in cells)
    ):
        return None
    return cells


def _default_client_factory() -> AbstractContextManager[TypeSafeClient]:
    return TypeSafeClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        retry=RetryPolicy(max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS),
    )


class JevClient:
    """Make at most one typed System One request for the requested phase."""

    def __init__(self, client_factory: Callable[[], Any] | None = None):
        self._client_factory = client_factory or _default_client_factory

    def decide_router(self, jev_state: Mapping[str, Any]) -> JevRouterDecision:
        load_typesafe_environment()
        thresholds = load_jev_thresholds()
        typesafe_state = _legacy_projection_state(jev_state)
        questions = build_router_questions(thresholds.noul_candidate_threshold)
        response, latency_ms = self._system_one(typesafe_state, questions)
        return reconcile_router(
            response,
            noul_candidate_threshold=thresholds.noul_candidate_threshold,
            confidence_threshold=thresholds.router_confidence_threshold,
            latency_ms=latency_ms,
            question_summary=question_summary(questions),
        )

    def decide_action(self, intent: str, jev_state: Mapping[str, Any]) -> JevActionDecision:
        load_typesafe_environment()
        thresholds = load_jev_thresholds()
        action_questions = build_action_questions(intent, jev_state)
        if not action_questions.questions:
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
                confidence_threshold=thresholds.action_confidence_threshold,
            )
        response, latency_ms = self._system_one(_legacy_projection_state(jev_state), action_questions.questions)
        return validate_action_answers(
            response,
            intent=intent,
            option_targets=action_questions.option_targets,
            confidence_threshold=thresholds.action_confidence_threshold,
            latency_ms=latency_ms,
            question_summary=action_questions.summary,
        )

    def _system_one(self, state: Mapping[str, Any], questions: Mapping[str, Any]) -> tuple[Any, int]:
        load_typesafe_environment()
        started = time.perf_counter()
        try:
            with use_configured_http_proxy_fallback():
                with self._client_factory() as client:
                    response = client.system_one(model=DEFAULT_MODEL_NAME, state=state, questions=questions)
        except JevDecisionError:
            raise
        except Exception as exc:
            raise JevApiError(type(exc).__name__) from None
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return response, elapsed_ms


def _default_async_client_factory() -> Any:
    return AsyncTypeSafeClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        retry=RetryPolicy(max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS),
    )


class AsyncJevClient:
    """Transport for one Runtime lifetime: one startup configuration, one SDK client.

    The configuration and the proxy fallback are established when the client is
    opened and released when it is closed, never per request. At most
    ``GLOBAL_IN_FLIGHT_LIMIT`` requests are in flight at any time.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] | None = None,
        dotenv_path: str | PathLike[str] | None = None,
    ):
        self._client_factory = client_factory or _default_async_client_factory
        self._dotenv_path = dotenv_path
        self._environment: AbstractContextManager[RuntimeConfig] | None = None
        self._client: Any | None = None
        self._config: RuntimeConfig | None = None
        self._in_flight: asyncio.Semaphore | None = None

    @property
    def config(self) -> RuntimeConfig:
        """The configuration frozen when this client was opened."""
        if self._config is None:
            raise RuntimeError("The async JEV client has not been opened.")
        return self._config

    async def __aenter__(self) -> "AsyncJevClient":
        if self._client is not None:
            raise RuntimeError("An async JEV client cannot be opened while it is already open.")
        environment = runtime_environment(self._dotenv_path)
        config = environment.__enter__()
        try:
            client = self._client_factory()
        except BaseException:
            environment.__exit__(*sys.exc_info())
            raise
        self._environment = environment
        self._config = config
        self._client = client
        self._in_flight = asyncio.Semaphore(GLOBAL_IN_FLIGHT_LIMIT)
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        environment, self._environment = self._environment, None
        client, self._client = self._client, None
        self._in_flight = None
        try:
            if client is not None:
                await client.aclose()
        finally:
            if environment is not None:
                environment.__exit__(exc_type, exc, traceback)
        return False

    async def system_one(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
        model: str | None = None,
    ) -> tuple[Any, int]:
        """Return the typed response with the measured request latency in milliseconds."""
        client, in_flight = self._client, self._in_flight
        if client is None or in_flight is None:
            raise RuntimeError("The async JEV client must be opened before sending requests.")
        model_name = model or self.config.model_name
        async with in_flight:
            started = time.perf_counter()
            try:
                response = await client.system_one(model=model_name, state=state, questions=questions)
            except JevDecisionError:
                raise
            except Exception as exc:
                raise JevApiError(type(exc).__name__) from None
            return response, int((time.perf_counter() - started) * 1000)

    async def decide_plant(
        self,
        jev_state: Mapping[str, Any],
        *,
        signals: StrategySignals | None = None,
        intent: Mapping[str, Any] | None = None,
        last_result: Mapping[str, Any] | None = None,
        all_state: Mapping[str, Any] | None = None,
    ) -> JevActionDecision:
        """Answer the whole plant decision with one speculative fan-out request.

        Every question of this decision (the placement Choice, or the lane chain
        when the candidates exceed the option cap) travels in the same request,
        so one decision costs exactly one ``system_one`` call (V29); an empty
        placement list costs none and waits locally (V32). There is no absolute
        plant gate: the placement Choice is taken as the model's argmax with no
        threshold at all, and the model's own discard option is the only thing
        that makes the branch wait (OD-41, R31, V57).
        """
        if intent is not None and intent.get("type_name"):
            jev_state = {**jev_state, "cards": [card for card in jev_state.get("cards") or [] if card.get("type_name") == intent["type_name"]]}
            signals = evaluate_strategy(jev_state)
        question_set = build_plant_questions(
            jev_state,
            signals=signals,
        )
        if not question_set.questions:
            return _local_action_wait("plant", "no_valid_action_targets")
        request_state = build_typesafe_state(jev_state, branch=BRANCH_PLANT, signals=signals, all_state=all_state)
        request_state.update(current_intent=intent, last_actual_result=last_result)
        response, latency_ms = await self.system_one(
            state=request_state,
            questions=question_set.questions,
        )
        from dataclasses import replace
        decision = combine_plant_decision(
            response,
            question_set=question_set,
            latency_ms=latency_ms,
            question_summary=question_set.summary,
        )
        return replace(decision, request_state=request_state)

    async def decide_shared(self, jev_state, *, all_state=None, intent=None, last_result=None):
        from dataclasses import replace
        from .questions import management_questions, MANAGEMENT_INTENT_QUESTION_ID, MANAGEMENT_TYPE_QUESTION_ID
        from .decision import _choice_probabilities
        question_set = build_collect_questions(jev_state, all_state=all_state)
        state = build_typesafe_state(jev_state, branch=BRANCH_COLLECT, all_state=all_state)
        state["current_intent"] = intent
        state["last_actual_result"] = last_result
        types = tuple(card["type_name"] for card in state["cards"])
        questions = {**question_set.questions, **management_questions(tuple(state["cards"] or ()))}
        response, latency = await self.system_one(state=state, questions=questions)
        errors = []
        if question_set.questions:
            try:
                decision = combine_collect_decision(response, question_set=question_set, latency_ms=latency, question_summary=question_summary(questions))
            except JevDecisionError:
                errors.append("invalid_collect_response")
                decision = replace(_local_action_wait("collect", "invalid_collect_response"), status="model_wait", latency_ms=latency, model=getattr(response, "model", None), question_summary=question_summary(questions))
        else:
            # No collectable item (OD-44): the collect component waits locally and
            # never touches ``response.answers``, so no ``invalid_collect_response``
            # can arise from the now-absent collect sub-question.
            decision = replace(_local_action_wait("collect", "no_valid_action_targets"), status="model_wait", latency_ms=latency, model=getattr(response, "model", None), question_summary=question_summary(questions))
        records = dict(decision.answers)
        management = None
        try:
            intent_answer = response.answers.get(MANAGEMENT_INTENT_QUESTION_ID)
            intent_choices = frozenset({"keep", "replace", "cancel"})
            intent_probabilities = _choice_probabilities(intent_answer, intent_choices)
            operation = getattr(intent_answer, "choice", None)
            if operation not in intent_probabilities or intent_probabilities[operation] != max(intent_probabilities.values()):
                raise JevDecisionError("Management intent must select its offered argmax.")
            records[MANAGEMENT_INTENT_QUESTION_ID] = {"choice": operation, "confidence": getattr(intent_answer, "confidence", None), "probabilities": intent_probabilities}
            type_name = None
            if operation == "replace":
                # Only a replacement names a construction type: keep and cancel are
                # complete answers on their own, so an omitted type option is not an
                # error (the model used to lose its own cancel answer here).
                type_answer = response.answers.get(MANAGEMENT_TYPE_QUESTION_ID)
                type_choices = frozenset(set(types) | {DISCARD_OPTION_ID})
                type_probabilities = _choice_probabilities(type_answer, type_choices)
                chosen_type = getattr(type_answer, "choice", None)
                if chosen_type not in type_probabilities or type_probabilities[chosen_type] != max(type_probabilities.values()):
                    raise JevDecisionError("Management type must select its offered argmax.")
                records[MANAGEMENT_TYPE_QUESTION_ID] = {"choice": chosen_type, "confidence": getattr(type_answer, "confidence", None), "probabilities": type_probabilities}
                type_name = chosen_type
            management = {"operation": operation, "type_name": type_name}
        except (JevDecisionError, AttributeError, TypeError):
            errors.append("invalid_management_response")
        return replace(decision, answers=records, management=management, request_state=state, component_errors=tuple(errors))

    async def decide_collect(
        self,
        jev_state: Mapping[str, Any],
        *,
        all_state: Mapping[str, Any] | None = None,
    ) -> JevActionDecision:
        """Answer the whole collect decision with one speculative fan-out request.

        The same zero-or-one request contract as :meth:`decide_plant` applies:
        one request with the absolute gate and the target Choice together, or no
        request when nothing is visible to collect.

        ``all_state`` must be the raw All State of the very sample ``jev_state``
        was projected from: it is the only source of a collectable item's ``id``
        (OD-32). Without it no option can be bound, so the branch concludes
        locally and sends nothing instead of asking about a target it could never
        verify at dispatch time.
        """
        question_set = build_collect_questions(
            jev_state,
            all_state=all_state,
        )
        if not question_set.questions:
            return _local_action_wait("collect", "no_valid_action_targets")
        response, latency_ms = await self.system_one(
            state=build_typesafe_state(jev_state, branch=BRANCH_COLLECT),
            questions=question_set.questions,
        )
        return combine_collect_decision(
            response,
            question_set=question_set,
            latency_ms=latency_ms,
            question_summary=question_set.summary,
        )


def _local_action_wait(intent: str, reason: str) -> JevActionDecision:
    """A decision concluded in code, without any request being sent."""
    return JevActionDecision(
        intent=intent,
        effective_action="wait",
        target=None,
        answers={},
        fallback_reason=reason,
        status="skipped_no_targets",
        model=None,
        usage={"input_tokens": None, "output_tokens": None},
        latency_ms=0,
        question_summary={},
        confidence_threshold=ACTION_CONFIDENCE_THRESHOLD,
    )


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


__all__ = [
    "ActionQuestionSet",
    "AsyncJevClient",
    "GLOBAL_IN_FLIGHT_LIMIT",
    "JevApiError",
    "JevClient",
    "build_action_questions",
    "build_router_questions",
    "build_typesafe_state",
]
