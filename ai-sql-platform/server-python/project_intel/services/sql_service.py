from __future__ import annotations

import re

from project_intel.core.config import OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import (
    get_db_config,
    get_project_columns,
    get_project_end_date_column,
    get_project_go_live_column,
    get_project_id_column,
    get_project_name_column,
    get_project_pm_column,
    get_project_start_date_column,
    get_project_status_column,
    get_project_table_columns,
    get_project_table_name,
)

def schema_text_projects() -> str:
    table_name = get_project_table_name()
    cols = get_project_columns() or ["project_id", "project_name", "status"]
    return f"Table: {table_name}\nColumns: " + ", ".join(cols)


def generate_sql(user_input: str, employee_name: str | None = None):
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    preferred_cols = get_project_table_columns()
    schema_text = schema_text_projects()
    dialect_rule = "Use SQL Server syntax (TOP, not LIMIT)" if db_type != "postgres" else "Use PostgreSQL syntax (LIMIT, not TOP)"
    table_name = get_project_table_name()
    pm_col = get_project_pm_column()
    employee_name = (employee_name or "").strip() or None
    employee_context = ""
    if employee_name:
        employee_context = f"""
Employee context:
- The selected employee is: "{employee_name}"
- If the user says "my" / "mine" / "assigned to me", interpret it as this employee.
- Filter using the person-name column `{pm_col}` (not numeric ID columns like `ownerid`).
- Do NOT use CURRENT_USER/current_user or database user functions.
"""

    prompt = f"""
You are an expert database developer.

Database schema:
{schema_text}
{employee_context}

Rules:
- {dialect_rule}
- Only return SQL
- Only query from the `{table_name}` table (no joins, no other tables).
- Only use columns that exist in the provided schema.
- Do NOT use database user functions like CURRENT_USER/current_user.
- When filtering by a person's name, use name columns (e.g., `assigntoname`) instead of ID columns (e.g., `assigntoid`).
- When selecting projects, prefer returning these columns when possible: {", ".join(preferred_cols)}
- If the user's question is conceptual (e.g., "risk", "governance") and there is no matching column, still return a safe query from `{table_name}` and let the app answer using the returned rows.

User request:
{user_input}
"""
    clients = get_openai_clients()
    if not clients:
        # No LLM configured; return a safe projects-only query so the app remains usable.
        cols = ", ".join(get_project_table_columns())
        if db_type == "postgres":
            return f"SELECT {cols} FROM {table_name} LIMIT 20"
        return f"SELECT TOP 20 {cols} FROM {table_name}"

    last_error = ""
    for client in clients:
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            sql = response.choices[0].message.content.strip()
            sql = re.sub(r"```sql|```", "", sql).strip()
            return sql
        except Exception as error:
            last_error = str(error)
            status_code = getattr(error, "status_code", None)
            if status_code is None:
                resp = getattr(error, "response", None)
                status_code = getattr(resp, "status_code", None)
            if status_code in (401, 403, 404, 429):
                continue
            raise

    # All keys failed; keep the app usable with a safe default query.
    cols = ", ".join(get_project_table_columns())
    if db_type == "postgres":
        return f"SELECT {cols} FROM {table_name} LIMIT 20"
    return f"SELECT TOP 20 {cols} FROM {table_name}"


def build_my_projects_sql(employee_name: str, limit: int = 100) -> str:
    """
    Deterministic fallback query for "my projects" requests when we know the employee name.
    Uses a name column (project PM / assignee) rather than CURRENT_USER/ownerid.
    """
    employee_name = (employee_name or "").strip()
    safe_limit = max(1, min(int(limit or 100), 500))

    table_name = get_project_table_name()
    id_col = get_project_id_column()
    pm_col = get_project_pm_column()
    columns = ", ".join(get_project_table_columns())
    available = set(get_project_columns() or [])
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    like_op = "ILIKE" if db_type == "postgres" else "LIKE"

    escaped = escape_sql_literal(employee_name)
    if pm_col not in available:
        if db_type == "postgres":
            return f"SELECT {columns} FROM {table_name} ORDER BY {id_col} LIMIT {safe_limit}"
        return f"SELECT TOP {safe_limit} {columns} FROM {table_name} ORDER BY {id_col}"

    if db_type == "postgres":
        return f"SELECT {columns} FROM {table_name} WHERE {pm_col} {like_op} '%{escaped}%' ORDER BY {id_col} LIMIT {safe_limit}"
    return f"SELECT TOP {safe_limit} {columns} FROM {table_name} WHERE {pm_col} {like_op} '%{escaped}%' ORDER BY {id_col}"


