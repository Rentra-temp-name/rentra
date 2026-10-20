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
