"""Environment-backed authentication settings (JWT secret, production checks)."""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger(__name__)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip().strip('"').strip("'")


def resolve_jwt_secret_key() -> str:
    """
    JWT signing secret from JWT_SECRET_KEY.

    - PRODUCTION=True: required; startup fails if missing.
    - Otherwise: use env value if set, else ephemeral dev secret (tokens reset on restart).
    """
    secret = _env("JWT_SECRET_KEY")
    production = os.getenv("PRODUCTION") == "True"

    if production:
        if not secret:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. Set it in backend/.env or the environment "
                "when PRODUCTION=True."
            )
        return secret

    if secret:
        return secret

    ephemeral = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET_KEY is not set; using an ephemeral dev-only secret. "
        "Add JWT_SECRET_KEY to backend/.env for stable sessions."
    )
    return ephemeral
