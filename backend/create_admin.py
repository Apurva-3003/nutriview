"""
Interactive helper: prompts for admin username and password, hashes the password with bcrypt,
and writes ADMIN_USERNAME and ADMIN_PASSWORD_HASH to backend/.env.

Run from the backend directory: python create_admin.py
"""

from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

import bcrypt


def _strip_existing_admin_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^ADMIN_USERNAME\s*=", stripped):
            continue
        if re.match(r"^ADMIN_PASSWORD_HASH\s*=", stripped):
            continue
        out.append(line.rstrip("\n"))
    return out


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    env_path = backend_dir / ".env"

    print("Nutri-View backend — create admin credentials (writes backend/.env)")
    username = input("Admin username: ").strip()
    if not username:
        print("Error: username cannot be empty.", file=sys.stderr)
        return 1

    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.", file=sys.stderr)
        return 1
    if not password:
        print("Error: password cannot be empty.", file=sys.stderr)
        return 1

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )

    raw_lines: list[str] = []
    if env_path.exists():
        raw_lines = env_path.read_text(encoding="utf-8").splitlines()

    kept = _strip_existing_admin_lines(raw_lines)
    # Quote hash so characters like $ are not misinterpreted by dotenv parsers
    new_block = [
        f'ADMIN_USERNAME="{username}"',
        f'ADMIN_PASSWORD_HASH="{password_hash}"',
    ]
    body = "\n".join(kept + new_block) + "\n"
    env_path.write_text(body, encoding="utf-8")

    print(f"Wrote {env_path}")
    print("Restart the Flask app if it is already running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
