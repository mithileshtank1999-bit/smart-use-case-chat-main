from __future__ import annotations

import json
import logging
import os
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone

# Thread/async-safe request-ID slot — set by RequestIDMiddleware per request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JSONFormatter(logging.Formatter):
    """Emits one JSON object per log record — structured for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get("-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)
        # Any extra fields passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """
    Call once at startup (from api/app.py).
    Reads LOG_LEVEL (default INFO) and LOG_FORMAT ('json' or 'text') from env.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "json").strip().lower()

    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Silence noisy third-party loggers
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
