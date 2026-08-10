"""Shared helpers for writing credential lines to backend/.env."""
from __future__ import annotations

import re
from pathlib import Path


def read_env_lines(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8").splitlines()


def strip_env_keys(lines: list[str], keys: frozenset[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if any(re.match(rf"^{re.escape(key)}\s*=", stripped) for key in keys):
            continue
        out.append(line.rstrip("\n"))
    return out


def write_env_lines(env_path: Path, lines: list[str], new_entries: list[str]) -> None:
    body = "\n".join(lines + new_entries) + "\n"
    env_path.write_text(body, encoding="utf-8")
