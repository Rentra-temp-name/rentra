"""Owner listing routes exercised through TestClient and local Postgres."""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.main import app


POINT = {"lat": 27.7172, "lng": 85.3249}
CORE_NUMERIC = (
    "bedrooms", "bathrooms_total", "western_commodes", "indian_squat_toilets",
    "kitchen_count", "balconies", "total_floors",
)


def seed_listing(conn, owner_id: str, status: str = "draft") -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    listing_id = conn.execute(
        """INSERT INTO app.listings (owner_id, title, rent_amount, point)
           VALUES (%s, 'Owner route fixture', 24000,
             extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)::extensions.geography)
           RETURNING id""", (owner_id,)
    ).fetchone()[0]
    if status in {"active", "rented", "sold_out", "unavailable"}:
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    if status in {"rented", "sold_out", "unavailable"}:
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    if status == "archived":
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
        conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    return str(listing_id)


def test_owner_full_listing_lifecycle_and_public_phone(db_conn, signed_in_user):
    with TestClient(app) as client:
        profile = client.get("/me", headers=signed_in_user["headers"])
        assert profile.status_code == 200
    db_conn.execute(
        "UPDATE app.profiles SET whatsapp = '+9779800001234' WHERE id = %s",
        (signed_in_user["id"],),
    )
    db_conn.commit()

    with TestClient(app) as client:
        created = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "API draft", "rent_amount": 24000, "point": POINT},
        )
        assert created.status_code == 201, created.text
        listing = created.json()
        assert listing["status"] == "draft" and listing["version"] >= 1

        with db_conn.cursor() as cur:
            attr_rows = cur.execute(
                """SELECT attribute.key, option.label FROM app.attributes AS attribute
                   JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
                   WHERE attribute.required_at_publish AND attribute.is_active AND option.is_active
                   AND option.sort_order = (SELECT min(other.sort_order) FROM app.attribute_options AS other
                                            WHERE other.attribute_id = attribute.id AND other.is_active)
                   ORDER BY attribute.key"""
            ).fetchall()
        answers = {key: [option] for key, option in attr_rows}
        numeric = {field: 1 for field in CORE_NUMERIC}
        patched = client.patch(
            f"/listings/{listing['id']}", headers=signed_in_user["headers"],
            json={"version": listing["version"], "answers": answers, "numeric": numeric},
        )
        assert patched.status_code == 200, patched.text
        listing = patched.json()
        assert listing["answers"] and listing["numeric"]

        published = client.post(
            f"/listings/{listing['id']}/publish", headers=signed_in_user["headers"]
        )
        assert published.status_code == 200, published.text
        public = client.get("/listings", headers=signed_in_user["headers"])
        item = next(row for row in public.json()["listings"] if row["id"] == listing["id"])
        assert item["whatsapp"] == "+9779800001234"

        assert client.post(
            f"/listings/{listing['id']}/status", headers=signed_in_user["headers"],
            json={"status": "rented"},
        ).json()["status"] == "rented"
        assert client.post(
            f"/listings/{listing['id']}/archive", headers=signed_in_user["headers"]
        ).json()["status"] == "archived"
        assert client.post(
            f"/listings/{listing['id']}/restore", headers=signed_in_user["headers"]
        ).json()["status"] == "rented"
        assert client.post(
            f"/listings/{listing['id']}/archive", headers=signed_in_user["headers"]
        ).json()["status"] == "archived"
        deleted = client.delete(
            f"/listings/{listing['id']}", headers=signed_in_user["headers"]
        )
        assert deleted.status_code == 200 and deleted.json()["deleted"] is True
        assert client.get(
            f"/me/listings/{listing['id']}", headers=signed_in_user["headers"]
        ).status_code == 404


def test_publish_error_names_missing_answers_numeric_and_whatsapp(db_conn, signed_in_user):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        db_conn.execute(
            "UPDATE app.profiles SET whatsapp = NULL WHERE id = %s", (signed_in_user["id"],)
        )
        db_conn.commit()
        draft = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "Incomplete", "rent_amount": 20000, "point": POINT},
        ).json()
        response = client.post(
            f"/listings/{draft['id']}/publish", headers=signed_in_user["headers"]
        )
    assert response.status_code == 422
    missing = response.json()["detail"]["missing"]
    assert "attribute:tenant_type" in missing
    assert "numeric:bedrooms" in missing
    assert "whatsapp" in missing
    assert "+977" not in response.text


def test_patch_stale_version_and_valid_patch_bump(signed_in_user):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        listing = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "Before", "rent_amount": 20000, "point": POINT},
        ).json()
        stale = client.patch(
            f"/listings/{listing['id']}", headers=signed_in_user["headers"],
            json={"version": listing["version"] + 1, "title": "Stale"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "VERSION_CONFLICT"
        unchanged = client.get(
            f"/me/listings/{listing['id']}", headers=signed_in_user["headers"]
        ).json()
        assert unchanged["version"] == listing["version"]
        changed = client.patch(
            f"/listings/{listing['id']}", headers=signed_in_user["headers"],
            json={"version": listing["version"], "title": "After"},
        )
    assert changed.status_code == 200
    assert changed.json()["title"] == "After"
    assert changed.json()["version"] > listing["version"]


@pytest.mark.parametrize(
    "field,value",
    [("owner_id", str(uuid.uuid4())), ("status", "active"), ("suspended_at", None),
     ("suspended_by", None), ("suspended_reason", "x"), ("created_at", "2020-01-01")],
)
def test_patch_rejects_protected_fields(field, value, signed_in_user):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        listing = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "Protected", "rent_amount": 20000, "point": POINT},
        ).json()
        response = client.patch(
            f"/listings/{listing['id']}", headers=signed_in_user["headers"],
            json={"version": listing["version"], "title": "Attempt", field: value},
        )
    assert response.status_code == 422


