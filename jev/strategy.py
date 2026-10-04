"""Deterministic strategy features derived from one JEV State projection.

Layering (P03 §3): facts (sun balance, cards, entities) -> computable features
(per-row counts, distances, occupancy) -> decision signals (the four groups in
:class:`StrategySignals`) -> JEV local judgement. This module owns the feature
and signal layer only: it is pure, synchronous, offline-testable, and performs
no I/O, no clock read, and no game access.

Unknown data is never fabricated. ``None`` always means "unknown" and is
serialized as JSON ``null`` by :meth:`StrategySignals.to_dict`; no DPS, house
arrival time, or threat probability is derived here. Every number, count, and
comparison is computed in code so no model has to do arithmetic.

Authorities: OD-22 (数值与口径 — branch keys, urgency thresholds, "raw distance
and raw HP never enter a key"), OD-30 (ordered urgency bands plus explicit
component facts), OD-15 (candidate enumeration), OD-29 (the resource layer never
predicts output) and OD-37/R27 (the model owns the construction goal: the
economy layer here only states the balance band, the declared plan's price, and
what the balance above that price can pay for; it never picks a plant).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Mapping, Sequence

from configs.plant_catalog import PLANTS, plant_info

BRANCH_PLANT = "plant"
BRANCH_COLLECT = "collect"
BRANCHES: tuple[str, ...] = (BRANCH_PLANT, BRANCH_COLLECT)

URGENCY_BANDS: tuple[str, ...] = ("none", "low", "medium", "high", "critical")
ECONOMY_SIGNALS: tuple[str, ...] = ("expand", "hold", "stop")
PHASES: tuple[str, ...] = ("economy", "development", "defense", "emergency", "recovery")

DEFAULT_ROW_COUNT = 5

ECONOMY_BANDS: tuple[str, ...] = ("scarce", "normal", "comfortable", "abundant")
"""Ordered balance bands, each boundary taken from the hand's own prices."""

PLAN_HOLD_REASON = "await_plan"
"""Local wait reason: the declared construction cannot be paid for yet."""

LANE_RESPONSE_URGENCIES: frozenset[str] = frozenset({"high", "critical"})
"""OD-30 bands close enough that a lane may not be left alone for a later goal.

``medium`` (a zombie still four to five cells out) is deliberately excluded: that
is still acceptable progress, so saving the declared goal's sun is worth more than
spending it on the lane now (CD-02). A lane that cannot stop what is in it is
covered by the separate condition in :func:`lane_needs_response`, not by a wider
band set here.
"""

_ROLE_BY_PLANT_NAME = {plant.name: plant.role for plant in PLANTS}


def plant_role_by_name(type_name: Any) -> str | None:
    """The catalog role of one plant *type name*, or ``None`` when it is unknown.

    A board cell encodes an occupied cell as ``plant:<type_name>`` and carries no
    type code, so this is how that cell's role is stated without inventing one.
    """
    return _ROLE_BY_PLANT_NAME.get(type_name) if isinstance(type_name, str) else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_sun(value: Any) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def _role_of(plant: Mapping[str, Any]) -> str | None:
    """Resolve one plant entity's catalog role, or None when it is unknown."""
    info = plant_info(plant.get("type_code"))
    if info is not None:
        return info.role
    return plant_role_by_name(plant.get("type_name"))


def _description_of(plant: Mapping[str, Any]) -> str | None:
    """Catalog ability text of one plant entity, or None when it is unknown.

    A description is only attached when the entity's catalog entry resolves to
    the same type name, so an unknown (for example modded or mismatched) plant
    never inherits another plant's text.
    """
    info = plant_info(plant.get("type_code"))
    if info is not None and info.name == plant.get("type_name"):
        return info.description_en or None
    return None


def _card_role(card: Mapping[str, Any]) -> str | None:
    return _role_of(card)


LANE_COMPOSITION_ROLES: tuple[str, ...] = ("resource", "attacker", "defender")
"""The three own-side composition classes of one lane (OD-49/R38).

A plant whose catalog role is not one of these -- an unknown type, ``control``,
or ``instant`` -- is counted in no class, so a lane's class sum always equals
the number of its resource/attacker/defender plants.
"""

BOARD_COLUMN_GEOMETRY = "column_center_x = lawn.first_cell_center_x + col * lawn.horizontal_spacing"
"""A fact, not advice: how the executor turns a board column into a screen x (OD-49)."""


def _board_rows(board: Mapping[str, Any]) -> int:
    """How many lanes the board declares; an unreadable grid falls back to 5."""
    rows = board.get("rows")
    return rows if type(rows) is int and rows > 0 else DEFAULT_ROW_COUNT


