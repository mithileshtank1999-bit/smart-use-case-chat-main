from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA
from project_intel.data.db_access import get_db_config, make_json_safe


@dataclass(frozen=True)
class ActionQueryResult:
    ok: bool
    error: str | None = None
    table: str | None = None
    schema: str | None = None
    rows: list[dict] | None = None
    count: int = 0
    note: str | None = None


def _safe_id(value: str, default: str) -> str:
    value = (value or "").strip()
    if not value:
        return default
    if not all(ch.isalnum() or ch == "_" for ch in value):
        return default
    return value


def _schema_search_path() -> list[str]:
    raw = (os.getenv("DB_SEARCH_PATH", "") or "").strip()
    schemas = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
    preferred = (DB_SCHEMA or "").strip()
    if preferred:
        schemas = [preferred] + [s for s in schemas if s != preferred]
    if "public" not in schemas:
        schemas.append("public")
    seen: set[str] = set()
    out: list[str] = []
    for s in schemas:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _load_columns(table: str) -> tuple[str | None, list[str]]:
    table = (table or "").strip()
    if not table:
        return None, []
    schemas = _schema_search_path()
    try:
        db = SessionLocal()
    except Exception:
        return None, []
    try:
        for schema in schemas:
            rows = db.execute(
                text(
                    "SELECT LOWER(column_name) FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
                ),
                {"s": schema, "t": table},
            ).fetchall()
            if rows:
                return schema, [str(r[0]) for r in rows if r and r[0]]
        return None, []
    except Exception:
        return None, []
    finally:
        db.close()


def _resolve(available: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c.lower() in available:
            return c.lower()
    return None


def _like(col: str, param: str) -> str:
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    if db_type == "postgres":
        return f"{col} ILIKE :{param}"
    return f"LOWER({col}) LIKE LOWER(:{param})"


def _with_limit(sql: str, limit: int) -> str:
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    safe = max(1, min(int(limit), 500))
    if db_type == "postgres":
        return f"{sql} LIMIT {safe}"
    s = sql.strip()
    if s.upper().startswith("SELECT "):
        return f"SELECT TOP {safe} {s[7:]}"
    return s


def _fetch(sql: str, params: dict) -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params)
        return make_json_safe([dict(row._mapping) for row in result])
    finally:
        db.close()


def _query_table(
    *,
    table: str,
    fallbacks: list[str],
    env_var: str,
    project_name: str | None,
    module_name: str | None,
    limit: int,
    not_found_note: str,
) -> ActionQueryResult:
    resolved_table = _safe_id(os.getenv(env_var, ""), table)
    schema, cols = _load_columns(resolved_table)

    # Try configured name, then provided default, then fallbacks
    if not schema or not cols:
        for fb in [table] + fallbacks:
            schema, cols = _load_columns(fb)
            if schema and cols:
                resolved_table = fb
                break

    if not schema or not cols:
        return ActionQueryResult(
            ok=False,
            error=f"{resolved_table}_not_found",
            table=resolved_table,
            note=not_found_note,
        )

    available = {c.lower() for c in cols}
    project_col = _resolve(available, ["project_name", "projectname", "project", "projectid"])
    module_col = _resolve(available, ["module_name", "modulename", "module"])
    status_col = _resolve(available, ["status", "statuscode", "state", "statusid"])

    where: list[str] = []
    params: dict = {}

    if project_name and project_col:
        where.append(_like(project_col, "project_name"))
        params["project_name"] = f"%{project_name}%"
    if module_name and module_col:
        where.append(_like(module_col, "module_name"))
        params["module_name"] = f"%{module_name}%"

    qualified = f"{schema}.{resolved_table}"
    sql = f"SELECT * FROM {qualified}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if status_col:
        sql += f" ORDER BY {status_col}"
    sql = _with_limit(sql, limit)

    try:
        rows = _fetch(sql, params)
        return ActionQueryResult(ok=True, table=resolved_table, schema=schema, rows=rows, count=len(rows))
    except Exception as exc:
        return ActionQueryResult(ok=False, error=str(exc), table=resolved_table, schema=schema)


def get_action_point_rows(
    *,
    project_name: str | None = None,
    module_name: str | None = None,
    limit: int = 100,
) -> ActionQueryResult:
    """
    Read-only access for Action Centre Points.
    Configure DB_ACTION_TABLE env var (defaults to 'actionpoints').
    """
    return _query_table(
        table="actionpoints",
        fallbacks=["actions", "action_points", "projectactions"],
        env_var="DB_ACTION_TABLE",
        project_name=project_name,
        module_name=module_name,
        limit=limit,
        not_found_note=(
            "Configure DB_ACTION_TABLE in .env to point at your action points table "
            "(e.g. actionpoints, actions, projectactions)."
        ),
    )


def get_risk_rows(
    *,
    project_name: str | None = None,
    module_name: str | None = None,
    limit: int = 100,
) -> ActionQueryResult:
    """
    Read-only access for project risks.
    Configure DB_RISK_TABLE env var (defaults to 'risks').
    """
    return _query_table(
        table="risks",
        fallbacks=["projectrisks", "project_risks", "riskregister"],
        env_var="DB_RISK_TABLE",
        project_name=project_name,
        module_name=module_name,
        limit=limit,
        not_found_note=(
            "Configure DB_RISK_TABLE in .env to point at your risks table "
            "(e.g. risks, projectrisks, riskregister)."
        ),
    )
