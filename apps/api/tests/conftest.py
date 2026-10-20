"""Pytest fixtures for rentra_api tests."""

import os
from collections.abc import Generator
import pytest
import psycopg

from rentra_api.config import get_settings


def get_test_database_url() -> str:
    """Read TEST_DATABASE_URL from environment or application settings."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        try:
            settings = get_settings()
            url = settings.TEST_DATABASE_URL
        except Exception:
            pass
    if not url:
        url = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Session fixture providing the configured TEST_DATABASE_URL."""
    return get_test_database_url()


@pytest.fixture(scope="function")
def db_connection(test_database_url: str) -> Generator[psycopg.Connection, None, None]:
    """Provide tests with a real Postgres connection. No mocks for DB tests."""
    conn = psycopg.connect(test_database_url)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="function")
def db_conn(db_connection: psycopg.Connection) -> psycopg.Connection:
    """Convenience alias for db_connection."""
    return db_connection


def get_rentra_api_password() -> str:
    """Read local password for rentra_api from environment or apps/api/.env."""
    pwd = os.environ.get("RENTRA_API_PASSWORD")
    if not pwd:
        from pathlib import Path
        from dotenv import dotenv_values

        for candidate in [
            Path(".env"),
            Path("apps/api/.env"),
            Path(__file__).resolve().parent.parent / ".env",
        ]:
            if candidate.is_file():
                vals = dotenv_values(candidate)
                if vals.get("RENTRA_API_PASSWORD"):
                    pwd = vals["RENTRA_API_PASSWORD"]
                    break
    if not pwd:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            from pathlib import Path
            from dotenv import dotenv_values

            for candidate in [
                Path(".env"),
                Path("apps/api/.env"),
                Path(__file__).resolve().parent.parent / ".env",
            ]:
                if candidate.is_file():
                    vals = dotenv_values(candidate)
                    if vals.get("DATABASE_URL"):
                        db_url = vals["DATABASE_URL"]
                        break
        if db_url and "rentra_api:" in db_url:
            from urllib.parse import urlparse

            parsed = urlparse(db_url)
            if parsed.password:
                pwd = parsed.password
    return pwd or ""


@pytest.fixture(scope="session", autouse=True)
def setup_rentra_api_role(test_database_url: str) -> None:
    """Session-scoped fixture to set the local password for rentra_api."""
    password = get_rentra_api_password()
    if not password:
        return
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("ALTER ROLE rentra_api WITH PASSWORD {}").format(
                    psycopg.sql.Literal(password)
                )
            )

