#!/usr/bin/env python3
"""Reject non-sequential or duplicate SDD Iteration directory identities."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path.cwd()
ITERATIONS = ROOT / ".sdd"
ITERATION_NAME = re.compile(r"^(?P<index>\d{3})-[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def iteration_name_errors() -> list[str]:
    if not ITERATIONS.exists():
        return []

    errors: list[str] = []
    names_by_index: defaultdict[str, list[str]] = defaultdict(list)
    for path in sorted(ITERATIONS.iterdir()):
        if not path.is_dir():
            continue
        match = ITERATION_NAME.fullmatch(path.name)
        if match is None:
            errors.append(
                f"invalid Iteration name {path.name!r}; expected NNN-short-title"
            )
            continue
        names_by_index[match.group("index")].append(path.name)

    for index, names in sorted(names_by_index.items()):
        if len(names) > 1:
            errors.append(f"duplicate Iteration index {index}: {', '.join(names)}")

    indexes = sorted(int(index) for index in names_by_index)
    if indexes:
        expected = list(range(1, indexes[-1] + 1))
        if indexes != expected:
            missing = sorted(set(expected) - set(indexes))
            details = (
                f"missing indexes: {', '.join(f'{index:03d}' for index in missing)}"
                if missing
                else f"found invalid starting index {indexes[0]:03d}"
            )
            errors.append(
                "Iteration indexes must start at 001 and remain contiguous; "
                + details
            )
    return errors


def main() -> int:
    errors = iteration_name_errors()
    if not errors:
        return 0

    print("SDD Iteration naming check failed:")
    for error in errors:
        print(f"- {error}")
    print("Allocate a new Iteration as max(existing NNN) + 1; do not use dates.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
