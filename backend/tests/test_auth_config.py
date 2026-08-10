"""Tests for JWT secret resolution."""
import os
import unittest
from unittest import mock

from auth_config import resolve_jwt_secret_key


class TestResolveJwtSecretKey(unittest.TestCase):
    def tearDown(self):
        for key in ("JWT_SECRET_KEY", "PRODUCTION"):
            os.environ.pop(key, None)

    def test_production_requires_secret(self):
        os.environ["PRODUCTION"] = "True"
        os.environ.pop("JWT_SECRET_KEY", None)
        with self.assertRaises(RuntimeError):
            resolve_jwt_secret_key()

    def test_production_uses_env(self):
        os.environ["PRODUCTION"] = "True"
        os.environ["JWT_SECRET_KEY"] = "fixed-production-secret"
        self.assertEqual(resolve_jwt_secret_key(), "fixed-production-secret")

    def test_dev_uses_env_when_set(self):
        os.environ.pop("PRODUCTION", None)
        os.environ["JWT_SECRET_KEY"] = "dev-secret"
        self.assertEqual(resolve_jwt_secret_key(), "dev-secret")

    def test_dev_ephemeral_when_unset(self):
        os.environ.pop("PRODUCTION", None)
        os.environ.pop("JWT_SECRET_KEY", None)
        with mock.patch("auth_config.secrets.token_hex", return_value="abc"):
            self.assertEqual(resolve_jwt_secret_key(), "abc")


if __name__ == "__main__":
    unittest.main()
