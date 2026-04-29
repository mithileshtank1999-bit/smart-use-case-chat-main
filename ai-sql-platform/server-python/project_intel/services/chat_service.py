from __future__ import annotations

from project_intel.data.db_access import (
    get_db_config,
    get_project_table_name,
    get_project_id_column,
    make_json_safe,
    fetch_rows_sqlalchemy,
    normalize_project_row,
)
from project_intel.services.answer_service import generate_answer_from_rows
from project_intel.services.rag_service import chat_via_rag
from project_intel.services.sql_service import (
    build_key_timeline_sql,
    build_my_projects_sql,
    generate_sql,
    is_key_timeline_milestones_request,
    is_select_from_projects_only,
    normalize_projects_select,
    rows_look_like_projects,
    should_render_project_table,
)
from project_intel.data.db_access import get_project_table_columns


def safe_projects_fallback_query(limit: int = 20) -> str:
    table_name = get_project_table_name()
    id_col = get_project_id_column()
    cols = ", ".join(get_project_table_columns())
    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    if db_type == "postgres":
        return f"SELECT {cols} FROM {table_name} ORDER BY {id_col} LIMIT {int(limit)}"
    return f"SELECT TOP {int(limit)} {cols} FROM {table_name} ORDER BY {id_col}"


async def run_query_sql(sql: str) -> dict:
    sql_lower = (sql or "").lower()
    if not sql_lower.strip().startswith("select"):
        return {"error": "Only SELECT queries allowed"}
    if not is_select_from_projects_only(sql):
        return {"error": "Only 'projects' table is allowed"}

    try:
        rows = fetch_rows_sqlalchemy(sql)
        return {"rows": rows or [], "count": len(rows or [])}
    except Exception as error:
        return {"error": str(error)}


async def handle_chat(messages: list[dict], employee_name: str | None = None) -> dict:
    if not messages:
        return {"response": "No message received"}

    user_msg = str(messages[-1].get("content") or "")
    employee_name = (employee_name or "").strip() or None

    rag_result = chat_via_rag(user_msg)
    if rag_result.get("handled"):
        return {"message": rag_result.get("message", "")}

    if is_key_timeline_milestones_request(user_msg):
        sql = build_key_timeline_sql(user_msg)
    else:
        sql = generate_sql(user_msg, employee_name=employee_name)

        # If the user is asking for "my projects" and we know the employee name,
        # avoid SQL like `ownerid = current_user` which can break on Postgres types.
        if employee_name and ("my" in user_msg.lower() or "mine" in user_msg.lower() or "assigned to me" in user_msg.lower()):
            if "current_user" in (sql or "").lower():
                sql = build_my_projects_sql(employee_name, limit=100)

        if not is_select_from_projects_only(sql):
            sql = safe_projects_fallback_query(20)
        else:
            sql = normalize_projects_select(sql)

    query_result = await run_query_sql(sql)
    if "error" in query_result:
        return {"response": f"DB Error: {query_result['error']}"}

    rows_raw = make_json_safe(query_result.get("rows", []) or [])
    rows = [normalize_project_row(row) for row in rows_raw if isinstance(row, dict)]
    answer = generate_answer_from_rows(user_msg, rows)

    message_parts: list[str] = []
    if answer:
        message_parts.append(answer)

    if rows_look_like_projects(rows) and should_render_project_table(user_msg):
        import json

        projects_payload = [
            {
                "project_id": str(row.get("project_id", "")),
                "project_name": str(row.get("project_name", "")),
                "status": str(row.get("status", "")),
                "go_live_date": make_json_safe(row.get("go_live_date", None)),
                "portfolio_name": make_json_safe(row.get("portfolio_name", None)),
                "portfolio_owner": make_json_safe(row.get("portfolio_owner", None)),
                "account_name": make_json_safe(row.get("account_name", None)),
                "project_manager": make_json_safe(row.get("project_manager", None)),
            }
            for row in rows
        ]
        message_parts.append("```json\n" + json.dumps(projects_payload, ensure_ascii=False, indent=2) + "\n```")

    message = "\n\n".join([part for part in message_parts if part])
    return {"message": message or "No matching data found.", "rows": rows, "count": len(rows), "sql": sql}
