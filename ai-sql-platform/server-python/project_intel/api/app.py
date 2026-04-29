from __future__ import annotations

from contextlib import asynccontextmanager
import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from project_intel.core.config import API_TITLE, CORS_ALLOW_ORIGINS
from project_intel.api.routes import router
from project_intel.services.rag_service import ensure_rag_index


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Optional pre-warm to reduce first-click latency (embeddings model load can be slow).
        if os.getenv("RAG_PREWARM", "").strip().lower() in ("1", "true", "yes", "y"):
            try:
                await asyncio.to_thread(ensure_rag_index)
            except Exception:
                pass
        yield

    app = FastAPI(title=API_TITLE, lifespan=lifespan)
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
