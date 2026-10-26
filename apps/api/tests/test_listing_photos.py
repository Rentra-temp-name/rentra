from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import threading
import uuid

import httpx
from PIL import Image
import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api import main as rentra_main
from rentra_api.main import PHOTO_BUCKET, app


POINT_SQL = "extensions.st_setsrid(extensions.st_makepoint(85.3249, 27.7172), 4326)::extensions.geography"
PHONE = "+9779801234567"


def ensure_profile(user: dict) -> None:
    with TestClient(app) as client:
        response = client.get("/me", headers=user["headers"])
    assert response.status_code == 200


def ensure_photo_bucket() -> None:
    settings = get_settings()
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    with httpx.Client(base_url=settings.SUPABASE_URL.rstrip("/"), timeout=15) as storage:
        current = storage.get(f"/storage/v1/bucket/{PHOTO_BUCKET}", headers=headers)
        if current.status_code == 404 or (
            current.status_code == 400 and "not found" in current.text.lower()
        ):
            created = storage.post(
                "/storage/v1/bucket",
                headers=headers,
                json={
                    "id": PHOTO_BUCKET,
                    "name": PHOTO_BUCKET,
                    "public": True,
                    "file_size_limit": 10 * 1024 * 1024,
                    "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
                },
            )
            assert created.status_code in (200, 201), "Local Supabase Storage bucket setup failed"
        else:
            assert current.status_code == 200, "Local Supabase Storage is unavailable"
            updated = storage.put(
                f"/storage/v1/bucket/{PHOTO_BUCKET}",
                headers=headers,
                json={"public": True, "file_size_limit": 10 * 1024 * 1024},
            )
            assert updated.is_success, "Local photo bucket configuration failed"


def seed_listing(conn: psycopg.Connection, owner_id: str, status: str = "draft") -> str:
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (PHONE, owner_id))
    listing_id = conn.execute(
        f"""INSERT INTO app.listings (owner_id, title, rent_amount, point)
            VALUES (%s, 'Photo integration listing', 25000, {POINT_SQL}) RETURNING id""",
        (owner_id,),
    ).fetchone()[0]
    if status in {"active", "rented", "sold_out", "unavailable", "archived", "suspended"}:
        conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    if status in {"rented", "sold_out", "unavailable"}:
        conn.execute("UPDATE app.listings SET status = %s WHERE id = %s", (status, listing_id))
    elif status == "archived":
        conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    elif status == "suspended":
        conn.execute("SELECT set_config('app.actor', 'admin', true)")
        conn.execute(
            "UPDATE app.listings SET suspended_at = now(), suspended_by = %s, suspended_reason = 'test' WHERE id = %s",
            (owner_id, listing_id),
        )
    return str(listing_id)


def seed_photo_rows(conn: psycopg.Connection, listing_id: str, count: int) -> list[str]:
    ids = []
    for position in range(1, count + 1):
        photo_id = uuid.uuid4()
        conn.execute(
            """INSERT INTO app.listing_photos
                   (id, listing_id, storage_path, thumb_path, position, width, height)
               VALUES (%s, %s, %s, %s, %s, 32, 24)""",
            (photo_id, listing_id, str(uuid.uuid4()), str(uuid.uuid4()), position),
        )
        ids.append(str(photo_id))
    return ids


