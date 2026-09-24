"""Build conservative, versioned State snapshots from P02 raw observations."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from itertools import count
from typing import Any, Callable, Mapping

from configs.pvz_1051 import TARGET_IDENTITY
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

_SCENE_NAMES = {
    0: "正在加载", 1: "主菜单", 2: "关卡介绍", 3: "正在游玩",
    4: "僵尸获胜", 5: "关卡奖励", 6: "制作人员名单", 7: "挑战场景",
}
_BACKGROUND_NAMES = {
    0: "白天", 1: "夜晚", 2: "泳池", 3: "浓雾", 4: "屋顶",
    5: "僵王战场", 6: "蘑菇花园", 7: "温室", 8: "僵尸水族馆", 9: "智慧树",
}
_MODE_NAMES = {
    0: "冒险模式",
    **{code: f"生存模式（普通，第 {code} 阶段）" for code in range(1, 6)},
    **{code: f"生存模式（困难，第 {code - 5} 阶段）" for code in range(6, 11)},
    **{code: f"生存模式（无尽，第 {code - 10} 阶段）" for code in range(11, 16)},
    16: "小游戏：战争与豌豆", 17: "小游戏：坚果保龄球", 18: "小游戏：老虎机",
    19: "小游戏：雨中播种", 20: "小游戏：宝石迷阵", 21: "小游戏：隐形僵尸",
    22: "小游戏：观星", 23: "小游戏：僵尸水族馆", 24: "小游戏：宝石迷阵转转乐",
    25: "小游戏：小鬼大麻烦", 26: "小游戏：传送门战斗", 27: "小游戏：列队",
    28: "小游戏：雪橇僵尸大作战", 29: "小游戏：极速", 30: "小游戏：打僵尸",
    31: "小游戏：最后一搏", 32: "小游戏：战争与豌豆（2）", 33: "小游戏：坚果保龄球（2）",
    34: "小游戏：跳跳舞会", 35: "小游戏：最终 Boss", 36: "小游戏：美术坚果",
    37: "小游戏：阳光日", 38: "小游戏：翻土", 39: "小游戏：大块头",
    40: "小游戏：美术向日葵", 41: "小游戏：空袭", 42: "小游戏：冰冻",
    43: "小游戏：禅境花园", 44: "小游戏：高重力", 45: "小游戏：墓地危机",
    46: "小游戏：铲子", 47: "小游戏：暴风雨夜", 48: "小游戏：蹦极闪电战",
    49: "小游戏：松鼠",
    50: "智慧树",
    **{code: f"砸罐子（第 {code - 50} 关）" for code in range(51, 61)},
    **{code: f"我是僵尸（第 {code - 60} 关）" for code in range(61, 71)},
    71: "促销模式", 72: "开场模式",
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
        "lanes": [{"row": row, "zombie_count": 0, "zombies": []} for row in range(5)],
        "items": None,
        "collectible_suns": None,
        "cards": None,
        "raw_snapshot": None,
    }


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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
    lanes: list[dict[str, Any]] = [{"row": row, "zombie_count": 0, "zombies": []} for row in range(5)]

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
        try:
            for zombie in raw_zombies:
                row, type_code, hp = zombie.get("row"), zombie.get("type"), zombie.get("hp")
                x, y = zombie.get("x"), zombie.get("y")
                if not (_integer(row) and 0 <= row < 5 and _integer(type_code) and _integer(hp) and hp >= 0 and _finite_number(x) and _finite_number(y)):
                    raise ValueError(f"Zombie has an invalid row, type, coordinates, or HP: {zombie!r}")
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
                }
                built_zombies.append(entry)
                lanes[row]["zombies"].append(entry.get("id") if entry.get("id") is not None else len(built_zombies) - 1)
            for lane in lanes:
                lane["zombie_count"] = len(lane["zombies"])
            zombies = built_zombies
        except (AttributeError, TypeError, ValueError) as exc:
            availability["zombies"] = availability["zombies.hp"] = "error"
            err = {"scope": "zombies", "message": str(exc)}
            errors.append(err)
            critical_errors.append(err)
            lanes = [{"row": row, "zombie_count": 0, "zombies": []} for row in range(5)]

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
        for slot in seed["slots"]:
            fields = slot.get("fields", {}) if isinstance(slot, Mapping) else {}
            type_code = _read_value(fields.get("slot_type"))
            imitator_type_code = _read_value(fields.get("imitator_type"))
            info = plant_info(imitator_type_code) if type_code == 48 else plant_info(type_code)
            type_info = plant_info(type_code)
            cards.append({
                "slot": slot.get("index"),
                "type_code": type_code,
                "type_name": type_info.name if type_info else "unknown",
                "imitator_type_code": imitator_type_code,
                "cooldown_progress_raw": _read_value(fields.get("cooldown_progress")),
                "cooldown_total_raw": _read_value(fields.get("cooldown_total")),
                "usable_flag_raw": _read_value(fields.get("usable_flag")),
                "cost": info.cost if info else None,
                "cost_source": "static_catalog" if info and info.cost is not None else None,
            })
        if slot_count == len(cards):
            availability["cards"] = availability["cards.cooldown"] = "provisional"
            evidence["cards"] = str(seed.get("evidence_level", "observed_once"))
            if all(card["cost"] is not None for card in cards):
                availability["cards.cost"] = "provisional"
                evidence["cards.cost"] = "static_catalog"
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
