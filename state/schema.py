"""Versioned JSON contract for normalized observations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


AVAILABILITY_VALUES = frozenset({"available", "provisional", "unavailable", "error"})


@dataclass(frozen=True)
class StateSnapshot:
    """A schema-v1 record kept as JSON-compatible values."""

    record: dict[str, Any]

    def to_json_record(self) -> dict[str, Any]:
        return deepcopy(self.record)


def to_json_record(snapshot: StateSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached JSON-ready record from a snapshot or mapping."""
    if isinstance(snapshot, StateSnapshot):
        record = snapshot.to_json_record()
    else:
        record = deepcopy(dict(snapshot))
    if record.get("schema_version") != 1:
        raise ValueError("Only State schema version 1 can be serialized.")
    availability = record.get("availability", {})
    invalid = {key: value for key, value in availability.items() if value not in AVAILABILITY_VALUES}
    if invalid:
        raise ValueError(f"Invalid availability value(s): {invalid}")
    return record
