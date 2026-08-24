"""Shared helpers for writing credential lines to backend/.env."""
from __future__ import annotations

import re
from pathlib import Path

_MIN_PASSWORD_LENGTH = 12
_PASSWORD_CLASS_PATTERNS = (
    re.compile(r"[a-z]"),
    re.compile(r"[A-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^A-Za-z0-9]"),
)


def password_complexity_error(password: str) -> str | None:
    """Return a human-readable error if `password` fails complexity rules, else None.

    Requires at least _MIN_PASSWORD_LENGTH characters and at least 3 of:
    lowercase letter, uppercase letter, digit, symbol. Does not check expiry/rotation.
    """
    if len(password) < _MIN_PASSWORD_LENGTH:
        return f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long."
    classes_met = sum(
        1 for pattern in _PASSWORD_CLASS_PATTERNS if pattern.search(password)
    )
    if classes_met < 3:
        return (
            "Password must include at least 3 of: lowercase letter, "
            "uppercase letter, digit, symbol."
        )
    return None


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
