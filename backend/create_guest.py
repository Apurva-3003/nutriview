"""
Interactive helper: prompts for guest username and password, hashes the password with bcrypt,
and writes GUEST_USERNAME and GUEST_PASSWORD to backend/.env.

Run from the backend directory: python create_guest.py
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

import bcrypt

from credential_utils import read_env_lines, strip_env_keys, write_env_lines

_GUEST_KEYS = frozenset({"GUEST_USERNAME", "GUEST_PASSWORD"})


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    env_path = backend_dir / ".env"

    print("Nutri-View backend — create guest credentials (writes backend/.env)")
    username = input("Guest username: ").strip()
    if not username:
        print("Error: username cannot be empty.", file=sys.stderr)
        return 1

    password = getpass.getpass("Guest password: ")
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

    kept = strip_env_keys(read_env_lines(env_path), _GUEST_KEYS)
    write_env_lines(
        env_path,
        kept,
        [
            f'GUEST_USERNAME="{username}"',
            f'GUEST_PASSWORD="{password_hash}"',
        ],
    )

    print(f"Wrote {env_path}")
    print("Restart the Flask app if it is already running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