def _board_column_direction(board: Mapping[str, Any]) -> dict[str, Any]:
    """The factual column direction of the board (OD-49/R38).

    Column 0 is the house side and the highest column is the side the zombies
    arrive from, because the executor's x grows with the column index. Only the
    direction is stated: no recommended column, quota, or layout follows.
    """
    cols = board.get("cols")
    highest = cols - 1 if type(cols) is int and cols > 0 else None
    return {
        "house_side_col": 0,
        "zombie_side_col": highest,
        "increasing_col_moves_toward_zombies": True,
        "geometry": BOARD_COLUMN_GEOMETRY,
    }


def _lane_composition(plants: Any, rows_count: int) -> list[dict[str, Any]] | None:
    """Per-lane own-side composition counts, or ``None`` when plants are unknown."""
    if not isinstance(plants, list):
        return None
    lanes = [{"row": row, **{role: 0 for role in LANE_COMPOSITION_ROLES}} for row in range(rows_count)]
    for plant in plants:
        if not isinstance(plant, Mapping):
            continue
        row = plant.get("row")
        role = _role_of(plant)
        if type(row) is int and 0 <= row < rows_count and role in LANE_COMPOSITION_ROLES:
            lanes[row][role] += 1
    return lanes


def _read_board(cells: Any) -> tuple[tuple[tuple[int, int], ...] | None, frozenset[tuple[int, int, str]]]:
    """Split projected board cells into plantable positions and occupied cells.

    ``None`` is a plantable cell, ``False`` is not plantable, ``"plant:<name>"``
    is occupied, and any other value (for example an explicit ``"unknown"``)
    counts as neither. A missing or malformed grid is unknown occupancy.
    """
    if not isinstance(cells, list) or not cells or not all(isinstance(row, list) for row in cells):
        return None, frozenset()
    plantable: list[tuple[int, int]] = []
    occupied: list[tuple[int, int, str]] = []
    for row_index, row in enumerate(cells):
        for column_index, cell in enumerate(row):
            if cell is None:
                plantable.append((row_index, column_index))
            elif isinstance(cell, str) and cell.startswith("plant:"):
                occupied.append((row_index, column_index, cell))
    return tuple(plantable), frozenset(occupied)


def _read_affordable(cards: Any, sun: int | None) -> frozenset[str]:
    """Card type names that are usable, off cooldown, and payable right now."""
    if sun is None or not isinstance(cards, list):
        return frozenset()
    affordable: set[str] = set()
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        if card.get("usable") is not True or card.get("cooldown_ready") is not True:
            continue
        cost = card.get("cost")
        if not _is_number(cost) or cost > sun:
            continue
        type_name = card.get("type_name")
        if isinstance(type_name, str) and type_name:
            affordable.add(type_name)
    return frozenset(affordable)


def _read_economy_signal(cards: Any, affordable: frozenset[str]) -> str:
    """Classify the current sample only; no output prediction, no reservation."""
    if not isinstance(cards, list):
        return "hold"
    resource_cards = [
        card for card in cards if isinstance(card, Mapping) and _card_role(card) == "resource"
    ]
    if not resource_cards:
        return "stop"
    if any(card.get("type_name") in affordable for card in resource_cards):
        return "expand"
    return "hold"


def card_costs(cards: Any) -> tuple[int, ...]:
    """Every non-negative integer price in hand, sorted ascending.

    ``costs`` is the price ladder of *this hand*: the economy layer compares the
    balance with it instead of with any configured sun number, so the same code
    works for a 50-sun sunflower hand and for a 300-sun melon hand.
    """
    if not isinstance(cards, (list, tuple)):
        return ()
    prices = [card.get("cost") for card in cards if isinstance(card, Mapping)]
    return tuple(sorted(price for price in prices if type(price) is int and price >= 0))


def card_price_band(cost: Any, costs: Sequence[int]) -> str | None:
    """One card's price position in this hand: ``low``, ``mid``, or ``high``.

    The two cuts are thirds of the hand's own distinct price ladder counted by
    position, so the label is comparative and needs no configured cost. A
    single-price hand has no position and reports ``mid``; an unknown price or an
    empty ladder reports ``None`` instead of a guess.
    """
    if type(cost) is not int or cost < 0:
        return None
    known = sorted({value for value in costs if type(value) is int and value >= 0})
    if not known or cost not in known:
        return None
    if len(known) == 1:
        return "mid"
    index = known.index(cost)
    third = len(known) / 3
    if index < third:
        return "low"
    if index < 2 * third:
        return "mid"
    return "high"


