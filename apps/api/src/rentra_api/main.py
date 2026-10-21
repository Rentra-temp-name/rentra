from contextlib import asynccontextmanager
from collections import defaultdict, deque
from ipaddress import ip_address, ip_network
from base64 import urlsafe_b64decode, urlsafe_b64encode
import json
import math
import threading
import time
from typing import Annotated, Any, AsyncGenerator
from urllib.parse import urljoin
import re
from uuid import UUID

import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rentra_api.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate required settings on startup."""
    get_settings()
    yield


app = FastAPI(title="Rentra API", version="0.1.0", lifespan=lifespan)


class InProcessReadLimiter:
    """One-process sliding-window limiter for public read routes."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: tuple[str, str], limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - window
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False, max(1, math.ceil(window - (now - events[0])))
            events.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


read_limiter = InProcessReadLimiter()
READ_LIMITED_PATHS = {"/health/ready", "/listings", "/areas", "/registry", "/map"}


def _request_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ip_address(peer)
        trusted = [
            ip_network(value.strip(), strict=False)
            for value in get_settings().TRUSTED_PROXY_CIDRS.split(",")
            if value.strip()
        ]
    except ValueError:
        return peer
    if not any(peer_ip in network for network in trusted):
        return str(peer_ip)

    forwarded = request.headers.get("x-forwarded-for", "")
    try:
        chain = [ip_address(value.strip()) for value in forwarded.split(",") if value.strip()]
    except ValueError:
        return str(peer_ip)
    for candidate in reversed(chain):
        if not any(candidate in network for network in trusted):
            return str(candidate)
    return str(peer_ip)


@app.middleware("http")
async def limit_public_reads(request: Request, call_next):
    if request.method != "GET" or not (
        request.url.path in READ_LIMITED_PATHS
        or request.url.path.startswith("/listings/")
    ):
        return await call_next(request)

    settings = get_settings()
    user_id = None
    authorization = request.headers.get("authorization", "")
    if authorization:
        if not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Invalid or missing bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user_id = str(_verify_access_token(authorization[7:].strip())["sub"])
        except HTTPException:
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Invalid or missing bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

    key = ("user", user_id) if user_id else ("ip", _request_ip(request))
    limit = settings.READ_RATE_LIMIT_USER if user_id else settings.READ_RATE_LIMIT_ANONYMOUS
    allowed, retry_after = read_limiter.allow(
        key, limit, settings.READ_RATE_WINDOW_SECONDS
    )
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"code": "rate_limited", "message": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)


class AccountDeletionRequested(Exception):
    pass


@app.exception_handler(AccountDeletionRequested)
async def account_deletion_requested_handler(
    request: Request, exc: AccountDeletionRequested
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"code": "account_deletion_requested", "message": "This account is pending deletion"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors without echoing request values such as exact coordinates."""
    safe_errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})


def get_db_connection() -> psycopg.Connection:
    """Return a new database connection configured for rentra_api."""
    return psycopg.connect(get_settings().DATABASE_URL)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def health_ready() -> dict[str, str]:
    """Readiness probe for the application database role."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                if cur.fetchone() != (1,):
                    raise HTTPException(status_code=503, detail="Database query failed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connection failed") from exc
    return {"status": "ok"}


def _verify_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    jwks_url = urljoin(settings.SUPABASE_URL.rstrip("/") + "/", "auth/v1/.well-known/jwks.json")
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm in (None, "none"):
            raise jwt.InvalidTokenError("Disallowed JWT algorithm")

        if algorithm in ("RS256", "ES256"):
            if not header.get("kid"):
                raise jwt.InvalidTokenError("Missing JWT key id")
            signing_key = PyJWKClient(jwks_url, timeout=5).get_signing_key_from_jwt(token)
            if signing_key.algorithm_name != algorithm:
                raise jwt.InvalidTokenError("JWT algorithm does not match its signing key")
            key = signing_key.key
            algorithms = [algorithm]
        else:
            raise jwt.InvalidTokenError("Disallowed JWT algorithm")

        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
            issuer=settings.SUPABASE_URL.rstrip("/") + "/auth/v1",
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        return claims
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid or missing bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=120)
    whatsapp: str | None = Field(default=None, max_length=16)
    confirm: bool = False

    @field_validator("whatsapp")
    @classmethod
    def normalize_whatsapp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        compact = "".join(value.strip().split()).replace("-", "").replace("(", "").replace(")", "")
        if not compact:
            return None
        if compact.startswith("+977"):
            digits = compact[4:]
        elif compact.startswith("977"):
            digits = compact[3:]
        elif compact.startswith("0"):
            digits = compact[1:]
        else:
            digits = compact
        normalized = "+977" + digits
        if not re.fullmatch(r"\+977[1-9][0-9]{7,9}", normalized):
            raise ValueError("whatsapp must be a valid Nepal phone number")
        return normalized

    @model_validator(mode="after")
    def confirm_only_for_whatsapp_clear(self) -> "ProfileUpdate":
        if self.confirm and (
            "whatsapp" not in self.model_fields_set or self.whatsapp is not None
        ):
            raise ValueError("confirm is only valid when clearing whatsapp")
        return self


