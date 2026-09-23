#!/usr/bin/env python3
"""
Warn when code appears to have changed but no SDD iteration delivery report exists.

Initial mode: warning only.
Change exit code to 2 if you want this to block Codex later.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path.cwd()
ITERATIONS = ROOT / ".sdd"


def git_changed_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    files = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def looks_like_code_change(files: list[str]) -> bool:
    code_suffixes = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
        ".cs", ".cpp", ".c", ".h", ".hpp", ".sql", ".yaml", ".yml",
        ".toml", ".json",
    }
    ignored_prefixes = (".sdd/", ".codex/", ".github/", "docs/")
    for file in files:
        path = Path(file)
        if file.startswith(ignored_prefixes):
            continue
        if path.suffix in code_suffixes:
            return True
    return False


def has_delivery_report() -> bool:
    if not ITERATIONS.exists():
        return False
    for delivery in ITERATIONS.glob("*/delivery.md"):
        if delivery.read_text(encoding="utf-8", errors="ignore").strip():
            return True
    return False


def main() -> int:
    files = git_changed_files()
    if looks_like_code_change(files) and not has_delivery_report():
        print(
            "SDD warning: code/config files changed, but no "
            ".sdd/<NNN-short-title>/delivery.md was found. "
            "Create an iteration delivery report before finalizing."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
