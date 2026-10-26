"""Tests for settings validation and health endpoints."""

import os
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from rentra_api.config import Settings, get_settings
from rentra_api.main import app, get_db_connection


class TestSettings:
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
            assert s.DATABASE_URL == env["DATABASE_URL"]
            assert s.SUPABASE_URL == env["SUPABASE_URL"]
            assert s.SUPABASE_SERVICE_ROLE_KEY == env["SUPABASE_SERVICE_ROLE_KEY"]
            assert s.FRONTEND_ORIGIN == env["FRONTEND_ORIGIN"]
            assert s.TEST_DATABASE_URL == env["TEST_DATABASE_URL"]

    def test_settings_fails_when_database_url_missing(self):
        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_supabase_url_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_service_role_key_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_frontend_origin_missing(self):
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/postgres",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_settings_fails_when_value_is_empty_or_whitespace(self):
        env = {
            "DATABASE_URL": "   ",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "FRONTEND_ORIGIN": "http://localhost:3000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
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
            assert "secret_pass" not in repr_str
            assert "super_secret_service_key" not in repr_str
            assert "***" in repr_str


class TestHealthEndpoints:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        self.client = TestClient(app)

    def test_health_liveness(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_readiness(self):
        response = self.client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user")
                assert cur.fetchone()[0] == "rentra_api"

    def test_ready_fails_when_db_down(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://rentra_api:pass@127.0.0.1:54399/postgres?connect_timeout=1"},
        ):
            get_settings.cache_clear()
            try:
                response = client.get("/health/ready")
                assert response.status_code != 200
            finally:
                get_settings.cache_clear()