def image_bytes(size: tuple[int, int] = (80, 40), color: str = "red", fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def storage_delete(path: str | None) -> None:
    if not path:
        return
    settings = get_settings()
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    httpx.delete(
        f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{PHOTO_BUCKET}/{path}",
        headers=headers,
        timeout=15,
    )


@pytest.fixture
def photo_context(db_conn, signed_in_user):
    ensure_photo_bucket()
    ensure_profile(signed_in_user)
    listing_id = seed_listing(db_conn, signed_in_user["id"])
    db_conn.commit()
    yield db_conn, signed_in_user, listing_id
    rows = db_conn.execute(
        "SELECT storage_path, thumb_path FROM app.listing_photos WHERE listing_id = %s",
        (listing_id,),
    ).fetchall()
    db_conn.commit()
    for original_path, thumb_path in rows:
        storage_delete(original_path)
        storage_delete(thumb_path)


def upload(client: TestClient, listing_id: str, headers: dict, data: bytes, content_type: str = "image/png"):
    return client.post(
        f"/listings/{listing_id}/photos",
        headers=headers,
        files={"file": ("client-name-is-ignored.bin", data, content_type)},
    )


def public_object(url: str) -> bytes:
    response = httpx.get(url, timeout=15)
    assert response.status_code == 200
    return response.content


def storage_object_names() -> set[str]:
    settings = get_settings()
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    response = httpx.post(
        f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/list/{PHOTO_BUCKET}",
        headers=headers,
        json={"prefix": "", "limit": 1000, "offset": 0},
        timeout=15,
    )
    assert response.status_code == 200, "Local Storage list API is unavailable"
    return {item["name"] for item in response.json()}


def test_photo_upload_stores_row_and_both_objects(photo_context):
    conn, owner, listing_id = photo_context
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], image_bytes())
    assert response.status_code == 201, response.text
    photo = response.json()
    assert photo["position"] == 1 and photo["width"] == 80 and photo["height"] == 40
    row = conn.execute(
        "SELECT id, position, width, height, storage_path, thumb_path FROM app.listing_photos WHERE listing_id = %s",
        (listing_id,),
    ).fetchone()
    assert str(row[0]) == photo["id"] and row[1:4] == (1, 80, 40)
    assert row[4] in photo["original_url"] and row[5] in photo["thumb_url"]
    assert Image.open(BytesIO(public_object(photo["original_url"]))).size == (80, 40)
    assert Image.open(BytesIO(public_object(photo["thumb_url"]))).size == (400, 300)


def test_thumbnail_fit_and_pad(photo_context):
    _, owner, listing_id = photo_context
    landscape = image_bytes((80, 40), "red")
    portrait = image_bytes((40, 80), "blue")
    with TestClient(app) as client:
        landscape_response = upload(client, listing_id, owner["headers"], landscape)
        portrait_response = upload(client, listing_id, owner["headers"], portrait)
    assert landscape_response.status_code == portrait_response.status_code == 201
    for response, content_pixel, bar_pixel in (
        (landscape_response, ((200, 54), (200, 245)), (200, 10)),
        (portrait_response, ((129, 150), (270, 150)), (10, 150)),
    ):
        thumb = Image.open(BytesIO(public_object(response.json()["thumb_url"]))).convert("RGB")
        assert thumb.size == (400, 300)
        assert max(thumb.getpixel(bar_pixel)) <= 12
        for pixel in content_pixel:
            value = thumb.getpixel(pixel)
            if response is landscape_response:
                assert value[0] > value[1] + 50
            else:
                assert value[2] > value[0] + 50


def test_exif_stripped_and_orientation_applied(photo_context):
    _, owner, listing_id = photo_context
    buffer = BytesIO()
    source = Image.new("RGB", (40, 20), "green")
    exif = source.getexif()
    exif[274] = 6
    source.save(buffer, format="JPEG", exif=exif)
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], buffer.getvalue(), "application/octet-stream")
    assert response.status_code == 201, response.text
    assert (response.json()["width"], response.json()["height"]) == (20, 40)
    stored = Image.open(BytesIO(public_object(response.json()["original_url"])))
    assert stored.size == (20, 40)
    assert len(stored.getexif()) == 0


def test_magic_byte_mismatch_rejected(photo_context):
    conn, owner, listing_id = photo_context
    before = conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0]
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], b"not an image", "image/jpeg")
    assert response.status_code == 415 and response.json()["detail"]["code"] == "PHOTO_TYPE_INVALID"
    assert conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0] == before


def test_oversize_rejected_and_nothing_stored(photo_context):
    conn, owner, listing_id = photo_context
    before = conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0]
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], b"x" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413 and response.json()["detail"]["code"] == "PHOTO_TOO_LARGE"
    assert conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0] == before


