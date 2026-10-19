import os
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from starlette.testclient import TestClient

from rentra_api.config import Settings
from rentra_api.main import app


class TestSettings(unittest.TestCase):
    def test_settings_succeeds_with_valid_env(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
            "TEST_DATABASE_URL": "postgresql://test:test@localhost:5432/test_db",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
            self.assertEqual(s.DATABASE_URL, env["DATABASE_URL"])
            self.assertEqual(s.SUPABASE_URL, env["SUPABASE_URL"])
            self.assertEqual(s.SUPABASE_SERVICE_ROLE_KEY, env["SUPABASE_SERVICE_ROLE_KEY"])
            self.assertEqual(s.FRONTEND_ORIGIN, env["FRONTEND_ORIGIN"])
            self.assertEqual(s.TEST_DATABASE_URL, env["TEST_DATABASE_URL"])

    def test_settings_fails_when_database_url_missing(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_supabase_url_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_service_role_key_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_frontend_origin_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_value_is_empty_or_whitespace(self):
        env = {
            "DATABASE_URL": "   ",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_secrets_masked_in_repr(self):
        env = {
            "DATABASE_URL": "postgresql://secret_user:secret_pass@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "super_secret_service_key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
            repr_str = repr(s)
            self.assertNotIn("secret_pass", repr_str)
            self.assertNotIn("super_secret_service_key", repr_str)
            self.assertIn("***", repr_str)


class TestHealthEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_liveness(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_readiness(self):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
