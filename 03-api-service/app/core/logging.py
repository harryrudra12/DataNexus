"""
DataNexus Era 3 — Structured Logging
JSON logs in production. Human-readable in dev. Correlation IDs everywhere.
"""
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict

import structlog
from structlog.types import EventDict, Processor

from .config import get_settings


# ─── Context vars for request tracking ────────────────────────
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var:    ContextVar[str] = ContextVar("user_id",    default="")
tenant_id_var:  ContextVar[str] = ContextVar("tenant_id",  default="")


def add_request_context(_, __, event_dict: EventDict) -> EventDict:
    """Inject request_id, user_id, tenant_id into every log line."""
    if rid := request_id_var.get():
        event_dict["request_id"] = rid
    if uid := user_id_var.get():
        event_dict["user_id"]    = uid
    if tid := tenant_id_var.get():
        event_dict["tenant_id"]  = tid
    return event_dict


def add_app_context(_, __, event_dict: EventDict) -> EventDict:
    """Add static app metadata."""
    settings = get_settings()
    event_dict["service"]     = "datanexus-api"
    event_dict["version"]     = settings.app_version
    event_dict["environment"] = settings.app_env
    return event_dict


def configure_logging() -> None:
    """Initialize structured logging once at app startup."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Pre-processors run before format-specific processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_app_context,
        add_request_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # In production, emit JSON. In development, color-formatted KV.
    if settings.is_production:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet down noisy libraries
    for noisy in ["uvicorn.access", "asyncio", "urllib3"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a logger anywhere in the app."""
    return structlog.get_logger(name)


def new_request_id() -> str:
    """Generate a fresh correlation ID for an incoming request."""
    return uuid.uuid4().hex
