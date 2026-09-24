"""Raw, evidence-graded PvZ 1.0.0.1051 memory reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from configs.pvz_1051 import (
    ARRAY_HEADER_OFFSETS,
    BOARD_POINTER_OFFSETS,
    BOARD_ROOT_RVA,
    CANDIDATE_OFFSETS,
    FIELD_OFFSETS,
)
from game.arrays import ArrayFormatError, ArrayHeader, inspect_array_header, iter_live_slots
from runtime.memory import MemoryReader, NullPointerError, follow_ptr32, read_f32, read_i32


def _hex(value: int) -> str:
    return f"0x{value:08X}"


def _observed_field(value: Any, *, meaning_status: str = "candidate") -> dict[str, Any]:
    return {
        "value": value,
        "evidence_level": "observed_once",
        "meaning_status": meaning_status,
    }


def resolve_board(memory: MemoryReader, module_base: int) -> tuple[int, int]:
    """Return (root, board) by following the versioned module-relative chain."""
    root_pointer_address = module_base + BOARD_ROOT_RVA
    root = memory.read_ptr32(root_pointer_address)
    if root == 0:
        raise NullPointerError(root_pointer_address)
    board = follow_ptr32(memory, root + BOARD_POINTER_OFFSETS[0])
    return root, board


def _resolve_root_and_optional_board(memory: MemoryReader, module_base: int) -> tuple[int, int]:
    """Resolve Root even when a menu scene has not created a Board yet."""
    root_pointer_address = module_base + BOARD_ROOT_RVA
    root = memory.read_u32(root_pointer_address)
    if root == 0:
        raise NullPointerError(root_pointer_address)
    board_pointer_address = root + BOARD_POINTER_OFFSETS[0]
    try:
        board = memory.read_u32(board_pointer_address)
    except Exception:
        raise
    return root, board


def read_sun_balance(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    return _observed_field(memory.read_u32(board_address + FIELD_OFFSETS["sun"]))


def _array_domain(
    memory: MemoryReader,
    board_address: int,
    domain_name: str,
    field_names: Mapping[str, int],
) -> dict[str, Any]:
    layout = FIELD_OFFSETS[domain_name]
    header = inspect_array_header(memory, board_address, layout, ARRAY_HEADER_OFFSETS)
    live_slots = iter_live_slots(
        memory,
        header,
        stride=int(layout["stride"]),
        object_id_offset=int(layout["object_id"]),
    )
    entities: list[dict[str, Any]] = []
    for slot in live_slots:
        entity: dict[str, Any] = {
            "slot": slot.index,
            "address": _hex(slot.address),
            "object_id": slot.object_id,
            "object_id_hex": f"0x{slot.object_id:08X}",
            "evidence_level": "observed_once",
            "active_rule": "object_id_high_16_bits_nonzero_candidate",
        }
        for field_name, offset in field_names.items():
            address = slot.address + int(offset)
            if field_name in ("x", "y"):
                integer_value = read_i32(memory, address)
                float_value = read_f32(memory, address)
                entity[field_name] = integer_value
                entity[f"{field_name}_f32_candidate"] = float_value
                entity[f"{field_name}_i32_candidate"] = integer_value
            elif field_name in ("hp", "helmet_hp", "shield_hp", "balloon_hp"):
                entity[field_name] = read_i32(memory, address)
            else:
                entity[field_name] = memory.read_u32(address)
        if domain_name == "items":
            integer_pair = (entity["x_i32_candidate"], entity["y_i32_candidate"])
            float_pair = (entity["x_f32_candidate"], entity["y_f32_candidate"])
            integer_plausible = (
                -100 <= integer_pair[0] <= 1200 and -100 <= integer_pair[1] <= 900
            )
            float_plausible = (
                -100 <= float_pair[0] <= 1200 and -100 <= float_pair[1] <= 900
            )
            if float_plausible and not integer_plausible:
                entity["x"], entity["y"] = float_pair
                interpretation = "f32_pixel_candidate"
            elif integer_plausible and not float_plausible:
                entity["x"], entity["y"] = integer_pair
                interpretation = "i32_pixel_candidate"
            else:
                entity["x"] = None
                entity["y"] = None
                interpretation = "unresolved"
            entity["coordinate_interpretation"] = interpretation
            entity["coordinate_meaning_status"] = "candidate"
            entity["type_meaning"] = "unknown"
            entity["type_4_sun_candidate"] = entity.get("type") == 4
            entity["collecting_flag_meaning"] = "candidate"
        elif domain_name == "zombies":
            entity["x"] = entity["x_f32_candidate"]
            entity["y"] = entity["y_f32_candidate"]
            entity["coordinate_interpretation"] = "f32_user_offset_candidate"
            entity["coordinate_meaning_status"] = "provisional"
        entities.append(entity)

    matches_count = len(entities) == header.live_count
    return {
        "status": "provisional" if matches_count else "candidate",
        "evidence_level": "observed_once",
        "live_rule_status": "provisional" if matches_count else "candidate",
        "live_rule": "scan max_used; object ID high 16 bits nonzero",
        "header": header.as_dict(),
        "reported_live_count": header.live_count,
        "scanned_live_count": len(entities),
        "counts_match": matches_count,
        "entities": entities,
        "dynamic_semantics": "not_verified_with_gameplay",
    }


def read_plants(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    layout = FIELD_OFFSETS["plants"]
    return _array_domain(
        memory,
        board_address,
        "plants",
        {"row": layout["row"], "type": layout["type"], "column": layout["column"]},
    )


def read_zombies(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    layout = FIELD_OFFSETS["zombies"]
    result = _array_domain(
        memory,
        board_address,
        "zombies",
        {
            "row": layout["row"],
            "type": layout["type"],
            "x": layout["x"],
            "y": layout["y"],
            "hp": layout["hp"],
            "helmet_hp": layout["helmet_hp"],
            "shield_hp": layout["shield_hp"],
            "balloon_hp": layout["balloon_hp"],
        },
    )
    for entity in result["entities"]:
        entity["row_in_bounds"] = 0 <= entity["row"] < 5
        entity["type_name"] = "unknown"
        entity["hp_semantics"] = "body, helmet, shield, and balloon HP are separate memory fields"
    return result


def read_items(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    layout = FIELD_OFFSETS["items"]
    return _array_domain(
        memory,
        board_address,
        "items",
        {
            "x": layout["x"],
            "y": layout["y"],
            "type": layout["type"],
            "collecting_flag": layout["collecting_candidate"],
        },
    )


def _candidate_u32_fields(
    memory: MemoryReader,
    base_address: int,
    fields: Mapping[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    values: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for name, offset in fields.items():
        try:
            values[name] = _observed_field(memory.read_u32(base_address + int(offset)))
        except Exception as exc:
            errors.append({"field": name, "error": str(exc)})
    return values, errors


def _candidate_u8_fields(
    memory: MemoryReader,
    base_address: int,
    fields: Mapping[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    values: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for name, offset in fields.items():
        try:
            value = memory.read_bytes(base_address + int(offset), 1)[0]
            values[name] = _observed_field(value)
        except Exception as exc:
            errors.append({"field": name, "error": str(exc)})
    return values, errors


def read_seed_bank(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    layout = CANDIDATE_OFFSETS["seed_bank"]
    pointer_address = board_address + int(layout["pointer"])
    seed_bank = memory.read_ptr32(pointer_address)
    if seed_bank == 0:
        raise NullPointerError(pointer_address)
    slot_count = memory.read_u32(seed_bank + int(layout["slot_count"]))
    if slot_count > int(layout["max_slots"]):
        raise ArrayFormatError(
            f"Candidate SeedBank slot count {slot_count} exceeds configured bound "
            f"{layout['max_slots']}."
        )

    slots: list[dict[str, Any]] = []
    start = seed_bank + int(layout["slots_inline"])
    for index in range(slot_count):
        address = start + index * int(layout["slot_stride"])
        fields: dict[str, Any] = {}
        for name in (
            "slot_type",
            "imitator_type",
            "cooldown_progress",
            "cooldown_total",
            "usable_flag",
        ):
            offset = int(layout[name])
            value = memory.read_u32(address + offset)
            fields[name] = _observed_field(value)
        slots.append({"index": index, "address": _hex(address), "fields": fields})

    return {
        "status": "provisional",
        "evidence_level": "observed_once",
        "meaning_status": "candidate; gameplay events not observed",
        "source_candidate": "PvZLib 1.0.0.1051 SeedPacket layout",
        "seed_bank_address": _hex(seed_bank),
        "slot_count": _observed_field(slot_count, meaning_status="provisional"),
        "slots_inline": True,
        "slots": slots,
        "cooldown_unit": "unknown",
    }


def read_game_progress(
    memory: MemoryReader,
    root_address: int,
    board_address: int,
) -> dict[str, Any]:
    scene_values, scene_errors = _candidate_u32_fields(
        memory, root_address, CANDIDATE_OFFSETS["scene"]
    )
    progress_offsets = CANDIDATE_OFFSETS["progress"]
    bool_fields = {name: progress_offsets[name] for name in ("pause_flag", "won_flag")}
    integer_fields = {
        name: offset for name, offset in progress_offsets.items()
        if name not in bool_fields
    }
    progress_values, progress_errors = _candidate_u32_fields(
        memory, board_address, integer_fields
    )
    bool_values, bool_errors = _candidate_u8_fields(
        memory, board_address, bool_fields
    )
    scene_values.update(progress_values)
    scene_values.update(bool_values)
    errors = scene_errors + progress_errors + bool_errors
    return {
        "status": "candidate" if scene_values else "unavailable",
        "evidence_level": "observed_once" if scene_values else "unavailable",
        "meaning_status": "candidate; no cross-scene or gameplay transitions observed",
        "raw_candidate_fields": scene_values,
        "read_errors": errors,
        "level_label": "unavailable",
        "current_wave_label": "unavailable",
    }


def read_terrain(memory: MemoryReader, board_address: int) -> dict[str, Any]:
    layout = CANDIDATE_OFFSETS["terrain"]
    address = board_address + int(layout["offset"])
    try:
        raw = memory.read_bytes(address, int(layout["candidate_size"]))
    except Exception as exc:
        return {
            "status": "unavailable",
            "evidence_level": "unavailable",
            "error": str(exc),
        }
    return {
        "status": "candidate",
        "evidence_level": "observed_once",
        "meaning_status": "candidate; element type and row/column indexing unverified",
        "address": _hex(address),
        "candidate_shape": {
            "rows": int(layout["candidate_rows"]),
            "columns": int(layout["candidate_columns"]),
        },
        "raw_hex": raw.hex(),
        "raw_byte_count": len(raw),
        "decoded_cells": "unavailable",
    }


def _safe_domain(name: str, reader: Any, *args: Any) -> dict[str, Any]:
    try:
        return reader(*args)
    except Exception as exc:
        return {
            "status": "unavailable",
            "evidence_level": "unavailable",
            "error": f"{name}: {exc}",
        }


def read_raw_snapshot(memory: MemoryReader, module_base: int) -> dict[str, Any]:
    """Collect known fields and preserve candidate evidence without overclaiming."""
    captured_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    root, board = _resolve_root_and_optional_board(memory, module_base)
    sun = _safe_domain("sun_balance", read_sun_balance, memory, board)
    arrays = {
        "plants": _safe_domain("plants", read_plants, memory, board),
        "zombies": _safe_domain("zombies", read_zombies, memory, board),
        "items": _safe_domain("items", read_items, memory, board),
    }
    candidates = {
        "seed_bank": _safe_domain("seed_bank", read_seed_bank, memory, board),
        "game_progress": _safe_domain("game_progress", read_game_progress, memory, root, board),
        "terrain": read_terrain(memory, board),
    }
    return {
        "captured_at_utc": captured_at,
        "evidence_policy": {
            "observed_once": "Single paused-frame evidence; not a dynamic gameplay verification.",
            "dynamic_semantics": "not_verified_with_gameplay",
        },
        "module_base": _hex(module_base),
        "root_address": _hex(root),
        "board_address": _hex(board),
        "sun": sun,
        "arrays": arrays,
        "candidates": candidates,
    }