def test_content_length_precheck(photo_context):
    conn, owner, listing_id = photo_context
    before_rows = conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0]
    before_objects = storage_object_names()
    with TestClient(app) as client:
        too_large = upload(client, listing_id, owner["headers"], b"x" * (6 * 1024 * 1024))
        missing_request = client.build_request(
            "POST", f"/listings/{listing_id}/photos", headers=owner["headers"],
            files={"file": ("photo.png", image_bytes(), "image/png")},
        )
        del missing_request.headers["content-length"]
        missing = client.send(missing_request)
    assert too_large.status_code == 413
    assert too_large.json()["code"] == "PHOTO_TOO_LARGE"
    assert missing.status_code == 411
    assert missing.json()["code"] == "PHOTO_LENGTH_REQUIRED"
    assert conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == before_rows
    assert storage_object_names() == before_objects


def test_pixel_cap_rejected(photo_context, monkeypatch):
    conn, owner, listing_id = photo_context
    before_objects = storage_object_names()
    monkeypatch.setattr(rentra_main, "PHOTO_MAX_PIXELS", 100)
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], image_bytes((11, 11)))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PHOTO_TOO_LARGE"
    assert conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 0
    assert storage_object_names() == before_objects


def test_mpo_jpeg_accepted(photo_context):
    _, owner, listing_id = photo_context
    buffer = BytesIO()
    Image.new("RGB", (30, 20), "red").save(
        buffer,
        format="MPO",
        save_all=True,
        append_images=[Image.new("RGB", (30, 20), "blue")],
    )
    mpo = buffer.getvalue()
    assert mpo.startswith(b"\xff\xd8\xff")
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], mpo, "image/jpeg")
    assert response.status_code == 201, response.text
    stored = Image.open(BytesIO(public_object(response.json()["original_url"]))).convert("RGB")
    red, green, blue = stored.getpixel((15, 10))
    assert red > blue + 50 and red > green + 50


def test_photo_cap_race_two_uploads(photo_context):
    conn, owner, listing_id = photo_context
    seed_photo_rows(conn, listing_id, 9)
    conn.commit()
    data = image_bytes((500, 500))

    def send_one():
        with TestClient(app) as client:
            return upload(client, listing_id, owner["headers"], data)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send_one(), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    rejected = next(response for response in responses if response.status_code == 409)
    assert rejected.json()["detail"]["code"] == "PHOTO_LIMIT"
    assert conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0] == 10


def test_photo_cap_race_below_cap_both_succeed(photo_context):
    conn, owner, listing_id = photo_context
    seed_photo_rows(conn, listing_id, 3)
    conn.commit()
    data = image_bytes((500, 500))
    barrier = threading.Barrier(2)

    def send_one():
        barrier.wait(timeout=10)
        with TestClient(app) as client:
            return upload(client, listing_id, owner["headers"], data)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send_one(), range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    positions = conn.execute(
        "SELECT position FROM app.listing_photos WHERE listing_id = %s ORDER BY position",
        (listing_id,),
    ).fetchall()
    assert [row[0] for row in positions] == [1, 2, 3, 4, 5]


def test_photo_cap_ten_enforced_by_db(photo_context):
    conn, _, listing_id = photo_context
    seed_photo_rows(conn, listing_id, 10)
    conn.commit()
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                """INSERT INTO app.listing_photos
                   (listing_id, storage_path, thumb_path, width, height, position)
                   VALUES (%s, 'overflow', 'overflow-thumb', 1, 1, 11)""",
                (listing_id,),
            )
    assert conn.execute("SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)).fetchone()[0] == 10


def test_failed_upload_leaves_no_storage_objects(photo_context):
    conn, owner, listing_id = photo_context
    seed_photo_rows(conn, listing_id, 10)
    conn.commit()
    before_objects = storage_object_names()
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], image_bytes())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PHOTO_LIMIT"
    assert storage_object_names() == before_objects
    assert conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE listing_id = %s", (listing_id,)
    ).fetchone()[0] == 10


def test_photo_write_bumps_listing_version(photo_context):
    conn, owner, listing_id = photo_context
    before = conn.execute("SELECT version FROM app.listings WHERE id = %s", (listing_id,)).fetchone()[0]
    with TestClient(app) as client:
        response = upload(client, listing_id, owner["headers"], image_bytes())
    assert response.status_code == 201, response.text
    after = conn.execute("SELECT version FROM app.listings WHERE id = %s", (listing_id,)).fetchone()[0]
    assert after == before + 1


