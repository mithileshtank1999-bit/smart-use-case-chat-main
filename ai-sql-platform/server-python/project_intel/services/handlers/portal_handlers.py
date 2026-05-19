from __future__ import annotations

import json

from project_intel.data.db_access import fetch_rows_sqlalchemy, make_json_safe
from project_intel.services.general_sql_service import (
    enforce_row_limit,
    generate_sql_any_table,
    is_safe_readonly_sql,
)

HandlerResult = dict | None

# (keyword, table-name hint passed to the SQL generator)
_PATTERNS: list[tuple[str, str]] = [
    ("my portal request summary report", "portal_requests or service_requests or requests"),
    ("my portal request summary", "portal_requests or service_requests or requests"),
    ("travel desk summary report", "travel_requests or traveldesk or travel_desk"),
    ("travel desk request summary", "travel_requests or traveldesk or travel_desk"),
    ("help desk-it request summary report", "helpdesk or it_requests or help_desk"),
    ("help desk it request summary report", "helpdesk or it_requests or help_desk"),
    ("help desk-it request summary", "helpdesk or it_requests or help_desk"),
    ("help desk it request summary", "helpdesk or it_requests or help_desk"),
]


def handle(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes portal / travel desk / help desk use cases via AI SQL generation."""
    hint = _match(lower)
    if not hint:
        return None
    return _run_query(text, hint)


def _match(lower: str) -> str | None:
    for keyword, hint in _PATTERNS:
        if keyword in lower:
            return hint
    return None


def _run_query(user_msg: str, table_hint: str) -> dict:
    enriched = (
        f"{user_msg}\n\n"
        f"[Hint: look for a table named one of: {table_hint}. "
        f"If none exist, use the closest matching table in the schema.]"
    )
    sql = generate_sql_any_table(enriched)
    if not sql or not is_safe_readonly_sql(sql):
        return {
            "handled": True,
            "message": (
                "Could not generate a safe query for this request. "
                f"Ensure one of these tables exists in your database: `{table_hint}`."
            ),
        }

    sql = enforce_row_limit(sql, limit=100)
    try:
        rows_raw = fetch_rows_sqlalchemy(sql) or []
        rows = make_json_safe([r for r in rows_raw if isinstance(r, dict)])
    except Exception as exc:
        return {
            "handled": True,
            "message": (
                f"Query executed but returned an error: `{exc}`.\n\n"
                f"Ensure the relevant table (`{table_hint}`) exists and DB_SCHEMA is correct."
            ),
        }

    if not rows:
        return {"handled": True, "message": f"No records found. (SQL: `{sql}`)"}

    preview = rows[:20]
    payload = json.dumps(preview, ensure_ascii=False, indent=2)
    more = "" if len(rows) <= 20 else f"\n\nShowing 20 of {len(rows)} rows."
    return {"handled": True, "message": f"```json\n{payload}\n```{more}"}
