from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncGenerator
from urllib.parse import urljoin
import re
from uuid import UUID

import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rentra_api.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate required settings on startup."""
    get_settings()
    yield


app = FastAPI(title="Rentra API", version="0.1.0", lifespan=lifespan)


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

    @field_validator("whatsapp")
    @classmethod
    def normalize_whatsapp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        compact = "".join(value.strip().split()).replace("-", "").replace("(", "").replace(")", "")
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
    if fields:
        assignments = ", ".join(f"{field} = %s" for field in sorted(fields))
        values = [getattr(update, field) for field in sorted(fields)]
        uid = str(profile["id"])
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true)", (uid,))
                cur.execute(
                    f"UPDATE app.profiles SET {assignments} WHERE id = %s RETURNING id, display_name, whatsapp, deletion_requested_at, created_at",
                    (*values, uid),
                )
                row = cur.fetchone()
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
