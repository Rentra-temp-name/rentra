from contextlib import asynccontextmanager
from collections import defaultdict, deque
from ipaddress import ip_address, ip_network
from base64 import urlsafe_b64decode, urlsafe_b64encode
import json
import hmac
import logging
import math
import threading
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated, Any, AsyncGenerator, Literal
from urllib.parse import quote, urljoin
import re
import uuid
from decimal import Decimal
from uuid import UUID

import jwt
import httpx
import psycopg
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.routing import Match

from rentra_api.config import get_settings
from rentra_api.logging_setup import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate required settings on startup."""
    get_settings()
    yield


app = FastAPI(title="Rentra API", version="0.1.0", lifespan=lifespan)
setup_logging()
logger = logging.getLogger("rentra_api")
HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ("route", "method", "status"))
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ("route", "method"))
RATE_LIMITED = Counter("rate_limited_total", "Rate limited requests")
CONNECT_TOTAL = Counter("connect_total", "New listing connections")
JOB_LAST_SUCCESS = Gauge("job_last_success_timestamp", "Unix timestamp of last successful job", ("job",))
STORAGE_BACKLOG = Gauge("storage_deletions_backlog", "Pending storage deletion rows")
STORAGE_OLDEST = Gauge("storage_deletions_oldest_pending_seconds", "Age of oldest pending storage deletion")

MATCHES_SQL = """WITH loc AS (
      SELECT search_point, search_radius_km FROM app.tenant_locations WHERE user_id=%s
    ), checks AS (
      SELECT l.id,l.title,l.rent_amount,l.created_at,
        extensions.st_y(l.point::extensions.geometry) lat,extensions.st_x(l.point::extensions.geometry) lng,
        p.whatsapp,
        count(*) FILTER(WHERE r.importance='must' AND miss) must_miss,
        count(*) FILTER(WHERE r.importance='nice' AND miss) nice_miss,
        count(*) FILTER(WHERE r.importance='must') must_total,
        count(*) FILTER(WHERE r.importance='nice') nice_total,
        coalesce(jsonb_agg(jsonb_build_object('field',r.label,'value',r.expected,'importance',r.importance)) FILTER(WHERE miss), '[]'::jsonb) misses
      FROM app.listings l CROSS JOIN loc
      CROSS JOIN LATERAL app.get_public_profile(l.owner_id) p
      LEFT JOIN LATERAL (
        SELECT r.importance, coalesce(a.key,n.field) label, coalesce(o.label,n.field) expected,
          CASE WHEN n.field IS NOT NULL THEN
            CASE n.field WHEN 'rent_amount' THEN l.rent_amount > n.value
              ELSE coalesce(ln.value,0) < n.value END
          ELSE NOT EXISTS (SELECT 1 FROM app.listing_answers la WHERE la.listing_id=l.id AND la.attribute_id=r.attribute_id AND la.option_id=r.option_id)
            AND NOT EXISTS(SELECT 1 FROM app.listing_answers la JOIN app.attribute_options ao ON ao.id=la.option_id WHERE la.listing_id=l.id AND la.attribute_id=r.attribute_id AND ao.is_exclusive)
          END miss
        FROM (SELECT user_id,attribute_id,option_id,pick_rule,importance,NULL::text field FROM app.requirements WHERE user_id=%s
              UNION ALL SELECT user_id,NULL,NULL,NULL,importance,field FROM app.requirement_numeric WHERE user_id=%s) r
        LEFT JOIN app.attributes a ON a.id=r.attribute_id LEFT JOIN app.attribute_options o ON o.id=r.option_id
        LEFT JOIN app.requirement_numeric n ON n.user_id=r.user_id AND n.field=r.field
        LEFT JOIN app.listing_numeric ln ON ln.listing_id=l.id AND ln.field=r.field
      ) r ON true
      WHERE l.status='active' AND l.suspended_at IS NULL AND l.owner_id<>%s
        AND extensions.st_dwithin(l.point,loc.search_point,loc.search_radius_km*1000)
      GROUP BY l.id,p.whatsapp
    ), scored AS (
      SELECT checks.*, CASE WHEN must_total>0 THEN (must_total-must_miss)::numeric/must_total
        WHEN nice_total>0 THEN (nice_total-nice_miss)::numeric/nice_total ELSE 1::numeric END score,
        ((must_total>0 AND must_miss=0) OR (must_total=0 AND nice_total>0 AND nice_miss=0)) perfect_flag,
        (must_total=0 AND nice_total=0) explore_flag
      FROM checks
    ), ordered AS (
      SELECT *,
        row_number() OVER(PARTITION BY perfect_flag ORDER BY score DESC, CASE WHEN must_total>0 THEN nice_total-nice_miss ELSE 0 END DESC, rent_amount,created_at DESC,id) ranked_row,
        current_date::text shuffle_day, md5(id::text||current_date::text) shuffle_key
      FROM scored
    ), page AS (
      SELECT ordered.*, row_number() OVER(PARTITION BY explore_flag ORDER BY shuffle_key,id) explore_page_row
      FROM ordered
      WHERE (%s::date IS NULL OR (explore_flag AND shuffle_day=%s AND (shuffle_key,id)>(%s,%s::uuid)) OR NOT explore_flag)
    ) SELECT id,title,rent_amount,lat,lng,whatsapp,created_at,misses,perfect_flag,explore_flag,must_total,nice_total,
      (SELECT coalesce(jsonb_agg(jsonb_build_object('id',ph.id,'position',ph.position,'width',ph.width,'height',ph.height,'storage_path',ph.storage_path,'thumb_path',ph.thumb_path) ORDER BY ph.position),'[]'::jsonb) FROM app.listing_photos ph WHERE ph.listing_id=page.id),
      shuffle_day,shuffle_key
      FROM page
      WHERE (NOT explore_flag OR explore_page_row<=%s)
        AND (explore_flag OR perfect_flag OR ranked_row<=100)
      ORDER BY CASE WHEN explore_flag THEN 2 ELSE 1 END,
        CASE WHEN explore_flag THEN shuffle_key END, score DESC,
        CASE WHEN must_total>0 THEN nice_total-nice_miss ELSE 0 END DESC,
        rent_amount,created_at DESC,id"""


class InProcessReadLimiter:
    """One-process sliding-window limiter for public read routes."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def allow(self, key: tuple[str, str], limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            cutoff = now - window
            if now - self._last_sweep >= 60:
                for stored_key, stored_events in list(self._events.items()):
                    while stored_events and stored_events[0] <= cutoff:
                        stored_events.popleft()
                    if not stored_events:
                        del self._events[stored_key]
                self._last_sweep = now
            events = self._events.get(key)
            if events is None:
                events = self._events[key]
            else:
                while events and events[0] <= cutoff:
                    events.popleft()
                if not events:
                    del self._events[key]
                    events = self._events[key]
            if len(events) >= limit:
                return False, max(1, math.ceil(window - (now - events[0])))
            events.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