def get_current_profile(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify bearer auth and load the caller's row within an owner-scoped transaction."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Invalid or missing bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = _verify_access_token(authorization[7:].strip())
    uid = claims["sub"]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
                cur.execute(
                    "INSERT INTO app.profiles (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                    (uid,),
                )
                cur.execute(
                    """SELECT id, display_name, whatsapp, deletion_requested_at, created_at
                       FROM app.profiles WHERE id = %s""",
                    (uid,),
                )
                row = cur.fetchone()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Profile storage unavailable") from exc

    if row is None:
        raise HTTPException(status_code=401, detail="Profile unavailable")
    profile = dict(zip(("id", "display_name", "whatsapp", "deletion_requested_at", "created_at"), row))
    if profile["deletion_requested_at"] is not None:
        raise AccountDeletionRequested()
    return profile


def profile_json(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(profile["id"]),
        "display_name": profile["display_name"],
        "whatsapp": profile["whatsapp"],
        "created_at": profile["created_at"].isoformat(),
    }


@app.get("/me")
def read_me(profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    """Return the authenticated user's own profile, including their public contact number."""
    return profile_json(profile)


@app.put("/me")
def update_me(
    update: ProfileUpdate,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    """Update only explicitly supplied allowlisted profile fields."""
    fields = update.model_fields_set & {"display_name", "whatsapp"}
    uid = str(profile["id"])
    clearing_whatsapp = "whatsapp" in update.model_fields_set and update.whatsapp is None
    if fields:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
                    if clearing_whatsapp:
                        if "display_name" in fields:
                            cur.execute(
                                "UPDATE app.profiles SET display_name = %s WHERE id = %s",
                                (update.display_name, uid),
                            )
                        cur.execute("SELECT app.clear_my_whatsapp(%s)", (update.confirm,))
                        updated_profile = {**profile, "whatsapp": None}
                        if "display_name" in fields:
                            updated_profile["display_name"] = update.display_name
                        return profile_json(updated_profile)

                    assignments = ", ".join(f"{field} = %s" for field in sorted(fields))
                    values = [getattr(update, field) for field in sorted(fields)]
                    cur.execute(
                        f"UPDATE app.profiles SET {assignments} WHERE id = %s RETURNING id, display_name, whatsapp, deletion_requested_at, created_at",
                        (*values, uid),
                    )
                    row = cur.fetchone()
        except psycopg.Error as exc:
            code = getattr(exc.diag, "message_primary", None)
            if code in {
                "WHATSAPP_CLEAR_ARCHIVES_LISTINGS",
                "WHATSAPP_REQUIRED_FOR_ACTIVE_LISTING",
            }:
                detail: dict[str, Any] = {
                    "code": code,
                    "message": (
                        "Confirm to archive active listings before clearing WhatsApp"
                        if code == "WHATSAPP_CLEAR_ARCHIVES_LISTINGS"
                        else "WhatsApp is required while an active listing remains"
                    ),
                }
                if code == "WHATSAPP_CLEAR_ARCHIVES_LISTINGS":
                    try:
                        detail["active_listings"] = int(exc.diag.message_detail or "0")
                    except ValueError:
                        detail["active_listings"] = 0
                raise HTTPException(status_code=409, detail=detail) from None
            raise HTTPException(
                status_code=503,
                detail={"code": "profile_storage_unavailable", "message": "Profile storage unavailable"},
            ) from None

        if row is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile_json(dict(zip(("id", "display_name", "whatsapp", "deletion_requested_at", "created_at"), row)))
    return profile_json(profile)


@app.get("/profiles/{profile_id}")
def read_public_profile(profile_id: UUID) -> dict[str, Any]:
    """Expose the explicitly public contact fields for visitor profile/listing views."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT display_name, whatsapp FROM app.get_public_profile(%s)",
                (str(profile_id),),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"display_name": row[0], "whatsapp": row[1]}


@app.get("/registry")
def read_registry() -> dict[str, Any]:
    """Return the active, read-only attribute and numeric-field registries."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id, a.key, a.type, a.pick_rule, a.is_active,
                          a.required_at_publish, o.id, o.label, o.sort_order,
                          o.is_exclusive, o.is_active
                   FROM app.attributes AS a
                   LEFT JOIN app.attribute_options AS o
                     ON o.attribute_id = a.id AND o.is_active
                   WHERE a.is_active
                   ORDER BY a.key, o.sort_order"""
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT key, unit, is_active FROM app.numeric_fields WHERE is_active ORDER BY key"
            )
            numeric_rows = cur.fetchall()

    attributes: dict[str, dict[str, Any]] = {}
    for row in rows:
        attribute_id, key, kind, pick_rule, active, required, option_id, label, order, exclusive, option_active = row
        attribute = attributes.setdefault(
            key,
            {
                "id": str(attribute_id),
                "key": key,
                "type": kind,
                "pick_rule": pick_rule,
                "is_active": active,
                "required_at_publish": required,
                "options": [],
            },
        )
        if option_id is not None:
            attribute["options"].append(
                {
                    "id": str(option_id),
                    "label": label,
                    "sort_order": order,
                    "is_exclusive": exclusive,
                    "is_active": option_active,
                }
            )
    return {
        "attributes": list(attributes.values()),
        "numeric_fields": [
            {"key": key, "unit": unit, "is_active": active}
            for key, unit, active in numeric_rows
        ],
    }


class LocationPointInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    latitude: float
    longitude: float

    @field_validator("latitude", "longitude")
    @classmethod
    def round_to_grid(cls, value: float) -> float:
        return round(value, 2)

    @model_validator(mode="after")
    def validate_nepal_bounds(self) -> "LocationPointInput":
        if not (26.3 <= self.latitude <= 30.5 and 80.0 <= self.longitude <= 88.3):
            raise ValueError("point must be inside the supported Nepal bounding box")
        return self


class TenantLocationsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    current_point: LocationPointInput
    search_point: LocationPointInput
    search_radius_km: float = Field(default=5, ge=1, le=50)


def _location_response(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        return {"current_point": None, "search_point": None, "search_radius_km": 5.0}
    current_lat, current_lon, search_lat, search_lon, radius, created_at, updated_at = row
    return {
        "current_point": {"latitude": float(current_lat), "longitude": float(current_lon)},
        "search_point": {"latitude": float(search_lat), "longitude": float(search_lon)},
        "search_radius_km": float(radius),
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


@app.get("/me/locations")
def read_my_locations(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    uid = str(profile["id"])
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
            cur.execute(
                """SELECT extensions.st_y(current_point::extensions.geometry),
                          extensions.st_x(current_point::extensions.geometry),
                          extensions.st_y(search_point::extensions.geometry),
                          extensions.st_x(search_point::extensions.geometry),
                          search_radius_km, created_at, updated_at
                   FROM app.tenant_locations WHERE user_id = %s""",
                (uid,),
            )
            row = cur.fetchone()
    return _location_response(row)


@app.put("/me/locations")
def update_my_locations(
    update: TenantLocationsUpdate,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    uid = str(profile["id"])
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
                cur.execute(
                    """INSERT INTO app.tenant_locations AS locations
                           (user_id, current_point, search_point, search_radius_km)
                       VALUES (
                           %s,
                           extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
                           extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography,
                           %s
                       )
                       ON CONFLICT (user_id) DO UPDATE SET
                           current_point = EXCLUDED.current_point,
                           search_point = EXCLUDED.search_point,
                           search_radius_km = EXCLUDED.search_radius_km,
                           updated_at = now()
                       WHERE locations.user_id = %s
                       RETURNING
                           extensions.st_y(current_point::extensions.geometry),
                           extensions.st_x(current_point::extensions.geometry),
                           extensions.st_y(search_point::extensions.geometry),
                           extensions.st_x(search_point::extensions.geometry),
                           search_radius_km, created_at, updated_at""",
                    (
                        uid,
                        update.current_point.longitude,
                        update.current_point.latitude,
                        update.search_point.longitude,
                        update.search_point.latitude,
                        update.search_radius_km,
                        uid,
                    ),
                )
                row = cur.fetchone()
    except psycopg.errors.CheckViolation as exc:
        raise HTTPException(status_code=422, detail="Invalid location") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Location storage unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Locations not found")
    return _location_response(row)


def _listing_result(row: tuple[Any, ...]) -> dict[str, Any]:
    listing_id, title, rent_amount, latitude, longitude, whatsapp, created_at = row
    return {
        "id": str(listing_id),
        "title": title,
        "rent_amount": str(rent_amount),
        "point": {"latitude": float(latitude), "longitude": float(longitude)},
        "whatsapp": whatsapp,
        "created_at": created_at.isoformat(),
    }


def _encode_listing_cursor(rent_amount: str, listing_id: Any) -> str:
    raw = json.dumps([rent_amount, str(listing_id)], separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_listing_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        rent_amount, listing_id = json.loads(raw)
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?", rent_amount):
            raise ValueError
        return rent_amount, UUID(listing_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_cursor", "message": "Invalid cursor"})


PUBLIC_LISTING_SELECT = """SELECT listing.id, listing.title, listing.rent_amount,
       extensions.st_y(listing.point::extensions.geometry),
       extensions.st_x(listing.point::extensions.geometry),
       public_profile.whatsapp, listing.created_at
FROM app.listings AS listing
CROSS JOIN LATERAL app.get_public_profile(listing.owner_id) AS public_profile
WHERE listing.status = 'active' AND listing.suspended_at IS NULL"""


@app.get("/listings")
def read_public_listings(
    page_size: int = Query(default=20, ge=1),
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return public listings with stable keyset pagination by rent and id."""
    settings = get_settings()
    if page_size > settings.LISTINGS_PAGE_MAX:
        raise HTTPException(
            status_code=422,
            detail={"code": "page_size_too_large", "message": "Page size exceeds the maximum"},
        )
    sql = PUBLIC_LISTING_SELECT
    params: list[Any] = []
    if cursor:
        rent_amount, listing_id = _decode_listing_cursor(cursor)
        sql += " AND (listing.rent_amount, listing.id) > (%s::numeric, %s::uuid)"
        params.extend((rent_amount, str(listing_id)))
    sql += " ORDER BY listing.rent_amount, listing.id LIMIT %s"
    params.append(page_size + 1)
    try:
        with get_db_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail={"code": "listing_storage_unavailable", "message": "Listings unavailable"}) from exc

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    next_cursor = None
    if has_more and visible_rows:
        next_cursor = _encode_listing_cursor(str(visible_rows[-1][2]), visible_rows[-1][0])
    return {"listings": [_listing_result(row) for row in visible_rows], "next_cursor": next_cursor}


@app.get("/listings/{listing_ref}")
def read_public_listing(listing_ref: str) -> dict[str, Any]:
    """Resolve either an id or a frontend slug ending in the listing UUID."""
    trailing_id = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$", listing_ref)
    if not trailing_id:
        raise HTTPException(status_code=404, detail={"code": "listing_not_found", "message": "Listing not found"})
    listing_id = UUID(trailing_id.group(1))
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                PUBLIC_LISTING_SELECT + " AND listing.id = %s",
                (str(listing_id),),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail={"code": "listing_storage_unavailable", "message": "Listing unavailable"}) from exc
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "listing_not_found", "message": "Listing not found"})
    return _listing_result(row)