def test_foreign_user_gets_404_on_photo_routes(db_conn, signed_in_pair):
    caller, owner = signed_in_pair
    ensure_photo_bucket()
    ensure_profile(caller)
    ensure_profile(owner)
    listing_id = seed_listing(db_conn, owner["id"])
    photo_ids = seed_photo_rows(db_conn, listing_id, 1)
    db_conn.commit()
    with TestClient(app) as client:
        created = upload(client, listing_id, caller["headers"], image_bytes())
        deleted = client.delete(
            f"/listings/{listing_id}/photos/{photo_ids[0]}", headers=caller["headers"]
        )
        reordered = client.post(
            f"/listings/{listing_id}/photos/reorder", headers=caller["headers"], json={"photo_ids": photo_ids}
        )
    assert [created.status_code, deleted.status_code, reordered.status_code] == [404, 404, 404]


def test_delete_photo_of_other_listing_404(photo_context):
    conn, owner, listing_a = photo_context
    listing_b = seed_listing(conn, owner["id"], "archived")
    photo_id = seed_photo_rows(conn, listing_b, 1)[0]
    conn.commit()
    try:
        with TestClient(app) as client:
            response = client.delete(
                f"/listings/{listing_a}/photos/{photo_id}", headers=owner["headers"]
            )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "PHOTO_NOT_FOUND"
        assert conn.execute(
            "SELECT count(*) FROM app.listing_photos WHERE id = %s", (photo_id,)
        ).fetchone()[0] == 1
    finally:
        conn.execute("DELETE FROM app.listing_photos WHERE listing_id = %s", (listing_b,))
        conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
        conn.execute("SELECT app.force_delete_listing(%s)", (listing_b,))
        conn.commit()


def test_suspended_listing_locks_photo_writes(photo_context):
    conn, owner, listing_id = photo_context
    conn.execute("SELECT set_config('app.actor', 'admin', true)")
    conn.execute(
        "UPDATE app.listings SET suspended_at = now(), suspended_by = %s, suspended_reason = 'test' WHERE id = %s",
        (owner["id"], listing_id),
    )
    photo_id = seed_photo_rows(conn, listing_id, 1)[0]
    conn.commit()
    with TestClient(app) as client:
        uploaded = upload(client, listing_id, owner["headers"], image_bytes())
        deleted = client.delete(f"/listings/{listing_id}/photos/{photo_id}", headers=owner["headers"])
        reordered = client.post(
            f"/listings/{listing_id}/photos/reorder", headers=owner["headers"], json={"photo_ids": [photo_id]}
        )
    assert all(response.status_code == 409 for response in (uploaded, deleted, reordered))
    assert all(
        response.json()["detail"]["code"] == "LISTING_SUSPENDED"
        for response in (uploaded, deleted, reordered)
    )


def test_archived_listing_rejects_photo_writes(photo_context):
    conn, owner, listing_id = photo_context
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    photo_id = seed_photo_rows(conn, listing_id, 1)[0]
    conn.execute("UPDATE app.listings SET status = 'archived' WHERE id = %s", (listing_id,))
    conn.commit()
    with TestClient(app) as client:
        uploaded = upload(client, listing_id, owner["headers"], image_bytes())
        deleted = client.delete(f"/listings/{listing_id}/photos/{photo_id}", headers=owner["headers"])
        reordered = client.post(
            f"/listings/{listing_id}/photos/reorder", headers=owner["headers"], json={"photo_ids": [photo_id]}
        )
    assert all(response.status_code == 409 for response in (uploaded, deleted, reordered))
    assert all(
        response.json()["detail"]["code"] == "LISTING_NOT_EDITABLE"
        for response in (uploaded, deleted, reordered)
    )


def test_reorder_changes_positions_in_db(photo_context):
    conn, owner, listing_id = photo_context
    photo_ids = seed_photo_rows(conn, listing_id, 3)
    conn.commit()
    with TestClient(app) as client:
        response = client.post(
            f"/listings/{listing_id}/photos/reorder",
            headers=owner["headers"],
            json={"photo_ids": list(reversed(photo_ids))},
        )
    assert response.status_code == 200, response.text
    positions = conn.execute(
        "SELECT id, position FROM app.listing_photos WHERE listing_id = %s ORDER BY position",
        (listing_id,),
    ).fetchall()
    assert [(str(row[0]), row[1]) for row in positions] == list(zip(reversed(photo_ids), (1, 2, 3)))


