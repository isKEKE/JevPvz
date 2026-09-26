"""Build conservative, versioned State snapshots from P02 raw observations."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from itertools import count
from typing import Any, Callable, Mapping

from configs.pvz_1051 import LAWN_GEOMETRY, TARGET_IDENTITY
from configs.plant_catalog import plant_info
from configs.zombie_catalog import zombie_name
from configs.item_catalog import item_name
from game.reader import read_raw_snapshot
from runtime.memory import ReadOnlyMemory
from runtime.process import (
    ProcessDiscoveryError,
    TargetNotRunningError,
    locate_target_process,
    main_module_base,
    verify_target_identity,
)
from .schema import StateSnapshot


_SEQUENCES = count(1)
_ARRAY_NAMES = ("plants", "zombies", "items")

# Plants that upgrade another plant and receive the Endless Survival surcharge.
# The current price rule adds 50 sun for each live plant of the same type.
_ENDLESS_UPGRADE_PLANT_CODES = frozenset({40, 41, 42, 43, 44, 46, 47})

_SCENE_NAMES = {
    0: "loading", 1: "menu", 2: "level_intro", 3: "playing",
    4: "zombies_win", 5: "level_award", 6: "credits", 7: "challenge",
}
_BACKGROUND_NAMES = {
    0: "day", 1: "night", 2: "pool", 3: "fog", 4: "roof",
    5: "boss_arena", 6: "mushroom_garden", 7: "greenhouse", 8: "zombiquarium", 9: "tree_of_wisdom",
}
_MODE_NAMES = {
    0: "adventure",
    **{code: f"survival_normal_stage_{code}" for code in range(1, 6)},
    **{code: f"survival_hard_stage_{code - 5}" for code in range(6, 11)},
    **{code: f"survival_endless_stage_{code - 10}" for code in range(11, 16)},
    **dict(enumerate(("war_and_peas", "wall_nut_bowling", "slot_machine", "it's_raining_seeds",
        "beghouled", "invisighoul", "seeing_stars", "zombiquarium", "beghouled_twist",
        "big_trouble_little_zombie", "portal_combat", "column_like_you_see", "bobsled_bonanza",
        "speed", "whack_a_zombie", "last_stand", "war_and_peas_2", "wall_nut_bowling_2",
        "pogo_party", "boss_rush", "art_challenge_wall_nut", "sunny_day", "grave_danger",
        "heavy_rain", "big_time", "art_challenge_sunflower", "air_raid", "ice_level",
        "zen_garden", "high_gravity", "graveyard", "shovel", "stormy_night",
        "bungee_blitz", "squirrel").__iter__(), start=16)),
    50: "tree_of_wisdom",
    **{code: f"vasebreaker_stage_{code - 50}" for code in range(51, 61)},
    **{code: f"i_zombie_stage_{code - 60}" for code in range(61, 71)},
    71: "promotion", 72: "intro",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_value(field: Any) -> Any:
    if isinstance(field, Mapping) and "value" in field:
        return field["value"]
    return field


def _status(raw_domain: Any) -> tuple[str, str]:
    if not isinstance(raw_domain, Mapping):
        return "unavailable", "unavailable"
    status = str(raw_domain.get("status", "unavailable"))
    evidence = str(raw_domain.get("evidence_level", "unavailable"))
    if status == "available" and evidence == "verified_with_gameplay":
        return "available", evidence
    if status == "unavailable":
        return ("error" if raw_domain.get("error") else "unavailable"), evidence
    if status in {"provisional", "candidate"} and "entities" in raw_domain:
        return "provisional", evidence
    if raw_domain.get("error") or raw_domain.get("read_errors"):
        return "error", evidence
    return "unavailable", evidence


def _current_card_cost(
    base_cost: Any,
    type_code: Any,
    mode_code: Any,
    plants: list[dict[str, Any]] | None,
) -> int | None:
    """Calculate prices for Adventure and standard Survival modes."""
    if not _integer(base_cost) or base_cost < 0 or not _integer(type_code):
        return None
    if mode_code == 0 or mode_code in range(1, 11):  # Adventure and Normal/Hard Survival.
        return base_cost
    if mode_code not in range(11, 16):  # Endless Survival stages only.
        return None
    if type_code not in _ENDLESS_UPGRADE_PLANT_CODES:
        return base_cost
    if plants is None:
        return None
    matching_plants = sum(1 for plant in plants if plant.get("type_code") == type_code)
    return base_cost + 50 * matching_plants


def _cooldown_ready(progress: Any, total: Any, usable_flag: Any) -> bool | None:
    """Use the dynamically verified SeedPacket usable byte for readiness.

    The raw counters are useful diagnostics, but valid ready cards may be at
    either counter boundary. Requiring progress==0 left initially ready cards
    unknown even when the usable byte was set. Preserve unknown for malformed
    counters or flags.
    """
    if not (_integer(progress) and _integer(total) and _integer(usable_flag)):
        return None
    if progress < 0 or total < 0 or progress > total or usable_flag not in (0, 1):
        return None
    return usable_flag == 1


def _game_allows_card_use(
    mode_code: Any,
    scene_code: Any,
    pause_flag: Any,
    won_flag: Any,
) -> bool | None:
    """Return whether a supported live Survival/Adventure game can accept a card."""
    if not _integer(mode_code) or mode_code not in range(16):
        return None
    if pause_flag == 1 or won_flag == 1:
        return False
    if pause_flag != 0 or won_flag != 0 or not _integer(scene_code):
        return None
    if scene_code == 3:
        return True
    if scene_code in range(8):
        return False
    return None


def _card_usable(
    cost: Any,
    cooldown_ready: Any,
    sun_balance: Any,
    game_allows_use: Any,
) -> bool | None:
    """Combine slot readiness, price input, balance, and game phase."""
    if game_allows_use is False or cooldown_ready is False:
        return False
    if game_allows_use is not True or cooldown_ready is not True:
        return None
    if not (_integer(cost) and cost >= 0 and _integer(sun_balance) and sun_balance >= 0):
        return None
    return sun_balance >= cost


def _unavailable_record(message: str, *, sequence: int, status: str = "error") -> dict[str, Any]:
    availability = {
        "sun_balance": "error",
        "plants": "error",
        "board.occupancy": "error",
        "zombies": "error",
        "zombies.hp": "error",
        "items": "error",
        "items.position": "error",
        "items.type": "error",
        "collectible_suns": "unavailable",
        "cards": "unavailable",
        "cards.cooldown": "unavailable",
        "cards.cost": "unavailable",
        "cards.cooldown_ready": "unavailable",
        "cards.usable": "unavailable",
        "zombies.distance_to_house_px": "unavailable",
        "zombies.distance_to_house_cells": "unavailable",
        "lanes.nearest_zombie_distance_to_house_px": "unavailable",
        "lanes.nearest_zombie_distance_to_house_cells": "unavailable",
        "game.phase": "unavailable",
        "game.scene": "unavailable",
        "game.mode": "unavailable",
        "game.background": "unavailable",
        "game.paused": "unavailable",
        "game.level": "unavailable",
        "game.wave": "unavailable",
        "game.total_waves": "unavailable",
        "game.level_complete": "unavailable",
        "board.terrain": "unavailable",
        "board.plantability": "unavailable",
    }
    return {
        "schema_version": 1,
        "observed_at_utc": _now(),
        "sample_sequence": sequence,
        "source": {
            "pid": None,
            "profile": "pvz-1.0.0.1051",
            "exe_sha256": TARGET_IDENTITY["sha256"],
        },
        "status": status,
        "valid": False,
        "decision_ready": False,
        "availability": availability,
        "evidence": {},
        "errors": [{"scope": "connection", "message": message}],
        "missing_fields": sorted(key for key, value in availability.items() if value == "unavailable"),
        "game": {
            "scene": None, "scene_code": None, "phase": None,
            "mode": None, "mode_code": None,
            "background": None, "background_code": None,
            "paused": None, "pause_raw_code": None,
            "level": None, "level_number": None, "level_raw_code": None,
            "wave": None, "spawned_waves": None, "wave_raw_code": None,
            "total_waves": None, "total_waves_raw_code": None,
            "level_complete": None, "level_complete_raw_code": None,
        },
        "sun_balance": None,
        "board": {
            "rows": 5,
            "cols": 9,
            "terrain": None,
            "plantability": [["unknown" for _ in range(9)] for _ in range(5)],
            "cells": [[None for _ in range(9)] for _ in range(5)],
        },
        "plants": None,
        "zombies": None,
        "lanes": [{"row": row, "zombie_count": 0, "zombies": [], "nearest_zombie_distance_to_house_px": None, "nearest_zombie_distance_to_house_cells": None} for row in range(5)],
        "items": None,
        "collectible_suns": None,
        "cards": None,
        "raw_snapshot": None,
    }


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _distance_to_house_cells(x: Any, geometry: Mapping[str, Any]) -> int | None:
    if not _finite_number(x):
        return None
    if not _finite_number(geometry.get("house_x")):
        return None
    boundary = geometry.get("grid_first_boundary_x")
    pitch = geometry.get("grid_cell_width_px")
    columns = geometry.get("grid_columns")
    if not (_finite_number(boundary) and _finite_number(pitch) and pitch > 0 and _integer(columns) and columns > 0):
        return None
    index = math.floor((float(x) - float(boundary)) / float(pitch)) + 1
    return max(0, min(columns - 1, index))


def build_state(
    raw_snapshot: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    sequence: int | None = None,
    retry_count: int = 0,
) -> StateSnapshot:
    """Normalize one raw P02 sample. Single-frame values remain provisional."""
    sequence = next(_SEQUENCES) if sequence is None else sequence
    observed = str(raw_snapshot.get("captured_at_utc") or _now())
    source_record = {
        "pid": None,
        "profile": "pvz-1.0.0.1051",
        "exe_sha256": TARGET_IDENTITY["sha256"],
        "module_base": raw_snapshot.get("module_base"),
        "root_address": raw_snapshot.get("root_address"),
        "board_address": raw_snapshot.get("board_address"),
    }
    if source:
        source_record.update(dict(source))

    availability = {
        "sun_balance": "unavailable",
        "plants": "unavailable",
        "board.occupancy": "unavailable",
        "zombies": "unavailable",
        "zombies.hp": "unavailable",
        "items": "unavailable",
        "items.position": "unavailable",
        "items.type": "unavailable",
        "collectible_suns": "unavailable",
        "cards": "unavailable",
        "cards.cooldown": "unavailable",
        "cards.cost": "unavailable",
        "cards.cooldown_ready": "unavailable",
        "cards.usable": "unavailable",
        "zombies.distance_to_house_px": "unavailable",
        "zombies.distance_to_house_cells": "unavailable",
        "lanes.nearest_zombie_distance_to_house_px": "unavailable",
        "lanes.nearest_zombie_distance_to_house_cells": "unavailable",
        "game.phase": "unavailable",
        "game.scene": "unavailable",
        "game.mode": "unavailable",
        "game.background": "unavailable",
        "game.paused": "unavailable",
        "game.level": "unavailable",
        "game.wave": "unavailable",
        "game.total_waves": "unavailable",
        "game.level_complete": "unavailable",
        "board.terrain": "unavailable",
        "board.plantability": "unavailable",
    }
    evidence: dict[str, str] = {}
    errors: list[dict[str, Any]] = []
    critical_errors: list[dict[str, Any]] = []

    sun_field = raw_snapshot.get("sun")
    sun_value = _read_value(sun_field)
    if _integer(sun_value) and sun_value >= 0:
        availability["sun_balance"] = "available" if isinstance(sun_field, Mapping) and sun_field.get("evidence_level") == "verified_with_gameplay" else "provisional"
        evidence["sun_balance"] = str(sun_field.get("evidence_level", "observed_once")) if isinstance(sun_field, Mapping) else "observed_once"
    else:
        message = "Sun balance was missing or not an unsigned integer."
        errors.append({"scope": "sun_balance", "message": message})
        critical_errors.append(errors[-1])
    sun_balance = sun_value if availability["sun_balance"] in {"available", "provisional"} else None

    arrays = raw_snapshot.get("arrays", {})
    normalized: dict[str, list[dict[str, Any]] | None] = {}
    for name in _ARRAY_NAMES:
        domain = arrays.get(name) if isinstance(arrays, Mapping) else None
        state, evidence_level = _status(domain)
        entities = domain.get("entities") if isinstance(domain, Mapping) else None
        if state in {"available", "provisional"} and isinstance(entities, list):
            reported = domain.get("reported_live_count")
            scanned = domain.get("scanned_live_count", len(entities))
            if (reported is not None and reported != len(entities)) or scanned != len(entities) or domain.get("counts_match") is False:
                state = "error"
                err = {"scope": name, "message": "Reported, scanned, and decoded entity counts do not agree."}
                errors.append(err)
                critical_errors.append(err)
            else:
                normalized[name] = entities
                evidence[name] = evidence_level or "observed_once"
        elif state in {"error", "unavailable"}:
            message = str(domain.get("error") or f"{name} could not be read.") if isinstance(domain, Mapping) else f"{name} was not present in the raw sample."
            errors.append({"scope": name, "message": message})
            critical_errors.append(errors[-1])
        availability[name] = state
        if name == "plants":
            availability["board.occupancy"] = state
        if name == "zombies":
            availability["zombies.hp"] = state

    plants: list[dict[str, Any]] | None = None
    zombies: list[dict[str, Any]] | None = None
    items: list[dict[str, Any]] | None = None
    cells: list[list[dict[str, Any] | None]] = [[None for _ in range(9)] for _ in range(5)]
    lanes: list[dict[str, Any]] = [{"row": row, "zombie_count": 0, "zombies": [], "nearest_zombie_distance_to_house_px": None, "nearest_zombie_distance_to_house_cells": None} for row in range(5)]

    raw_plants = normalized.get("plants")
    if raw_plants is not None:
        built_plants: list[dict[str, Any]] = []
        occupants_by_cell: dict[tuple[int, int], list[dict[str, Any]]] = {}
        try:
            for plant in raw_plants:
                row, column, type_code = plant.get("row"), plant.get("column"), plant.get("type")
                info = plant_info(type_code)
                if not (_integer(row) and _integer(column) and info is not None) or not (0 <= row < 5 and 0 <= column < 9):
                    raise ValueError(f"Plant has an invalid type/row/column: {plant!r}")
                entry = {
                    "id": plant.get("object_id"),
                    "slot": plant.get("slot"),
                    "type_code": type_code,
                    "type_name": info.name,
                    "row": row,
                    "col": column,
                }
                occupants_by_cell.setdefault((row, column), []).append(entry)
                built_plants.append(entry)
            for (row, column), occupants in occupants_by_cell.items():
                # Pumpkin protects a plant; lily pads and flower pots support one.
                # Keep every entity while exposing the central plant at the old cell keys.
                layer_order = {30: 1, 16: 2, 33: 2}
                ordered = sorted(
                    occupants,
                    key=lambda item: (
                        layer_order.get(item["type_code"], 0),
                        item["type_code"],
                        item["id"] if _integer(item["id"]) else -1,
                        item["slot"] if _integer(item["slot"]) else -1,
                    ),
                )
                cells[row][column] = {**ordered[0], "plants": ordered, "plant_count": len(ordered)}
            plants = built_plants
        except (AttributeError, TypeError, ValueError) as exc:
            availability["plants"] = availability["board.occupancy"] = "error"
            err = {"scope": "plants", "message": str(exc)}
            errors.append(err)
            critical_errors.append(err)
            plants = None
            cells = [[None for _ in range(9)] for _ in range(5)]

    raw_zombies = normalized.get("zombies")
    if raw_zombies is not None:
        built_zombies: list[dict[str, Any]] = []
        candidate_domains = raw_snapshot.get("candidates", {})
        raw_game = candidate_domains.get("game_progress", {}) if isinstance(candidate_domains, Mapping) else {}
        raw_progress = raw_game.get("raw_candidate_fields", {}) if isinstance(raw_game, Mapping) else {}
        raw_scene = _read_value(raw_progress.get("scene")) if isinstance(raw_progress, Mapping) else None
        raw_mode = _read_value(raw_progress.get("mode")) if isinstance(raw_progress, Mapping) else None
        raw_background = _read_value(raw_progress.get("background")) if isinstance(raw_progress, Mapping) else None
        geometry = (
            LAWN_GEOMETRY.get(_BACKGROUND_NAMES.get(raw_background))
            if raw_scene == 3 and _integer(raw_mode) and raw_mode in range(16)
            else None
        ) or {}
        try:
            for zombie in raw_zombies:
                row, type_code, hp = zombie.get("row"), zombie.get("type"), zombie.get("hp")
                x, y = zombie.get("x"), zombie.get("y")
                if not (_integer(row) and 0 <= row < 5 and _integer(type_code) and _integer(hp) and hp >= 0 and _finite_number(x) and _finite_number(y)):
                    raise ValueError(f"Zombie has an invalid row, type, coordinates, or HP: {zombie!r}")
                house_x = geometry.get("house_x")
                distance = max(0.0, float(x) - house_x) if _finite_number(house_x) else None
                distance_cells = _distance_to_house_cells(x, geometry)
                armor_fields = ("helmet_hp", "shield_hp", "balloon_hp")
                armor_hp = {
                    name: max(0, zombie[name]) if _integer(zombie.get(name)) else None
                    for name in armor_fields
                }
                total_hp = hp + sum(armor_hp.values()) if all(value is not None for value in armor_hp.values()) else None
                entry = {
                    "id": zombie.get("object_id"),
                    "slot": zombie.get("slot"),
                    "type_code": type_code,
                    "type_name": zombie_name(type_code) or "unknown",
                    "row": row,
                    "x": x,
                    "y": y,
                    "hp": hp,
                    "body_hp": hp,
                    **armor_hp,
                    "total_hp": total_hp,
                    "distance_to_house_px": distance,
                    "distance_to_house_cells": distance_cells,
                }
                built_zombies.append(entry)
                lanes[row]["zombies"].append(entry.get("id") if entry.get("id") is not None else len(built_zombies) - 1)
            for lane in lanes:
                lane["zombie_count"] = len(lane["zombies"])
                lane_entries = [zombie for zombie in built_zombies if zombie["row"] == lane["row"]]
                distances = [zombie["distance_to_house_px"] for zombie in lane_entries]
                lane["nearest_zombie_distance_to_house_px"] = min(distances) if distances and all(d is not None for d in distances) else None
                cell_distances = [zombie["distance_to_house_cells"] for zombie in lane_entries]
                lane["nearest_zombie_distance_to_house_cells"] = min(cell_distances) if cell_distances and all(_integer(d) for d in cell_distances) else None
            zombies = built_zombies
            house_x = geometry.get("house_x") if isinstance(geometry, Mapping) else None
            if _finite_number(house_x):
                availability["zombies.distance_to_house_px"] = "available"
                availability["lanes.nearest_zombie_distance_to_house_px"] = "available"
                evidence["zombies.distance_to_house_px"] = "verified_with_gameplay; Human calibrated daytime house_x=0"
                evidence["lanes.nearest_zombie_distance_to_house_px"] = "derived_from_verified_zombie_distances"
            grid_geometry_valid = (
                _finite_number(house_x)
                and _finite_number(geometry.get("grid_first_boundary_x"))
                and _finite_number(geometry.get("grid_cell_width_px"))
                and _integer(geometry.get("grid_columns"))
            )
            if grid_geometry_valid:
                availability["zombies.distance_to_house_cells"] = "available"
                availability["lanes.nearest_zombie_distance_to_house_cells"] = "available"
                evidence["zombies.distance_to_house_cells"] = "verified_with_gameplay; Human calibrated 80px columns and X=50 boundary"
                evidence["lanes.nearest_zombie_distance_to_house_cells"] = "derived_from_verified_zombie_grid_distances"
        except (AttributeError, TypeError, ValueError) as exc:
            availability["zombies"] = availability["zombies.hp"] = "error"
            availability["zombies.distance_to_house_px"] = "error"
            availability["zombies.distance_to_house_cells"] = "error"
            availability["lanes.nearest_zombie_distance_to_house_px"] = "error"
            availability["lanes.nearest_zombie_distance_to_house_cells"] = "error"
            err = {"scope": "zombies", "message": str(exc)}
            errors.append(err)
            critical_errors.append(err)
            lanes = [{"row": row, "zombie_count": 0, "zombies": [], "nearest_zombie_distance_to_house_px": None, "nearest_zombie_distance_to_house_cells": None} for row in range(5)]

    raw_items = normalized.get("items")
    items_position_status = availability["items"] if raw_items is not None else "unavailable"
    if raw_items is not None:
        built_items: list[dict[str, Any]] = []
        has_positions = True
        for item in raw_items:
            x, y, type_code = item.get("x"), item.get("y"), item.get("type")
            if not (_integer(type_code) and _finite_number(x) and _finite_number(y)):
                has_positions = False
            name = item_name(type_code)
            built_items.append({
                "id": item.get("object_id"),
                "slot": item.get("slot"),
                "type_code": type_code if _integer(type_code) else None,
                "type_name": name or "unknown",
                "type_meaning": "candidate" if name else "unknown",
                "x": x if _finite_number(x) else None,
                "y": y if _finite_number(y) else None,
                "coordinate_interpretation": item.get("coordinate_interpretation", "unknown"),
            })
        items = built_items
        availability["items.position"] = availability["items"] if has_positions else "unavailable"
        availability["items.type"] = availability["items"]
        evidence["items.type"] = "static_coin_type_mapping; memory_field_provisional"

    candidates = raw_snapshot.get("candidates", {})
    cards = None
    seed = candidates.get("seed_bank") if isinstance(candidates, Mapping) else None
    if isinstance(seed, Mapping) and isinstance(seed.get("slots"), list):
        cards = []
        slot_count = _read_value(seed.get("slot_count"))
        raw_game = candidates.get("game_progress", {}) if isinstance(candidates, Mapping) else {}
        raw_progress = raw_game.get("raw_candidate_fields", {}) if isinstance(raw_game, Mapping) else {}
        raw_mode_code = _read_value(raw_progress.get("mode")) if isinstance(raw_progress, Mapping) else None
        raw_scene_code = _read_value(raw_progress.get("scene", raw_progress.get("root"))) if isinstance(raw_progress, Mapping) else None
        raw_pause_flag = _read_value(raw_progress.get("pause_flag")) if isinstance(raw_progress, Mapping) else None
        raw_won_flag = _read_value(raw_progress.get("won_flag")) if isinstance(raw_progress, Mapping) else None
        game_allows_use = _game_allows_card_use(
            raw_mode_code, raw_scene_code, raw_pause_flag, raw_won_flag
        )
        for slot in seed["slots"]:
            fields = slot.get("fields", {}) if isinstance(slot, Mapping) else {}
            type_code = _read_value(fields.get("slot_type"))
            imitator_type_code = _read_value(fields.get("imitator_type"))
            type_info = plant_info(type_code)
            price_type_code = imitator_type_code if type_code == 48 else type_code
            cost_domain = (candidates.get("plant_definition_costs", {})
                           if isinstance(candidates, Mapping) else {})
            cost_entries = cost_domain.get("entries", {}) if isinstance(cost_domain, Mapping) else {}
            cost_record = (
                cost_entries.get(str(price_type_code))
                if isinstance(cost_entries, Mapping) and _integer(price_type_code) and 0 <= price_type_code < 48
                else None
            )
            base_cost = cost_record.get("cost") if isinstance(cost_record, Mapping) else None
            current_cost = _current_card_cost(base_cost, price_type_code, raw_mode_code, plants)
            cooldown_progress = _read_value(fields.get("cooldown_progress"))
            cooldown_total = _read_value(fields.get("cooldown_total"))
            usable_flag = _read_value(fields.get("usable_flag"))
            cooldown_ready = (
                _cooldown_ready(cooldown_progress, cooldown_total, usable_flag)
                if _integer(raw_mode_code) and raw_mode_code in range(16)
                else None
            )
            cards.append({
                "slot": slot.get("index"),
                "type_code": type_code,
                "type_name": type_info.name if type_info else "unknown",
                "imitator_type_code": imitator_type_code,
                "cooldown_progress_raw": cooldown_progress,
                "cooldown_total_raw": cooldown_total,
                "usable_flag_raw": usable_flag,
                "cost": current_cost,
                "cost_source": (
                    "plant_definition_base_plus_endless_upgrade_surcharge_observed_once"
                    if current_cost is not None and raw_mode_code in range(11, 16)
                    else "plant_definition_table_verified_with_gameplay"
                    if current_cost is not None and raw_mode_code in range(11)
                    else None
                ),
                "cooldown_ready": cooldown_ready,
                "usable": _card_usable(current_cost, cooldown_ready, sun_balance, game_allows_use),
            })
        if slot_count == len(cards):
            availability["cards"] = availability["cards.cooldown"] = "provisional"
            evidence["cards"] = str(seed.get("evidence_level", "observed_once"))
            if all(card["cost"] is not None for card in cards):
                if _integer(raw_mode_code) and raw_mode_code in range(11):
                    availability["cards.cost"] = "available"
                    evidence["cards.cost"] = (
                        "verified_with_gameplay; Human confirmed standard Adventure/Survival prices against the game on 2026-09-26"
                    )
                elif _integer(raw_mode_code) and raw_mode_code in range(11, 16):
                    availability["cards.cost"] = "provisional"
                    evidence["cards.cost"] = (
                        "PlantDefinition base prices and Endless upgrade rule calculated; Endless price event not confirmed"
                    )
                else:
                    availability["cards.cost"] = "unavailable"
            else:
                availability["cards.cost"] = "unavailable"
            availability["cards.cooldown_ready"] = (
                "available" if cards and all(type(card["cooldown_ready"]) is bool for card in cards)
                else "unavailable"
            )
            if cards and all(type(card["usable"]) is bool for card in cards):
                availability["cards.usable"] = (
                    "available" if availability["cards.cost"] == "available"
                    else "provisional" if availability["cards.cost"] == "provisional"
                    else "unavailable"
                )
            else:
                availability["cards.usable"] = "unavailable"
            if availability["cards.cooldown_ready"] == "available":
                evidence["cards.cooldown_ready"] = (
                    "verified_with_gameplay; Human observed false after planting and true after cooldown recovery on 2026-09-26"
                )
            if availability["cards.usable"] == "available":
                evidence["cards.usable"] = (
                    "verified_with_gameplay; Human confirmed card state against price, cooldown, sun balance, and active gameplay on 2026-09-26"
                )
            elif availability["cards.usable"] == "provisional":
                evidence["cards.usable"] = (
                    "derived from cooldown, sun balance, and active game state; the Endless price input remains provisional"
                )
        else:
            availability["cards"] = availability["cards.cooldown"] = "error"
            errors.append({"scope": "cards", "message": "Seed slot count does not match decoded slots."})
    game_raw = candidates.get("game_progress") if isinstance(candidates, Mapping) else None
    progress = game_raw.get("raw_candidate_fields", {}) if isinstance(game_raw, Mapping) else {}
    progress_errors = {
        str(error.get("field")): str(error.get("error", "read failed"))
        for error in (game_raw.get("read_errors", []) if isinstance(game_raw, Mapping) else [])
        if isinstance(error, Mapping)
    }

    # Accept old diagnostic snapshots that called the Root scene field "root".
    scene_field = progress.get("scene", progress.get("root"))
    raw_values = {
        "scene": _read_value(scene_field),
        "mode": _read_value(progress.get("mode")),
        "background": _read_value(progress.get("background")),
        "level": _read_value(progress.get("level")),
        "current_wave": _read_value(progress.get("current_wave")),
        "total_waves": _read_value(progress.get("total_waves")),
        "pause_flag": _read_value(progress.get("pause_flag")),
        "won_flag": _read_value(progress.get("won_flag")),
    }
    scene_code = raw_values["scene"] if _integer(raw_values["scene"]) else None
    mode_code = raw_values["mode"] if _integer(raw_values["mode"]) else None
    board_fields_irrelevant = scene_code in {0, 1, 6}

    def set_progress_status(key: str, field_name: str, valid: bool, *, board_field: bool = False) -> None:
        if board_field and board_fields_irrelevant:
            availability[key] = "unavailable"
            return
        if valid:
            availability[key] = "provisional"
            field_record = progress.get(field_name)
            evidence[key] = str(field_record.get("evidence_level", "observed_once")) if isinstance(field_record, Mapping) else "observed_once"
        elif field_name in progress_errors:
            availability[key] = "error"
            errors.append({"scope": key, "message": f"Progress field {field_name} could not be read: {progress_errors[field_name]}"})

    scene_name = _SCENE_NAMES.get(scene_code) if scene_code is not None else None
    mode_name = _MODE_NAMES.get(mode_code) if mode_code is not None else None
    background_code = raw_values["background"] if _integer(raw_values["background"]) else None
    background_name = _BACKGROUND_NAMES.get(background_code) if background_code is not None else None

    level_code = raw_values["level"] if _integer(raw_values["level"]) else None
    level_value: int | str | None = None
    if level_code is not None and not board_fields_irrelevant:
        if mode_code == 0 and 1 <= level_code <= 50:
            world_index, stage_index = divmod(level_code - 1, 10)
            level_value = f"{world_index + 1}-{stage_index + 1}"
        else:
            level_value = level_code
    spawned_code = raw_values["current_wave"] if _integer(raw_values["current_wave"]) else None
    total_waves_code = raw_values["total_waves"] if _integer(raw_values["total_waves"]) else None
    pause_raw = raw_values["pause_flag"]
    paused = bool(pause_raw) if _integer(pause_raw) and pause_raw in (0, 1) else None
    level_complete_raw = raw_values["won_flag"]
    level_complete = bool(level_complete_raw) if _integer(level_complete_raw) and level_complete_raw in (0, 1) else None

    set_progress_status("game.scene", "scene", scene_code is not None)
    availability["game.phase"] = availability["game.scene"]
    if "game.scene" in evidence:
        evidence["game.phase"] = evidence["game.scene"]
    set_progress_status("game.mode", "mode", mode_code is not None)
    set_progress_status("game.background", "background", background_code is not None, board_field=True)
    set_progress_status("game.level", "level", level_code is not None, board_field=True)
    set_progress_status("game.wave", "current_wave", spawned_code is not None and spawned_code >= 0, board_field=True)
    set_progress_status("game.total_waves", "total_waves", total_waves_code is not None and total_waves_code >= 0, board_field=True)
    set_progress_status("game.paused", "pause_flag", paused is not None, board_field=True)
    set_progress_status("game.level_complete", "won_flag", level_complete is not None, board_field=True)
    if (pause_raw is not None and paused is None and not board_fields_irrelevant):
        availability["game.paused"] = "error"
        errors.append({"scope": "game.paused", "message": "Pause flag must be a single byte with value 0 or 1."})
    if (level_complete_raw is not None and level_complete is None and not board_fields_irrelevant):
        availability["game.level_complete"] = "error"
        errors.append({"scope": "game.level_complete", "message": "Level-complete flag must be a single byte with value 0 or 1."})
    game = {
        "scene": scene_name,
        "scene_code": scene_code,
        "mode": mode_name,
        "mode_code": mode_code,
        "phase": scene_name,
        "background": background_name,
        "background_code": background_code,
        "paused": paused if not board_fields_irrelevant else None,
        "pause_raw_code": pause_raw if _integer(pause_raw) else None,
        "level": level_value,
        "level_number": level_code if not board_fields_irrelevant else None,
        "level_raw_code": level_code,
        "wave": spawned_code if not board_fields_irrelevant else None,
        "spawned_waves": spawned_code if not board_fields_irrelevant and spawned_code is not None and spawned_code >= 0 else None,
        "wave_raw_code": spawned_code,
        "total_waves": total_waves_code if not board_fields_irrelevant and total_waves_code is not None and total_waves_code >= 0 else None,
        "total_waves_raw_code": total_waves_code,
        "level_complete": level_complete if not board_fields_irrelevant else None,
        "level_complete_raw_code": level_complete_raw if _integer(level_complete_raw) else None,
        "progress_raw": progress,
    }

    terrain = candidates.get("terrain") if isinstance(candidates, Mapping) else None
    if isinstance(terrain, Mapping) and terrain.get("error"):
        availability["board.terrain"] = "error"
        errors.append({"scope": "board.terrain", "message": str(terrain["error"])})

    for name in _ARRAY_NAMES:
        domain = arrays.get(name) if isinstance(arrays, Mapping) else None
        if availability[name] == "error" and isinstance(domain, Mapping) and domain.get("error"):
            errors.append({"scope": name, "message": str(domain["error"])})

    missing_fields = sorted(key for key, value in availability.items() if value == "unavailable")
    valid = not critical_errors
    record = {
        "schema_version": 1,
        "observed_at_utc": observed,
        "sample_sequence": sequence,
        "retry_count": retry_count,
        "source": source_record,
        "status": "ok" if valid else "error",
        "valid": valid,
        "decision_ready": False,
        "availability": availability,
        "evidence": evidence,
        "errors": errors,
        "missing_fields": missing_fields,
        "game": game,
        "sun_balance": sun_balance,
        "board": {
            "rows": 5,
            "cols": 9,
            "terrain": None,
            "plantability": [["unknown" for _ in range(9)] for _ in range(5)],
            "cells": cells,
        },
        "plants": plants,
        "zombies": zombies,
        "lanes": lanes,
        "items": items,
        "collectible_suns": None,
        "cards": cards,
        "raw_snapshot": dict(raw_snapshot),
    }
    if availability["items.position"] == "unavailable" and items is not None:
        record["missing_fields"].append("items.position")
        record["missing_fields"] = sorted(set(record["missing_fields"]))
    return StateSnapshot(record)


def _capture_raw() -> tuple[dict[str, Any], dict[str, Any]]:
    process = locate_target_process(str(TARGET_IDENTITY["path"]))
    identity = verify_target_identity(process, TARGET_IDENTITY)
    module_base = main_module_base(process.pid, TARGET_IDENTITY["path"])
    with ReadOnlyMemory(process.pid) as memory:
        raw = read_raw_snapshot(memory, module_base)
    source = identity.as_dict()
    source.update({"profile": "pvz-1.0.0.1051", "exe_sha256": identity.sha256})
    return raw, source


def capture_state(raw_reader: Callable[[], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Capture one sample, retrying once when required data is inconsistent."""
    sequence = next(_SEQUENCES)
    reader = raw_reader or _capture_raw
    try:
        raw, source = reader()
        first = build_state(raw, source=source, sequence=sequence)
        if first.record["valid"]:
            return first.to_json_record()
        raw_retry, source_retry = reader()
        second = build_state(raw_retry, source=source_retry, sequence=sequence, retry_count=1)
        return second.to_json_record()
    except (ProcessDiscoveryError, OSError, RuntimeError, ValueError, KeyError) as exc:
        message = str(exc)
        status = "disconnected" if isinstance(exc, TargetNotRunningError) else "error"
        return _unavailable_record(message, sequence=sequence, status=status)
