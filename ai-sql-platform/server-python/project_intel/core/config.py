from __future__ import annotations

import os
from dotenv import load_dotenv
from pathlib import Path


# Load environment variables early for the API process (from server-python/.env).
_base_dir = Path(__file__).resolve().parents[2]
load_dotenv(_base_dir / ".env")


API_TITLE = os.getenv("API_TITLE", "Project Intelligence API")

# UI runs on Vite (commonly 5173; some setups use 8080). Keep backwards-compatible defaults.
_default_origins = ",".join(
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
)
CORS_ALLOW_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", _default_origins).split(",") if origin.strip()]

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")


def _safe_identifier(value: str, default: str) -> str:
    value = (value or "").strip()
    if not value:
        return default
    # Allow only simple identifiers to prevent SQL injection via config.
    if not all(ch.isalnum() or ch == "_" for ch in value):
        return default
    return value


PROJECT_TABLE = _safe_identifier(os.getenv("DB_PROJECT_TABLE", ""), "projects")

# Optional column remapping for deployments where column names differ.
PROJECT_ID_COL = _safe_identifier(os.getenv("DB_PROJECT_ID_COL", ""), "project_id")
PROJECT_NAME_COL = _safe_identifier(os.getenv("DB_PROJECT_NAME_COL", ""), "project_name")
PROJECT_STATUS_COL = _safe_identifier(os.getenv("DB_PROJECT_STATUS_COL", ""), "status")
PROJECT_GO_LIVE_COL = _safe_identifier(os.getenv("DB_PROJECT_GO_LIVE_COL", ""), "go_live_date")

# Timeline and context (optional)
PROJECT_START_DATE_COL = _safe_identifier(os.getenv("DB_PROJECT_START_DATE_COL", ""), "start_date")
PROJECT_END_DATE_COL = _safe_identifier(os.getenv("DB_PROJECT_END_DATE_COL", ""), "end_date")
PROJECT_ACCOUNT_NAME_COL = _safe_identifier(os.getenv("DB_PROJECT_ACCOUNT_NAME_COL", ""), "account_name")
PROJECT_PORTFOLIO_NAME_COL = _safe_identifier(os.getenv("DB_PROJECT_PORTFOLIO_NAME_COL", ""), "portfolio_name")
PROJECT_PORTFOLIO_OWNER_COL = _safe_identifier(os.getenv("DB_PROJECT_PORTFOLIO_OWNER_COL", ""), "portfolio_owner")
PROJECT_PM_COL = _safe_identifier(os.getenv("DB_PROJECT_PM_COL", ""), "project_manager")

# Comma-separated list of columns that are allowed to be updated via the API write endpoint.
# If empty, a conservative default is used.
DB_WRITE_ALLOWED_COLS = [c.strip().lower() for c in os.getenv("DB_WRITE_ALLOWED_COLS", "").split(",") if c.strip()]

# Default DB schema (used for timesheet/employee lookups in this app).
DB_SCHEMA = _safe_identifier(os.getenv("DB_SCHEMA", "dbo"), "dbo")

# Timesheet: optional comma-separated list of allowed/commonly-used "items"
# (stored in dbo.timesheet.relatedtoname in this app's default mapping).
TIMESHEET_ITEMS = [v.strip() for v in os.getenv("TIMESHEET_ITEMS", "").split(",") if v.strip()]

# ---------------------------------------------------------------------------
# n8n Automation integration
# ---------------------------------------------------------------------------
N8N_BASE_URL = (os.getenv("N8N_BASE_URL") or "").rstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY") or ""
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET") or ""