def test_delete_removes_row_and_objects(photo_context):
    conn, owner, listing_id = photo_context
    with TestClient(app) as client:
        uploaded = upload(client, listing_id, owner["headers"], image_bytes())
        photo = uploaded.json()
        deleted = client.delete(
            f"/listings/{listing_id}/photos/{photo['id']}", headers=owner["headers"]
        )
    assert uploaded.status_code == 201 and deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True, "storage_deleted": True}
    assert conn.execute("SELECT count(*) FROM app.listing_photos WHERE id = %s", (photo["id"],)).fetchone()[0] == 0
    assert httpx.get(photo["original_url"], timeout=15).status_code in (400, 404)
    assert httpx.get(photo["thumb_url"], timeout=15).status_code in (400, 404)


def test_storage_delete_failure_logged_without_path(photo_context, monkeypatch, caplog):
    conn, owner, listing_id = photo_context
    with TestClient(app) as client:
        uploaded = upload(client, listing_id, owner["headers"], image_bytes())
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()
    original_path = photo["original_url"].rsplit("/", 1)[-1]
    thumb_path = photo["thumb_url"].rsplit("/", 1)[-1]

    def fail_delete(*args, **kwargs):
        raise httpx.ConnectError("storage unavailable")

    monkeypatch.setattr(httpx, "delete", fail_delete)
    with TestClient(app) as client:
        deleted = client.delete(
            f"/listings/{listing_id}/photos/{photo['id']}", headers=owner["headers"]
        )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "storage_deleted": False}
    assert "photo_storage_delete_failed" in caplog.text
    assert original_path not in caplog.text and thumb_path not in caplog.text
    assert conn.execute(
        "SELECT count(*) FROM app.listing_photos WHERE id = %s", (photo["id"],)
    ).fetchone()[0] == 0


def test_photo_write_rate_limit_returns_429(photo_context):
    _, owner, listing_id = photo_context
    with TestClient(app) as client:
        responses = [
            client.post(
                f"/listings/{listing_id}/photos",
                headers={**owner["headers"], "Content-Length": "0"},
                content=b"",
            )
            for _ in range(21)
        ]
    assert all(response.status_code == 422 for response in responses[:20])
    assert responses[20].status_code == 429


def test_public_detail_shows_photos(photo_context):
    conn, owner, listing_id = photo_context
    conn.execute("SELECT set_config('app.user_id', %s, true)", (owner["id"],))
    conn.execute("SELECT set_config('app.actor', 'owner', true)")
    conn.execute("UPDATE app.listings SET status = 'active' WHERE id = %s", (listing_id,))
    conn.commit()
    with TestClient(app) as client:
        uploaded = upload(client, listing_id, owner["headers"], image_bytes())
        public = client.get(f"/listings/{listing_id}")
        private = client.get(f"/me/listings/{listing_id}", headers=owner["headers"])
    assert uploaded.status_code == 201, uploaded.text
    assert public.status_code == private.status_code == 200
    assert public.json()["photos"] == private.json()["photos"]
    assert public.json()["photos"][0]["id"] == uploaded.json()["id"]


def test_phone_never_in_logs_or_errors_for_photo_routes(photo_context, caplog):
    conn, owner, listing_id = photo_context
    conn.execute("UPDATE app.profiles SET whatsapp = %s WHERE id = %s", (PHONE, owner["id"]))
    conn.commit()
    with TestClient(app) as client:
        invalid = upload(client, listing_id, owner["headers"], PHONE.encode(), "image/jpeg")
        foreign = client.delete(
            f"/listings/{uuid.uuid4()}/photos/{uuid.uuid4()}", headers=owner["headers"]
        )
    assert invalid.status_code == 415 and PHONE not in invalid.text
    assert foreign.status_code == 404 and PHONE not in foreign.text
    assert PHONE not in caplog.text