@app.get("/areas")
def read_areas() -> dict[str, list[Any]]:
    """No named areas are seeded yet; do not synthesize district or area records."""
    return {"areas": []}


@app.get("/map")
def read_map(bbox: str = Query(...), zoom: str = Query(...)) -> dict[str, Any]:
    """Return bounded public clusters at low zoom and phone-free points at high zoom."""
    try:
        west, south, east, north = (float(value) for value in bbox.split(","))
        zoom_value = float(zoom)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_map_bounds", "message": "Invalid map bounds"})
    if (
        not all(math.isfinite(value) for value in (west, south, east, north, zoom_value))
        or not (80.0 <= west < east <= 88.3)
        or not (26.3 <= south < north <= 30.5)
        or not (0 <= zoom_value <= 22)
    ):
        raise HTTPException(status_code=422, detail={"code": "invalid_map_bounds", "message": "Invalid map bounds"})

    settings = get_settings()
    cap = settings.MAP_RESPONSE_CAP
    try:
        with get_db_connection() as conn:
            if zoom_value < settings.MAP_CLUSTER_ZOOM:
                eps = min(0.5, 0.002 * (2 ** (settings.MAP_CLUSTER_ZOOM - zoom_value)))
                rows = conn.execute(
                    """WITH visible AS (
                           SELECT listing.id, listing.rent_amount,
                                  listing.point::extensions.geometry AS geom
                           FROM app.listings AS listing
                           WHERE listing.status = 'active'
                             AND listing.suspended_at IS NULL
                             AND extensions.st_intersects(
                                 listing.point,
                                 extensions.st_makeenvelope(%s, %s, %s, %s, 4326)::extensions.geography
                             )
                       ), clustered AS (
                           SELECT extensions.st_clusterdbscan(geom, %s, 1) OVER () AS cluster_id,
                                  geom
                           FROM visible
                       )
                       SELECT count(*)::integer,
                              extensions.st_y(extensions.st_centroid(extensions.st_collect(geom))),
                              extensions.st_x(extensions.st_centroid(extensions.st_collect(geom)))
                       FROM clustered GROUP BY cluster_id ORDER BY cluster_id LIMIT %s""",
                    (west, south, east, north, eps, cap + 1),
                ).fetchall()
                return {
                    "type": "clusters",
                    "clusters": [
                        {"count": row[0], "latitude": float(row[1]), "longitude": float(row[2])}
                        for row in rows[:cap]
                    ],
                    "capped": len(rows) > cap,
                }

            rows = conn.execute(
                """SELECT listing.id,
                          extensions.st_y(listing.point::extensions.geometry),
                          extensions.st_x(listing.point::extensions.geometry),
                          listing.rent_amount
                   FROM app.listings AS listing
                   WHERE listing.status = 'active'
                     AND listing.suspended_at IS NULL
                     AND extensions.st_intersects(
                         listing.point,
                         extensions.st_makeenvelope(%s, %s, %s, %s, 4326)::extensions.geography
                     )
                   ORDER BY listing.rent_amount, listing.id LIMIT %s""",
                (west, south, east, north, cap + 1),
            ).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail={"code": "map_storage_unavailable", "message": "Map unavailable"}) from exc
    return {
        "type": "points",
        "points": [
            {"id": str(row[0]), "lat": float(row[1]), "lng": float(row[2]), "rent": str(row[3])}
            for row in rows[:cap]
        ],
        "capped": len(rows) > cap,
    }
