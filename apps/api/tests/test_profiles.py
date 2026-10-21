"""Integration coverage for profiles using local Auth and PostgreSQL services."""

import json
import uuid
from datetime import datetime, timezone

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


def auth_headers(token: str) -> dict[str, str]:
    settings = get_settings()
    return {"Authorization": f"Bearer {token}", "apikey": settings.SUPABASE_SERVICE_ROLE_KEY}


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


def test_rejects_correct_claims_signed_with_different_key(signed_in_user):
    auth_token = signed_in_user["token"]
    auth_header = jwt.get_unverified_header(auth_token)
    claims = jwt.decode(auth_token, options={"verify_signature": False})
    other_private_key = ec.generate_private_key(ec.SECP256R1())
    wrong_signature_token = jwt.encode(
        claims,
        other_private_key,
        algorithm="ES256",
        headers={"kid": auth_header["kid"]},
    )

    assert jwt.get_unverified_header(wrong_signature_token)["kid"] == auth_header["kid"]
    assert jwt.decode(wrong_signature_token, options={"verify_signature": False}) == claims
    with TestClient(app) as client:
        response = client.get("/me", headers=auth_headers(wrong_signature_token))
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


def test_public_profile_only_shows_contact_fields_and_hides_deleted_or_unknown(signed_in_user, test_database_url):
    with TestClient(app) as client:
        changed = client.put("/me", headers=signed_in_user["headers"],
                             json={"display_name": "Public landlord", "whatsapp": "9812345678"})
    with psycopg.connect(test_database_url) as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (signed_in_user["id"],))
        conn.execute("SELECT set_config('app.actor', 'owner', true)")
        conn.execute(
            """INSERT INTO app.listings (owner_id, title, rent_amount, point)
               VALUES (
                   %s, 'Public profile test listing', 25000,
                   extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)::extensions.geography
               )""",
            (signed_in_user["id"],),
        )
        conn.execute(
            "UPDATE app.listings SET status = 'active' WHERE owner_id = %s",
            (signed_in_user["id"],),
        )
    with TestClient(app) as client:
        public = client.get(f"/profiles/{signed_in_user['id']}")
    assert changed.status_code == 200
    assert public.status_code == 200
    assert set(public.json()) == {"display_name", "whatsapp"}
    assert public.json()["display_name"] == "Public landlord"
    assert public.json()["whatsapp"] == "+9779812345678"

    with psycopg.connect(test_database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE app.profiles SET deletion_requested_at = now() WHERE id = %s",
            (signed_in_user["id"],),
        )
    with TestClient(app) as client:
        deleted = client.get(f"/profiles/{signed_in_user['id']}")
        unknown = client.get(f"/profiles/{uuid.uuid4()}")
    assert deleted.status_code == 404
    assert unknown.status_code == 404


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
        cur.execute(
            "SELECT has_function_privilege('rentra_api', 'app.get_public_profile(uuid)', 'EXECUTE')"
        )
        assert cur.fetchone()[0] is True
        for role in ("anon", "authenticated"):
            cur.execute(
                "SELECT has_function_privilege(%s, 'app.get_public_profile(uuid)', 'EXECUTE')",
                (role,),
            )
            assert cur.fetchone()[0] is False
