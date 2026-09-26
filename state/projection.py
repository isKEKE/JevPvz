"""Explicit decision-facing projections of JSON-ready State samples."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .schema import to_json_record


def project_jev_state(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Project one All State record through the fixed JEV allowlist.

    This function deliberately constructs every output mapping rather than
    copying and deleting diagnostic fields. Missing values stay null; field
    availability diagnostics remain in All State and are not sent to JEV.
    """
    state = to_json_record(sample)
    game = state.get("game") if isinstance(state.get("game"), Mapping) else {}
    board = state.get("board") if isinstance(state.get("board"), Mapping) else {}
    availability = state.get("availability") if isinstance(state.get("availability"), Mapping) else {}

    def pick(source: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: deepcopy(source.get(key)) for key in keys}

    def pick_jev_zombie(zombie: Mapping[str, Any]) -> dict[str, Any]:
        return pick(
            zombie,
            ("type_code", "type_name", "row", "x", "y", "hp", "body_hp", "helmet_hp", "shield_hp", "balloon_hp", "distance_to_house_px", "distance_to_house_cells"),
        )

    source_cells = board.get("cells")
    occupancy_status = availability.get("board.occupancy", "unavailable")
    plantability_grid = board.get("plantability")
    occupancy_valid = (
        occupancy_status in {"available", "provisional"}
        and isinstance(source_cells, list)
        and len(source_cells) == 5
        and all(
            isinstance(row, list)
            and len(row) == 9
            and all(
                cell is None
                or (
                    isinstance(cell, Mapping)
                    and isinstance(cell.get("type_code"), int)
                    and not isinstance(cell.get("type_code"), bool)
                )
                for cell in row
            )
            for row in source_cells
        )
    )
    plantability_shape_valid = (
        isinstance(plantability_grid, list)
        and len(plantability_grid) == 5
        and all(isinstance(row, list) and len(row) == 9 for row in plantability_grid)
    )
    plantability_values_valid = plantability_shape_valid and all(
        type(cell) is bool or cell is None or cell == "unknown"
        for row in plantability_grid
        for cell in row
    )
    standard_day_lawn = game.get("background") == "day"
    compact_cells = None
    if occupancy_valid and plantability_values_valid and standard_day_lawn:
        compact_cells = []
        for row_index, row in enumerate(source_cells):
            projected_row: list[str | bool | None] = []
            for column_index, cell in enumerate(row):
                if isinstance(cell, Mapping):
                    type_name = cell.get("type_name")
                    if not isinstance(type_name, str) or not type_name:
                        compact_cells = None
                        break
                    projected_row.append(f"plant:{type_name}")
                else:
                    plantability = plantability_grid[row_index][column_index]
                    projected_row.append(False if plantability is False else None)
            if compact_cells is None:
                break
            compact_cells.append(projected_row)

    result: dict[str, Any] = {
        "schema_version": state.get("schema_version"),
        "observed_at_utc": state.get("observed_at_utc"),
        "sample_sequence": state.get("sample_sequence"),
        "status": state.get("status"),
        "valid": state.get("valid"),
        "decision_ready": state.get("decision_ready"),
        "game": pick(game, ("phase", "mode", "background", "paused", "level", "wave", "total_waves", "level_complete")),
        "sun_balance": deepcopy(state.get("sun_balance")),
        "board": {
            "rows": 5,
            "cols": 9,
            "cells": compact_cells,
        },
        "plants": None if state.get("plants") is None else [
            pick(plant, ("type_code", "type_name", "row", "col"))
            for plant in state["plants"] if isinstance(plant, Mapping)
        ],
        "zombies": None if state.get("zombies") is None else [
            pick_jev_zombie(zombie)
            for zombie in state["zombies"] if isinstance(zombie, Mapping)
        ],
        "lanes": [
            pick(lane, ("row", "zombie_count", "nearest_zombie_distance_to_house_cells"))
            for lane in state.get("lanes", []) if isinstance(lane, Mapping)
        ],
        "items": None if state.get("items") is None else [
            pick(item, ("type_code", "type_name", "x", "y")) for item in state["items"] if isinstance(item, Mapping)
        ],
        "cards": None if state.get("cards") is None else [
            pick(card, ("slot", "type_code", "type_name", "cost", "cooldown_ready", "usable"))
            for card in state["cards"] if isinstance(card, Mapping)
        ],
    }
    return result