def test_patch_rejects_invalid_option_wrong_attribute_cardinality_and_rent_numeric(
    db_conn, signed_in_user
):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        listing = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "Registry validation", "rent_amount": 20000, "point": POINT},
        ).json()
        ids = db_conn.execute(
            """SELECT a.key, o.label FROM app.attributes a JOIN app.attribute_options o ON o.attribute_id=a.id
               WHERE a.key IN ('pets', 'dietary') ORDER BY a.key, o.sort_order"""
        ).fetchall()
        pets = [label for key, label in ids if key == "pets"]
        dietary = [label for key, label in ids if key == "dietary"]
        cases = [
            {"answers": {"pets": ["not_an_option"]}},
            {"answers": {"pets": [dietary[0]]}},
            {"answers": {"dietary": dietary[:2]}},
            {"numeric": {"rent_amount": 1000}},
        ]
        for invalid in cases:
            response = client.patch(
                f"/listings/{listing['id']}", headers=signed_in_user["headers"],
                json={"version": listing["version"], **invalid},
            )
            assert response.status_code == 422, response.text


def test_foreign_user_gets_not_found_on_all_owner_id_routes(db_conn, signed_in_pair):
    owner, other = signed_in_pair
    with TestClient(app) as client:
        client.get("/me", headers=owner["headers"])
        listing_id = seed_listing(db_conn, owner["id"])
        db_conn.commit()
        paths = [
            ("GET", f"/me/listings/{listing_id}", None),
            ("PATCH", f"/listings/{listing_id}", {"version": 1, "title": "x"}),
            ("POST", f"/listings/{listing_id}/publish", None),
            ("POST", f"/listings/{listing_id}/status", {"status": "active"}),
            ("POST", f"/listings/{listing_id}/archive", None),
            ("POST", f"/listings/{listing_id}/restore", None),
            ("DELETE", f"/listings/{listing_id}", None),
        ]
        for method, path, payload in paths:
            response = client.request(method, path, headers=other["headers"], json=payload)
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["detail"]["code"] == "LISTING_NOT_FOUND"
        own_list = client.get("/me/listings", headers=other["headers"])
        assert own_list.status_code == 200
        assert listing_id not in {item["id"] for item in own_list.json()["listings"]}


def test_suspended_listing_locked_for_owner_on_write_routes(db_conn, signed_in_user):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        draft = seed_listing(db_conn, signed_in_user["id"], "draft")
        archived = seed_listing(db_conn, signed_in_user["id"], "archived")
        active = seed_listing(db_conn, signed_in_user["id"], "active")
        db_conn.execute("SELECT set_config('app.actor', 'admin', true)")
        for listing_id in (draft, archived, active):
            db_conn.execute(
                "UPDATE app.listings SET suspended_at = now(), suspended_by = %s WHERE id = %s",
                (signed_in_user["id"], listing_id),
            )
        active_version = db_conn.execute(
            "SELECT version FROM app.listings WHERE id = %s AND owner_id = %s",
            (active, signed_in_user["id"]),
        ).fetchone()[0]
        db_conn.commit()
        responses = [
            client.patch(f"/listings/{active}", headers=signed_in_user["headers"], json={"version": active_version, "title": "x"}),
            client.post(f"/listings/{draft}/publish", headers=signed_in_user["headers"]),
            client.post(f"/listings/{active}/status", headers=signed_in_user["headers"], json={"status": "rented"}),
            client.post(f"/listings/{active}/archive", headers=signed_in_user["headers"]),
            client.post(f"/listings/{archived}/restore", headers=signed_in_user["headers"]),
            client.delete(f"/listings/{archived}", headers=signed_in_user["headers"]),
        ]
    assert all(response.status_code == 409 for response in responses)
    assert all(response.json()["detail"]["code"] == "LISTING_SUSPENDED" for response in responses)


def test_draft_cap_twenty(db_conn, signed_in_user):
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        for _ in range(20):
            seed_listing(db_conn, signed_in_user["id"])
        db_conn.commit()
        response = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "Twenty-first", "rent_amount": 20000, "point": POINT},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DRAFT_LIMIT"


def test_write_rate_limit_returns_429(monkeypatch, signed_in_user):
    settings = get_settings()
    monkeypatch.setattr(settings, "WRITE_RATE_LIMIT_USER", 1)
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        payload = {"title": "Limited", "rent_amount": 20000, "point": POINT}
        first = client.post("/listings", headers=signed_in_user["headers"], json=payload)
        second = client.post("/listings", headers=signed_in_user["headers"], json=payload)
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


def test_phone_never_appears_in_owner_route_error_or_logs(caplog, db_conn, signed_in_user):
    secret_phone = "+9779800012345"
    with TestClient(app) as client:
        client.get("/me", headers=signed_in_user["headers"])
        db_conn.execute(
            "UPDATE app.profiles SET whatsapp = %s WHERE id = %s",
            (secret_phone, signed_in_user["id"]),
        )
        db_conn.commit()
        response = client.post(
            "/listings", headers=signed_in_user["headers"],
            json={"title": "No phone in errors", "rent_amount": 20000, "point": POINT},
        ).json()
        failed = client.post(
            f"/listings/{response['id']}/status", headers=signed_in_user["headers"],
            json={"status": "invalid"},
        )
    assert failed.status_code == 422
    assert secret_phone not in failed.text
    assert secret_phone not in caplog.text
