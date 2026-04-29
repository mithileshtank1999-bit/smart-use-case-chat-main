from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import (
    DB_WRITE_ALLOWED_COLS,
    PROJECT_ACCOUNT_NAME_COL,
    PROJECT_END_DATE_COL,
    PROJECT_GO_LIVE_COL,
    PROJECT_ID_COL,
    PROJECT_NAME_COL,
    PROJECT_PM_COL,
    PROJECT_PORTFOLIO_NAME_COL,
    PROJECT_PORTFOLIO_OWNER_COL,
    PROJECT_START_DATE_COL,
    PROJECT_STATUS_COL,
    PROJECT_TABLE,
)


def get_db_config():
    db_type = (os.getenv("DB_TYPE", "sqlserver") or "sqlserver").strip().lower()
    return {
        "db_type": db_type,
        "host": os.getenv("DB_HOST", ""),
        "port": int(os.getenv("DB_PORT", "5432" if db_type == "postgres" else "1433")),
        "database_name": os.getenv("DB_NAME", ""),
        "username": os.getenv("DB_USER", ""),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def get_project_table_name() -> str:
    return PROJECT_TABLE


def _resolve_column(configured: str, fallbacks: list[str]) -> str:
    configured = (configured or "").strip()
    available = set(get_project_columns() or [])
    if configured and configured.lower() in available:
        return configured.lower()
    for candidate in fallbacks:
        if candidate.lower() in available:
            return candidate.lower()
    # Return configured (or first fallback) even if it doesn't exist; callers may handle errors.
    return (configured or (fallbacks[0] if fallbacks else "")).lower()


def get_project_id_column() -> str:
    return _resolve_column(PROJECT_ID_COL, ["projectid", "project_id", "id"])


def get_project_name_column() -> str:
    return _resolve_column(PROJECT_NAME_COL, ["projectname", "project_name", "name"])


def get_project_status_column() -> str:
    return _resolve_column(PROJECT_STATUS_COL, ["statuscode", "status", "statusid", "statuscodeid"])


def get_project_go_live_column() -> str:
    return _resolve_column(PROJECT_GO_LIVE_COL, ["enddate", "go_live_date", "go_live", "golive", "end_date"])


def get_project_start_date_column() -> str:
    return _resolve_column(PROJECT_START_DATE_COL, ["startdate", "start_date"])


def get_project_end_date_column() -> str:
    return _resolve_column(PROJECT_END_DATE_COL, ["enddate", "end_date"])


def get_project_account_name_column() -> str:
    return _resolve_column(PROJECT_ACCOUNT_NAME_COL, ["companyname", "account_name", "accountname"])


def get_project_portfolio_name_column() -> str:
    return _resolve_column(PROJECT_PORTFOLIO_NAME_COL, ["portfolioid", "portfolio_name", "portfolio"])


def get_project_portfolio_owner_column() -> str:
    return _resolve_column(PROJECT_PORTFOLIO_OWNER_COL, ["ownerid", "portfolio_owner", "owner"])


def get_project_pm_column() -> str:
    return _resolve_column(PROJECT_PM_COL, ["assigntoname", "assigntoid", "project_manager", "pm"])


def normalize_project_row(row: dict) -> dict:
    """
    Normalize DB column names to the stable API keys used by the UI.
    This allows DB schemas like `projectid` while keeping `project_id` in responses.
    """
    if not isinstance(row, dict):
        return row

    normalized = dict(row)
    # Use an ordered list (not a dict) so the same underlying column can map to
    # multiple stable keys (e.g. `enddate` -> both `end_date` and `go_live_date`).
    mappings: list[tuple[str, str]] = [
        (get_project_id_column(), "project_id"),
        (get_project_name_column(), "project_name"),
        (get_project_status_column(), "status"),
        # If your schema doesn't have a dedicated go-live column, point DB_PROJECT_GO_LIVE_COL to enddate.
        (get_project_go_live_column(), "go_live_date"),
        (get_project_start_date_column(), "start_date"),
        (get_project_end_date_column(), "end_date"),
        (get_project_account_name_column(), "account_name"),
        (get_project_portfolio_name_column(), "portfolio_name"),
        (get_project_portfolio_owner_column(), "portfolio_owner"),
        (get_project_pm_column(), "project_manager"),
    ]

    for actual_col, stable_key in mappings:
        if stable_key in normalized and normalized.get(stable_key) not in (None, ""):
            continue
        if actual_col in normalized and normalized.get(actual_col) not in (None, ""):
            normalized[stable_key] = normalized.get(actual_col)
            continue
        # Case-insensitive fallback.
        actual_lower = str(actual_col).lower()
        for key in row.keys():
            if str(key).lower() == actual_lower and row.get(key) not in (None, ""):
                normalized[stable_key] = row.get(key)
                break

    return normalized


def _allowed_write_columns() -> set[str]:
    """
    Restrict which columns can be updated via API writes.
    Use `DB_WRITE_ALLOWED_COLS` to override.
    """
    if DB_WRITE_ALLOWED_COLS:
        return set(DB_WRITE_ALLOWED_COLS)
    # Conservative defaults based on the column list the user provided.
    return {
        "detail",
        "statuscode",
        "statusid",
        "statuscodeid",
        "ownerid",
        "assigntoid",
        "assigntoname",
        "assigntocode",
        "laststatuschangedon",
        "lastmodifiedby",
        "lastmodifiedon",
        "isescalated",
        "escalatedon",
        "duration",
        "billable",
        "portfolioid",
        "accountid",
        "companyname",
        "opportunityid",
        "parentid",
        "relatedtoid",
        "relatedtoname",
        "relatedtotypeid",
    }


def patch_project_row(project_id: str, updates: dict) -> dict:
    """
    Update allowed fields for a single project row and return the updated row.
    This is designed for Postgres (uses RETURNING), but will also work for SQL Server
    by performing a follow-up SELECT.
    """
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("project_id is required")
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates must be a non-empty object")

    table_name = get_project_table_name()
    id_col = get_project_id_column()
    available = set(get_project_columns())
    allowed = _allowed_write_columns()
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()

    # Normalize update keys to lowercase to match `get_project_columns()` output.
    cleaned: dict[str, object] = {}
    for key, value in updates.items():
        col = str(key or "").strip().lower()
        if not col or col == id_col.lower():
            continue
        if col not in available:
            continue
        if col not in allowed:
            continue
        cleaned[col] = value

    if not cleaned:
        raise ValueError("No allowed columns to update for this request")

    set_sql = ", ".join([f"{col} = :{col}" for col in cleaned.keys()])
    params = dict(cleaned)
    params["pid"] = project_id

    db = SessionLocal()
    try:
        if db_type == "postgres":
            result = db.execute(
                text(f"UPDATE {table_name} SET {set_sql} WHERE {id_col} = :pid RETURNING *"),
                params,
            )
            row = result.fetchone()
            db.commit()
            return normalize_project_row(make_json_safe(dict(row._mapping)) if row else {})

        # SQL Server fallback: update then select.
        db.execute(text(f"UPDATE {table_name} SET {set_sql} WHERE {id_col} = :pid"), params)
        db.commit()
        result = db.execute(text(f"SELECT * FROM {table_name} WHERE {id_col} = :pid"), {"pid": project_id})
        row = result.fetchone()
        return normalize_project_row(make_json_safe(dict(row._mapping)) if row else {})
    finally:
        db.close()


async def query_postgres(sql: str, params: list | None = None):
    import asyncpg

    cfg = get_db_config()
    conn = await asyncpg.connect(
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database_name"],
        user=cfg["username"],
        password=cfg["password"],
        ssl="prefer",
        timeout=10,
    )
    try:
        pg_sql = re.sub(r"@p(\d+)", lambda match: f"${int(match.group(1)) + 1}", sql)
        rows = await conn.fetch(pg_sql, *(params or []))
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def query_sqlserver(sql: str, params: list | None = None):
    import pyodbc

    cfg = get_db_config()
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={cfg['host']};"
        f"DATABASE={cfg['database_name']};"
        f"UID={cfg['username']};"
        f"PWD={cfg['password']}"
    )
    cursor = conn.cursor()
    # Convert `@p0`, `@p1`, ... placeholders to `?` for pyodbc.
    sql_prepared = re.sub(r"@p\d+", "?", sql)
    cursor.execute(sql_prepared, *(params or []))
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


