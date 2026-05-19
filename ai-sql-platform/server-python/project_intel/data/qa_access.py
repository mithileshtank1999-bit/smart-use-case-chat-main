from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA
from project_intel.data.db_access import get_db_config, make_json_safe


def _safe_identifier(value: str, default: str) -> str:
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
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _qualified(table: str, schema: str) -> str:
    return f"{schema}.{table}"


def _resolve_column(available: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        c = (candidate or "").strip().lower()
        if not c:
            continue
        if c in available:
            return c
    return None


def _load_table_columns(table: str) -> tuple[str | None, list[str]]:
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
            rows = (
                db.execute(
                    text(
                        """
                        SELECT LOWER(column_name) AS column_name
                        FROM information_schema.columns
                        WHERE table_schema = :schema AND table_name = :table
                        ORDER BY ordinal_position
                        """
                    ),
                    {"schema": schema, "table": table},
                )
                .fetchall()
            )
            if rows:
                return schema, [str(r[0]) for r in rows if r and r[0]]
        return None, []
    except Exception:
        return None, []
    finally:
        db.close()


def _select_with_limit(sql: str, *, limit: int) -> str:
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    safe_limit = max(1, min(int(limit or 50), 500))
    if db_type == "postgres":
        return f"{sql} LIMIT {safe_limit}"
    # SQL Server
    sql = sql.strip()
    if sql.lower().startswith("select "):
        return f"SELECT TOP {safe_limit} {sql[7:]}"
    return sql


@dataclass(frozen=True)
class QaQueryResult:
    ok: bool
    error: str | None = None
    table: str | None = None
    schema: str | None = None
    rows: list[dict] | None = None
    count: int = 0
    note: str | None = None


def _fetch_rows(sql: str, params: dict) -> list[dict]:
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params)
        return make_json_safe([dict(row._mapping) for row in result])
    finally:
        db.close()


def get_case_rows(
    *,
    stage: str | None = None,
    case_id: str | None = None,
    module_name: str | None = None,
    journey_name: str | None = None,
    project_name: str | None = None,
    limit: int = 50,
) -> QaQueryResult:
    """
    Best-effort read-only access for "case" use cases.

    Requires a configured table name (env `DB_QA_CASE_TABLE`, default `cases`).
    The function introspects columns and only applies filters where matching columns exist.
    """
    table = _safe_identifier(os.getenv("DB_QA_CASE_TABLE", ""), "cases")
    schema, cols = _load_table_columns(table)
    if not schema or not cols:
        return QaQueryResult(
            ok=False,
            error="case_table_not_found",
            table=table,
            schema=schema,
            note="Configure DB_QA_CASE_TABLE (and optionally DB_SCHEMA/DB_SEARCH_PATH) to point at your cases table.",
        )

    available = {c.lower() for c in cols}
    id_col = _resolve_column(available, ["case_id", "caseid", "id", "ticket_id", "ticketid"])
    module_col = _resolve_column(available, ["module_name", "modulename", "module"])
    journey_col = _resolve_column(available, ["journey_name", "journeyname", "journey"])
    project_col = _resolve_column(available, ["project_name", "projectname", "project"])
    stage_col = _resolve_column(available, ["stage", "environment", "test_stage"])

    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    where: list[str] = []
    params: dict = {}

    if case_id and id_col:
        where.append(f"{id_col} = :case_id")
        params["case_id"] = case_id
    def _like(col: str, param: str) -> str:
        if db_type == "postgres":
            return f"{col} ILIKE :{param}"
        return f"LOWER({col}) LIKE LOWER(:{param})"

    if module_name and module_col:
        where.append(_like(module_col, "module_name"))
        params["module_name"] = f"%{module_name}%"
    if journey_name and journey_col:
        where.append(_like(journey_col, "journey_name"))
        params["journey_name"] = f"%{journey_name}%"
    if project_name and project_col:
        where.append(_like(project_col, "project_name"))
        params["project_name"] = f"%{project_name}%"
    if stage and stage_col:
        where.append(_like(stage_col, "stage"))
        params["stage"] = f"%{stage}%"

    qualified = _qualified(table, schema)
    sql = f"SELECT * FROM {qualified}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql = _select_with_limit(sql, limit=limit)

    try:
        rows = _fetch_rows(sql, params)
        return QaQueryResult(ok=True, table=table, schema=schema, rows=rows, count=len(rows or []))
    except Exception as exc:
        return QaQueryResult(ok=False, error=str(exc), table=table, schema=schema)


def get_test_case_rows(
    *,
    stage: str | None = None,
    test_case_id: str | None = None,
    module_name: str | None = None,
    journey_name: str | None = None,
    project_name: str | None = None,
    limit: int = 50,
) -> QaQueryResult:
    """
    Best-effort read-only access for "test case" use cases.

    Requires a configured table name (env `DB_QA_TESTCASE_TABLE`, default `testcases`).
    """
    table = _safe_identifier(os.getenv("DB_QA_TESTCASE_TABLE", ""), "testcases")
    schema, cols = _load_table_columns(table)
    if not schema or not cols:
        return QaQueryResult(
            ok=False,
            error="testcase_table_not_found",
            table=table,
            schema=schema,
            note="Configure DB_QA_TESTCASE_TABLE (and optionally DB_SCHEMA/DB_SEARCH_PATH) to point at your testcases table.",
        )

    available = {c.lower() for c in cols}
    id_col = _resolve_column(available, ["test_case_id", "testcase_id", "testcaseid", "id"])
    module_col = _resolve_column(available, ["module_name", "modulename", "module"])
    journey_col = _resolve_column(available, ["journey_name", "journeyname", "journey"])
    project_col = _resolve_column(available, ["project_name", "projectname", "project"])
    stage_col = _resolve_column(available, ["stage", "environment", "test_stage"])

    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    where: list[str] = []
    params: dict = {}

    if test_case_id and id_col:
        where.append(f"{id_col} = :test_case_id")
        params["test_case_id"] = test_case_id
    def _like(col: str, param: str) -> str:
        if db_type == "postgres":
            return f"{col} ILIKE :{param}"
        return f"LOWER({col}) LIKE LOWER(:{param})"

    if module_name and module_col:
        where.append(_like(module_col, "module_name"))
        params["module_name"] = f"%{module_name}%"
    if journey_name and journey_col:
        where.append(_like(journey_col, "journey_name"))
        params["journey_name"] = f"%{journey_name}%"
    if project_name and project_col:
        where.append(_like(project_col, "project_name"))
        params["project_name"] = f"%{project_name}%"
    if stage and stage_col:
        where.append(_like(stage_col, "stage"))
        params["stage"] = f"%{stage}%"

    qualified = _qualified(table, schema)
    sql = f"SELECT * FROM {qualified}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql = _select_with_limit(sql, limit=limit)

    try:
        rows = _fetch_rows(sql, params)
        return QaQueryResult(ok=True, table=table, schema=schema, rows=rows, count=len(rows or []))
    except Exception as exc:
        return QaQueryResult(ok=False, error=str(exc), table=table, schema=schema)
