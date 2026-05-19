"""
FastAPI entrypoint used by `uvicorn main:app`.

The full API implementation lives under `project_intel` (routers, services, DB access).
This module keeps a stable import path and hosts a small local-only endpoint for
persisting DB connection settings (`/api/db-connections`) used by the Settings page.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import dotenv_values, set_key
from fastapi import Body, HTTPException, Request
from pydantic import BaseModel, Field

from project_intel.api.app import create_app

app = create_app()

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


class DbConnectionPayload(BaseModel):
    id: str | None = None
    connection_name: str = Field(default="Default")
    db_type: str = Field(default="sqlserver")
    host: str = Field(default="")
    port: int = Field(default=1433)
    database_name: str = Field(default="")
    username: str = Field(default="")
    encrypted_password: str | None = None
    is_active: bool | int | None = True


def _ensure_env_file_exists() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.write_text("", encoding="utf-8")


def _get_or_create_connection_id() -> str:
    existing = (os.getenv("DB_CONNECTION_ID", "") or "").strip()
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    _ensure_env_file_exists()
    set_key(str(ENV_PATH), "DB_CONNECTION_ID", new_id)
    os.environ["DB_CONNECTION_ID"] = new_id
    return new_id


def _assert_local_db_settings_allowed(request: Request) -> None:
    """
    These endpoints exist only to support local/dev usage (Settings page persisting DB_* values).
    In production, persisting secrets via an unauthenticated HTTP endpoint is unsafe.
    """
    enabled = (os.getenv("ENABLE_LOCAL_DB_SETTINGS") or "").strip().lower() in ("1", "true", "yes", "y")
    if not enabled:
        # Hide the endpoint completely unless explicitly enabled.
        raise HTTPException(status_code=404, detail="Not found")

    client_host = getattr(getattr(request, "client", None), "host", "") or ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/api/db-connections")
async def get_db_connections(request: Request):
    """
    Local-only helper used by the Settings page when running without Supabase.
    Reads connection info from `server-python/.env` / process env vars.
    """
    _assert_local_db_settings_allowed(request)
    env = {**dotenv_values(ENV_PATH), **os.environ}
    conn_id = (env.get("DB_CONNECTION_ID") or "").strip() or _get_or_create_connection_id()
    db_type = (env.get("DB_TYPE") or "sqlserver").strip().lower() or "sqlserver"

    data = {
        "id": conn_id,
        "connection_name": (env.get("DB_CONNECTION_NAME") or "Default").strip() or "Default",
        "db_type": db_type,
        "host": (env.get("DB_HOST") or "").strip(),
        "port": int((env.get("DB_PORT") or ("5432" if db_type == "postgres" else "1433")).strip()),
        "database_name": (env.get("DB_NAME") or "").strip(),
        "username": (env.get("DB_USER") or "").strip(),
    }
    # Match the shape expected by `src/pages/Settings.tsx`.
    return {"data": data}


@app.post("/api/db-connections")
async def upsert_db_connections(request: Request, payload: DbConnectionPayload = Body(...)):
    """
    Local-only helper used by the Settings page when running without Supabase.
    Persists DB_* settings to `server-python/.env` and updates process env vars.
    """
    _assert_local_db_settings_allowed(request)
    _ensure_env_file_exists()

    conn_id = (payload.id or "").strip() or _get_or_create_connection_id()
    db_type = (payload.db_type or "sqlserver").strip().lower() or "sqlserver"

    set_key(str(ENV_PATH), "DB_CONNECTION_ID", conn_id)
    set_key(str(ENV_PATH), "DB_CONNECTION_NAME", (payload.connection_name or "Default").strip() or "Default")
    set_key(str(ENV_PATH), "DB_TYPE", db_type)
    set_key(str(ENV_PATH), "DB_HOST", (payload.host or "").strip())
    set_key(str(ENV_PATH), "DB_PORT", str(int(payload.port)))
    set_key(str(ENV_PATH), "DB_NAME", (payload.database_name or "").strip())
    set_key(str(ENV_PATH), "DB_USER", (payload.username or "").strip())

    # Only update password if explicitly provided (supports "edit without retyping password").
    if payload.encrypted_password is not None and str(payload.encrypted_password).strip() != "":
        set_key(str(ENV_PATH), "DB_PASSWORD", str(payload.encrypted_password))
        os.environ["DB_PASSWORD"] = str(payload.encrypted_password)

    # Keep process env in sync so the next `/api/db-proxy` call can use the new values
    # without requiring a full restart (some clients still may need reload).
    os.environ["DB_CONNECTION_ID"] = conn_id
    os.environ["DB_CONNECTION_NAME"] = (payload.connection_name or "Default").strip() or "Default"
    os.environ["DB_TYPE"] = db_type
    os.environ["DB_HOST"] = (payload.host or "").strip()
    os.environ["DB_PORT"] = str(int(payload.port))
    os.environ["DB_NAME"] = (payload.database_name or "").strip()
    os.environ["DB_USER"] = (payload.username or "").strip()

    return {"id": conn_id}
