"""Privacy-preserving JSON logging and optional Sentry setup."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from rentra_api.config import get_settings

_EVENT_RE = re.compile(r"^[a-z0-9_]+$")
_FIELDS = (
    "ts", "level", "service", "env", "version", "request_id", "route_template",
    "method", "status", "latency_ms", "user_id", "event",
)


class JsonFormatter(logging.Formatter):
    """Emit a strict, allow-listed JSON record."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        event = getattr(record, "event", "log_event")
        if not isinstance(event, str) or not _EVENT_RE.fullmatch(event):
            event = "invalid_event"
        values: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "service": "rentra_api",
            "env": settings.ENV,
            "version": settings.SERVICE_VERSION,
            "request_id": getattr(record, "request_id", None),
            "route_template": getattr(record, "route_template", None),
            "method": getattr(record, "method", None),
            "status": getattr(record, "status", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "user_id": getattr(record, "user_id", None),
            "event": event,
        }
        return json.dumps({key: values[key] for key in _FIELDS}, separators=(",", ":"))


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    event.pop("request", None)
    event.pop("user", None)
    event.pop("server_name", None)
    for exception in event.get("exception", {}).get("values", []):
        exception["value"] = exception.get("type", "Exception")
    return event


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    for name in ("uvicorn", "uvicorn.error"):
        log = logging.getLogger(name)
        log.handlers[:] = [handler]
        log.propagate = False
        log.setLevel(settings.LOG_LEVEL.upper())
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            send_default_pii=False,
            include_local_variables=False,
            max_breadcrumbs=0,
            before_send=_before_send,
        )
