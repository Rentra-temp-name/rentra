"""Integration coverage for profiles using local Auth and PostgreSQL services."""

import uuid
import json
from datetime import datetime, timezone

import httpx
import jwt
import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


def auth_headers(token: str) -> dict[str, str]:
    settings = get_settings()
    return {"Authorization": f"Bearer {token}", "apikey": settings.SUPABASE_SERVICE_ROLE_KEY}


@pytest.fixture
def signed_in_user():
    settings = get_settings()
    email = f"rentra-{uuid.uuid4()}@example.test"
    password = f"T!{uuid.uuid4()}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        created = auth.post(
            "/auth/v1/admin/users",
            headers=headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        assert created.status_code in (200, 201), created.text
        user_id = created.json()["id"]
        signed_in = auth.post(
            "/auth/v1/token?grant_type=password",
            headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY},
            json={"email": email, "password": password},
        )
        assert signed_in.status_code == 200, signed_in.text
    token = signed_in.json()["access_token"]
    yield {"id": user_id, "token": token, "email": email, "headers": auth_headers(token)}
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        deleted = auth.delete(f"/auth/v1/admin/users/{user_id}", headers=headers)
        assert deleted.status_code in (200, 204), deleted.text


@pytest.fixture
def signed_in_pair(signed_in_user):
    # The second real Auth account is created through the same local Auth API.
    settings = get_settings()
    email = f"rentra-{uuid.uuid4()}@example.test"
    password = f"T!{uuid.uuid4()}"
    admin_headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        created = auth.post("/auth/v1/admin/users", headers=admin_headers,
                            json={"email": email, "password": password, "email_confirm": True})
        assert created.status_code in (200, 201), created.text
        user_id = created.json()["id"]
        signed_in = auth.post("/auth/v1/token?grant_type=password",
                              headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY},
                              json={"email": email, "password": password})
        assert signed_in.status_code == 200, signed_in.text
    user_b = {"id": user_id, "token": signed_in.json()["access_token"],
              "headers": auth_headers(signed_in.json()["access_token"])}
    yield signed_in_user, user_b
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as auth:
        deleted = auth.delete(f"/auth/v1/admin/users/{user_id}", headers=admin_headers)
        assert deleted.status_code in (200, 204), deleted.text


def test_local_auth_uses_real_supabase_signing_method(signed_in_user):
    header = jwt.get_unverified_header(signed_in_user["token"])
    assert header["alg"] == "ES256"


@pytest.mark.parametrize("tamper", ["expired", "issuer", "audience", "signature", "none", "wrong_algorithm"])
def test_rejects_invalid_real_token_variants(signed_in_user, tamper):
    token = signed_in_user["token"]
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})
    if tamper == "expired":
        claims["exp"] = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())
    elif tamper == "issuer":
        claims["iss"] = "https://wrong.example/auth/v1"
    elif tamper == "audience":
        claims["aud"] = "wrong"
    if tamper == "none":
        header["alg"] = "none"
    elif tamper == "wrong_algorithm":
        header["alg"] = "HS256"
    bad = jwt.api_jws.base64url_encode(json.dumps(header, separators=(",", ":")).encode()).decode()
    bad += "." + jwt.api_jws.base64url_encode(json.dumps(claims, separators=(",", ":")).encode()).decode()
    signature = token.split(".")[2]
    if tamper == "signature":
        signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    bad += "." + ("" if tamper == "none" else signature)
    with TestClient(app) as client:
        response = client.get("/me", headers=auth_headers(bad))
    assert response.status_code == 401


def test_missing_token_is_rejected():
    with TestClient(app) as client:
        response = client.get("/me")
    assert response.status_code == 401


def test_first_request_creates_profile_once(signed_in_user, test_database_url):
    with TestClient(app) as client:
        first = client.get("/me", headers=signed_in_user["headers"])
        second = client.get("/me", headers=signed_in_user["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == signed_in_user["id"]
    with psycopg.connect(test_database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM app.profiles WHERE id = %s", (signed_in_user["id"],))
        assert cur.fetchone()[0] == 1


def test_update_normalizes_phone_and_rejects_invalid_or_unknown_fields(signed_in_user):
    with TestClient(app) as client:
        updated = client.put("/me", headers=signed_in_user["headers"],
                             json={"display_name": "Landlord", "whatsapp": "09876543210"})
        invalid_phone = client.put("/me", headers=signed_in_user["headers"],
                                   json={"whatsapp": "+1 212 555 0100"})
        unknown = client.put("/me", headers=signed_in_user["headers"],
                             json={"role": "admin"})
    assert updated.status_code == 200
    assert updated.json()["whatsapp"] == "+9779876543210"
    assert invalid_phone.status_code == 422
    assert unknown.status_code == 422


def test_visitors_can_see_public_profile_contact_fields(signed_in_user):
    with TestClient(app) as client:
        changed = client.put("/me", headers=signed_in_user["headers"],
                             json={"display_name": "Public landlord", "whatsapp": "9812345678"})
        public = client.get(f"/profiles/{signed_in_user['id']}")
    assert changed.status_code == 200
    assert public.status_code == 200
    assert public.json()["display_name"] == "Public landlord"
    assert public.json()["whatsapp"] == "+9779812345678"


def test_rls_blocks_cross_user_select_and_update_and_unset_user(signed_in_pair, test_database_url):
    user_a, user_b = signed_in_pair
    with TestClient(app) as client:
        assert client.put("/me", headers=user_b["headers"],
                          json={"display_name": "B", "whatsapp": "9812345678"}).status_code == 200
        assert client.get("/me", headers=user_a["headers"]).status_code == 200
    with psycopg.connect(get_settings().DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE rentra_api")
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user_a["id"],))
            cur.execute("SELECT id FROM app.profiles WHERE id = %s", (user_b["id"],))
            assert cur.fetchall() == []
            cur.execute("UPDATE app.profiles SET display_name = 'stolen' WHERE id = %s RETURNING id",
                        (user_b["id"],))
            assert cur.fetchall() == []
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SET ROLE rentra_api")
            cur.execute("SELECT count(*) FROM app.profiles")
            assert cur.fetchone()[0] == 0


def test_database_rejects_other_users_insert_and_has_no_delete_grant(signed_in_pair, test_database_url):
    user_a, user_b = signed_in_pair
    with psycopg.connect(get_settings().DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE rentra_api")
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user_a["id"],))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO app.profiles (id) VALUES (%s)", (user_b["id"],))
            conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT has_table_privilege('rentra_api', 'app.profiles', 'DELETE')")
            assert cur.fetchone()[0] is False


def test_deletion_requested_account_is_rejected(signed_in_user, test_database_url):
    with TestClient(app) as client:
        assert client.get("/me", headers=signed_in_user["headers"]).status_code == 200
    with psycopg.connect(test_database_url) as conn, conn.cursor() as cur:
        cur.execute("UPDATE app.profiles SET deletion_requested_at = now() WHERE id = %s",
                    (signed_in_user["id"],))
    with TestClient(app) as client:
        response = client.get("/me", headers=signed_in_user["headers"])
    assert response.status_code == 403
    assert response.json() == {
        "code": "account_deletion_requested",
        "message": "This account is pending deletion",
    }


def test_profile_grants_and_rls(db_conn: psycopg.Connection):
    with db_conn.cursor() as cur:
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'app.profiles'::regclass")
        assert cur.fetchone()[0] is True
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cur.execute("SELECT has_table_privilege(%s, 'app.profiles', %s)", (role, privilege))
                assert cur.fetchone()[0] is False
