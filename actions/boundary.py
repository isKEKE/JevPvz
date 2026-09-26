"""Decision-facing validation and adaptation for guarded PvZ actions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from configs.item_catalog import item_name
from configs.plant_catalog import plant_info
from .executor import ActionExecutor


_PLANT_AVAILABILITY = frozenset({"available", "provisional"})
_ITEM_AVAILABILITY = frozenset({"available", "provisional"})
_ACTIONS = frozenset({"place_plant", "collect_item", "shovel_cell"})


class ActionValidationError(ValueError):
    """A semantic action could not be proven safe from the supplied State pair."""


@dataclass(frozen=True)
class ValidatedAction:
    """Normalized executor arguments produced only after boundary validation."""

    action: str
    arguments: Mapping[str, Any]


class ActionValidator:
    """Fail-closed checks over decision-visible JEV State and matching All State."""

    def validate(
        self,
        request: Any,
        *,
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
    ) -> ValidatedAction:
        if not isinstance(request, Mapping):
            raise ActionValidationError("Action request must be an object.")
        if any(not isinstance(key, str) for key in request):
            raise ActionValidationError("Action request keys must be strings.")
        if not isinstance(jev_state, Mapping) or not isinstance(all_state, Mapping):
            raise ActionValidationError("JEV State and All State must both be objects.")
        self._require_same_sample(jev_state, all_state)

        action = request.get("action")
        if not isinstance(action, str) or action not in _ACTIONS:
            raise ActionValidationError("action must be place_plant, collect_item, or shovel_cell.")

        common = {"action", "timeout_ms", "poll_interval_ms"}
        fields = {
            "place_plant": common | {"type_name", "row", "col"},
            "collect_item": common | {"type_code", "type_name", "x", "y"},
            "shovel_cell": common | {"row", "col"},
        }[action]
        extras = set(request) - fields
        if extras:
            raise ActionValidationError(
                f"Unsupported request key(s): {', '.join(sorted(extras))}."
            )
        required = {
            "place_plant": {"type_name", "row", "col"},
            "collect_item": {"type_code", "type_name", "x", "y"},
            "shovel_cell": {"row", "col"},
        }[action]
        missing = required - set(request)
        if missing:
            raise ActionValidationError(
                f"Missing request key(s): {', '.join(sorted(missing))}."
            )

        arguments = self._timing_arguments(request)
        if action == "place_plant":
            arguments.update(self._validate_place(request, jev_state, all_state))
        elif action == "collect_item":
            arguments.update(self._validate_collect(request, jev_state, all_state))
        else:
            arguments.update(self._validate_shovel(request, jev_state, all_state))
        return ValidatedAction(action=action, arguments=arguments)

    @staticmethod
    def _require_same_sample(
        jev_state: Mapping[str, Any], all_state: Mapping[str, Any]
    ) -> None:
        jev_sequence = jev_state.get("sample_sequence")
        all_sequence = all_state.get("sample_sequence")
        if (
            not _is_int(jev_sequence) or jev_sequence < 1
            or not _is_int(all_sequence) or all_sequence < 1
            or jev_sequence != all_sequence
        ):
            raise ActionValidationError(
                "JEV State and All State must have the same valid sample_sequence."
            )

    @staticmethod
    def _timing_arguments(request: Mapping[str, Any]) -> dict[str, int]:
        result: dict[str, int] = {}
        ranges = {"timeout_ms": (100, 120_000), "poll_interval_ms": (50, 2_000)}
        for name, (minimum, maximum) in ranges.items():
            if name not in request:
                continue
            value = request[name]
            if not _is_int(value) or not minimum <= value <= maximum:
                raise ActionValidationError(
                    f"{name} must be an integer from {minimum} through {maximum}."
                )
            result[name] = value
        return result

    def _validate_place(
        self,
        request: Mapping[str, Any],
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        type_name = _known_name(request.get("type_name"), "type_name")
        row, col = _coordinates(request)
        card = self._unique_card(jev_state, type_name)
        if card.get("usable") is not True:
            raise ActionValidationError("Selected card usable must be the boolean true.")
        cell = self._board_cell(jev_state, row, col)
        if cell is not None:
            raise ActionValidationError("place_plant requires the target JEV board cell to be null.")

        plants = self._all_plants(all_state)
        if any(plant["row"] == row and plant["col"] == col for plant in plants):
            raise ActionValidationError(
                "JEV and All State disagree: the requested plant cell is not empty."
            )
        slot = card.get("slot")
        if not _is_int(slot) or not 0 <= slot <= 9:
            raise ActionValidationError("Selected card has an invalid zero-based slot.")
        return {
            "type_name": type_name,
            "card_slot": slot + 1,
            "row": row,
            "col": col,
        }

    def _validate_shovel(
        self,
        request: Mapping[str, Any],
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        row, col = _coordinates(request)
        cell = self._board_cell(jev_state, row, col)
        if not isinstance(cell, str) or not cell.startswith("plant:"):
            raise ActionValidationError(
                "shovel_cell requires a JEV cell encoded as plant:<type_name>."
            )
        type_name = _known_name(cell[len("plant:"):], "target plant type_name")
        plants = self._all_plants(all_state)
        target_plants = [
            plant for plant in plants if plant["row"] == row and plant["col"] == col
        ]
        if not target_plants:
            raise ActionValidationError(
                "JEV and All State disagree: the requested plant cell has no plant entity."
            )
        if not any(plant["type_name"] == type_name for plant in target_plants):
            raise ActionValidationError(
                "JEV and All State disagree about the plant occupying the requested cell."
            )
        return {"row": row, "col": col}

    def _validate_collect(
        self,
        request: Mapping[str, Any],
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        attributes = _item_attributes(request, "request item")
        jev_items = jev_state.get("items")
        if not isinstance(jev_items, list):
            raise ActionValidationError("JEV items are unavailable or malformed.")
        jev_matches = [
            item for item in jev_items
            if _item_attributes(item, "JEV item") == attributes
        ]
        if len(jev_matches) != 1:
            raise ActionValidationError(
                "The requested visible item must occur exactly once in the current JEV State."
            )

        items = self._all_items(all_state)
        matches = [item for item in items if _item_attributes(item, "All State item") == attributes]
        if len(matches) != 1:
            raise ActionValidationError(
                "The visible item attributes must resolve to exactly one current All State item ID."
            )
        return {"item_id": matches[0]["id"]}

    def _unique_card(
        self, jev_state: Mapping[str, Any], requested_type_name: str
    ) -> Mapping[str, Any]:
        cards = jev_state.get("cards")
        if not isinstance(cards, list) or not cards:
            raise ActionValidationError("JEV cards are unavailable or malformed.")
        seen_slots: set[int] = set()
        matches: list[Mapping[str, Any]] = []
        required_fields = {
            "slot", "type_code", "type_name", "cost", "cooldown_ready", "usable",
        }
        for card in cards:
            if not isinstance(card, Mapping) or not required_fields.issubset(card):
                raise ActionValidationError("JEV cards contain an incomplete card record.")
            slot, type_code = card.get("slot"), card.get("type_code")
            name = card.get("type_name")
            if not _is_int(slot) or not 0 <= slot <= 9:
                raise ActionValidationError("JEV cards contain an invalid zero-based slot.")
            if slot in seen_slots:
                raise ActionValidationError("JEV cards contain duplicate slots.")
            seen_slots.add(slot)
            if not _is_int(type_code) or type_code < 0:
                raise ActionValidationError("JEV cards contain an unknown plant type code.")
            _require_catalog_name(type_code, name, "card plant")
            if name == requested_type_name:
                matches.append(card)
        if len(matches) != 1:
            raise ActionValidationError(
                "The requested plant type must map to exactly one current JEV card."
            )
        return matches[0]

    def _board_cell(
        self, jev_state: Mapping[str, Any], row: int, col: int
    ) -> Any:
        board = jev_state.get("board")
        cells = board.get("cells") if isinstance(board, Mapping) else None
        if (
            not isinstance(board, Mapping)
            or not _is_int(board.get("rows")) or board.get("rows") != 5
            or not _is_int(board.get("cols")) or board.get("cols") != 9
            or not isinstance(cells, list) or len(cells) != 5
            or any(not isinstance(line, list) or len(line) != 9 for line in cells)
        ):
            raise ActionValidationError("JEV board cells are unavailable or malformed.")
        for line in cells:
            for value in line:
                if value is None or value is False:
                    continue
                if (
                    isinstance(value, str)
                    and value.startswith("plant:")
                    and _valid_name(value[len("plant:"):])
                    and value[len("plant:"):] != "unknown"
                ):
                    continue
                raise ActionValidationError("JEV board contains an unknown cell value.")
        return cells[row][col]

    @staticmethod
    def _all_plants(all_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        availability = all_state.get("availability")
        plants = all_state.get("plants")
        if (
            not isinstance(availability, Mapping)
            or availability.get("plants") not in _PLANT_AVAILABILITY
            or not isinstance(plants, list)
        ):
            raise ActionValidationError("All State plants are unavailable.")
        seen_ids: set[int] = set()
        result: list[Mapping[str, Any]] = []
        for plant in plants:
            if not isinstance(plant, Mapping):
                raise ActionValidationError("All State contains a malformed plant entity.")
            plant_id = plant.get("id")
            row, col = plant.get("row"), plant.get("col")
            type_code, type_name = plant.get("type_code"), plant.get("type_name")
            if not _object_id(plant_id) or plant_id in seen_ids:
                raise ActionValidationError("All State plant IDs are incomplete or ambiguous.")
            if not _is_int(row) or not 0 <= row < 5 or not _is_int(col) or not 0 <= col < 9:
                raise ActionValidationError("All State contains a plant with an invalid row or col.")
            if not _is_int(type_code) or type_code < 0:
                raise ActionValidationError("All State contains a plant with an unknown type code.")
            _require_catalog_name(type_code, type_name, "All State plant")
            seen_ids.add(plant_id)
            result.append(plant)
        return result

    @staticmethod
    def _all_items(all_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        availability = all_state.get("availability")
        items = all_state.get("items")
        if (
            not isinstance(availability, Mapping)
            or availability.get("items") not in _ITEM_AVAILABILITY
            or availability.get("items.position") not in _ITEM_AVAILABILITY
            or not isinstance(items, list)
        ):
            raise ActionValidationError("All State items or item positions are unavailable.")
        seen_ids: set[int] = set()
        result: list[Mapping[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ActionValidationError("All State contains a malformed item entity.")
            item_id = item.get("id")
            if not _object_id(item_id) or item_id in seen_ids:
                raise ActionValidationError("All State item IDs are incomplete or ambiguous.")
            _item_attributes(item, "All State item")
            seen_ids.add(item_id)
            result.append(item)
        return result


class ActionAdapter:
    """Convert a validated semantic action into the existing executor API."""

    def dispatch(self, action: ValidatedAction, executor: Any) -> Any:
        arguments = dict(action.arguments)
        if action.action == "place_plant":
            type_name = arguments.pop("type_name")
            card_slot = arguments.pop("card_slot")
            row, col = arguments.pop("row"), arguments.pop("col")
            return executor.place_plant(
                card_slot,
                row,
                col,
                expected_type_name=type_name,
                **arguments,
            )
        if action.action == "collect_item":
            item_id = arguments.pop("item_id")
            return executor.collect_item(item_id, **arguments)
        if action.action == "shovel_cell":
            row, col = arguments.pop("row"), arguments.pop("col")
            return executor.shovel_cell(row, col, **arguments)
        raise ActionValidationError("Validated action has an unsupported action name.")


class ActionBoundary:
    """Single decision-facing entry point for validation and guarded dispatch."""

    def __init__(
        self,
        executor: Any | None = None,
        *,
        validator: ActionValidator | None = None,
        adapter: ActionAdapter | None = None,
    ):
        self._executor = executor if executor is not None else ActionExecutor()
        self._validator = validator if validator is not None else ActionValidator()
        self._adapter = adapter if adapter is not None else ActionAdapter()

    def dispatch(
        self,
        request: Any,
        *,
        jev_state: Mapping[str, Any],
        all_state: Mapping[str, Any],
    ) -> Any:
        validated = self._validator.validate(
            request,
            jev_state=jev_state,
            all_state=all_state,
        )
        return self._adapter.dispatch(validated, self._executor)


def _coordinates(request: Mapping[str, Any]) -> tuple[int, int]:
    row, col = request.get("row"), request.get("col")
    if not _is_int(row) or not 0 <= row < 5:
        raise ActionValidationError("row must be an integer from 0 through 4.")
    if not _is_int(col) or not 0 <= col < 9:
        raise ActionValidationError("col must be an integer from 0 through 8.")
    return row, col


def _known_name(value: Any, label: str) -> str:
    if not _valid_name(value) or value == "unknown":
        raise ActionValidationError(f"{label} must be a known, non-empty name.")
    return value


def _valid_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def _require_catalog_name(type_code: int, type_name: Any, label: str) -> None:
    name = _known_name(type_name, f"{label} type_name")
    info = plant_info(type_code)
    if info is None or info.name != name:
        raise ActionValidationError(f"{label} has an unknown or conflicting type code/name.")


def _item_attributes(item: Any, label: str) -> tuple[int, str, int | float, int | float]:
    if not isinstance(item, Mapping):
        raise ActionValidationError(f"{label} must be an object.")
    type_code = item.get("type_code")
    type_name = _known_name(item.get("type_name"), f"{label} type_name")
    x, y = item.get("x"), item.get("y")
    if not _is_int(type_code) or type_code < 0:
        raise ActionValidationError(f"{label} type_code must be a non-negative integer.")
    if item_name(type_code) != type_name:
        raise ActionValidationError(f"{label} has an unknown or conflicting type code/name.")
    if not _finite_number(x) or not _finite_number(y):
        raise ActionValidationError(f"{label} x and y must be finite numbers.")
    return type_code, type_name, x, y


def _object_id(value: Any) -> bool:
    return _is_int(value) and 0 <= value <= 0xFFFFFFFF


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


__all__ = [
    "ActionAdapter",
    "ActionBoundary",
    "ActionValidationError",
    "ActionValidator",
    "ValidatedAction",
]