async def query(sql: str, params: list | None = None):
    cfg = get_db_config()
    if cfg["db_type"] == "postgres":
        return await query_postgres(sql, params)
    return await query_sqlserver(sql, params)


def make_json_safe(value):
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def fetch_rows_sqlalchemy(sql: str, params: dict | None = None):
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params or {})
        rows = [dict(row._mapping) for row in result]
        return make_json_safe(rows)
    finally:
        db.close()


PROJECT_COLUMNS_AVAILABLE: list[str] | None = None


def load_projects_columns() -> list[str]:
    table_name = get_project_table_name()
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                SELECT LOWER(COLUMN_NAME) AS column_name
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
                """
            ),
            {"table_name": table_name},
        )
        columns = [str(row[0]).strip() for row in result.fetchall() if row and row[0]]
        if columns:
            return columns
    except Exception:
        pass
    finally:
        db.close()

    # Fallback: inspect a sample row (works even if INFORMATION_SCHEMA is restricted).
    try:
        cfg = get_db_config()
        db_type = (cfg.get("db_type") or "sqlserver").strip().lower()
        sample_sql = f"SELECT * FROM {table_name} LIMIT 1" if db_type == "postgres" else f"SELECT TOP 1 * FROM {table_name}"
        sample = fetch_rows_sqlalchemy(sample_sql)
        if isinstance(sample, list) and sample and isinstance(sample[0], dict):
            return [str(key).lower() for key in sample[0].keys()]
    except Exception:
        pass

    return ["project_id", "project_name", "status"]


def get_project_columns() -> list[str]:
    global PROJECT_COLUMNS_AVAILABLE
    if PROJECT_COLUMNS_AVAILABLE is None or len(PROJECT_COLUMNS_AVAILABLE) == 0:
        PROJECT_COLUMNS_AVAILABLE = load_projects_columns()
    return PROJECT_COLUMNS_AVAILABLE


def get_project_table_columns() -> list[str]:
    cols = set(get_project_columns())
    preferred = [
        get_project_id_column(),
        get_project_name_column(),
        get_project_status_column(),
        get_project_go_live_column(),
        get_project_portfolio_name_column(),
        get_project_portfolio_owner_column(),
        get_project_account_name_column(),
        get_project_pm_column(),
    ]
    available = [c for c in preferred if c in cols]
    if not available:
        return [get_project_id_column(), get_project_name_column(), get_project_status_column()]
    ordered = []
    for key in [get_project_id_column(), get_project_name_column()]:
        if key in cols and key in available and key not in ordered:
            ordered.append(key)
    for c in available:
        if c not in ordered:
            ordered.append(c)
    return ordered


def build_search_sql(filters: dict | None):
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    table_name = get_project_table_name()
    sql = f"SELECT * FROM {table_name} WHERE 1=1"
    params: list = []
    param_index = 0
    available_cols = set(get_project_columns())

    field_to_column = {
        "project_id": get_project_id_column(),
        "project_name": get_project_name_column(),
        "status": get_project_status_column(),
        "go_live_date": get_project_go_live_column(),
    }

    if not filters:
        return sql + f" ORDER BY {get_project_id_column()}", params

    for field, operator in [
        ("project_id", "="),
        ("project_name", "LIKE"),
        ("account_name", "LIKE"),
        ("account_id", "="),
        ("portfolio_name", "LIKE"),
        ("status", "LIKE"),
        ("project_manager", "LIKE"),
    ]:
        db_col = field_to_column.get(field, field)
        if db_col not in available_cols:
            continue
        value = filters.get(field)
        if value:
            effective_op = operator
            if db_type == "postgres" and operator == "LIKE":
                effective_op = "ILIKE"
            sql += f" AND {db_col} {effective_op} @p{param_index}"
            params.append(f"%{value}%" if operator in ("LIKE", "ILIKE") else value)
            param_index += 1

    sql += f" ORDER BY {get_project_id_column()}"
    return sql, params


async def fetch_schema_text() -> str:
    table_name = get_project_table_name()
    db = SessionLocal()
    result = db.execute(
        text(
            """
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    db.close()

    schema_text = f"Table: {table_name}\nColumns:\n"
    for row in result:
        schema_text += f"- {row[0]} ({row[1]})\n"
    return schema_text