read_limiter = InProcessReadLimiter()
write_limiter = InProcessReadLimiter()
READ_LIMITED_PATHS = {"/listings", "/areas", "/registry", "/map"}


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
    path = request.url.path
    if path == "/metrics":
        return await call_next(request)
    if request.method == "POST" and re.fullmatch(r"/listings/[^/]+/photos", path):
        content_length = request.headers.get("content-length")
        if content_length is None:
            return JSONResponse(
                status_code=411,
                content={"code": "PHOTO_LENGTH_REQUIRED", "message": "Content-Length is required"},
            )
        try:
            declared_length = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=411,
                content={"code": "PHOTO_LENGTH_REQUIRED", "message": "Content-Length is required"},
            )
        if declared_length > PHOTO_MAX_BYTES + 64 * 1024:
            return JSONResponse(
                status_code=413,
                content={"code": "PHOTO_TOO_LARGE", "message": "Photo exceeds 5 MB"},
            )
    is_write = request.method in {"POST", "PATCH", "DELETE", "PUT"} and (
        path == "/me/requirements" or
        (path == "/me" and request.method == "DELETE") or
        path == "/listings" or (path.startswith("/listings/") and not path.endswith("/connect"))
    )
    is_read = request.method == "GET" and (
        path in READ_LIMITED_PATHS
        or path.startswith("/listings/")
        or path == "/me/connections"
        or path.startswith("/me/connections/profile/")
        or path == "/me/notifications"
        or path == "/me/saved"
        or path == "/admin/reports"
    )
    if not (is_write or is_read):
        return await call_next(request)

    settings = get_settings()
    user_id = None
    authorization = request.headers.get("authorization", "")
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = str(_verify_access_token(authorization[7:].strip())["sub"])
        except HTTPException:
            # These middleware-limited reads are public; invalid credentials use the IP bucket.
            user_id = None

    if is_write:
        # Authenticated dependencies return the usual 401 when no token is supplied.
        if user_id is None:
            return await call_next(request)
        allowed, retry_after = write_limiter.allow(
            ("user", user_id), settings.WRITE_RATE_LIMIT_USER,
            settings.READ_RATE_WINDOW_SECONDS,
        )
    else:
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


@app.middleware("http")
async def observe_request(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        matched_route = request.scope.get("route")
        if matched_route is None:
            for candidate in app.router.routes:
                match, _child_scope = candidate.matches(request.scope)
                if match == Match.FULL:
                    matched_route = candidate
                    break
        route = getattr(matched_route, "path", "unmatched")
        elapsed = time.perf_counter() - started
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        HTTP_REQUESTS.labels(route, request.method, str(status_code)).inc()
        if status_code == 429:
            RATE_LIMITED.inc()
        HTTP_DURATION.labels(route, request.method).observe(elapsed)
        logger.info(
            "http_request",
            extra={
                "event": "http_request", "request_id": request_id,
                "route_template": route, "method": request.method,
                "status": status_code, "latency_ms": round(elapsed * 1000, 3),
                "user_id": getattr(request.state, "user_id", None),
            },
        )


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


@app.get("/metrics", include_in_schema=False)
def metrics(authorization: Annotated[str | None, Header()] = None) -> Response:
    token = get_settings().METRICS_TOKEN
    if not token:
        raise HTTPException(status_code=404, detail="Not found")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    JOB_LAST_SUCCESS.clear()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT kind, job, value FROM app.get_ops_metrics()").fetchall()
    for kind, job, value in rows:
        if kind == "job_last_success_timestamp" and value is not None:
            JOB_LAST_SUCCESS.labels(job).set(value)
        elif kind == "storage_deletions_backlog":
            STORAGE_BACKLOG.set(value)
        elif kind == "storage_deletions_oldest_pending_seconds":
            STORAGE_OLDEST.set(value)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = Field(default=False, strict=True)


def get_current_profile(
    authorization: Annotated[str | None, Header()] = None,
    request: Request = None,
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
    if request is not None:
        request.state.user_id = str(uid)
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
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Invalid or missing bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
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


class ListingPointInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lat: float
    lng: float

    @model_validator(mode="after")
    def within_nepal(self) -> "ListingPointInput":
        if not (26.3 <= self.lat <= 30.5 and 80.0 <= self.lng <= 88.3):
            raise ValueError("point must be inside the supported Nepal bounding box")
        return self


class ListingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    title: str = Field(min_length=1, max_length=500)
    rent_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    point: ListingPointInput

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()

class ListingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    rent_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    point: ListingPointInput | None = None
    answers: dict[str, list[str] | str] | None = None
    numeric: dict[str, float] | None = None

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def has_patch_fields(self) -> "ListingPatch":
        if not (self.model_fields_set - {"version"}):
            raise ValueError("at least one editable field is required")
        return self


class ListingStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"draft", "active", "rented", "sold_out", "unavailable", "archived"}:
            raise ValueError("invalid listing status")
        return value


class PhotoReorderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photo_ids: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator("photo_ids")
    @classmethod
    def photo_ids_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("photo_ids must be unique")
        return value


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementNumericInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    importance: Literal["must", "nice"]


class RequirementsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attributes: dict[str, dict[str, Literal["must", "nice"]]] = Field(default_factory=dict)
    numeric: dict[str, RequirementNumericInput] = Field(default_factory=dict)


class MatchesResponse(StrictResponse):
    perfect: list[dict[str, Any]]
    ranked: list[dict[str, Any]]
    explore: bool = False
    nudge: bool = False


class ListingPhotoResponse(StrictResponse):
    id: UUID
    position: int
    width: int
    height: int
    original_url: str
    thumb_url: str | None


class PhotoDeleteResponse(StrictResponse):
    deleted: bool
    storage_deleted: bool


class PhotoReorderResponse(StrictResponse):
    photos: list[ListingPhotoResponse]


class ConnectResponse(StrictResponse):
    wa_link: str | None


class ConnectedProfileResponse(StrictResponse):
    display_name: str | None
    whatsapp: str | None
    wa_link: str | None


class ConnectedListingSummary(StrictResponse):
    id: UUID
    title: str
    wa_link: str | None = None


class ConnectionItemResponse(StrictResponse):
    id: UUID
    created_at: datetime
    listing: ConnectedListingSummary


class ConnectionsResponse(StrictResponse):
    connections: list[ConnectionItemResponse]
    next_cursor: str | None


class NotificationUserResponse(StrictResponse):
    id: UUID
    display_name: str | None


class NotificationListingResponse(StrictResponse):
    id: UUID
    title: str


class NotificationItemResponse(StrictResponse):
    id: UUID
    kind: Literal["property_connected", "profile_connected", "saved_listing_changed"]
    created_at: datetime
    read_at: datetime | None
    other_user: NotificationUserResponse | None
    listing: NotificationListingResponse | None


class NotificationsResponse(StrictResponse):
    notifications: list[NotificationItemResponse]
    unread_count: int
    next_cursor: str | None


class NotificationReadResponse(StrictResponse):
    id: UUID
    read_at: datetime


class SaveListingResponse(StrictResponse):
    listing_id: UUID
    saved: bool


class SavedListingItemResponse(StrictResponse):
    id: UUID
    title: str
    rent: Decimal
    visible: bool
    wa_link: str | None = None


class SavedListingsResponse(StrictResponse):
    saved: list[SavedListingItemResponse]
    next_cursor: str | None


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


class ReportResultResponse(StrictResponse):
    id: UUID
    status: Literal["open", "resolved"]
    created_at: datetime


class AdminReportItemResponse(StrictResponse):
    id: UUID
    reporter_id: UUID | None
    listing_id: UUID | None
    snapshot_title: str
    snapshot_whatsapp: str | None
    reason: str
    status: Literal["open", "resolved"]
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime


class AdminReportsResponse(StrictResponse):
    reports: list[AdminReportItemResponse]
    next_cursor: str | None


class AdminResolveResponse(StrictResponse):
    id: UUID
    listing_id: UUID | None
    status: Literal["open", "resolved"]
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime


class AdminResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, strict=True)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 500:
            raise ValueError("note must be at most 500 characters")
        return value or None


class AdminSuspendInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


class AdminSuspendResponse(StrictResponse):
    listing_id: UUID
    suspended_at: datetime


class AdminUnsuspendResponse(StrictResponse):
    listing_id: UUID
    suspended: bool


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


@app.delete("/me", response_model=None)
def delete_me(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    body: AccountDeletionRequest | None = None,
) -> dict[str, bool] | JSONResponse:
    if body is None or not body.confirm:
        return JSONResponse(status_code=400, content={"code": "CONFIRM_REQUIRED"})
    user_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
                cur.execute("SELECT app.request_account_deletion()")
            conn.commit()
    except psycopg.Error as exc:
        code = getattr(exc.diag, "message_primary", None)
        if code in {"ACCOUNT_HAS_SUSPENDED_LISTING", "LISTING_SUSPENDED"}:
            return JSONResponse(
                status_code=409,
                content={
                    "code": "ACCOUNT_HAS_SUSPENDED_LISTING",
                    "message": "Account cannot be deleted while a listing is suspended",
                },
            )
        raise HTTPException(
            status_code=503,
            detail={"code": "account_deletion_storage_unavailable", "message": "Account deletion unavailable"},
        ) from None

    result = _auth_delete_user(user_id)
    if result in {"ok", "already_gone"}:
        return {"deleted": True}
    code = result if result in {"timeout", "network"} or re.fullmatch(r"http_[0-9]{3}", result or "") else "network"
    logger.warning("account_deletion_auth_pending", extra={"event": "account_deletion_auth_pending"})
    return JSONResponse(status_code=202, content={"status": "deletion_pending"})


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


def _encode_feed_cursor(created_at: datetime, item_id: Any) -> str:
    raw = json.dumps([created_at.isoformat(), str(item_id)], separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_feed_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        created_at_raw, item_id_raw = json.loads(raw)
        created_at = datetime.fromisoformat(created_at_raw)
        if created_at.tzinfo is None:
            raise ValueError
        return created_at.astimezone(timezone.utc), UUID(item_id_raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_cursor", "message": "Invalid cursor"})


PUBLIC_LISTING_SELECT = """SELECT listing.id, listing.title, listing.rent_amount,
       extensions.st_y(listing.point::extensions.geometry),
       extensions.st_x(listing.point::extensions.geometry),
       public_profile.whatsapp, listing.created_at
FROM app.listings AS listing
CROSS JOIN LATERAL app.get_public_profile(listing.owner_id) AS public_profile
WHERE listing.status = 'active' AND listing.suspended_at IS NULL"""


def _listing_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "LISTING_NOT_FOUND", "message": "Listing not found"},
    )


def _listing_db_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc.diag, "message_primary", None) or "LISTING_STORAGE_ERROR"
    if code == "LISTING_NOT_FOUND":
        return _listing_not_found()
    conflict_codes = {
        "LISTING_INVALID_TRANSITION", "LISTING_SUSPENDED", "LISTING_NOT_RESTORABLE",
        "LISTING_NOT_DRAFT", "LISTING_DELETE_REQUIRES_ARCHIVED", "DRAFT_LIMIT",
        "VERSION_CONFLICT", "WHATSAPP_REQUIRED",
    }
    if code == "LISTING_PUBLISH_INCOMPLETE":
        missing = [item for item in (getattr(exc.diag, "message_detail", None) or "").split(",") if item]
        return HTTPException(
            status_code=422,
            detail={"code": code, "message": "Listing is missing required publish information", "missing": missing},
        )
    if code in conflict_codes:
        return HTTPException(
            status_code=409,
            detail={"code": code, "message": "Listing cannot be changed in its current state"},
        )
    if isinstance(exc, (psycopg.errors.CheckViolation, psycopg.errors.ForeignKeyViolation,
                        psycopg.errors.UniqueViolation, psycopg.errors.InvalidTextRepresentation,
                        psycopg.errors.NumericValueOutOfRange)):
        return HTTPException(
            status_code=422,
            detail={"code": "INVALID_LISTING_DATA", "message": "Listing data is invalid"},
        )
    return HTTPException(
        status_code=503,
        detail={"code": "LISTING_STORAGE_UNAVAILABLE", "message": "Listing storage unavailable"},
    )


PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_MAX_PIXELS = 25_000_000
PHOTO_THUMB_WIDTH = 400
PHOTO_THUMB_HEIGHT = 300
PHOTO_BUCKET = "listing-photos"
PHOTO_MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
PHOTO_NORMALIZE_SEMAPHORE = threading.BoundedSemaphore(2)


def _photo_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _photo_public_url(path: str) -> str:
    settings = get_settings()
    return (
        f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/"
        f"{PHOTO_BUCKET}/{quote(path, safe='')}"
    )


def _photo_json(row: tuple[Any, ...]) -> dict[str, Any]:
    photo_id, position, width, height, storage_path, thumb_path = row
    return {
        "id": str(photo_id),
        "position": position,
        "width": width,
        "height": height,
        "original_url": _photo_public_url(storage_path),
        "thumb_url": _photo_public_url(thumb_path) if thumb_path else None,
    }