def economy_band(sun: int | None, costs: Sequence[int]) -> str | None:
    """Where the current balance sits on the prices already in hand.

    ==============  ==========================================================
    ``scarce``      below every price in hand (nothing in hand is payable yet)
    ``normal``      at or above the lowest price, below the middle price
    ``comfortable`` at or above the middle price, below the highest price
    ``abundant``    at or above the highest price in hand
    ==============  ==========================================================

    Every boundary comes from the hand's own price ladder, so the band is a fact
    about this sample and needs no configured sun threshold. ``None`` means the
    balance or the price ladder is unknown; nothing is guessed for it.
    """
    if type(sun) is not int or sun < 0:
        return None
    known = sorted(cost for cost in costs if type(cost) is int and cost >= 0)
    if not known:
        return None
    lowest, highest = known[0], known[-1]
    middle = known[len(known) // 2]
    if sun < lowest:
        return "scarce"
    if sun < middle:
        return "normal"
    if sun < highest:
        return "comfortable"
    return "abundant"


def plan_facts(
    cards: Any,
    sun: int | None,
    plan: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """The model's declared next construction as facts, or ``None`` without one.

    The price is resolved from the card in hand carrying that type name on every
    call, so a price change is reflected instead of remembered. A plan whose type
    is not in hand keeps ``cost``/``payable``/``shortfall`` as ``None``: an
    unreadable goal never becomes a premise, and the caller then narrows nothing.
    """
    if not isinstance(plan, Mapping):
        return None
    type_name = plan.get("type_name")
    if not isinstance(type_name, str) or not type_name:
        return None
    cost = None
    if isinstance(cards, (list, tuple)):
        for card in cards:
            if (
                isinstance(card, Mapping)
                and card.get("type_name") == type_name
                and type(card.get("cost")) is int
            ):
                cost = card["cost"]
                break
    known_balance = type(sun) is int and sun >= 0
    return {
        "type_name": type_name,
        "cost": cost,
        "payable": None if cost is None or not known_balance else sun >= cost,
        "shortfall": None if cost is None or not known_balance else max(0, cost - sun),
    }


def economy_facts(
    jev_state: Mapping[str, Any],
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The resource layer of one sample: band, declared plan, and its surplus.

    No income rate, no future sun, and no prediction is computed. ``band`` labels
    the current balance against this hand's prices, ``plan`` states the goal the
    model declared, and ``sun_above_plan`` is the subtraction that is left once
    that goal is paid for (``None`` while it is not payable). ``plan: null`` means
    no goal is declared, which is a complete value, not missing data.
    """
    sun = _read_sun(jev_state.get("sun_balance")) if isinstance(jev_state, Mapping) else None
    cards = jev_state.get("cards") if isinstance(jev_state, Mapping) else None
    costs = card_costs(cards)
    declared = plan_facts(cards, sun, plan)
    above = None
    if (
        isinstance(declared, Mapping)
        and declared["payable"] is True
        and type(declared["cost"]) is int
        and sun is not None
    ):
        above = sun - declared["cost"]
    return {
        "sun": sun,
        "band": economy_band(sun, costs),
        "cheapest_cost": costs[0] if costs else None,
        "highest_cost": costs[-1] if costs else None,
        "plan": declared,
        "sun_above_plan": above,
    }


def lane_needs_response(rows: Sequence[RowSignals]) -> bool:
    """True when at least one lane may not be left to a later decision.

    A lane counts when its ordered urgency band is ``high`` or higher
    (:data:`LANE_RESPONSE_URGENCIES`), or when it holds a zombie while nothing in
    that lane can attack it -- the same fact the ``undefended`` presentation band
    states. Only ordered bands and component facts are read, so no lane number,
    layout, or quota enters here.
    """
    for row in rows:
        if row.urgency in LANE_RESPONSE_URGENCIES:
            return True
        if (
            type(row.zombie_count) is int
            and row.zombie_count > 0
            and row.attacker_count == 0
        ):
            return True
    return False


@dataclass(frozen=True)
class PlantSpendDecision:
    """Which card types the plant branch may offer, and why it holds instead.

    ``hold_reason`` is set exactly when ``type_names`` is empty because the branch
    is saving: the caller then records the wait instead of asking a question whose
    every answer would spend the sun the declared plan still needs.
    """

    type_names: frozenset[str]
    hold_reason: str | None


def plant_spend_decision(
    signals: StrategySignals,
    cards: Any,
    plan: Mapping[str, Any] | None = None,
) -> PlantSpendDecision:
    """Limit the offer to placements that do not compete with the declared plan.

    The rules are code, and none of them is a configured sun threshold:

    1. No plan: the full affordable set, exactly as OD-15 enumerates it.
    2. Plan still needs sun and no lane needs a response: nothing is offered and
       the branch waits (``await_plan``). Every cheaper placement on offer now is
       exactly what would spend the plan's sun.
    3. Plan still needs sun but a lane cannot be left alone: the full affordable
       set, because an immediate answer outranks a long-term goal.
    4. Plan is payable: the plan plus every card the balance *above* the plan's
       own price can pay for. A small surplus therefore offers the plan alone,
       while a large one frees the whole hand again -- the balance no longer
       silently caps which plants the model may consider.

    ``affordable`` is always intersected with the result, so a card that is on
    cooldown or unusable is never offered back by its own plan.
    """
    affordable = signals.affordable
    if not isinstance(plan, Mapping):
        return PlantSpendDecision(affordable, None)
    declared = plan_facts(cards, signals.sun, plan)
    if declared is None or declared["cost"] is None or signals.sun is None:
        return PlantSpendDecision(affordable, None)
    cost = declared["cost"]
    if signals.sun < cost:
        if lane_needs_response(signals.rows):
            return PlantSpendDecision(affordable, None)
        return PlantSpendDecision(frozenset(), PLAN_HOLD_REASON)
    surplus = signals.sun - cost
    prices = {
        card.get("type_name"): card.get("cost")
        for card in (cards if isinstance(cards, (list, tuple)) else ())
        if isinstance(card, Mapping)
    }
    allowed = {declared["type_name"]} | {
        type_name
        for type_name in affordable
        if type(price := prices.get(type_name)) is int and price <= surplus
    }
    return PlantSpendDecision(frozenset(allowed) & affordable, None)


def _read_zombie_rows(zombies: Any) -> tuple[dict[int, int], dict[int, int], dict[int, int | None]] | None:
    """Per-row zombie count / nearest distance in cells / total hp from one sample."""
    if not isinstance(zombies, list):
        return None
    counts: dict[int, int] = {}
    nearest: dict[int, int] = {}
    hp_totals: dict[int, int | None] = {}
    for zombie in zombies:
        if not isinstance(zombie, Mapping):
            continue
        row = zombie.get("row")
        if type(row) is not int or row < 0:
            continue
        counts[row] = counts.get(row, 0) + 1
        distance = zombie.get("distance_to_house_cells")
        if _is_number(distance):
            cells = int(round(distance))
            current = nearest.get(row)
            if current is None or cells < current:
                nearest[row] = cells
        hp = _zombie_hp(zombie)
        if hp is None or hp_totals.get(row, 0) is None:
            hp_totals[row] = None
        else:
            hp_totals[row] = (hp_totals.get(row) or 0) + hp
    return counts, nearest, hp_totals


def _zombie_hp(zombie: Mapping[str, Any]) -> int | None:
    hp = zombie.get("hp")
    if _is_number(hp):
        return int(hp)
    parts = [zombie.get(key) for key in ("body_hp", "helmet_hp", "shield_hp", "balloon_hp")]
    known = [int(part) for part in parts if _is_number(part)]
    if not known:
        return None
    return sum(known)


def _read_plant_rows(plants: Any) -> dict[int, dict[str, Any]] | None:
    """Per-row attacker count and defender presence; unknown roles stay unknown."""
    if not isinstance(plants, list):
        return None
    rows: dict[int, dict[str, Any]] = {}
    for plant in plants:
        if not isinstance(plant, Mapping):
            continue
        row = plant.get("row")
        if type(row) is not int or row < 0:
            continue
        entry = rows.setdefault(row, {"attackers": 0, "defender": False, "unknown_role": False})
        role = _role_of(plant)
        if role == "attacker":
            entry["attackers"] += 1
        elif role == "defender":
            entry["defender"] = True
        elif role is None:
            entry["unknown_role"] = True
    return rows


def urgency_band(zombie_count: int, nearest_cells: int | None) -> str:
    """Map one lane's zombie count and nearest distance to an OD-30 ordered band.

    The thresholds are the OD-22 table, applied to the zombie closest to the
    house in that lane:

    ==========  ==========================================================
    ``none``    ``zombie_count == 0`` or ``nearest_cells is None``
    ``critical`` ``nearest_cells <= 1`` or (``nearest_cells <= 3`` and count >= 3)
    ``high``    ``nearest_cells <= 3`` or (``nearest_cells <= 5`` and count >= 3)
    ``medium``  ``nearest_cells <= 5``
    ``low``     otherwise (nearest 6-8)
    ==========  ==========================================================

    ``nearest_cells is None`` means the distance fact is unknown, so the band is
    reported as ``none``; callers that need to distinguish "lane clear" from
    "distance unknown" must read ``nearest_cells`` itself.
    """
    if type(zombie_count) is not int or zombie_count <= 0 or nearest_cells is None:
        return "none"
    if nearest_cells <= 1 or (nearest_cells <= 3 and zombie_count >= 3):
        return "critical"
    if nearest_cells <= 3 or (nearest_cells <= 5 and zombie_count >= 3):
        return "high"
    if nearest_cells <= 5:
        return "medium"
    return "low"


def lane_threat_band(lane: Mapping[str, Any]) -> str:
    """One lane's threat label, escalating a lane that has no attacker of its own.

    The base band is the OD-22 table (``unknown`` when a zombie is present but the
    distance fact is missing). A lane with no attacker plant is *at least* ``high``
    -- nothing there can stop a zombie -- and a lane that already holds a zombie
    while having no attacker is ``undefended``, the top label above ``critical``.
    The escalation is presentation only: scheduling and branch keys keep using
    :func:`urgency_band`, so no decision cadence changes.
    """
    count = lane.get("zombie_count")
    cells = lane.get("nearest_cells")
    attackers = lane.get("attacker_count")
    if type(attackers) is int and attackers <= 0:
        return "undefended" if type(count) is int and count > 0 else "high"
    if type(count) is int and count > 0 and cells is None:
        return "unknown"
    return urgency_band(count, cells)


def crowd_band(zombie_count: Any) -> str:
    """Ordered crowd label for one lane, so no count has to reach the model."""
    if type(zombie_count) is not int or zombie_count <= 0:
        return "none"
    if zombie_count == 1:
        return "single"
    if zombie_count == 2:
        return "pair"
    if zombie_count <= 4:
        return "small_group"
    return "horde"


def proximity_band(cells: Any) -> str | None:
    """Ordered proximity label of one zombie's distance to the house."""
    if type(cells) is not int:
        return None
    if cells <= 1:
        return "at_the_door"
    if cells <= 3:
        return "very_close"
    if cells <= 5:
        return "close"
    if cells <= 8:
        return "midfield"
    return "far"


def armor_band(zombie: Mapping[str, Any]) -> str | None:
    """``armored`` while any helmet/shield hp remains, ``none`` when reported clear."""
    reported = False
    for key in ("helmet_hp", "shield_hp"):
        value = zombie.get(key)
        if _is_number(value):
            reported = True
            if value > 0:
                return "armored"
    return "none" if reported else None


@dataclass(frozen=True)
class RowSignals:
    """Per-lane threat facts plus the ordered urgency band derived from them."""

    row: int
    zombie_count: int | None
    nearest_cells: int | None
    hp_total: int | None
    attacker_count: int | None
    has_defender: bool | None
    urgency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "zombie_count": self.zombie_count,
            "nearest_cells": self.nearest_cells,
            "hp_total": self.hp_total,
            "attacker_count": self.attacker_count,
            "has_defender": self.has_defender,
            "urgency": self.urgency,
        }


@dataclass(frozen=True)
class StrategySignals:
    """The four signal groups the strategy layer hands to JEV or to a branch key."""

    sun: int | None
    affordable: frozenset[str]
    economy_signal: str
    phase: str
    rows: tuple[RowSignals, ...]
    empty_plantable_cells: tuple[tuple[int, int], ...] | None
    occupied_cells: frozenset[tuple[int, int, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sun": self.sun,
            "affordable": sorted(self.affordable),
            "economy_signal": self.economy_signal,
            "phase": self.phase,
            "rows": [row.to_dict() for row in self.rows],
            "empty_plantable_cells": (
                None
                if self.empty_plantable_cells is None
                else [[row, col] for row, col in self.empty_plantable_cells]
            ),
            "occupied_cells": [[row, col, cell] for row, col, cell in sorted(self.occupied_cells)],
        }


def _row_signals(
    row: int,
    zombie_rows: tuple[dict[int, int], dict[int, int], dict[int, int | None]] | None,
    plant_rows: dict[int, dict[str, Any]] | None,
) -> RowSignals:
    if zombie_rows is None:
        zombie_count: int | None = None
        nearest_cells: int | None = None
        hp_total: int | None = None
    else:
        counts, nearest, hp_totals = zombie_rows
        zombie_count = counts.get(row, 0)
        nearest_cells = nearest.get(row)
        hp_total = hp_totals.get(row) if row in counts else 0
    if plant_rows is None:
        attacker_count: int | None = None
        has_defender: bool | None = None
    else:
        entry = plant_rows.get(row)
        if entry is None:
            attacker_count, has_defender = 0, False
        elif entry["unknown_role"]:
            attacker_count, has_defender = None, None
        else:
            attacker_count, has_defender = entry["attackers"], entry["defender"]
    return RowSignals(
        row=row,
        zombie_count=zombie_count,
        nearest_cells=nearest_cells,
        hp_total=hp_total,
        attacker_count=attacker_count,
        has_defender=has_defender,
        urgency=urgency_band(zombie_count or 0, nearest_cells),
    )


def _phase(rows: tuple[RowSignals, ...], economy_signal: str) -> str:
    """Derive the global strategic phase from lane urgency and the resource layer.

    Rules, evaluated in order (all of them use the current sample only):

    1. ``emergency`` — any lane urgency is ``critical``.
    2. ``defense`` — any lane urgency is ``high`` (and none is ``critical``).
    3. ``recovery`` — any lane urgency is ``medium`` (and none is higher):
       threats are close enough to need the line rebuilt before contact.
    4. ``economy`` — every lane is ``none`` and the resource layer says
       ``expand`` (an affordable sun producer is in hand right now).
    5. ``development`` — everything else (lanes ``none``/``low`` without an
       expanding economy).
    """
    urgencies = {row.urgency for row in rows}
    if "critical" in urgencies:
        return "emergency"
    if "high" in urgencies:
        return "defense"
    if "medium" in urgencies:
        return "recovery"
    if economy_signal == "expand" and urgencies <= {"none"}:
        return "economy"
    return "development"


def evaluate_strategy(jev_state: Mapping[str, Any]) -> StrategySignals:
    """Turn one JEV State projection into the four decision-signal groups.

    Only facts present in ``jev_state`` are used; nothing is projected forward.
    ``sun`` and ``affordable`` describe the current sample, ``empty_plantable_cells``
    lists every projected ``None`` cell as an actionable position, and each row
    carries its ordered urgency band plus explicit component facts. Missing data
    stays ``None`` instead of being guessed.
    """
    if not isinstance(jev_state, Mapping):
        jev_state = {}
    board = jev_state.get("board")
    cells = board.get("cells") if isinstance(board, Mapping) else None
    empty_plantable_cells, occupied_cells = _read_board(cells)
    sun = _read_sun(jev_state.get("sun_balance"))
    cards = jev_state.get("cards")
    affordable = _read_affordable(cards, sun)
    economy_signal = _read_economy_signal(cards, affordable)
    zombie_rows = _read_zombie_rows(jev_state.get("zombies"))
    plant_rows = _read_plant_rows(jev_state.get("plants"))
    row_count = len(cells) if isinstance(cells, list) and cells else DEFAULT_ROW_COUNT
    rows = tuple(_row_signals(row, zombie_rows, plant_rows) for row in range(row_count))
    return StrategySignals(
        sun=sun,
        affordable=affordable,
        economy_signal=economy_signal,
        phase=_phase(rows, economy_signal),
        rows=rows,
        empty_plantable_cells=empty_plantable_cells,
        occupied_cells=occupied_cells,
    )


def build_plant_branch_state_key(signals: StrategySignals, *, wave: int | None = None) -> Hashable:
    """OD-22 PlantBranch key: affordable cards, per-lane facts, occupied cells.

    Only the ordered urgency band, ``zombie_count``, ``attacker_count``, and
    ``has_defender`` enter the per-lane part; raw ``nearest_cells``, raw hp, and
    every sample metadata field are excluded, so a continuous distance or hp
    change inside one band does not produce a new key.

    ``wave == 0`` means the level has not started, where the game still reports a
    transient batch of preset zombies that vanishes a fraction of a second later
    (measured: 9 zombies at ``distance 8`` gone within 0.93 s). Those zombie
    components are dropped from the key then, so the transient neither invalidates
    a first planting decision nor becomes a planting premise (OD-45, R34). A
    missing, unparseable, or ``None`` ``wave`` is fail-safe: the zombie components
    stay in the key exactly as before.
    """
    zombie_lane_facts: Hashable = (
        ()
        if wave == 0
        else tuple(
            (row.urgency, row.zombie_count, row.attacker_count, row.has_defender)
            for row in signals.rows
        )
    )
    return (
        signals.affordable,
        zombie_lane_facts,
        signals.occupied_cells,
    )


def build_collect_branch_state_key(jev_state: Mapping[str, Any]) -> frozenset[tuple[int, int]]:
    """OD-32 CollectBranch key: ``frozenset((type_code, count))``.

    The key answers exactly one question: did the set of collectable items change?
    Only which item types are visible and how many of each are in it; item
    coordinates, item ids, and every sample metadata field are excluded.

    Coordinates used to be part of this key as rounded 8 px cells (the OD-22
    definition). That premise was wrong: a dropped item keeps falling for the whole
    JEV round trip -- measured 263-507 ms against a 20 px fall, i.e. three cells --
    so the key changed on every sample and every already answered collect decision
    was thrown away as ``superseded`` before it could be dispatched. Item identity
    is now bound by item id at dispatch time (OD-32) instead, which tolerates any
    amount of motion without ever re-binding to a different item.

    An item without a non-negative integer ``type_code`` or without finite
    coordinates is skipped: such an item can never be offered as a collect option
    (:func:`jev.client._collect_item_facts` drops it too), so it must not move the
    key either.
    """
    items = jev_state.get("items") if isinstance(jev_state, Mapping) else None
    if not isinstance(items, list):
        return frozenset()
    counts: dict[int, int] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        type_code = item.get("type_code")
        x = item.get("x")
        y = item.get("y")
        if type(type_code) is not int or type_code < 0 or not _is_number(x) or not _is_number(y):
            continue
        counts[type_code] = counts.get(type_code, 0) + 1
    return frozenset(counts.items())


def build_branch_state_key(
    branch: str,
    jev_state: Mapping[str, Any],
    signals: StrategySignals | None = None,
) -> Hashable:
    """Build the OD-32 semantic key for one branch; compare with ``==``.

    The result is hashable. ``sample_sequence``, ``observed_at_utc``,
    ``identity_verified_at_utc``, latency, raw distance, raw ``x``/``y``, and raw
    hp are excluded by construction. The PlantBranch key needs ``signals`` and
    recomputes them from ``jev_state`` when they are not supplied.
    """
    if branch == BRANCH_PLANT:
        resolved = signals if signals is not None else evaluate_strategy(jev_state)
        return build_plant_branch_state_key(resolved, wave=_read_wave(jev_state))
    if branch == BRANCH_COLLECT:
        return build_collect_branch_state_key(jev_state)
    raise ValueError(f"unknown branch: {branch!r}")


def _read_wave(jev_state: Mapping[str, Any]) -> int | None:
    """Read ``game.wave`` as a non-negative ``int``; anything else is ``None``.

    ``None`` is the conservative value: it keeps every zombie component in the
    key, so a missing or malformed wave only ever makes the key more sensitive.
    """
    if not isinstance(jev_state, Mapping):
        return None
    game = jev_state.get("game")
    wave = game.get("wave") if isinstance(game, Mapping) else None
    if type(wave) is int and wave >= 0:
        return wave
    return None


def build_plant_candidates(
    jev_state: Mapping[str, Any],
    signals: StrategySignals | None = None,
    *,
    plan: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate every validated ``{"type_name", "row", "col"}`` candidate.

    Without a ``plan`` the set is exactly ``affordable`` x
    ``empty_plantable_cells``: the cells are projected empty-and-plantable
    positions and the types are payable, usable, cooldown-ready cards, so no
    candidate needs further filtering. Per OD-15 the enumeration is complete,
    with no local ranking, no cap, and no shortlist; the order is the
    deterministic ``(type_name, row, col)`` enumeration order (not a strategy)
    so tests and Trace stay stable.

    A declared ``plan`` first limits the affordable set through
    :func:`plant_spend_decision`, so the placements offered are the plan plus
    whatever the balance above the plan's own price can pay for. An empty list
    then means the caller must wait locally; the economy hold is
    ``await_plan`` and the pre-existing reasons stay
    (``wait``/``await_resource``/``await_cooldown``).
    """
    resolved = signals if signals is not None else evaluate_strategy(jev_state)
    cells = resolved.empty_plantable_cells
    allowed = plant_spend_decision(resolved, jev_state.get("cards"), plan).type_names
    if not cells or not allowed:
        return []
    return [
        {"type_name": type_name, "row": row, "col": col}
        for type_name in sorted(allowed)
        for row, col in sorted(cells)
    ]


def removable_cells(jev_state: Mapping[str, Any]) -> tuple[tuple[int, int, str], ...]:
    """Every board cell the runtime can offer for removal, stably ordered.

    A cell is removable exactly when its projected value is ``plant:<type_name>``
    with a non-empty type name -- the same encoding
    ``ActionBoundary._validate_shovel`` requires. Every other value (``None``,
    ``False``, ``"unknown"``, a number) and a missing or malformed grid is
    ignored instead of guessed. The result is ``(row, col, type_name)`` sorted by
    row then column, so the same sample always enumerates identically.

    The type name is not restricted to the catalog: a board cell carries no type
    code, and a name the catalog cannot resolve is stated as facts with
    ``role: null`` rather than dropped.
    """
    if not isinstance(jev_state, Mapping):
        return ()
    board = jev_state.get("board")
    cells = board.get("cells") if isinstance(board, Mapping) else None
    if not isinstance(cells, list) or not cells or not all(isinstance(row, list) for row in cells):
        return ()
    found: list[tuple[int, int, str]] = []
    for row_index, row in enumerate(cells):
        for column_index, cell in enumerate(row):
            if not isinstance(cell, str) or not cell.startswith("plant:"):
                continue
            type_name = cell[len("plant:"):]
            if type_name:
                found.append((row_index, column_index, type_name))
    return tuple(sorted(found))


def management_facts(
    jev_state: Mapping[str, Any],
    all_state: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Current observations and arithmetic, without desired counts or layouts.

    ``plan`` only enriches the ``economy`` group with the goal the model already
    declared; it is never invented here and never turns into a lineup.
    """
    from configs.plant_catalog import production_currency
    sun = _read_sun(jev_state.get("sun_balance"))
    cards = []
    for card in jev_state.get("cards") or []:
        if not isinstance(card, Mapping): continue
        info = plant_info(card.get("type_code")); cost = card.get("cost")
        resolved = info is not None and info.name == card.get("type_name")
        cards.append({"type_name": info.name if resolved else card.get("type_name"), "cost": cost,
                      "payable": None if sun is None or not _is_number(cost) else sun >= cost,
                      "shortfall": None if sun is None or not _is_number(cost) else max(0, cost - sun),
                      "usable": card.get("usable"), "cooldown_ready": card.get("cooldown_ready"),
                      "description_en": info.description_en if resolved else None,
                      "production_currency": production_currency(info.name) if resolved else None,
                      "role": _role_of(card)})
    plants = jev_state.get("plants"); counts = {}
    for plant in plants or []:
        if isinstance(plant, Mapping):
            name = plant.get("type_name")
            if isinstance(name, str): counts[name] = counts.get(name, 0) + 1
    board = jev_state.get("board")
    board_facts = None
    rows_count = DEFAULT_ROW_COUNT
    if isinstance(board, Mapping):
        rows_count = _board_rows(board)
        board_facts = {"cells": board.get("cells"), "column_direction": _board_column_direction(board)}
    game = jev_state.get("game")
    source_game = all_state.get("game") if isinstance(all_state, Mapping) else None
    availability = all_state.get("availability", {}) if isinstance(all_state, Mapping) else {}
    matching = isinstance(all_state, Mapping) and jev_state.get("sample_sequence") is not None and jev_state.get("observed_at_utc") is not None and all_state.get("sample_sequence") == jev_state.get("sample_sequence") and all_state.get("observed_at_utc") == jev_state.get("observed_at_utc")
    waves = {key: game.get(key) if matching and isinstance(game, Mapping) and isinstance(source_game, Mapping) and game.get(key) == source_game.get(key) and availability.get(f"game.{key}") in {"available", "provisional"} and _is_number(game.get(key)) and game[key] >= 0 else None for key in ("wave", "total_waves")}
    observed_lanes = [{key: row.to_dict().get(key) for key in ("row", "zombie_count", "nearest_cells", "hp_total", "attacker_count", "has_defender")} for row in evaluate_strategy(jev_state).rows]
    return {"sun": sun, "cards": cards, "economy": economy_facts(jev_state, plan),
            "plant_counts": counts if isinstance(plants, list) else None,
            "lane_composition": _lane_composition(plants, rows_count),
            "board": board_facts,
            "plants": [{**{key: plant.get(key) for key in ("type_name", "row", "col", "hp")}, "role": _role_of(plant), "description_en": _description_of(plant)} for plant in plants if isinstance(plant, Mapping)] if isinstance(plants, list) else None,
            "zombies": [{key: z.get(key) for key in ("type_name", "row", "distance_to_house_cells", "hp", "body_hp", "helmet_hp", "shield_hp")} for z in jev_state.get("zombies") or [] if isinstance(z, Mapping)],
            "observed_lanes": observed_lanes, "waves": waves}


def threat_label_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Replace the zombie-side threat numbers of one request state with labels.

    The model compares ordered labels far more reliably than integers, and the
    comparisons are already made by code (the OD-22 band table, plus the ordered
    crowd/proximity/armor labels). Only zombie-side facts are labelled: the
    per-lane plant counts, the sun, the waves and every card/plant fact stay as
    they were, and no key is added or removed. The numeric form keeps feeding
    :func:`management_state_key`, which reads :func:`management_facts` directly.
    """
    result = dict(facts)
    zombies = facts.get("zombies")
    if isinstance(zombies, list):
        result["zombies"] = [
            {
                "type_name": zombie.get("type_name"),
                "row": zombie.get("row"),
                "proximity": proximity_band(zombie.get("distance_to_house_cells")),
                "armor": armor_band(zombie),
            }
            for zombie in zombies
            if isinstance(zombie, Mapping)
        ]
    lanes = facts.get("observed_lanes")
    if isinstance(lanes, list):
        names_by_row: dict[Any, list[str]] = {}
        for zombie in zombies or []:
            if isinstance(zombie, Mapping) and isinstance(zombie.get("type_name"), str):
                bucket = names_by_row.setdefault(zombie.get("row"), [])
                if zombie["type_name"] not in bucket:
                    bucket.append(zombie["type_name"])
        result["observed_lanes"] = [
            {
                "row": lane.get("row"),
                "threat": lane_threat_band(lane),
                "crowd": crowd_band(lane.get("zombie_count")),
                "composition": ", ".join(sorted(names_by_row.get(lane.get("row"), []))) or None,
                "attacker_count": lane.get("attacker_count"),
                "has_defender": lane.get("has_defender"),
            }
            for lane in lanes
            if isinstance(lane, Mapping)
        ]
    return result


def management_state_key(jev_state: Mapping[str, Any], all_state: Mapping[str, Any] | None = None) -> Hashable:
    import json
    facts = management_facts(jev_state, all_state)
    del facts["observed_lanes"]  # Raw HP/distances remain facts, never per-frame triggers.
    facts["zombies"] = [(z.get("type_name"), z.get("row"), int(z["distance_to_house_cells"]) if _is_number(z.get("distance_to_house_cells")) else None) for z in facts["zombies"]]
    facts["plants"] = [(p.get("type_name"), p.get("row"), p.get("col")) for p in facts["plants"] or []]
    return json.dumps(facts, sort_keys=True)


def collect_identity_key(all_state: Mapping[str, Any]) -> Hashable:
    return tuple((item.get("id"), item.get("type_code")) for item in all_state.get("items") or [] if isinstance(item, Mapping))
