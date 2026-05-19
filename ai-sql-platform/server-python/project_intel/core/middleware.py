from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from project_intel.core.logging_config import request_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Reads X-Request-ID from the incoming request (or generates one).
    Sets it in the async context var so every log line carries it.
    Echoes it back in the response header.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = req_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Catches any unhandled exception and returns a structured JSON error response
    instead of a raw 500 / stack trace.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            req_id = request_id_var.get("-")
            logger.exception("Unhandled error during request", extra={"path": request.url.path})
            return JSONResponse(
                {
                    "ok": False,
                    "error_code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "request_id": req_id,
                },
                status_code=500,
            )