def _listing_photos_json(conn: psycopg.Connection, listing_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, position, width, height, storage_path, thumb_path
           FROM app.listing_photos WHERE listing_id = %s ORDER BY position""",
        (listing_id,),
    ).fetchall()
    return [_photo_json(row) for row in rows]


def _photo_magic_format(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _read_photo_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = upload.file.read(min(64 * 1024, PHOTO_MAX_BYTES + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > PHOTO_MAX_BYTES:
            raise _photo_error(413, "PHOTO_TOO_LARGE", "Photo exceeds 5 MB")
        chunks.append(chunk)
    if not size:
        raise _photo_error(415, "PHOTO_TYPE_INVALID", "Photo must be a JPEG, PNG, or WebP image")
    return b"".join(chunks)


def _normalize_photo_unlocked(data: bytes) -> tuple[bytes, bytes, int, int, str]:
    detected_format = _photo_magic_format(data)
    if detected_format is None:
        raise _photo_error(415, "PHOTO_TYPE_INVALID", "Photo must be a JPEG, PNG, or WebP image")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ({"JPEG", "MPO"} if detected_format == "JPEG" else {detected_format}):
                raise _photo_error(415, "PHOTO_TYPE_INVALID", "Photo content does not match its image type")
            source.seek(0)
            if source.width * source.height > PHOTO_MAX_PIXELS:
                raise _photo_error(413, "PHOTO_TOO_LARGE", "Photo dimensions exceed the supported limit")
            oriented = ImageOps.exif_transpose(source)
            width, height = oriented.size
            preserve_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
            normalized = oriented.convert("RGBA" if preserve_alpha else "RGB")
            original_buffer = BytesIO()
            save_options: dict[str, Any] = {}
            if detected_format == "JPEG":
                save_options = {"quality": 90, "optimize": True}
            elif detected_format == "WEBP":
                save_options = {"quality": 92, "method": 6}
            else:
                save_options = {"optimize": True}
            normalized.save(original_buffer, format=detected_format, **save_options)

            box_width = PHOTO_THUMB_WIDTH
            box_height = PHOTO_THUMB_HEIGHT
            settings = get_settings()
            bar_color = ImageColor.getrgb(settings.PHOTO_BAR_COLOR)[:3]
            scale = min(box_width / width, box_height / height)
            fitted_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            fitted = normalized.resize(fitted_size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (box_width, box_height), bar_color)
            offset = ((box_width - fitted.width) // 2, (box_height - fitted.height) // 2)
            if fitted.mode == "RGBA":
                canvas.paste(fitted, offset, fitted.getchannel("A"))
            else:
                canvas.paste(fitted, offset)
            thumb_buffer = BytesIO()
            canvas.save(thumb_buffer, format="JPEG", quality=90, optimize=True)
            return original_buffer.getvalue(), thumb_buffer.getvalue(), width, height, PHOTO_MIME_BY_FORMAT[detected_format]
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise _photo_error(413, "PHOTO_TOO_LARGE", "Photo dimensions exceed the supported limit")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise _photo_error(415, "PHOTO_TYPE_INVALID", "Photo must be a valid JPEG, PNG, or WebP image")


def _normalize_photo(data: bytes) -> tuple[bytes, bytes, int, int, str]:
    with PHOTO_NORMALIZE_SEMAPHORE:
        return _normalize_photo_unlocked(data)


def _storage_headers(content_type: str | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "false"
    return headers


def _auth_delete_user(user_id: str) -> str:
    """Delete an Auth user without exposing credentials or identifiers in logs."""
    try:
        settings = get_settings()
        response = httpx.delete(
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{quote(user_id, safe='')}",
            headers=_storage_headers(),
            timeout=15,
        )
        if 200 <= response.status_code < 300:
            return "ok"
        if response.status_code == 404:
            return "already_gone"
        return f"http_{response.status_code}"
    except httpx.TimeoutException:
        return "timeout"
    except httpx.RequestError:
        return "network"
    except Exception:
        return "network"


def _storage_object_url(path: str) -> str:
    settings = get_settings()
    return (
        f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/"
        f"{PHOTO_BUCKET}/{quote(path, safe='')}"
    )


def _storage_upload(path: str, data: bytes, content_type: str) -> None:
    try:
        response = httpx.post(
            _storage_object_url(path), headers=_storage_headers(content_type), content=data, timeout=30
        )
        if not response.is_success:
            raise RuntimeError("storage upload failed")
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None


def _storage_delete(path: str) -> bool:
    try:
        response = httpx.delete(_storage_object_url(path), headers=_storage_headers(), timeout=15)
        if response.is_success or response.status_code == 404:
            return True
    except Exception:
        pass
    logger.warning("photo_storage_delete_failed", extra={"event": "photo_storage_delete_failed"})
    return False


def _photo_listing_for_owner(
    conn: psycopg.Connection, listing_id: str, owner_id: str, *, lock: bool = False
) -> tuple[str, Any] | None:
    suffix = " FOR UPDATE" if lock else ""
    return conn.execute(
        "SELECT status, suspended_at FROM app.listings WHERE id = %s AND owner_id = %s" + suffix,
        (listing_id, owner_id),
    ).fetchone()


def _check_photo_listing_state(state: tuple[str, Any] | None) -> None:
    if state is None:
        raise _listing_not_found()
    listing_status, suspended_at = state
    if suspended_at is not None:
        raise _photo_error(409, "LISTING_SUSPENDED", "Suspended listings cannot be changed")
    if listing_status == "archived":
        raise _photo_error(409, "LISTING_NOT_EDITABLE", "Archived listings cannot be changed")


def _owned_listing_json(conn: psycopg.Connection, owner_id: str, listing_id: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT listing.id, listing.title, listing.rent_amount,
                  extensions.st_y(listing.point::extensions.geometry),
                  extensions.st_x(listing.point::extensions.geometry), listing.status,
                  listing.version, listing.created_at, listing.updated_at,
                  listing.archived_from_status, listing.archived_at,
                  listing.status_changed_at
           FROM app.listings AS listing
           WHERE listing.id = %s AND listing.owner_id = %s""",
        (listing_id, owner_id),
    ).fetchone()
    if row is None:
        raise _listing_not_found()
    answers = conn.execute(
        """SELECT attribute.key, option.label
           FROM app.listing_answers AS answer
           JOIN app.attributes AS attribute ON attribute.id = answer.attribute_id
           JOIN app.attribute_options AS option ON option.id = answer.option_id
           WHERE answer.listing_id = %s AND EXISTS (
               SELECT 1 FROM app.listings AS listing
               WHERE listing.id = answer.listing_id AND listing.owner_id = %s
           )
           ORDER BY attribute.key, option.sort_order""",
        (listing_id, owner_id),
    ).fetchall()
    numeric = conn.execute(
        """SELECT numeric_value.field, numeric_value.value
           FROM app.listing_numeric AS numeric_value
           WHERE numeric_value.listing_id = %s AND EXISTS (
               SELECT 1 FROM app.listings AS listing
               WHERE listing.id = numeric_value.listing_id AND listing.owner_id = %s
           )
           ORDER BY numeric_value.field""",
        (listing_id, owner_id),
    ).fetchall()
    answer_map: dict[str, list[str]] = {}
    for attribute_key, option_key in answers:
        answer_map.setdefault(attribute_key, []).append(option_key)
    return {
        "id": str(row[0]), "title": row[1], "rent_amount": str(row[2]),
        "point": {"lat": float(row[3]), "lng": float(row[4])},
        "status": row[5], "version": row[6],
        "created_at": row[7].isoformat(), "updated_at": row[8].isoformat(),
        "archived_from_status": row[9],
        "archived_at": row[10].isoformat() if row[10] else None,
        "status_changed_at": row[11].isoformat(),
        "answers": answer_map,
        "numeric": {key: str(value) for key, value in numeric},
    }


def _validate_answer_payload(conn: psycopg.Connection, answers: dict[str, list[str] | str]) -> list[tuple[str, str]]:
    registry_rows = conn.execute(
        """SELECT attribute.key, attribute.type, option.label, option.is_exclusive
           FROM app.attributes AS attribute
           LEFT JOIN app.attribute_options AS option
             ON option.attribute_id = attribute.id AND option.is_active
           WHERE attribute.is_active"""
    ).fetchall()
    registry: dict[str, dict[str, Any]] = {}
    for key, pick_type, option_label, exclusive in registry_rows:
        item = registry.setdefault(key, {"type": pick_type, "options": {}})
        if option_label is not None:
            item["options"][option_label] = bool(exclusive)

    normalized: list[tuple[str, str]] = []
    invalid = False
    for key, raw_values in answers.items():
        values = [raw_values] if isinstance(raw_values, str) else raw_values
        attribute = registry.get(key)
        if attribute is None or len(values) != len(set(values)):
            invalid = True
            continue
        if attribute["type"] in {"single", "yes_no"} and len(values) > 1:
            invalid = True
        if any(option not in attribute["options"] for option in values):
            invalid = True
            continue
        if any(attribute["options"][option] for option in values) and len(values) > 1:
            invalid = True
        normalized.extend((key, option) for option in values)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ANSWERS", "message": "Answers contain an invalid attribute or option selection"},
        )
    return normalized


NUMERIC_LISTING_FIELDS = {
    "bedrooms", "bathrooms_total",
    "kitchen_count", "balconies", "total_floors", "size_value", "max_people",
    "road_access_width_ft", "main_road_distance_km",
}


