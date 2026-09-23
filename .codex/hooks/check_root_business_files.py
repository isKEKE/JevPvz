#!/usr/bin/env python3
"""
Warn when new business-like files appear at repository root.

Initial mode: warning only.
Change exit code to 2 if you want this to block Codex later.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path.cwd()
ALLOWED_ROOT_NAMES = {
    "README.md", "AGENTS.md", "LICENSE", "CHANGELOG.md",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "requirements.txt", "uv.lock", "poetry.lock",
    "tsconfig.json", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    ".gitignore", ".env.example", ".prettierrc", ".eslintrc", ".eslintrc.json",
}
ALLOWED_ROOT_PREFIXES = (".",)
BUSINESS_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".sql"}


def new_files() -> list[str]:
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
        status = line[:2]
        file = line[3:].strip()
        if status.strip() in {"??", "A"}:
            files.append(file)
    return files


def suspicious_root_files(files: list[str]) -> list[str]:
    suspicious = []
    for file in files:
        path = Path(file)
        if len(path.parts) != 1:
            continue
        if path.name in ALLOWED_ROOT_NAMES:
            continue
        if path.name.startswith(ALLOWED_ROOT_PREFIXES):
            continue
        if path.suffix in BUSINESS_SUFFIXES:
            suspicious.append(file)
    return suspicious


def main() -> int:
    suspicious = suspicious_root_files(new_files())
    if suspicious:
        print("SDD warning: new root-level business-like files detected:")
        for file in suspicious:
            print(f"- {file}")
        print("Move them into the existing project structure or justify the root-level placement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
