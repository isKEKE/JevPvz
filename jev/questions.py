"""Reviewable question definitions for the autonomous runtime.

The shared request asks one collection Noul (only when there are collectable
items) and independent model construction intent/type questions. Collection
authorizes a local frozen ID cohort;
IDs and coordinates never enter its model input. The plant request asks only a
complete legal placement Choice, without local lane reranking: the model's own
discard option (``none_of_the_above``) decides whether to act at all, so no plant
absolute gate exists. Legacy economy/row/collect-target helpers remain for
historical consumers; ``should_invest_economy`` and the row questions are no
longer part of any runtime question set. Noul gates use NOUL_CANDIDATE_THRESHOLD,
except the collection gate, which is pinned to the reviewable anchor
``COLLECT_ACT_THRESHOLD``; relative Choices use argmax without a confidence gate.
No prescribed lineup, phase policy, or layout is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from typesafe_sdk import Choice, Noul

from .config import (
    DEFAULT_ACTION_CONFIDENCE_THRESHOLD,
    DEFAULT_NOUL_CANDIDATE_THRESHOLD,
    DEFAULT_ROUTER_CONFIDENCE_THRESHOLD,
)
from .strategy import card_costs, card_price_band

# --------------------------------------------------------------- thresholds

NOUL_CANDIDATE_THRESHOLD = DEFAULT_NOUL_CANDIDATE_THRESHOLD
"""Absolute gate for Noul questions (OD-08 revised, OD-13); P02-only after T16."""

COLLECT_ACT_THRESHOLD = 0.5
"""Fixed anchor for ``should_collect_now`` (OD-42, R32): "more likely than not".

Pinned here, independent of ``JEV_NOUL_CANDIDATE_THRESHOLD``, so the collect
gate cannot drift with the P02 gate config; ``jev/decision.py``
:func:`combine_collect_decision` consumes this constant.
"""

ACTION_CONFIDENCE_THRESHOLD = DEFAULT_ACTION_CONFIDENCE_THRESHOLD
"""P02 synchronous Action Choice gate (``validate_action_answers``); no branch uses it."""

ROUTER_CONFIDENCE_THRESHOLD = DEFAULT_ROUTER_CONFIDENCE_THRESHOLD
"""P02 historical router gate; no runtime branch uses it after T4."""

# ------------------------------------------------------- hand-editable facts

PLANT_EXPERIENCE_PATH = Path(__file__).resolve().parents[1] / "configs" / "plant_experience.txt"
"""Repository plant-experience file (OD-58, R47).