def normalize_projects_select(sql: str) -> str:
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    # Normalization is tuned for SQL Server patterns; avoid rewriting postgres queries.
    if db_type == "postgres":
        return (sql or "").strip().rstrip(";")

    table_name = get_project_table_name()
    sql_stripped = sql.strip().rstrip(";")
    sql_lower = sql_stripped.lower()

    if not sql_lower.startswith("select"):
        return sql_stripped

    if not re.search(rf"\bfrom\s+(?:\[[^\]]+\]\.)*\[?{re.escape(table_name)}\]?\b", sql_lower):
        return sql_stripped

    unsafe_markers = ["count(", " group by ", " distinct ", " sum(", " avg(", " min(", " max("]
    if any(marker in sql_lower for marker in unsafe_markers):
        return sql_stripped

    match = re.search(
        rf"select\s+(top\s+\d+\s+)?(.+?)\s+from\s+(?:\[[^\]]+\]\.)*\[?{re.escape(table_name)}\]?\s+",
        sql_stripped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return sql_stripped

    top_clause = match.group(1) or ""
    normalized_columns = ", ".join(get_project_table_columns())
    return re.sub(
        rf"select\s+(top\s+\d+\s+)?(.+?)\s+from\s+(?:\[[^\]]+\]\.)*\[?{re.escape(table_name)}\]?\s+",
        f"SELECT {top_clause}{normalized_columns} FROM {table_name} ",
        sql_stripped,
        flags=re.IGNORECASE | re.DOTALL,
        count=1,
    )


def is_select_from_projects_only(sql: str) -> bool:
    table_name = get_project_table_name().lower()
    sql_stripped = (sql or "").strip().rstrip(";")
    if not sql_stripped:
        return False
    sql_lower = sql_stripped.lower()
    if not sql_lower.startswith("select"):
        return False

    refs = re.findall(r"\b(from|join)\s+([a-z0-9_\[\]\.\"']+)", sql_lower)
    if not refs:
        return False

    for _kw, identifier in refs:
        ident = (
            identifier.replace("[", "")
            .replace("]", "")
            .replace('"', "")
            .replace("'", "")
            .strip()
        )
        table = ident.split(".")[-1]
        if table != table_name:
            return False

    return True


def rows_look_like_projects(rows: list[dict]) -> bool:
    if not rows:
        return False
    keys = set(rows[0].keys())
    required = {"project_id", "project_name"}
    return required.issubset(keys)


def should_render_project_table(user_question: str) -> bool:
    q = user_question.lower()
    triggers = ["show", "list", "projects", "project table", "results", "find", "search"]
    return any(token in q for token in triggers)


def is_key_timeline_milestones_request(user_question: str) -> bool:
    q = (user_question or "").lower()
    triggers = [
        "key timeline milestones",
        "timeline milestones summary",
        "individual project milestones summary",
        "executive project summary",
    ]
    return any(t in q for t in triggers)


def escape_sql_literal(value: str) -> str:
    return (value or "").replace("'", "''").replace("\x00", "")


def get_key_timeline_columns() -> list[str]:
    cols = set(get_project_columns())
    preferred = [
        get_project_id_column(),
        get_project_name_column(),
        get_project_status_column(),
        get_project_start_date_column(),
        get_project_end_date_column(),
        get_project_go_live_column(),
        # Optional milestone columns if your schema has them.
        "fsd_sign_off",
        "fsd_signoff",
        "fsd_sign_off_date",
        "fsd_signoff_date",
        "fsd_signoff_status",
        "dev_start_date",
        "dev_end_date",
        "sit_start_date",
        "sit_end_date",
        "uat_start_date",
        "uat_end_date",
    ]
    available = [c for c in preferred if c in cols]
    if not available:
        return get_project_table_columns()
    return available


def build_key_timeline_sql(user_question: str) -> str:
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    table_name = get_project_table_name()
    id_col = get_project_id_column()
    columns = get_key_timeline_columns()
    cols_csv = ", ".join(columns)

    project_name = ""
    try:
        match = re.search(r"for\s+project\s+(.+?)(?:[\.\n\r]|$)", user_question or "", flags=re.IGNORECASE)
        project_name = (match.group(1) if match else "").strip().strip('"').strip("'")
    except Exception:
        project_name = ""

    project_id = ""
    try:
        id_match = re.search(r"\bproject[_\s-]*id\s*[:=]\s*([a-z0-9_\-]+)\b", user_question or "", flags=re.IGNORECASE)
        project_id = (id_match.group(1) if id_match else "").strip()
    except Exception:
        project_id = ""

    if project_name:
        escaped = escape_sql_literal(project_name)
        like_op = "ILIKE" if db_type == "postgres" else "LIKE"
        where_parts = [f"project_name {like_op} '%{escaped}%'"]
        if project_id:
            where_parts.append(f"project_id = '{escape_sql_literal(project_id)}'")
        where_clause = " OR ".join(where_parts)
        if db_type == "postgres":
            return f"SELECT {cols_csv} FROM {table_name} WHERE {where_clause} ORDER BY {id_col} LIMIT 20"
        return f"SELECT TOP 20 {cols_csv} FROM {table_name} WHERE {where_clause} ORDER BY {id_col}"

    if db_type == "postgres":
        return f"SELECT {cols_csv} FROM {table_name} ORDER BY {id_col} LIMIT 20"
    return f"SELECT TOP 20 {cols_csv} FROM {table_name} ORDER BY {id_col}"
