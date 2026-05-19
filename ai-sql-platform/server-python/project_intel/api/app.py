from __future__ import annotations

from contextlib import asynccontextmanager
import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from project_intel.core.config import API_TITLE, CORS_ALLOW_ORIGINS
from project_intel.core.logging_config import configure_logging
from project_intel.core.middleware import (
    ErrorHandlerMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
)
from project_intel.core.rate_limit import limiter
from project_intel.api.routes import router
from project_intel.services.rag_service import ensure_rag_index

# Configure structured logging as early as possible.
configure_logging()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if os.getenv("RAG_PREWARM", "").strip().lower() in ("1", "true", "yes", "y"):
            try:
                await asyncio.to_thread(ensure_rag_index)
            except Exception:
                pass
        yield

    app = FastAPI(title=API_TITLE, lifespan=lifespan)

    # Rate limiter state (slowapi)
    app.state.limiter = limiter
    try:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    except ImportError:
        pass  # slowapi not installed — limits are no-ops

    # Middleware is applied in LIFO order — ErrorHandler must wrap everything.
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS or ["http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
