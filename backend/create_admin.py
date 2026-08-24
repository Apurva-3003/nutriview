"""
Interactive helper: prompts for admin username and password, hashes the password with bcrypt,
and writes ADMIN_USERNAME and ADMIN_PASSWORD_HASH to backend/.env.

Optionally generates JWT_SECRET_KEY if it is not already set.

Run from the backend directory: python create_admin.py
"""

from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

import bcrypt

from credential_utils import (
    password_complexity_error,
    read_env_lines,
    strip_env_keys,
    write_env_lines,
)

_ADMIN_KEYS = frozenset({"ADMIN_USERNAME", "ADMIN_PASSWORD_HASH"})
_JWT_KEY = "JWT_SECRET_KEY"


def _jwt_already_set(env_path: Path) -> bool:
    for line in read_env_lines(env_path):
        stripped = line.strip()
        if stripped.startswith(f"{_JWT_KEY}="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return True
    return False


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

    complexity_error = password_complexity_error(password)
    if complexity_error:
        print(f"Error: {complexity_error}", file=sys.stderr)
        return 1

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )

    kept = strip_env_keys(read_env_lines(env_path), _ADMIN_KEYS)
    new_entries = [
        f'ADMIN_USERNAME="{username}"',
        f'ADMIN_PASSWORD_HASH="{password_hash}"',
    ]

    if not _jwt_already_set(env_path):
        jwt_secret = secrets.token_hex(32)
        new_entries.append(f'JWT_SECRET_KEY="{jwt_secret}"')
        print("Generated JWT_SECRET_KEY (add to production deployments).")

    write_env_lines(env_path, kept, new_entries)

    print(f"Wrote {env_path}")
    print("Run python create_guest.py to set guest credentials if needed.")
    print("Restart the Flask app if it is already running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
