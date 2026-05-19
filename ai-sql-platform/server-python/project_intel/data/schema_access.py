from __future__ import annotations

import os

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA


def _safe_identifier(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not all(ch.isalnum() or ch == "_" for ch in value):
        return ""
    return value


def schema_search_path() -> list[str]:
    raw = (os.getenv("DB_SEARCH_PATH", "") or "").strip()
    schemas = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
    preferred = _safe_identifier(DB_SCHEMA or "")
    if preferred:
        schemas = [preferred] + [s for s in schemas if s != preferred]
    if "public" not in schemas:
        schemas.append("public")
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in schemas:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def list_tables(*, max_tables: int = 80) -> list[dict]:
    """
    Returns [{schema, table}] for the configured schema search path.
    Uses information_schema so it works for Postgres and SQL Server.
    """
    schemas = schema_search_path()
    if not schemas:
        return []

    safe_max = max(1, min(int(max_tables or 80), 500))
    placeholders = ", ".join([f":s{i}" for i in range(len(schemas))])
    params = {f"s{i}": schemas[i] for i in range(len(schemas))}

    sql = f"""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema IN ({placeholders})
        ORDER BY table_schema, table_name
    """

    db = SessionLocal()
    try:
        rows = db.execute(text(sql), params).fetchall()
        out: list[dict] = []
        for r in rows[:safe_max]:
            if not r:
                continue
            out.append({"schema": str(r[0]), "table": str(r[1])})
        return out
    finally:
        db.close()


def list_columns(*, schema: str, table: str, max_cols: int = 80) -> list[dict]:
    safe_schema = _safe_identifier(schema)
    safe_table = _safe_identifier(table)
    if not safe_schema or not safe_table:
        return []
    safe_max = max(1, min(int(max_cols or 80), 300))

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                ORDER BY ordinal_position
                """
            ),
            {"schema": safe_schema, "table": safe_table},
        ).fetchall()
        out: list[dict] = []
        for r in rows[:safe_max]:
            if not r:
                continue
            out.append(
                {
                    "name": str(r[0]),
                    "type": str(r[1]),
                    "nullable": (str(r[2] or "").upper() == "YES"),
                    "position": int(r[3]) if r[3] is not None else None,
                }
            )
        return out
    finally:
        db.close()


def build_schema_overview_text(*, max_tables: int = 40, max_cols: int = 25) -> str:
    """
    Produces an LLM-friendly schema summary across multiple tables.
    Keep this intentionally compact to avoid huge prompts.
    """
    safe_max_tables = max(1, min(int(max_tables or 40), 200))
    safe_max_cols = max(1, min(int(max_cols or 25), 100))

    tables = list_tables(max_tables=safe_max_tables)
    if not tables:
        return "No tables discovered via information_schema for the configured DB_SCHEMA/DB_SEARCH_PATH."

    lines: list[str] = []
    for t in tables[:safe_max_tables]:
        schema = str(t.get("schema") or "")
        table = str(t.get("table") or "")
        cols = list_columns(schema=schema, table=table, max_cols=safe_max_cols)
        col_parts: list[str] = []
        for c in cols[:safe_max_cols]:
            name = str(c.get("name") or "")
            dtype = str(c.get("type") or "")
            if name:
                col_parts.append(f"{name} ({dtype})" if dtype else name)
        lines.append(f"Table: {schema}.{table}")
        if col_parts:
            lines.append("Columns: " + ", ".join(col_parts))
        lines.append("")
    return "\n".join(lines).strip()

