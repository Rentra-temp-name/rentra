"""Tests for step 1 security foundation.

Covers schema isolation, role permissions, default privileges, RLS enforcement,
PostgREST exposure prevention, and /health/ready database connectivity.
"""

import httpx
import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app, get_db_connection


def test_schema_app_no_usage_for_anon_and_authenticated(db_conn: psycopg.Connection):
    """Verify anon and authenticated roles have no USAGE or CREATE privileges on schema app."""
    with db_conn.cursor() as cur:
        for role in ["anon", "authenticated"]:
            cur.execute("SELECT has_schema_privilege(%s, 'app', 'USAGE')", (role,))
            has_usage = cur.fetchone()[0]
            assert not has_usage, f"Role {role} should not have USAGE on schema app"

            cur.execute("SELECT has_schema_privilege(%s, 'app', 'CREATE')", (role,))
            has_create = cur.fetchone()[0]
            assert not has_create, f"Role {role} should not have CREATE on schema app"


def test_temp_table_in_app_has_no_privileges_for_anon_or_authenticated(db_conn: psycopg.Connection):
    """Verify tables created in schema app receive no default privileges for anon or authenticated."""
    table_name = "app.temp_security_test"
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table_name} (id serial primary key, val text);")
        db_conn.commit()
        try:
            privileges = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
            for role in ["anon", "authenticated"]:
                for priv in privileges:
                    cur.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, table_name, priv),
                    )
                    has_priv = cur.fetchone()[0]
                    assert not has_priv, f"Role {role} should not have {priv} on {table_name}"
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {table_name};")
            db_conn.commit()


def test_rentra_api_role_attributes_and_no_object_ownership(db_conn: psycopg.Connection):
    """Verify rentra_api is not superuser, not BYPASSRLS, and owns no objects in schema app."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolbypassrls, rolinherit, rolcreatedb, rolcreaterole, rolcanlogin "
            "FROM pg_roles WHERE rolname = 'rentra_api'"
        )
        row = cur.fetchone()
        assert row is not None, "rentra_api role must exist"
        rolsuper, rolbypassrls, rolinherit, rolcreatedb, rolcreaterole, rolcanlogin = row

        assert not rolsuper, "rentra_api must not be superuser"
        assert not rolbypassrls, "rentra_api must not have BYPASSRLS"
        assert not rolinherit, "rentra_api must have NOINHERIT"
        assert not rolcreatedb, "rentra_api must have NOCREATEDB"
        assert not rolcreaterole, "rentra_api must have NOCREATEROLE"
        assert rolcanlogin, "rentra_api must have LOGIN"

        cur.execute(
            "SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'app'"
        )
        owner_row = cur.fetchone()
        assert owner_row is not None
        assert owner_row[0] != "rentra_api", "rentra_api must not own schema app"

        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'app' AND r.rolname = 'rentra_api'
            """
        )
        owned_objects = cur.fetchall()
        assert len(owned_objects) == 0, f"rentra_api must own no objects in app, but owns: {owned_objects}"


def test_all_tables_in_app_have_rls_enabled(db_conn: psycopg.Connection):
    """Verify every table in schema app has RLS enabled (guards future tables; passes with 0 tables now)."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'app'
              AND c.relkind = 'r'
              AND c.relrowsecurity = false
            """
        )
        unprotected_tables = cur.fetchall()
        assert len(unprotected_tables) == 0, f"Found tables in schema app without RLS: {unprotected_tables}"


def test_supabase_rest_api_rejects_app_profile():
    """Verify PostgREST rejects requests targeting schema app via Accept-Profile."""
    settings = get_settings()
    rest_url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Accept-Profile": "app",
    }
    response = httpx.get(rest_url, headers=headers)
    assert response.status_code in (404, 406), (
        f"Expected REST API to reject Accept-Profile: app, got status {response.status_code}: {response.text}"
    )


def test_health_ready_connects_as_rentra_api_and_executes_select_1():
    """Verify /health/ready connects as rentra_api and executes SELECT 1 against the real DB."""
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user")
            assert cur.fetchone()[0] == "rentra_api"