def _validate_numeric_payload(conn: psycopg.Connection, values: dict[str, float]) -> dict[str, Decimal]:
    active = {
        row[0] for row in conn.execute(
            "SELECT key FROM app.numeric_fields WHERE is_active AND key <> 'rent_amount'"
        ).fetchall()
    }
    if not set(values).issubset(NUMERIC_LISTING_FIELDS & active):
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_NUMERIC_FIELDS", "message": "Numeric fields contain an unsupported key"},
        )
    return {key: Decimal(str(value)) for key, value in values.items()}


@app.post("/listings", status_code=201)
def create_listing(
    body: ListingCreate,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    owner_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            conn.execute("SELECT set_config('app.actor', 'owner', true)")
            # Serialize per-owner draft counts so concurrent creates cannot exceed the cap.
            conn.execute("SELECT id FROM app.profiles WHERE id = %s FOR UPDATE", (owner_id,))
            count = conn.execute(
                "SELECT count(*) FROM app.listings WHERE owner_id = %s AND status = 'draft'",
                (owner_id,),
            ).fetchone()[0]
            if count >= 20:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "DRAFT_LIMIT", "message": "Maximum number of drafts reached"},
                )
            listing_id = conn.execute(
                """INSERT INTO app.listings (owner_id, title, rent_amount, point)
                   VALUES (%s, %s, %s,
                     extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography)
                   RETURNING id""",
                (owner_id, body.title, body.rent_amount,
                 body.point.lng, body.point.lat),
            ).fetchone()[0]
            return _owned_listing_json(conn, owner_id, str(listing_id))
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _listing_db_error(exc) from exc