A hand-editable UTF-8 text file with one guidance per line; ``#`` comment and
blank lines are ignored. It only supplies *supplementary* guidance: the fixed
direction anchor sentence stays in code, and nothing here is validated at
runtime -- over-budget or unknown ``state.<field>`` references surface only in
tests (V72).
"""


def load_plant_experience(path: Path | None = None) -> tuple[str, ...]:
    """Guidance lines of the hand-editable experience file, in file order (R47).

    Comments (``#`` prefix) and blank lines are dropped; every kept line is
    stripped of surrounding whitespace and must be non-empty. The file is read
    on every call (never cached), a missing file yields ``()``, and the content
    is neither validated nor truncated -- unknown ``state.<field>`` references
    and budget overshoot are guarded by tests, not by the runtime.
    """
    source = path or PLANT_EXPERIENCE_PATH
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return tuple(lines)

# ------------------------------------------------------------- question ids

ROW_COUNT = 5
MAX_CHOICE_OPTIONS = 255
"""Official Choice option cap including the discard option (OD-15)."""

DISCARD_OPTION_ID = "none_of_the_above"
"""Explicit discard option that every target Choice must offer (OD-15)."""

PLANT_ROW_QUESTION_PREFIX = "row_needs_response_r"
ECONOMY_QUESTION_ID = "should_invest_economy"
PLANT_TARGET_QUESTION_ID = "plant_target"
PLANT_LANE_QUESTION_ID = "plant_target_lane"
PLANT_LANE_OPTION_PREFIX = "lane_"
PLANT_LANE_TARGET_QUESTION_PREFIX = "plant_target_lane_"

SHOVEL_TARGET_QUESTION_ID = "shovel_target"
"""The removal Choice of the plant request (CD-08): which occupied cell to clear."""

COLLECT_NOW_QUESTION_ID = "should_collect_now"
COLLECT_TARGET_QUESTION_ID = "collect_target"

PLANT_ROW_QUESTION_IDS: tuple[str, ...] = tuple(
    f"{PLANT_ROW_QUESTION_PREFIX}{row}" for row in range(ROW_COUNT)
)

# ---------------------------------------------------------------- state keys

PLANT_STATE_FIELDS: tuple[str, ...] = ("sun", "cards", "economy", "plant_counts", "lane_composition", "board", "plants", "zombies", "waves", "observed_lanes", "catalog_context")
COLLECT_STATE_FIELDS: tuple[str, ...] = (*PLANT_STATE_FIELDS, "items")



@dataclass(frozen=True)
class QuestionSpec:
    """One reviewable question declaration: the single attribute it judges.

    ``threshold`` names the constant that governs this answer; Noul questions use
    :data:`NOUL_CANDIDATE_THRESHOLD`. A relative Choice declares ``argmax``
    instead, meaning it is decided by the model's highest option and is filtered
    by no threshold (revised OD-13).
    """

    question_id: str
    kind: str
    attribute: str
    threshold: str


PLANT_QUESTION_SPECS: tuple[QuestionSpec, ...] = (
    QuestionSpec(PLANT_TARGET_QUESTION_ID, "choice", "which complete legal placement to perform, or the discard option to wait", "argmax"),
)
COLLECT_QUESTION_SPECS: tuple[QuestionSpec, ...] = (
    QuestionSpec(COLLECT_NOW_QUESTION_ID, "noul", "whether to collect the frozen visible cohort now", "collect_act_threshold"),
)


@dataclass(frozen=True)
class ChoiceLevel:
    """One Choice question, its option ids, and the target each option binds.

    ``targets[DISCARD_OPTION_ID]`` is an empty mapping: selecting it means the
    model declined every offered option.
    """

    question_id: str
    level: int
    targets: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class DecisionQuestionSet:
    """Every question of one decision, sent together in a single request."""

    intent: str
    questions: Mapping[str, Any]
    candidates: tuple[Mapping[str, Any], ...]
    choice_levels: tuple[ChoiceLevel, ...]
    split: bool
    summary: Mapping[str, Any]


# ------------------------------------------------------- absolute gate texts


def _threshold_text(threshold: float) -> str:
    return f"{threshold:g}"


def plant_row_question(row: int, noul_candidate_threshold: float = NOUL_CANDIDATE_THRESHOLD) -> Noul:
    """Absolute per-lane gate: does this one lane need another planting response?"""
    return Noul(
        instructions=(
            f"Judge lane {row} alone: given the zombies in that lane and the plants already defending it, "
            f"does lane {row} need another planting response right now? Read lane {row}'s observed "
            f"zombie_count, nearest_cells, hp_total, attacker_count and has_defender from state.observed_lanes[{row}], "
            "and the abilities of the zombie types present from state.catalog_context. Use those facts "
            "exactly as they are given: do not read any other lane, do not count, add, or compare numbers, "
            "and do not consider any pending decision. Answer true when this lane alone needs a response "
            f"now. The runtime treats a probability of {_threshold_text(noul_candidate_threshold)} or higher "
            "as true."
        ),
        criteria={
            "true": f"Lane {row} needs another planting response now.",
            "false": f"Lane {row} does not need another planting response now.",
        },
    )


def economy_question(noul_candidate_threshold: float = NOUL_CANDIDATE_THRESHOLD) -> Noul:
    """Absolute resource gate: is now a good time to put the current sun into economy?"""
    return Noul(
        instructions=(
            "Judge one thing only: is now a good time to invest the sun you currently have in economy "
            "instead of in an immediate defensive planting? Read state.phase, state.economy_signal, "
            "state.sun and state.affordable as they are given; do not predict future sun, do not add "
            "anything up, and do not consider the planting options. The runtime treats a probability of "
            f"{_threshold_text(noul_candidate_threshold)} or higher as true."
        ),
        criteria={
            "true": "Investing the current sun in economy is the better move now.",
            "false": "Do not invest the current sun in economy now.",
        },
    )


def collect_now_question(collect_act_threshold: float = COLLECT_ACT_THRESHOLD) -> Noul:
    """Absolute gate for the collect branch, pinned to ``COLLECT_ACT_THRESHOLD``."""
    return Noul(
        instructions=(
            "Judge one thing only: is collecting the visible items listed in state.items worth "
            "doing now instead of waiting? state.items lists every currently visible item with its "
            "type and code-computed count; read those facts as they are given and do not "
            "count anything. The runtime treats a probability of "
            f"{_threshold_text(collect_act_threshold)} or higher as true."
        ),
        criteria={
            "true": "Collecting the visible cohort now is worth doing.",
            "false": "Do not collect a visible item now.",
        },
    )


# -------------------------------------------------------- relative choices

PLANT_LAYOUT_ANCHOR = (
    "Columns are numbered from the house side (column 0) toward the zombie side, as given by "
    "state.board.column_direction. A fragile resource plant is usually safer toward the house side "
    "and a durable blocker on the zombie side of what it protects, but an immediate threat in that "
    "lane's state.observed_lanes row outranks any long-term layout preference."
)
"""Fixed direction anchor appended to every plant instructions text (OD-56, R45).

It always states the column direction semantics and that an immediate lane threat
outranks any long-term layout preference. It names no column number, no quota, and
no categorical rule, and it never filters candidates (OD-15 keeps the full
enumeration).
"""


ECONOMY_ANCHOR = (
    "state.economy is the resource fact of this decision: band compares state.sun with the prices in "
    "hand (scarce = below every price in hand, normal = below the middle price, comfortable = below the "
    "highest price, abundant = at or above the highest price), plan is the next construction you already "
    "declared with its cost and the sun it still needs, and sun_above_plan is what is left once that plan "
    "is paid for. While plan still needs sun the placements offered are limited to it; once it is payable "
    "they are that plan's placements together with every other placement sun_above_plan can pay for, so a "
    "large balance does not narrow the choice by itself. Choosing the discard option is how you keep "
    "saving for a plan you cannot pay for yet."
)
"""Fixed economy anchor appended to every plant instructions text.

It only states the semantics of the resource facts the runtime already computes
(balance band against this hand's own prices, the declared plan and its price, and
that plan's own surplus) and how the offered set follows from them. It names no
sun number, no plant, and no build order, and it never ranks the options.
"""


def _plant_layout_guidance() -> str:
    """The shared layout paragraph appended after every plant instructions text.

    The fixed anchor sentence is always present; the hand-editable experience
    file contributes supplementary guidance lines after it (OD-58, R47). A
    missing or empty file degrades to the anchor sentence alone.
    """
    return " " + " ".join((PLANT_LAYOUT_ANCHOR, *load_plant_experience()))


def _plant_economy_guidance() -> str:
    """The fixed economy paragraph appended to every plant instructions text.

    It states the resource facts and the offer rule that follows from them, so a
    declared goal is readable in the question itself instead of having to be
    inferred from a changing candidate list.
    """
    return " " + ECONOMY_ANCHOR


def plant_target_question(criteria: Mapping[str, Any]) -> Choice:
    """Relative choice over every validated placement plus the discard option."""
    return Choice(
        instructions=(
            "Choose exactly one placement from the complete list of placements that are legal right now, "
            f"or choose {DISCARD_OPTION_ID} when none of them is the right move now. Every option is one "
            "complete, already validated type/row/column placement; the option states the plant ability, "
            "its cost, its role, and the lane it would be placed in, and that lane's facts are the entry "
            "of the same lane number in state.observed_lanes. Compare the offered placements with each other only; "
            "do not count, and do not name anything that is not offered."
            + _plant_layout_guidance()
            + _plant_economy_guidance()
        ),
        criteria=dict(criteria),
    )


def plant_lane_question(criteria: Mapping[str, Any]) -> Choice:
    """Level-1 choice of the over-255 chain: which lane should receive the planting?"""
    return Choice(
        instructions=(
            "Choose the one lane that should receive the next planting, or choose "
            f"{DISCARD_OPTION_ID} when no lane should be planted right now. Each option names one lane, "
            "and that lane's facts are the entry of the same lane number in state.observed_lanes. The complete list "
            "of placements inside each lane is asked as a separate question."
            + _plant_layout_guidance()
            + _plant_economy_guidance()
        ),
        criteria=dict(criteria),
    )


def plant_lane_target_question(row: int, criteria: Mapping[str, Any]) -> Choice:
    """Level-2 choice of the over-255 chain: which placement inside one lane?"""
    return Choice(
        instructions=(
            f"Assume the next planting goes into lane {row}. Choose exactly one placement from the complete "
            f"list of legal placements in lane {row}, or choose {DISCARD_OPTION_ID} when none of them is the "
            f"right move now. Every option states the plant ability, its cost, and its column in lane {row}; "
            f"lane {row}'s facts are state.observed_lanes[{row}]. Compare the offered placements with each other only; "
            "do not count, and do not name anything that is not offered."
            + _plant_layout_guidance()
            + _plant_economy_guidance()
        ),
        criteria=dict(criteria),
    )


def shovel_target_question(criteria: Mapping[str, Any]) -> Choice:
    """Relative choice over every removable occupied cell plus the discard option.

    One action per decision is enforced by the code merge, not by this text: the
    options state each cell's own row, column, plant type and catalog role, and the
    question never says which cell to clear or in what order. The executor removes
    one plant in the chosen cell and guarantees no specific entity of a stacked
    cell, so the text promises exactly that and nothing more.
    """
    return Choice(
        instructions=(
            "Choose exactly one occupied board cell to clear, or choose "
            f"{DISCARD_OPTION_ID} when none of them is the right move now. Every option names one "
            "occupied cell by its zero-based row and column, the plant type the board reports there, "
            "and that type's catalog role when it resolves; removing a cell removes one plant in "
            "that cell, and no option selects one specific entity of a stacked cell. Compare the "
            "offered cells with each other only; do not count, and do not name anything that is not "
            "offered."
            + _plant_economy_guidance()
        ),
        criteria=dict(criteria),
    )


def collect_target_question(criteria: Mapping[str, Any]) -> Choice:
    """Relative choice over every visible item plus the discard option."""
    return Choice(
        instructions=(
            "Choose exactly one visible item to collect now, or choose "
            f"{DISCARD_OPTION_ID} when none of the listed items is worth collecting now. Every option names "
            "one currently visible item by its sample-local index and type; compare the offered items with "
            "each other only, and do not count."
        ),
        criteria=dict(criteria),
    )


# ------------------------------------------------------- option ids and text


def plant_option_id(type_name: str, row: int, col: int) -> str:
    return f"{type_name}@r{row}c{col}"


def shovel_option_id(row: int, col: int) -> str:
    """The option id of one removable occupied cell (``remove@r<row>c<col>``)."""
    return f"remove@r{row}c{col}"


def plant_lane_option_id(row: int) -> str:
    return f"{PLANT_LANE_OPTION_PREFIX}{row}"


def plant_lane_target_question_id(row: int) -> str:
    return f"{PLANT_LANE_TARGET_QUESTION_PREFIX}{row}"


def collect_option_id(index: int) -> str:
    return f"item_{index}"


def plant_option_criteria(
    *,
    type_name: str,
    row: int,
    col: int,
    cost: int | None,
    role: str | None,
    description_en: str | None,
    engagement: str | None = None,
) -> dict[str, Any]:
    """One placement option: what it places, where, and the plant's ability text.

    ``description_en`` is the English catalog ability (R6); an empty value means
    the local catalog has no ability text for that type, which is stated as
    unavailable instead of being invented. ``engagement`` states whether the plant
    reaches zombies from range or only at melee distance (``none`` when it never
    attacks), so placement does not depend on inferring it from the prose.
    """
    return {
        "what": f"Place {type_name.replace('_', ' ')} on the empty cell at zero-based row {row}, column {col}.",
        "type_name": type_name,
        "lane": row,
        "column": col,
        "cost": cost,
        "role": role,
        "plant_ability": description_en or "unknown: this type has no local ability text",
        "engagement": engagement,
    }


def shovel_option_criteria(*, type_name: str, row: int, col: int, role: str | None) -> dict[str, Any]:
    """One removal option: which cell, which plant type, and that type's role.

    Facts only: the cell's zero-based row and column, the type name the board
    reports for it, and the catalog role when it resolves (``None`` when it does
    not). Nothing states that the cell should be cleared or cleared first.
    """
    return {
        "what": (
            f"Remove the {type_name.replace('_', ' ')} the board reports in the occupied cell at "
            f"zero-based row {row}, column {col}."
        ),
        "type_name": type_name,
        "lane": row,
        "column": col,
        "role": role,
    }


def lane_option_criteria(row: int) -> dict[str, Any]:
    return {"what": f"Send the next planting into lane {row}.", "lane": row}


def collect_option_criteria(*, index: int, type_name: str, x: float, y: float) -> dict[str, Any]:
    return {
        "what": f"Collect the visible {type_name.replace('_', ' ')} at sample-local item index {index}.",
        "type_name": type_name,
        "index": index,
        "x": x,
        "y": y,
    }


def discard_option_criteria(level_label: str) -> dict[str, Any]:
    return {"what": f"{level_label}: none of the listed options is the right move now."}


def plant_target_options(candidates: int) -> bool:
    """True when the placement options must be chained instead of asked at once."""
    return candidates + 1 > MAX_CHOICE_OPTIONS


# --------------------------------------------------------------- summaries


def question_summary(questions: Mapping[str, Any]) -> dict[str, Any]:
    """Serialize the declared questions for the Trace record and V41 review."""
    summary: dict[str, Any] = {}
    for question_id, question in questions.items():
        record = question.model_dump(exclude_none=True) if hasattr(question, "model_dump") else {}
        summary[question_id] = {
            "type": record.get("type"),
            "instructions": record.get("instructions"),
            "criteria": record.get("criteria"),
        }
    return summary


__all__ = [
    "ACTION_CONFIDENCE_THRESHOLD",
    "COLLECT_ACT_THRESHOLD",
    "COLLECT_NOW_QUESTION_ID",
    "COLLECT_QUESTION_SPECS",
    "COLLECT_STATE_FIELDS",
    "COLLECT_TARGET_QUESTION_ID",
    "ChoiceLevel",
    "DecisionQuestionSet",
    "DISCARD_OPTION_ID",
    "ECONOMY_QUESTION_ID",
    "MAX_CHOICE_OPTIONS",
    "NOUL_CANDIDATE_THRESHOLD",
    "PLANT_EXPERIENCE_PATH",
    "PLANT_LANE_OPTION_PREFIX",
    "PLANT_LANE_QUESTION_ID",
    "PLANT_LANE_TARGET_QUESTION_PREFIX",
    "PLANT_QUESTION_SPECS",
    "PLANT_ROW_QUESTION_IDS",
    "PLANT_ROW_QUESTION_PREFIX",
    "PLANT_STATE_FIELDS",
    "PLANT_TARGET_QUESTION_ID",
    "QuestionSpec",
    "ROUTER_CONFIDENCE_THRESHOLD",
    "ROW_COUNT",
    "SHOVEL_TARGET_QUESTION_ID",
    "collect_now_question",
    "collect_option_criteria",
    "collect_option_id",
    "collect_target_question",
    "discard_option_criteria",
    "economy_question",
    "lane_option_criteria",
    "load_plant_experience",
    "plant_lane_option_id",
    "plant_lane_question",
    "plant_lane_target_question",
    "plant_lane_target_question_id",
    "plant_option_criteria",
    "plant_option_id",
    "plant_row_question",
    "plant_target_options",
    "plant_target_question",
    "question_summary",
    "shovel_option_criteria",
    "shovel_option_id",
    "shovel_target_question",
]


MANAGEMENT_INTENT_QUESTION_ID = "construction_intent"
MANAGEMENT_TYPE_QUESTION_ID = "next_construction_type"


def _construction_option_text(card: Mapping[str, Any], costs: tuple[int, ...] = ()) -> str:
    """One construction-type option: the card's own catalog facts, nothing more.

    ``costs`` is the hand's own price ladder, used only for the comparative
    ``low``/``mid``/``high`` price position (a fact about this hand, not a build
    order). No recommendation is added.
    """
    parts = [f"Build {card.get('type_name')}"]
    ability = card.get("description_en")
    if isinstance(ability, str) and ability.strip():
        parts.append(ability.strip())
    cost = card.get("cost")
    if type(cost) is int:
        position = card_price_band(cost, costs)
        parts.append(f"cost {cost} ({position} price in hand)" if position else f"cost {cost}")
    shortfall = card.get("shortfall")
    if card.get("payable") is True:
        parts.append("payable now")
    elif type(shortfall) is int:
        parts.append(f"short by {shortfall}")
    return " — ".join(parts) + "."


def management_questions(
    cards: tuple[Mapping[str, Any], ...],
    *,
    economy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The context-only construction intent/type questions (OD-43).

    Every construction-type option repeats the facts the shared state already
    carries for that card -- its catalog ability text, its cost, its comparative
    price position in the current hand and its current payment fact -- so the type
    can be chosen without cross-referencing the card list and an unfamiliar (for
    example modded) plant is never mistaken for a known one. No line-up, quota, or
    recommendation is supplied.

    ``economy`` is the same resource fact group the shared state carries. When it
    is present the intent question also states what the declared goal does to the
    planting branch (keep saving while it still needs sun, offer it first once
    payable), so nothing about the offered set has to be guessed from a changing
    list.

    There is no urgency Noul: the removed immediate-response signal had no
    consumer, and the model's own discard option now owns the act/wait decision.
    """
    costs = card_costs(cards)
    options: dict[str, str] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        name = card.get("type_name")
        if isinstance(name, str) and name:
            options[name] = _construction_option_text(card, costs)
    options[DISCARD_OPTION_ID] = "No construction type."
    goal = "your current next construction goal using observed facts"
    if isinstance(economy, Mapping):
        goal += (
            ". state.economy.plan is that goal with its cost and the sun it still needs: while it still "
            "needs sun the planting branch keeps saving for it, and once it is payable that branch offers "
            "it first"
        )
    return {
        MANAGEMENT_INTENT_QUESTION_ID: Choice(instructions=f"Choose whether to keep, replace, or cancel {goal}.", criteria={"keep": "Keep current construction intent.", "replace": "Choose new construction type.", "cancel": "Cancel construction for now."}),
        MANAGEMENT_TYPE_QUESTION_ID: Choice(instructions="Choose your next construction type. Every option states that type's catalog ability, its cost, its price position in the current hand and its current payment fact; you may wait for an unaffordable one. No prescribed lineup or layout is supplied.", criteria=options),
    }
