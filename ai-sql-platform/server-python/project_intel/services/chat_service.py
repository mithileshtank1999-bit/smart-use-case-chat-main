from __future__ import annotations

import os

from project_intel.data.db_access import (
    get_db_config,
    get_project_table_name,
    get_project_id_column,
    make_json_safe,
    fetch_rows_sqlalchemy,
    normalize_project_row,
)
from project_intel.services.answer_service import generate_answer_from_rows
from project_intel.services.document_service import answer_from_documents, search_documents
from project_intel.services.meeting_service import extract_meeting_intelligence
from project_intel.services.rag_service import chat_via_rag
from project_intel.services.usecase_dispatch import dispatch_usecase_chat
from project_intel.services.general_sql_service import enforce_row_limit, generate_sql_any_table, is_safe_readonly_sql
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
    """
    Executes a validated read-only SQL query.

    Safety model:
    - Always require read-only SQL (SELECT/WITH, single statement, no writes/DDL).
    - By default, only allow the configured projects table.
    - Opt-in to "any table" queries via ALLOW_ANY_TABLE_QUERIES=1 (use with least-privilege DB user).
    """
    raw = (sql or "").strip()
    if not raw:
        return {"error": "Empty query"}

    if not is_safe_readonly_sql(raw):
        return {"error": "Only read-only SELECT/WITH queries are allowed"}

    allow_any_table = (os.getenv("ALLOW_ANY_TABLE_QUERIES") or "").strip().lower() in ("1", "true", "yes", "y")
    if not allow_any_table and not is_select_from_projects_only(raw):
        return {
            "error": "Only 'projects' table is allowed",
            "hint": "Set ALLOW_ANY_TABLE_QUERIES=1 to enable read-only queries across the schema (recommended only with a read-only, least-privilege DB user).",
        }

    try:
        rows = fetch_rows_sqlalchemy(raw)
        return {"rows": rows or [], "count": len(rows or [])}
    except Exception as error:
        return {"error": str(error)}


async def handle_chat(messages: list[dict], employee_name: str | None = None) -> dict:
    if not messages:
        return {"response": "No message received"}

    user_msg = str(messages[-1].get("content") or "")
    employee_name = (employee_name or "").strip() or None

    usecase_result = dispatch_usecase_chat(user_msg)
    if usecase_result and usecase_result.get("handled"):
        return {"message": str(usecase_result.get("message") or "")}

    rag_result = chat_via_rag(user_msg)
    if rag_result.get("handled"):
        return {"message": rag_result.get("message", "")}

    _lower = user_msg.lower()

    # Meeting intelligence: structured extraction when the user asks for action items,
    # decisions, or risks from a meeting — searches uploaded transcript documents.
    _MEETING_INTENT = (
        "action item", "extract action", "meeting summary", "meeting notes",
        "summarize the meeting", "summarise the meeting", "meeting transcript",
        "decisions from the meeting", "risks from the meeting",
    )
    if any(k in _lower for k in _MEETING_INTENT):
        doc_hits = search_documents(user_msg, top_k=8)
        if doc_hits:
            transcript_text = "\n\n".join(h["text"] for h in doc_hits)
            intel = extract_meeting_intelligence(transcript_text)
            if intel.get("ok"):
                parts = []
                if intel.get("summary"):
                    parts.append(f"**Summary**\n{intel['summary']}")
                if intel.get("action_items"):
                    rows = "\n".join(
                        f"- **{a.get('owner', '?')}**: {a.get('description', '')} "
                        f"(due: {a.get('due_date') or 'TBD'}, priority: {a.get('priority', '?')})"
                        for a in intel["action_items"]
                    )
                    parts.append(f"**Action Items**\n{rows}")
                if intel.get("decisions"):
                    rows = "\n".join(f"- {d.get('description', '')}" for d in intel["decisions"])
                    parts.append(f"**Decisions**\n{rows}")
                if intel.get("risks"):
                    rows = "\n".join(
                        f"- [{r.get('severity', '?')}] {r.get('description', '')} — "
                        f"{r.get('mitigation') or 'no mitigation noted'}"
                        for r in intel["risks"]
                    )
                    parts.append(f"**Risks**\n{rows}")
                return {"message": "\n\n".join(parts) or "No meeting intelligence extracted."}

    # Document Q&A: answer from uploaded files when the query references a document.
    _DOC_KEYWORDS = ("document", "uploaded", "file", "pdf", "docx", "report", "attachment")
    if any(k in _lower for k in _DOC_KEYWORDS):
        doc_hits = search_documents(user_msg, top_k=5)
        if doc_hits:
            doc_answer = answer_from_documents(user_msg, doc_hits)
            if doc_answer:
                return {"message": doc_answer}

    sql = ""
    if is_key_timeline_milestones_request(user_msg):
        sql = build_key_timeline_sql(user_msg)
    else:
        # Prefer DB-as-knowledgebase queries across the whole schema.
        allow_any_table = (os.getenv("ALLOW_ANY_TABLE_QUERIES") or "").strip().lower() in ("1", "true", "yes", "y")
        proposed = generate_sql_any_table(user_msg) if allow_any_table else None
        if proposed and is_safe_readonly_sql(proposed):
            sql = enforce_row_limit(proposed, limit=200)
        else:
            # Fallback: legacy projects-only behavior.
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
    rows: list[dict] = [row for row in rows_raw if isinstance(row, dict)]

    # Only apply project normalization when rows look project-shaped; otherwise keep original keys.
    if rows_look_like_projects(rows):
        rows = [normalize_project_row(row) for row in rows]

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