@app.get("/me/listings")
def read_my_listings(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    owner_id = str(profile["id"])
    with get_db_connection() as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
        listing_ids = conn.execute(
            "SELECT id FROM app.listings WHERE owner_id = %s ORDER BY created_at DESC, id",
            (owner_id,),
        ).fetchall()
        listings = [_owned_listing_json(conn, owner_id, str(row[0])) for row in listing_ids]
    return {"listings": listings}


@app.get("/me/listings/{listing_ref}")
def read_my_listing(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    with get_db_connection() as conn:
        conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
        listing = _owned_listing_json(conn, owner_id, listing_id)
        listing["photos"] = _listing_photos_json(conn, listing_id)
        return listing


@app.post("/listings/{listing_ref}/photos", status_code=201, response_model=ListingPhotoResponse)
def upload_listing_photo(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            state = _photo_listing_for_owner(conn, listing_id, owner_id)
            _check_photo_listing_state(state)
    except HTTPException:
        raise
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None

    try:
        raw_data = _read_photo_upload(file)
    except HTTPException:
        raise
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    try:
        original_data, thumb_data, width, height, content_type = _normalize_photo(raw_data)
    except HTTPException:
        raise
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    storage_path = str(uuid.uuid4())
    thumb_path = str(uuid.uuid4())
    uploaded_paths: list[str] = []
    try:
        uploaded_paths.append(storage_path)
        uploaded_paths.append(thumb_path)
        _storage_upload(storage_path, original_data, content_type)
        _storage_upload(thumb_path, thumb_data, "image/jpeg")
        try:
            with get_db_connection() as conn:
                conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
                state = _photo_listing_for_owner(conn, listing_id, owner_id, lock=True)
                _check_photo_listing_state(state)
                position = conn.execute(
                    """SELECT positions.candidate FROM generate_series(1, 10) AS positions(candidate)
                       WHERE NOT EXISTS (
                           SELECT 1 FROM app.listing_photos AS photo
                           WHERE photo.listing_id = %s AND photo.position = positions.candidate
                       ) ORDER BY positions.candidate LIMIT 1""",
                    (listing_id,),
                ).fetchone()
                next_position = position[0] if position is not None else 11
                row = conn.execute(
                    """INSERT INTO app.listing_photos
                           (listing_id, storage_path, thumb_path, position, width, height)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id, position, width, height, storage_path, thumb_path""",
                    (listing_id, storage_path, thumb_path, next_position, width, height),
                ).fetchone()
        except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation) as exc:
            if getattr(exc.diag, "constraint_name", None) in {
                "listing_photos_listing_position_key", "listing_photos_position_check",
            }:
                raise _photo_error(409, "PHOTO_LIMIT", "A listing can have at most 10 photos") from None
            raise
        return _photo_json(row)
    except HTTPException:
        for uploaded_path in uploaded_paths:
            _storage_delete(uploaded_path)
        raise
    except psycopg.Error:
        for uploaded_path in uploaded_paths:
            _storage_delete(uploaded_path)
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    except Exception:
        for uploaded_path in uploaded_paths:
            _storage_delete(uploaded_path)
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None


@app.delete("/listings/{listing_ref}/photos/{photo_id}", response_model=PhotoDeleteResponse)
def delete_listing_photo(
    listing_ref: str,
    photo_id: UUID,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            _check_photo_listing_state(_photo_listing_for_owner(conn, listing_id, owner_id, lock=True))
            row = conn.execute(
                """DELETE FROM app.listing_photos
                   WHERE listing_id = %s AND id = %s
                   RETURNING storage_path, thumb_path""",
                (listing_id, photo_id),
            ).fetchone()
    except psycopg.Error:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    except HTTPException:
        raise
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    if row is None:
        raise _photo_error(404, "PHOTO_NOT_FOUND", "Photo not found")
    original_deleted = _storage_delete(row[0])
    thumb_deleted = _storage_delete(row[1])
    return {"deleted": True, "storage_deleted": original_deleted and thumb_deleted}


@app.post("/listings/{listing_ref}/photos/reorder", response_model=PhotoReorderResponse)
def reorder_listing_photos(
    listing_ref: str,
    body: PhotoReorderInput,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            _check_photo_listing_state(_photo_listing_for_owner(conn, listing_id, owner_id, lock=True))
            existing = conn.execute(
                "SELECT id FROM app.listing_photos WHERE listing_id = %s ORDER BY position",
                (listing_id,),
            ).fetchall()
            existing_ids = {row[0] for row in existing}
            requested_ids = set(body.photo_ids)
            if len(existing) != len(body.photo_ids) or existing_ids != requested_ids:
                raise _photo_error(422, "PHOTO_ORDER_INVALID", "Photo order must include every listing photo once")
            conn.execute(
                """UPDATE app.listing_photos AS photo
                   SET position = ordering.position::smallint
                   FROM unnest(%s::uuid[]) WITH ORDINALITY AS ordering(id, position)
                   WHERE photo.listing_id = %s AND photo.id = ordering.id""",
                (body.photo_ids, listing_id),
            )
            photos = _listing_photos_json(conn, listing_id)
    except HTTPException:
        raise
    except psycopg.Error:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    except Exception:
        raise _photo_error(503, "PHOTO_STORAGE_UNAVAILABLE", "Photo storage unavailable") from None
    return {"photos": photos}


@app.patch("/listings/{listing_ref}")
def patch_listing(
    listing_ref: str,
    body: ListingPatch,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    explicitly_set = body.model_fields_set - {"version"}
    for key in {"title", "rent_amount", "point", "answers", "numeric"} & explicitly_set:
        if getattr(body, key) is None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_LISTING_DATA", "message": f"{key} cannot be null"})
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            conn.execute("SELECT set_config('app.actor', 'owner', true)")
            current = conn.execute(
                "SELECT status, version, suspended_at FROM app.listings WHERE id = %s AND owner_id = %s FOR UPDATE",
                (listing_id, owner_id),
            ).fetchone()
            if current is None:
                raise _listing_not_found()
            if current[1] != body.version:
                raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT", "message": "Listing version is stale"})
            if current[2] is not None:
                raise HTTPException(status_code=409, detail={"code": "LISTING_SUSPENDED", "message": "Suspended listings cannot be changed"})
            if current[0] == "archived":
                raise HTTPException(status_code=409, detail={"code": "LISTING_NOT_EDITABLE", "message": "Archived listings cannot be changed"})

            assignments: list[str] = []
            values: list[Any] = []
            if "title" in explicitly_set:
                assignments.append("title = %s")
                values.append(body.title)
            if "rent_amount" in explicitly_set:
                assignments.append("rent_amount = %s")
                values.append(body.rent_amount)
            if "point" in explicitly_set:
                assignments.append("point = extensions.st_setsrid(extensions.st_makepoint(%s, %s), 4326)::extensions.geography")
                values.extend((body.point.lng, body.point.lat))
            if assignments:
                conn.execute(
                    f"UPDATE app.listings SET {', '.join(assignments)} WHERE id = %s AND owner_id = %s",
                    (*values, listing_id, owner_id),
                )

            if "answers" in explicitly_set:
                normalized = _validate_answer_payload(conn, body.answers or {})
                conn.execute(
                    """DELETE FROM app.listing_answers AS answer
                       WHERE answer.listing_id = %s AND EXISTS (
                         SELECT 1 FROM app.listings AS listing
                         WHERE listing.id = answer.listing_id AND listing.owner_id = %s
                       )""",
                    (listing_id, owner_id),
                )
                for attribute_key, option_key in normalized:
                    conn.execute(
                        """INSERT INTO app.listing_answers (listing_id, attribute_id, option_id)
                           SELECT %s, attribute.id, option.id
                           FROM app.attributes AS attribute
                           JOIN app.attribute_options AS option ON option.attribute_id = attribute.id
                           WHERE attribute.key = %s AND attribute.is_active
                             AND option.label = %s AND option.is_active
                             AND EXISTS (SELECT 1 FROM app.listings AS listing
                                         WHERE listing.id = %s AND listing.owner_id = %s)""",
                        (listing_id, attribute_key, option_key, listing_id, owner_id),
                    )

            if "numeric" in explicitly_set:
                numeric = _validate_numeric_payload(conn, body.numeric or {})
                conn.execute(
                    """DELETE FROM app.listing_numeric AS numeric_value
                       WHERE numeric_value.listing_id = %s AND EXISTS (
                         SELECT 1 FROM app.listings AS listing
                         WHERE listing.id = numeric_value.listing_id AND listing.owner_id = %s
                       )""",
                    (listing_id, owner_id),
                )
                for field, value in numeric.items():
                    conn.execute(
                        """INSERT INTO app.listing_numeric (listing_id, field, value)
                           SELECT %s, numeric_field.key, %s
                           FROM app.numeric_fields AS numeric_field
                           WHERE numeric_field.key = %s AND numeric_field.is_active
                             AND EXISTS (SELECT 1 FROM app.listings AS listing
                                         WHERE listing.id = %s AND listing.owner_id = %s)""",
                        (listing_id, value, field, listing_id, owner_id),
                    )
            return _owned_listing_json(conn, owner_id, listing_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _listing_db_error(exc) from exc


def _call_listing_function(
    function_sql: str,
    listing_ref: str,
    profile: dict[str, Any],
    args: tuple[Any, ...] = (),
) -> Any:
    try:
        listing_id = str(UUID(listing_ref))
    except ValueError:
        raise _listing_not_found()
    owner_id = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (owner_id,))
            result = conn.execute(function_sql, (listing_id, *args)).fetchone()[0]
            return result
    except psycopg.Error as exc:
        raise _listing_db_error(exc) from exc


def _listing_after_function(listing_ref: str, profile: dict[str, Any], function_sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any]:
    _call_listing_function(function_sql, listing_ref, profile, args)
    return read_my_listing(listing_ref, profile)


@app.post("/listings/{listing_ref}/publish")
def publish_owner_listing(listing_ref: str, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    return _listing_after_function(listing_ref, profile, "SELECT app.publish_listing(%s)")


@app.post("/listings/{listing_ref}/status")
def set_owner_listing_status(listing_ref: str, body: ListingStatusInput, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    return _listing_after_function(listing_ref, profile, "SELECT app.set_listing_status(%s, %s)", (body.status,))


@app.post("/listings/{listing_ref}/archive")
def archive_owner_listing(listing_ref: str, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    return _listing_after_function(listing_ref, profile, "SELECT app.archive_listing(%s)")


@app.post("/listings/{listing_ref}/restore")
def restore_owner_listing(listing_ref: str, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    return _listing_after_function(listing_ref, profile, "SELECT app.restore_listing(%s)")


@app.delete("/listings/{listing_ref}")
def delete_owner_listing(listing_ref: str, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, Any]:
    paths = _call_listing_function("SELECT app.force_delete_listing(%s)", listing_ref, profile)
    return {"deleted": True, "storage_paths": paths}


def _connect_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc.diag, "message_primary", None)
    if code == "LISTING_NOT_FOUND":
        return HTTPException(
            status_code=404,
            detail={"code": "LISTING_NOT_FOUND", "message": "Listing not found"},
        )
    if code == "CONNECT_OWN_LISTING":
        return HTTPException(
            status_code=400,
            detail={"code": "CONNECT_OWN_LISTING", "message": "Cannot connect to your own listing"},
        )
    if code == "CONNECT_LIMIT":
        retry_after = getattr(exc.diag, "message_detail", None) or "1"
        return HTTPException(
            status_code=429,
            detail={"code": "CONNECT_LIMIT", "message": "Connection limit reached"},
            headers={"Retry-After": retry_after},
        )
    return HTTPException(
        status_code=503,
        detail={"code": "CONNECTION_STORAGE_UNAVAILABLE", "message": "Connections unavailable"},
    )


def _profile_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
    )


@app.post("/listings/{listing_ref}/connect", response_model=ConnectResponse)
def connect_to_listing(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        listing_id = UUID(listing_ref)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"code": "LISTING_NOT_FOUND", "message": "Listing not found"},
        )
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            wa_link, inserted = conn.execute(
                "SELECT wa_link, inserted FROM app.connect_listing_counted(%s)", (listing_id,)
            ).fetchone()
            if inserted:
                CONNECT_TOTAL.inc()
    except psycopg.Error as exc:
        raise _connect_error(exc) from exc
    return {"wa_link": wa_link}


@app.get("/me/connections/profile/{user_id}", response_model=ConnectedProfileResponse)
def read_connected_profile(
    user_id: UUID,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            row = conn.execute(
                "SELECT display_name, whatsapp, wa_link FROM app.get_connected_profile(%s)",
                (str(user_id),),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "PROFILE_STORAGE_UNAVAILABLE", "message": "Profile unavailable"},
        ) from exc
    if row is None:
        raise _profile_not_found()
    return {"display_name": row[0], "whatsapp": row[1], "wa_link": row[2]}


@app.get(
    "/me/connections",
    response_model=ConnectionsResponse,
    response_model_exclude_unset=True,
)
def read_my_connections(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    page_size: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, Any]:
    before_created_at, before_id = _decode_feed_cursor(cursor)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            rows = conn.execute(
                """SELECT * FROM app.get_my_connections(
                       %s::timestamptz, %s::uuid, %s::integer
                   )""",
                (before_created_at, before_id, page_size + 1),
            ).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONNECTION_STORAGE_UNAVAILABLE", "message": "Connections unavailable"},
        ) from exc

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    connections = []
    for row in visible_rows:
        listing = {"id": row[2], "title": row[3]}
        if row[4]:
            listing["wa_link"] = row[5]
        connections.append({"id": row[0], "created_at": row[1], "listing": listing})
    next_cursor = None
    if has_more and visible_rows:
        next_cursor = _encode_feed_cursor(visible_rows[-1][1], visible_rows[-1][0])
    return {"connections": connections, "next_cursor": next_cursor}


@app.get("/me/notifications", response_model=NotificationsResponse)
def read_my_notifications(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    page_size: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, Any]:
    before_created_at, before_id = _decode_feed_cursor(cursor)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            unread_count = conn.execute(
                "SELECT count(*) FROM app.notifications WHERE user_id = %s AND read_at IS NULL",
                (str(profile["id"]),),
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT * FROM app.get_my_notifications(
                       %s::timestamptz, %s::uuid, %s::integer
                   )""",
                (before_created_at, before_id, page_size + 1),
            ).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "NOTIFICATION_STORAGE_UNAVAILABLE", "message": "Notifications unavailable"},
        ) from exc

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    notifications = []
    for row in visible_rows:
        other_user = None
        if row[4] is not None:
            other_user = {"id": row[4], "display_name": row[5]}
        listing = None
        if row[6] is not None:
            listing = {"id": row[6], "title": row[7]}
        notifications.append({
            "id": row[0],
            "kind": row[1],
            "created_at": row[2],
            "read_at": row[3],
            "other_user": other_user,
            "listing": listing,
        })
    next_cursor = None
    if has_more and visible_rows:
        next_cursor = _encode_feed_cursor(visible_rows[-1][2], visible_rows[-1][0])
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "next_cursor": next_cursor,
    }


def _step8_db_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc.diag, "message_primary", None)
    if code == "ADMIN_NOT_FOUND":
        return HTTPException(status_code=404, detail="Not Found")
    if code == "LISTING_NOT_FOUND":
        return _listing_not_found()
    if code == "SAVE_OWN_LISTING":
        return HTTPException(
            status_code=400,
            detail={"code": code, "message": "Cannot save your own listing"},
        )
    if code == "REPORT_OWN_LISTING":
        return HTTPException(
            status_code=400,
            detail={"code": code, "message": "Cannot report your own listing"},
        )
    if code == "REPORT_LIMIT":
        retry_after = getattr(exc.diag, "message_detail", None) or "1"
        return HTTPException(
            status_code=429,
            detail={"code": code, "message": "Report limit reached"},
            headers={"Retry-After": retry_after},
        )
    if code == "REPORT_NOT_FOUND":
        return HTTPException(
            status_code=404,
            detail={"code": code, "message": "Report not found"},
        )
    if code in {"LISTING_ALREADY_SUSPENDED", "LISTING_NOT_SUSPENDED"}:
        return HTTPException(
            status_code=409,
            detail={"code": code, "message": "Listing suspension state conflict"},
        )
    if code in {"INVALID_REPORT_REASON", "INVALID_REPORT_STATUS", "ADMIN_REASON_REQUIRED", "INVALID_ADMIN_NOTE"}:
        return HTTPException(
            status_code=422,
            detail={"code": code, "message": "Request data is invalid"},
        )
    return HTTPException(
        status_code=503,
        detail={"code": "STEP8_STORAGE_UNAVAILABLE", "message": "Request unavailable"},
    )


def _step8_listing_id(listing_ref: str) -> UUID:
    try:
        return UUID(listing_ref)
    except ValueError:
        raise _listing_not_found()


@app.post("/listings/{listing_ref}/save", response_model=SaveListingResponse)
def save_listing(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    listing_id = _step8_listing_id(listing_ref)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            conn.execute("SELECT app.save_listing(%s)", (listing_id,))
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {"listing_id": listing_id, "saved": True}


@app.delete("/listings/{listing_ref}/save", response_model=SaveListingResponse)
def unsave_listing(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    listing_id = _step8_listing_id(listing_ref)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            conn.execute("SELECT app.unsave_listing(%s)", (listing_id,))
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {"listing_id": listing_id, "saved": False}


@app.get(
    "/me/saved",
    response_model=SavedListingsResponse,
    response_model_exclude_unset=True,
)
def read_my_saved_listings(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    page_size: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, Any]:
    before_created_at, before_id = _decode_feed_cursor(cursor)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            rows = conn.execute(
                """SELECT * FROM app.get_my_saved(
                       %s::timestamptz, %s::uuid, %s::integer
                   )""",
                (before_created_at, before_id, page_size + 1),
            ).fetchall()
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    saved = []
    for row in visible_rows:
        item = {
            "id": row[0], "title": row[1], "rent": row[2], "visible": row[3],
        }
        if row[3]:
            item["wa_link"] = row[4]
        saved.append(item)
    next_cursor = None
    if has_more and visible_rows:
        next_cursor = _encode_feed_cursor(visible_rows[-1][5], visible_rows[-1][0])
    return {"saved": saved, "next_cursor": next_cursor}


@app.post("/listings/{listing_ref}/report", response_model=ReportResultResponse)
def report_listing(
    listing_ref: str,
    body: ReportInput,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    listing_id = _step8_listing_id(listing_ref)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            row = conn.execute(
                "SELECT * FROM app.report_listing(%s, %s)",
                (listing_id, body.reason),
            ).fetchone()
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {"id": row[0], "status": row[6], "created_at": row[9]}


@app.get(
    "/admin/reports",
    response_model=AdminReportsResponse,
    response_model_exclude_unset=True,
)
def read_admin_reports(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    report_status: Literal["open", "resolved"] = Query(default="open", alias="status"),
    page_size: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, Any]:
    before_created_at, before_id = _decode_feed_cursor(cursor)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            rows = conn.execute(
                """SELECT * FROM app.admin_list_reports(
                       %s, %s::timestamptz, %s::uuid, %s::integer
                   )""",
                (report_status, before_created_at, before_id, page_size + 1),
            ).fetchall()
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    reports = [
        {
            "id": row[0], "reporter_id": row[1], "listing_id": row[2],
            "snapshot_title": row[3], "snapshot_whatsapp": row[4], "reason": row[5],
            "status": row[6], "resolved_by": row[7], "resolved_at": row[8],
            "created_at": row[9],
        }
        for row in visible_rows
    ]
    next_cursor = None
    if has_more and visible_rows:
        next_cursor = _encode_feed_cursor(visible_rows[-1][9], visible_rows[-1][0])
    return {"reports": reports, "next_cursor": next_cursor}


@app.post("/admin/reports/{report_id}/resolve", response_model=AdminResolveResponse)
def resolve_admin_report(
    report_id: UUID,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    body: AdminResolveInput | None = None,
) -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            row = conn.execute(
                "SELECT * FROM app.admin_resolve_report(%s, %s)",
                (report_id, body.note if body is not None else None),
            ).fetchone()
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {
        "id": row[0], "listing_id": row[2], "status": row[6],
        "resolved_by": row[7], "resolved_at": row[8], "created_at": row[9],
    }


@app.post("/admin/listings/{listing_ref}/suspend", response_model=AdminSuspendResponse)
def suspend_admin_listing(
    listing_ref: str,
    body: AdminSuspendInput,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    listing_id = _step8_listing_id(listing_ref)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            row = conn.execute(
                "SELECT result.id AS listing_id, result.suspended_at AS suspended_at FROM app.admin_suspend_listing(%s, %s) AS result",
                (listing_id, body.reason),
            ).fetchone()
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {"listing_id": row[0], "suspended_at": row[1]}


@app.post("/admin/listings/{listing_ref}/unsuspend", response_model=AdminUnsuspendResponse)
def unsuspend_admin_listing(
    listing_ref: str,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    listing_id = _step8_listing_id(listing_ref)
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            conn.execute("SELECT app.admin_unsuspend_listing(%s)", (listing_id,))
    except psycopg.Error as exc:
        raise _step8_db_error(exc) from exc
    return {"listing_id": listing_id, "suspended": False}


@app.post(
    "/me/notifications/{notification_id}/read",
    response_model=NotificationReadResponse,
)
def mark_notification_read(
    notification_id: UUID,
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
) -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(profile["id"]),))
            row = conn.execute(
                """UPDATE app.notifications
                   SET read_at = COALESCE(read_at, now())
                   WHERE id = %s AND user_id = %s
                   RETURNING id, read_at""",
                (str(notification_id), str(profile["id"])),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "NOTIFICATION_STORAGE_UNAVAILABLE", "message": "Notifications unavailable"},
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOTIFICATION_NOT_FOUND", "message": "Notification not found"},
        )
    return {"id": row[0], "read_at": row[1]}


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


@app.put("/me/requirements")
def replace_requirements(body: RequirementsInput, profile: Annotated[dict[str, Any], Depends(get_current_profile)]) -> dict[str, bool]:
    uid = str(profile["id"])
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
            with conn.transaction():
                conn.execute("DELETE FROM app.requirements WHERE user_id=%s", (uid,))
                conn.execute("DELETE FROM app.requirement_numeric WHERE user_id=%s", (uid,))
                for key, picks in body.attributes.items():
                    rows = conn.execute(
                        """SELECT a.id, a.pick_rule, o.id, o.label FROM app.attributes a
                           JOIN app.attribute_options o ON o.attribute_id=a.id
                           WHERE a.key=%s AND a.is_active AND o.is_active""", (key,)
                    ).fetchall()
                    if not rows or any(label not in {r[3] for r in rows} for label in picks):
                        raise HTTPException(status_code=422, detail={"code":"INVALID_REQUIREMENT_OPTION","message":"Unknown or inactive requirement option"})
                    if not picks:
                        continue
                    rule = rows[0][1]
                    if rule in {"single", "yes_no"} and len(picks) > 1:
                        raise HTTPException(status_code=422, detail="Only one option is allowed")
                    for label, importance in picks.items():
                        option = next(r for r in rows if r[3] == label)
                        conn.execute("INSERT INTO app.requirements(user_id,attribute_id,option_id,pick_rule,importance) VALUES (%s,%s,%s,%s,%s)", (uid, option[0], option[2], rule, importance))
                allowed_numeric = {"rent_amount", "bedrooms", "bathrooms_total", "size_value", "max_people"}
                if set(body.numeric) - allowed_numeric:
                    raise HTTPException(status_code=422, detail={"code":"INVALID_REQUIREMENT_FIELD","message":"Unknown numeric requirement field"})
                for field, requirement in body.numeric.items():
                    inserted = conn.execute("INSERT INTO app.requirement_numeric(user_id,field,value,importance) SELECT %s,key,%s,%s FROM app.numeric_fields WHERE key=%s AND is_active", (uid, requirement.value, requirement.importance, field))
                    if inserted.rowcount != 1:
                        raise HTTPException(status_code=422, detail={"code":"INVALID_REQUIREMENT_FIELD","message":"Unknown or inactive numeric requirement field"})
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=422, detail="Only one single-choice must is allowed per attribute") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail={"code":"REQUIREMENTS_STORAGE_UNAVAILABLE","message":"Requirements unavailable"}) from exc
    return {"replaced": True}


@app.get("/matches")
def read_matches(
    profile: Annotated[dict[str, Any], Depends(get_current_profile)],
    cursor: str | None = None,
    page_size: int = Query(20, ge=1, le=50),
) -> dict[str, Any]:
    uid = str(profile["id"])
    cursor_day = cursor_hash = cursor_id = None
    if cursor:
        try:
            raw_cursor = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            cursor_day, cursor_hash, cursor_id = json.loads(raw_cursor)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cursor_day):
                raise ValueError
            if datetime.fromisoformat(cursor_day).date().isoformat() != cursor_day:
                raise ValueError
            if not re.fullmatch(r"[0-9a-f]{32}", cursor_hash):
                raise ValueError
            cursor_id = str(UUID(cursor_id))
        except (ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=422, detail={"code": "invalid_cursor", "message": "Invalid cursor"})
    sql = MATCHES_SQL
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
            rows = conn.execute(sql, (uid, uid, uid, uid, cursor_day, cursor_day,
                                      cursor_hash, cursor_id, page_size + 1)).fetchall()
    except psycopg.Error as exc:
        exception_name = re.sub(r"[^a-z0-9_]", "_", type(exc).__name__.lower())
        logger.error(
            "matches_query_failed",
            extra={"event": f"matches_query_failed_{exception_name}"},
        )
        raise HTTPException(status_code=503, detail={"code":"MATCH_STORAGE_UNAVAILABLE","message":"Matches unavailable"}) from exc

    has_more = len(rows) > page_size and bool(rows and rows[0][9])
    visible_rows = rows[:page_size] if rows and rows[0][9] else rows
    next_cursor = None
    if has_more and visible_rows:
        last = visible_rows[-1]
        token = json.dumps([last[13], last[14], str(last[0])], separators=(",", ":")).encode()
        next_cursor = urlsafe_b64encode(token).decode().rstrip("=")
    perfect=[]; ranked=[]; explore=[]
    for row in visible_rows:
        listing={"id":str(row[0]),"title":row[1],"rent_amount":str(row[2]),"point":{"latitude":float(row[3]),"longitude":float(row[4])},"whatsapp":row[5],"created_at":row[6].isoformat(),"photos":[{"id":str(ph['id']),"position":ph['position'],"width":ph['width'],"height":ph['height'],"original_url":_photo_public_url(ph['storage_path']),"thumb_url":_photo_public_url(ph['thumb_path']) if ph['thumb_path'] else None} for ph in row[12]]}
        if row[8]: perfect.append(listing)
        elif row[9]: explore.append(listing)
        else: ranked.append({"listing":listing,"misses":[f"{m['field']}: {m['value']}" for m in row[7] if row[10] == 0 or m["importance"] == "must"]})
    return {"perfect":perfect,"ranked":ranked,"explore":bool(rows and rows[0][9]),"nudge":not rows or all(row[9] for row in rows),"explore_listings":explore,"next_cursor":next_cursor}


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
            photos = _listing_photos_json(conn, str(listing_id)) if row is not None else []
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail={"code": "listing_storage_unavailable", "message": "Listing unavailable"}) from exc
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "listing_not_found", "message": "Listing not found"})
    listing = _listing_result(row)
    listing["photos"] = photos
    return listing


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
