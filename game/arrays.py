"""Bounds-checked sparse DataArray inspection for the target game's objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from runtime.memory import MemoryReader, read_ptr32


class ArrayFormatError(ValueError):
    """Raised when a remote array header violates the expected DataArray bounds."""


@dataclass(frozen=True)
class ArrayHeader:
    address: int
    data_address: int
    max_used: int
    capacity: int
    free_list_head: int
    live_count: int

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        for key in ("address", "data_address"):
            result[f"{key}_hex"] = f"0x{result[key]:08X}"
        return result


@dataclass(frozen=True)
class LiveSlot:
    index: int
    address: int
    object_id: int

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["address_hex"] = f"0x{self.address:08X}"
        result["object_id_hex"] = f"0x{self.object_id:08X}"
        return result


def inspect_array_header(
    memory: MemoryReader,
    board_address: int,
    layout: Mapping[str, int],
    header_offsets: Mapping[str, int],
) -> ArrayHeader:
    """Read and validate a DataArray header embedded at a Board-relative offset."""
    address = board_address + int(layout["header"])
    data_address = read_ptr32(memory, address + int(header_offsets["data"]))
    max_used = memory.read_u32(address + int(header_offsets["max_used"]))
    capacity = memory.read_u32(address + int(header_offsets["capacity"]))
    free_list_head = memory.read_u32(address + int(header_offsets["free_list_head"]))
    live_count = memory.read_u32(address + int(header_offsets["live_count"]))

    if not (0 <= live_count <= max_used <= capacity):
        raise ArrayFormatError(
            f"Invalid DataArray bounds at 0x{address:08X}: "
            f"live={live_count}, max_used={max_used}, capacity={capacity}."
        )
    if max_used and not data_address:
        raise ArrayFormatError(
            f"DataArray at 0x{address:08X} has {max_used} used slot(s) but a null data pointer."
        )
    if capacity > 100000:
        raise ArrayFormatError(f"Unreasonable DataArray capacity {capacity} at 0x{address:08X}.")

    return ArrayHeader(
        address=address,
        data_address=data_address,
        max_used=max_used,
        capacity=capacity,
        free_list_head=free_list_head,
        live_count=live_count,
    )


def iter_live_slots(
    memory: MemoryReader,
    header: ArrayHeader,
    stride: int,
    object_id_offset: int,
) -> list[LiveSlot]:
    """Scan through max-used and treat a nonzero ID high word as a live candidate."""
    if stride <= 0 or object_id_offset < 0 or object_id_offset + 4 > stride:
        raise ValueError(f"Invalid slot layout: stride={stride}, ID offset={object_id_offset}.")
    slots: list[LiveSlot] = []
    for index in range(header.max_used):
        address = header.data_address + index * stride
        object_id = memory.read_u32(address + object_id_offset)
        if (object_id >> 16) != 0:
            slots.append(LiveSlot(index=index, address=address, object_id=object_id))
    return slots
