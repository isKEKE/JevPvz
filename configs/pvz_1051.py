"""Static offsets and identity for the repository's Plants vs. Zombies 1.0.0.1051."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = PROJECT_ROOT / ".game" / "PlantsVsZombies.exe"

TARGET_IDENTITY = {
    "path": str(TARGET_PATH),
    "executable_name": "PlantsVsZombies.exe",
    "file_version": "1.0.0.1051",
    "pe_machine": 0x014C,
    "sha256": "F587903E9C3AD3890C1F4E2FBC1FE1EA88BD191E3D623D6F291283F6658C8DD4",
}

# The first pointer is stored at module_base + BOARD_ROOT_RVA; the next is at
# root + 0x768. Each remote pointer is four bytes because the game is x86.
BOARD_ROOT_RVA = 0x002A9EC0
BOARD_POINTER_OFFSETS = (0x768,)

# Board-relative, version-specific fields. The candidate table is deliberately
# kept separate from the verified user-provided fields below.
FIELD_OFFSETS = {
    "sun": 0x5560,
    "zombies": {
        "header": 0x90,
        "stride": 0x15C,
        "row": 0x1C,
        "type": 0x24,
        "x": 0x2C,
        "y": 0x30,
        "hp": 0xC8,
        "helmet_hp": 0xD0,
        "shield_hp": 0xDC,
        "balloon_hp": 0xE4,
        "object_id": 0x158,
    },
    "plants": {
        "header": 0xAC,
        "stride": 0x14C,
        "row": 0x1C,
        "type": 0x24,
        "column": 0x28,
        "object_id": 0x148,
    },
    "items": {
        "header": 0xE4,
        "stride": 0xD8,
        "x": 0x24,
        "y": 0x28,
        "collecting_candidate": 0x50,
        "type": 0x58,
        "object_id": 0xD0,
    },
}

ARRAY_HEADER_OFFSETS = {
    "data": 0x00,
    "max_used": 0x04,
    "capacity": 0x08,
    "free_list_head": 0x0C,
    "live_count": 0x10,
}

# Public 1.0.0.1051 reverse-engineering candidates. These are probe targets,
# not claims that the candidate meanings have passed gameplay verification.
CANDIDATE_OFFSETS = {
    "scene": {"scene": 0x7FC, "mode": 0x7F8},
    "progress": {
        "pause_flag": 0x164,
        "background": 0x554C,
        "level": 0x5550,
        "total_waves": 0x5564,
        "current_wave": 0x557C,
        "won_flag": 0x55FC,
    },
    "seed_bank": {
        "pointer": 0x144,
        "slot_count": 0x24,
        "slots_inline": 0x28,
        "slot_stride": 0x50,
        "slot_type": 0x34,
        "imitator_type": 0x38,
        "cooldown_progress": 0x24,
        "cooldown_total": 0x28,
        "usable_flag": 0x48,
        "max_slots": 10,
    },
    "terrain": {
        "offset": 0x168,
        "candidate_rows": 6,
        "candidate_columns": 9,
        "candidate_size": 54,
    },
    "item_semantics": {
        "coordinates_type_candidates": ("i32", "f32"),
        "ordinary_sun_type_candidate": 4,
        "small_sun_type_candidate": 5,
        "large_sun_type_candidate": 6,
    },
}
