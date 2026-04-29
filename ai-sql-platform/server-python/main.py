"""
FastAPI server - drop-in replacement for the Express server.
Set VITE_API_BASE_URL=http://localhost:8000/api in .env.local
"""

from dotenv import load_dotenv
import os
from openai import OpenAI
import re
import httpx
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy import text
from db import SessionLocal
from rag import (
    HybridRagIndex,
    LocalSentenceTransformerEmbedder,
    chunk_project_row,
    parse_project_name_from_query,
)


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

load_dotenv()
print("DB_HOST:", os.getenv("DB_HOST"))

app = FastAPI(title="Project Intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_config():
    return {
        "db_type": os.getenv("DB_TYPE", "sqlserver"),
        "host": os.getenv("DB_HOST", ""),
        "port": int(os.getenv("DB_PORT", "5432" if os.getenv("DB_TYPE") == "postgres" else "1433")),
        "database_name": os.getenv("DB_NAME", ""),
        "username": os.getenv("DB_USER", ""),
        "password": os.getenv("DB_PASSWORD", ""),
    }


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
    cursor.execute(sql)
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


async def query(sql: str, params: list | None = None):
    cfg = get_db_config()
    if cfg["db_type"] == "postgres":
        return await query_postgres(sql, params)
    return await query_sqlserver(sql, params)


def build_search_sql(filters: dict | None):
    sql = "SELECT * FROM projects WHERE 1=1"
    params: list = []
    param_index = 0
    available_cols = set(get_project_columns())

    if not filters:
        return sql + " ORDER BY project_id", params

    for field, operator in [
        ("project_id", "="),
        ("project_name", "LIKE"),
        ("account_name", "LIKE"),
        ("account_id", "="),
        ("portfolio_name", "LIKE"),
        ("status", "LIKE"),
        ("project_manager", "LIKE"),
    ]:
        if field not in available_cols:
            continue
        value = filters.get(field)
        if value:
            sql += f" AND {field} {operator} @p{param_index}"
            params.append(f"%{value}%" if operator == "LIKE" else value)
            param_index += 1

    sql += " ORDER BY project_id"
    return sql, params


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


def is_pmo_rag_use_case(user_question: str) -> str | None:
    q = (user_question or "").lower()
    if any(k in q for k in ["milestones summary", "timeline milestones", "key timeline milestones"]):
        return "timeline"
    if any(k in q for k in ["health status", "health summary", "project health"]):
        return "health"
    if any(k in q for k in ["risk indicators", "risk summary", "project risk"]):
        return "risk"
    return None


RAG_INDEX: HybridRagIndex | None = None
RAG_INDEX_ERROR: str | None = None


def ensure_rag_index() -> HybridRagIndex | None:
    global RAG_INDEX, RAG_INDEX_ERROR
    if RAG_INDEX is not None:
        return RAG_INDEX
    if RAG_INDEX_ERROR:
        return None

    try:
        embedder = LocalSentenceTransformerEmbedder(os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"))
        RAG_INDEX = HybridRagIndex(embedder)
        # Lazy build; caller can trigger rebuild explicitly when needed.
        return RAG_INDEX
    except Exception as exc:
        RAG_INDEX_ERROR = str(exc)
        print("RAG INIT ERROR:", RAG_INDEX_ERROR)
        return None


def rebuild_rag_index(project_name: str | None = None, project_id: str | None = None) -> dict:
    idx = ensure_rag_index()
    if idx is None:
        return {
            "ok": False,
            "error": "rag_unavailable",
            "message": RAG_INDEX_ERROR or "RAG is not available in this environment.",
        }

    project_name = (project_name or "").strip()
    project_id = (project_id or "").strip()

    # Pull only columns that exist for chunking; fall back to SELECT * if INFORMATION_SCHEMA is restricted.
    cols = set(get_project_columns())
    preferred = [
        "project_id",
        "project_name",
        "status",
        "start_date",
        "fsd_sign_off",
        "fsd_signoff",
        "fsd_sign_off_date",
        "fsd_signoff_date",
        "dev_start_date",
        "dev_end_date",
        "sit_start_date",
        "sit_end_date",
        "uat_start_date",
        "uat_end_date",
        "go_live_date",
        "portfolio_name",
        "portfolio_owner",
        "account_name",
        "project_manager",
        "hod",
        "svp",
        "action_owner",
        "risk_statement",
        "severity",
        "impact",
        "schedule_health",
        "financial_health",
        "delivery_progress",
        "completion",
    ]
    available = [c for c in preferred if c in cols]

    where_sql = ""
    params: dict = {}
    if project_id:
        where_sql = " WHERE project_id = :pid"
        params["pid"] = project_id
    elif project_name:
        where_sql = " WHERE project_name LIKE :pname"
        params["pname"] = f"%{project_name}%"

    if available:
        sql = f"SELECT {', '.join(available)} FROM projects{where_sql} ORDER BY project_id"
    else:
        sql = f"SELECT * FROM projects{where_sql} ORDER BY project_id"

    rows = fetch_rows_sqlalchemy(sql, params)
    if not isinstance(rows, list):
        rows = []

    idx.clear()
    docs_added = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        docs = chunk_project_row(row)
        idx.add_documents(docs)
        docs_added += len(docs)

    return {"ok": True, "projects": len(rows), "documents": docs_added, "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")}


def build_rag_prompt(use_case: str, project_name: str, context_docs: list[dict]) -> str:
    import json

    context_json = json.dumps(context_docs, ensure_ascii=False, indent=2)
    project_label = project_name or "Selected project"

    if use_case == "timeline":
        return f"""
You are a PMO AI Assistant responsible for generating a Key Timeline Milestones Summary for an individual project for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). Do not guess missing dates; use "Not available".

Output (markdown):
 Milestones Overview
| Milestone | Date/Range |
|---|---|
| Project Start Date | ... |
| FSD Sign Off | ... |
| Development Phase | ... |
| SIT Phase | ... |
| UAT Phase | ... |
| Go-Live Date | ... |

🔎 Summary Highlights
- <2–3 bullets, 1 sentence each>

The LAST line must be exactly:
Overall Timeline Health: <Green/Amber/Red> — <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""

    if use_case == "health":
        return f"""
You are a PMO AI Assistant generating an Executive Project Health Summary for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). Do not infer numbers or dates that are not present.

Output (markdown):
Health Snapshot
- Overall: ...
- Schedule: ...
- Financial: ...
- Delivery: ...
- Risk: ...

🔎 Key Drivers
- <2–4 bullets, 1 sentence each>

The LAST line must be exactly:
Overall Health: <Green/Amber/Red> — <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""

    # risk
    return f"""
You are a PMO AI Assistant generating a concise Risk Indicators Summary for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). If risks are missing, say so clearly.

Output (markdown):
⚠️ Risk Indicators
- <3–6 bullets; include severity/impact when available>

✅ Mitigation Focus
- <2–4 bullets; actionable, ownership-oriented>

The LAST line must be exactly:
Overall Risk Posture: <Green/Amber/Red> — <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""


def fetch_rows_sqlalchemy(sql: str, params: dict | None = None):
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params or {})
        rows = [dict(row._mapping) for row in result]
        return make_json_safe(rows)
    finally:
        db.close()


SYSTEM_PROMPT = """You are a Project Intelligence Assistant (Agent PMP). You operate using a two-stage prompt architecture:

**Stage 1 - Query Understanding (NL -> Structured Filters):**
When a user asks a question, first extract structured search filters from their natural language query. Identify fields such as:
- project_id, project_name, account_name, account_id, portfolio_name, module_name, journey_name
- employee_name, resource_name, case_id, test_case_id
- status (Active, Delayed, Completed, In Progress, On Hold, etc.)
- date ranges, model_name, search queries

Present the extracted filters as a JSON block so the user can confirm or adjust before retrieval.

**Stage 2 - Data Retrieval & Response:**
After filters are confirmed, present the structured query that would be sent to the portal API. Since the portal API is not yet connected, generate a realistic mock/demo response.

IMPORTANT: When returning project data results, you MUST format them as a JSON code block containing an array of objects with these exact fields:
```json
[
  {
    "project_id": "PRJ001",
    "project_name": "Example Project",
    "status": "Active",
    "go_live_date": "2026-06-30",
    "portfolio_name": "Banking Portfolio",
    "portfolio_owner": "John Smith",
    "account_name": "ABC Bank",
    "project_manager": "Alice Johnson"
  }
]
```

This format will be automatically rendered as an interactive table in the UI.

**Response Guidelines:**
- Always show the extracted filters first as a JSON code block
- Then show the simulated structured response using the project array format above
- Use markdown tables for non-project tabular data (timesheets, defects, test cases)
- Use bullet points and headers for readability
- Clearly label mock data as "[Demo Data - API not yet connected]"
- When the user selects a use case from the sidebar, treat the pre-filled prompt template as their query and proceed with Stage 1

**Supported Use Case Categories:**
Project Planning Intelligence, Timesheet Management, Defect & Case Management, Test Cases Management, Intelligent Document Management, Report Automation, AI Meeting Summary, Smart Issue/Risk Analysis, Resource Allocation & Optimization"""


class AIRequest(BaseModel):
    message: str


class DBRequest(BaseModel):
    query_type: str
    filters: dict | None = None


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


class SummaryRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    project_data: dict | None = None


class RagRebuildRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None


class RagSearchRequest(BaseModel):
    query: str
    top_k: int | None = 5
    project_id: str | None = None
    project_name: str | None = None
    chunk_types: list[str] | None = None


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEFAULT_PROJECT_TABLE_COLUMNS = [
    "project_id",
    "project_name",
    "status",
]
PROJECT_COLUMNS_AVAILABLE: list[str] | None = None


def load_projects_columns() -> list[str]:
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                SELECT LOWER(COLUMN_NAME) AS column_name
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'projects'
                ORDER BY ORDINAL_POSITION
                """
            )
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
        sample = fetch_rows_sqlalchemy("SELECT TOP 1 * FROM projects")
        if isinstance(sample, list) and sample and isinstance(sample[0], dict):
            return [str(key).lower() for key in sample[0].keys()]
    except Exception:
        pass

    return list(DEFAULT_PROJECT_TABLE_COLUMNS)


def get_project_columns() -> list[str]:
    global PROJECT_COLUMNS_AVAILABLE
    if PROJECT_COLUMNS_AVAILABLE is None or len(PROJECT_COLUMNS_AVAILABLE) == 0:
        PROJECT_COLUMNS_AVAILABLE = load_projects_columns()
    return PROJECT_COLUMNS_AVAILABLE


def get_project_table_columns() -> list[str]:
    cols = set(get_project_columns())
    preferred = [
        "project_id",
        "project_name",
        "status",
        "go_live_date",
        "portfolio_name",
        "portfolio_owner",
        "account_name",
        "project_manager",
    ]
    available = [c for c in preferred if c in cols]
    if not available:
        return list(DEFAULT_PROJECT_TABLE_COLUMNS)
    # Ensure id+name stay first if present.
    ordered = []
    for key in ["project_id", "project_name"]:
        if key in cols and key in available and key not in ordered:
            ordered.append(key)
    for c in available:
        if c not in ordered:
            ordered.append(c)
    return ordered


def schema_text_projects() -> str:
    cols = get_project_columns() or list(DEFAULT_PROJECT_TABLE_COLUMNS)
    return "Table: projects\nColumns: " + ", ".join(cols)


def generate_sql(user_input: str):
    preferred_cols = get_project_table_columns()
    schema_text = schema_text_projects()
    prompt = f"""
You are an expert SQL Server developer.

Database schema:
{schema_text}

Rules:
- Use SQL Server syntax (TOP, not LIMIT)
- Only return SQL
- Only query from the `projects` table (no joins, no other tables).
- Only use columns that exist in the provided schema.
- When selecting projects, prefer returning these columns when possible: {", ".join(preferred_cols)}
- If the user's question is conceptual (e.g., "risk", "governance") and there is no matching column, still return a safe query from `projects` and let the app answer using the returned rows.

User request:
{user_input}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    sql = response.choices[0].message.content.strip()
    sql = re.sub(r"```sql|```", "", sql).strip()
    return sql


def normalize_projects_select(sql: str) -> str:
    sql_stripped = sql.strip().rstrip(";")
    sql_lower = sql_stripped.lower()

    if not sql_lower.startswith("select"):
        return sql_stripped

    # Normalize only when targeting projects (supports schema-qualified and bracketed identifiers).
    if not re.search(r"\bfrom\s+(?:\[[^\]]+\]\.)*\[?projects\]?\b", sql_lower):
        return sql_stripped

    # Skip aggregates/distinct/grouping queries.
    unsafe_markers = ["count(", " group by ", " distinct ", " sum(", " avg(", " min(", " max("]
    if any(marker in sql_lower for marker in unsafe_markers):
        return sql_stripped

    match = re.search(
        r"select\s+(top\s+\d+\s+)?(.+?)\s+from\s+(?:\[[^\]]+\]\.)*\[?projects\]?\s+",
        sql_stripped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return sql_stripped

    top_clause = match.group(1) or ""
    normalized_columns = ", ".join(get_project_table_columns())
    return re.sub(
        r"select\s+(top\s+\d+\s+)?(.+?)\s+from\s+(?:\[[^\]]+\]\.)*\[?projects\]?\s+",
        f"SELECT {top_clause}{normalized_columns} FROM projects ",
        sql_stripped,
        flags=re.IGNORECASE | re.DOTALL,
        count=1,
    )


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


def is_select_from_projects_only(sql: str) -> bool:
    sql_stripped = (sql or "").strip().rstrip(";")
    if not sql_stripped:
        return False
    sql_lower = sql_stripped.lower()
    if not sql_lower.startswith("select"):
        return False

    refs = re.findall(r"\b(from|join)\s+([a-z0-9_\[\]\.]+)", sql_lower)
    if not refs:
        return False

    for _kw, identifier in refs:
        ident = identifier.replace("[", "").replace("]", "").strip()
        table = ident.split(".")[-1]
        if table != "projects":
            return False

    return True


def is_key_timeline_milestones_request(user_question: str) -> bool:
    q = (user_question or "").lower()
    triggers = [
        "key timeline milestones",
        "timeline milestones summary",
        "individual project milestones summary",
        "executive project summary",
    ]
    return any(t in q for t in triggers)


def pick_best_project_row(user_question: str, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    # Try to match "for project <name>" from the request against row["project_name"].
    try:
        match = re.search(r"for\s+project\s+(.+?)(?:[\.\n\r]|$)", user_question or "", flags=re.IGNORECASE)
        requested_name = (match.group(1) if match else "").strip().strip('"').strip("'")
    except Exception:
        requested_name = ""

    if requested_name:
        requested_lower = requested_name.lower()
        for row in rows:
            row_name = str(row.get("project_name") or "").strip()
            if row_name and row_name.lower() == requested_lower:
                return row
        for row in rows:
            row_name = str(row.get("project_name") or "").strip()
            if row_name and (requested_lower in row_name.lower() or row_name.lower() in requested_lower):
                return row

    return rows[0]


def escape_sql_literal(value: str) -> str:
    # Minimal escaping for SQL string literals.
    return (value or "").replace("'", "''").replace("\x00", "")


def get_key_timeline_columns() -> list[str]:
    cols = set(get_project_columns())
    preferred = [
        "project_id",
        "project_name",
        "status",
        "start_date",
        # FSD sign-off variants
        "fsd_sign_off",
        "fsd_signoff",
        "fsd_sign_off_date",
        "fsd_signoff_date",
        "fsd_signoff_status",
        # Delivery phases
        "dev_start_date",
        "dev_end_date",
        "sit_start_date",
        "sit_end_date",
        "uat_start_date",
        "uat_end_date",
        "go_live_date",
    ]
    available = [c for c in preferred if c in cols]
    if not available:
        # Fallback to whatever the normal table columns are so the chat doesn't break.
        return get_project_table_columns()
    return available


def build_key_timeline_sql(user_question: str) -> str:
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
        where_parts = [f"project_name LIKE '%{escaped}%'"]
        if project_id:
            where_parts.append(f"project_id = '{escape_sql_literal(project_id)}'")
        where_clause = " OR ".join(where_parts)
        return f"SELECT TOP 20 {cols_csv} FROM projects WHERE {where_clause} ORDER BY project_id"

    return f"SELECT TOP 20 {cols_csv} FROM projects ORDER BY project_id"


def generate_answer_from_rows(user_question: str, rows: list[dict]) -> str:
    import json

    safe_rows = make_json_safe(rows or [])
    preview_rows = safe_rows[:50]
    rows_json = json.dumps(preview_rows, ensure_ascii=False, indent=2)
    truncated_note = ""
    if len(safe_rows) > len(preview_rows):
        truncated_note = f"\n\nNote: Only the first {len(preview_rows)} rows are shown (of {len(safe_rows)} total)."

    if is_key_timeline_milestones_request(user_question) and safe_rows:
        selected_project = pick_best_project_row(user_question, safe_rows) or safe_rows[0]
        project_json = json.dumps(selected_project, ensure_ascii=False, indent=2)

        prompt = f"""
You are a PMO AI Assistant responsible for generating a Key Timeline Milestones Summary for an individual project for leadership review.

Your task:
- Analyse the provided Project JSON data and produce a one-page executive summary suitable for PMO leaders, HODs, SVPs, and Portfolio Owners.

Guidelines:
- Write in clear, professional PMO language.
- Keep the response concise and leadership-focused.
- Use ONLY the provided Project JSON data. If a value is missing, write "Not available" (do not guess).
- Include relevant professional emojis for section headers to improve readability.
- End the response with an overall timeline health assessment as the FINAL line.

Milestones to include (structured):
- Project Start Date
- FSD Sign Off
- Development Phase
- SIT Phase
- UAT Phase
- Go-Live Date

Field mapping hints (use what exists; otherwise "Not available"):
- Start: start_date
- FSD Sign Off: fsd_sign_off, fsd_signoff, fsd_sign_off_date, fsd_signoff_date, fsd_signoff_status
- Development: dev_start_date, dev_end_date
- SIT: sit_start_date, sit_end_date
- UAT: uat_start_date, uat_end_date
- Go-Live: go_live_date

Output format (markdown):
- Use emoji section headers (e.g., 🗓️, 🔎, ✅).
- Use this EXACT milestone table format (each row must be on its own line; do not put the whole table on one line):
| Milestone | Date/Range |
|---|---|
| Project Start Date | YYYY-MM-DD / Not available |
| FSD Sign Off | YYYY-MM-DD / Not available |
| Development Phase | YYYY-MM-DD → YYYY-MM-DD / Not available |
| SIT Phase | YYYY-MM-DD → YYYY-MM-DD / Not available |
| UAT Phase | YYYY-MM-DD → YYYY-MM-DD / Not available |
| Go-Live Date | YYYY-MM-DD / Not available |
- For ranges, use the arrow symbol "→" between start and end dates.
- Add a **🔎 Summary Highlights** section with 2–3 bullet points (1 sentence each). No long paragraphs.
- The LAST line must be exactly: "Overall Timeline Health: <Green/Amber/Red> — <1 sentence rationale>"

Project JSON Data:
{project_json}
"""
    else:
        prompt = f"""
You are a helpful project intelligence assistant.

Answer the user's question using ONLY the data in the JSON rows below.
- If the rows are empty, say you couldn't find any matching data.
- If the user asks for a "two liner" summary, respond in 2 short lines max.
- Do not invent fields that are not present in the rows.
- If the question asks for a short summary, do not paste raw rows.

User question:
{user_question}

Rows (JSON):
{rows_json}{truncated_note}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}]
    )
    return (response.choices[0].message.content or "").strip()


@app.post("/api/rag/rebuild")
async def rag_rebuild(req: RagRebuildRequest):
    result = rebuild_rag_index(project_name=req.project_name, project_id=req.project_id)
    status = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status)


@app.post("/api/rag/search")
async def rag_search(req: RagSearchRequest):
    idx = ensure_rag_index()
    if idx is None:
        return JSONResponse(
            {"ok": False, "error": "rag_unavailable", "message": RAG_INDEX_ERROR or "RAG is not available."},
            status_code=500,
        )

    query_text = (req.query or "").strip()
    if not query_text:
        return JSONResponse({"ok": False, "error": "empty_query"}, status_code=400)

    chunk_types = set(req.chunk_types or []) if req.chunk_types else None
    docs = idx.hybrid_search(
        query_text,
        top_k=max(1, int(req.top_k or 5)),
        project_name=req.project_name,
        project_id=req.project_id,
        chunk_types=chunk_types,
    )
    return {
        "ok": True,
        "count": len(docs),
        "results": [
            {"doc_id": d.doc_id, "text": d.text, "metadata": make_json_safe(d.metadata)} for d in docs
        ],
    }


async def fetch_schema():
    db = SessionLocal()
    result = db.execute(text("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'projects'
    """)).fetchall()
    db.close()

    schema_text = "Table: projects\nColumns:\n"
    for row in result:
        schema_text += f"- {row[0]} ({row[1]})\n"
    return schema_text


def empty_summary(governance_message: str = ""):
    return {
        "overview": {},
        "health": {},
        "timeline": {},
        "governance": {"summary": governance_message} if governance_message else {},
        "financial": {},
        "risks": {},
        "highlights": {},
        "milestones": []
    }


def pick_first(project_data: dict, *keys: str):
    for key in keys:
        value = project_data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_fallback_summary(project_data: dict):
    project_name = pick_first(project_data, "project_name")
    status = pick_first(project_data, "status")
    project_id = pick_first(project_data, "project_id")
    portfolio = pick_first(project_data, "portfolio_name", "portfolio")
    portfolio_owner = pick_first(project_data, "portfolio_owner")
    account_name = pick_first(project_data, "account_name", "customer_name")
    project_manager = pick_first(project_data, "project_manager", "hod")
    go_live_date = pick_first(project_data, "go_live_date")
    billing_model = pick_first(project_data, "billing_model")
    objective = pick_first(project_data, "project_objective", "objective")
    module_name = pick_first(project_data, "module", "module_name")
    service_value = pick_first(project_data, "project_service_value", "service_value")
    revenue_recognized = pick_first(project_data, "revenue_recognized")
    cumulative_invoice = pick_first(project_data, "cumulative_invoice")
    advance = pick_first(project_data, "advance")
    revenue_available = pick_first(project_data, "revenue_available", "revenue_remaining")
    risk_statement = pick_first(project_data, "risk_statement")
    severity = pick_first(project_data, "severity")
    impact = pick_first(project_data, "impact")
    aging = pick_first(project_data, "aging")
    pending = pick_first(project_data, "pending")
    hod = pick_first(project_data, "hod")
    svp = pick_first(project_data, "svp")
    action_owner = pick_first(project_data, "action_owner")

    summary_text = (
        f"{project_name or 'Selected project'} is currently connected to the live project dataset."
        if project_name or project_id
        else "Live summary data is limited for this project."
    )

    milestones = [
        {"label": "Start Date", "date": pick_first(project_data, "start_date"), "status": "Available" if pick_first(project_data, "start_date") else "No data"},
        {"label": "Development", "date": " to ".join(filter(None, [pick_first(project_data, "dev_start_date"), pick_first(project_data, "dev_end_date")])), "status": "Available" if pick_first(project_data, "dev_start_date", "dev_end_date") else "No data"},
        {"label": "SIT", "date": " to ".join(filter(None, [pick_first(project_data, "sit_start_date"), pick_first(project_data, "sit_end_date")])), "status": "Available" if pick_first(project_data, "sit_start_date", "sit_end_date") else "No data"},
        {"label": "UAT", "date": " to ".join(filter(None, [pick_first(project_data, "uat_start_date"), pick_first(project_data, "uat_end_date")])), "status": "Available" if pick_first(project_data, "uat_start_date", "uat_end_date") else "No data"},
        {"label": "Go Live", "date": go_live_date, "status": "Available" if go_live_date else "No data"},
    ]

    return {
        "overview": {
            "project_name": project_name,
            "project_id": project_id,
            "status": status,
            "completion": pick_first(project_data, "completion"),
            "billing_model": billing_model,
            "modules_delivered": module_name,
            "objective": objective or f"Summary generated from connected project data for {project_name or project_id or 'the selected project'}.",
            "portfolio": portfolio,
            "portfolio_owner": portfolio_owner,
        },
        "health": {
            "overall": status or "No data",
            "schedule": pick_first(project_data, "schedule_health"),
            "financial": pick_first(project_data, "financial_health"),
            "delivery": pick_first(project_data, "delivery_progress", "completion"),
            "risk": severity or pick_first(project_data, "risk_level"),
        },
        "timeline": {
            "start_date": pick_first(project_data, "start_date"),
            "dev_start_date": pick_first(project_data, "dev_start_date"),
            "dev_end_date": pick_first(project_data, "dev_end_date"),
            "sit_start_date": pick_first(project_data, "sit_start_date"),
            "sit_end_date": pick_first(project_data, "sit_end_date"),
            "uat_start_date": pick_first(project_data, "uat_start_date"),
            "uat_end_date": pick_first(project_data, "uat_end_date"),
            "go_live_date": go_live_date,
        },
        "governance": {
            "summary": "Governance details are partially available from the current project dataset.",
            "project_manager": project_manager,
            "hod": hod,
            "svp": svp,
            "portfolio_owner": portfolio_owner,
            "action_owner": action_owner,
        },
        "financial": {
            "project_service_value": service_value,
            "revenue_recognized": revenue_recognized,
            "cumulative_invoice": cumulative_invoice,
            "advance": advance,
            "revenue_available": revenue_available,
        },
        "risks": {
            "risk_statement": risk_statement,
            "severity": severity,
            "impact": impact,
            "aging": aging,
            "pending": pending,
        },
        "highlights": {
            "module": module_name,
            "summary": summary_text,
            "key_win": account_name or portfolio or "No additional highlight data yet.",
        },
        "milestones": [milestone for milestone in milestones if milestone["date"] or milestone["status"] == "No data"],
    }


def deep_fill_summary(summary: dict, fallback: dict):
    merged = dict(fallback)
    for key, value in summary.items():
        if isinstance(value, dict) and isinstance(fallback.get(key), dict):
            merged[key] = deep_fill_summary(value, fallback[key])
        elif isinstance(value, list):
            merged[key] = value if value else fallback.get(key, [])
        elif value not in (None, ""):
            merged[key] = value
        else:
            merged[key] = fallback.get(key)
    return merged


def generate_summary(project_data: dict):
    prompt = f"""
You are a strict JSON generator.

Return ONLY valid JSON.
Do NOT include any text, explanation, or markdown.

Project Data:
{project_data}

Return exactly this structure:
{{
  "overview": {{
    "project_name": "",
    "project_id": "",
    "status": "",
    "completion": "",
    "billing_model": "",
    "modules_delivered": "",
    "objective": "",
    "portfolio": "",
    "portfolio_owner": ""
  }},
  "health": {{
    "overall": "",
    "schedule": "",
    "financial": "",
    "delivery": "",
    "risk": ""
  }},
  "timeline": {{
    "start_date": "",
    "dev_start_date": "",
    "dev_end_date": "",
    "sit_start_date": "",
    "sit_end_date": "",
    "uat_start_date": "",
    "uat_end_date": "",
    "go_live_date": ""
  }},
  "governance": {{
    "project_manager": "",
    "hod": "",
    "svp": "",
    "portfolio_owner": "",
    "action_owner": ""
  }},
  "financial": {{
    "project_service_value": "",
    "revenue_recognized": "",
    "cumulative_invoice": "",
    "advance": "",
    "revenue_available": ""
  }},
  "risks": {{
    "risk_statement": "",
    "severity": "",
    "impact": "",
    "aging": "",
    "pending": ""
  }},
  "highlights": {{
    "module": "",
    "summary": "",
    "key_win": ""
  }},
  "milestones": [
    {{
      "label": "",
      "date": "",
      "status": ""
    }}
  ]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.choices[0].message.content.strip()
    print("RAW LLM OUTPUT:", raw)

    import json

    try:
        return json.loads(raw)
    except Exception:
        print("INVALID JSON FROM LLM:", raw)
        return empty_summary("Error generating summary")


@app.post("/api/ai-query")
async def ai_query(req: AIRequest):
    try:
        schema = await fetch_schema()
        prompt = f"""
        You are an expert SQL Server developer.

        Schema:
        {schema}

        User request:
        {req.message}
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        sql = response.choices[0].message.content.strip()
        print("Generated SQL:", sql)
        return {"query": sql}
    except Exception as error:
        return {"error": str(error)}


@app.post("/api/summary")
async def get_summary(request: Request):
    # Manual parsing avoids FastAPI/Pydantic 422s when the client sends unexpected shapes.
    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        return JSONResponse(
            {"summary": empty_summary("Invalid request body"), "error": "invalid_body"},
            status_code=400
        )

    project_id = str(body.get("project_id") or "").strip()
    project_name = str(body.get("project_name") or "").strip()
    project_data = body.get("project_data") if isinstance(body.get("project_data"), dict) else {}
    project_data = make_json_safe(project_data or {})

    if not project_data:
        db = SessionLocal()
        try:
            if project_id:
                result = db.execute(
                    text("SELECT * FROM projects WHERE project_id = :id"),
                    {"id": project_id}
                )
            elif project_name:
                result = db.execute(
                    text("SELECT * FROM projects WHERE project_name = :name"),
                    {"name": project_name}
                )
            else:
                result = None

            row = result.fetchone() if result else None
        finally:
            db.close()

        if row:
            project_data = make_json_safe(dict(row._mapping))
            project_id = project_id or str(project_data.get("project_id", "")).strip()
            project_name = project_name or str(project_data.get("project_name", "")).strip()

    if not project_data:
        return JSONResponse(
            {"summary": empty_summary("Project lookup failed"), "error": "project_not_found"},
            status_code=404
        )

    fallback_summary = build_fallback_summary(project_data)

    try:
        generated_summary = generate_summary(project_data)
    except Exception as error:
        print("SUMMARY GENERATION ERROR:", str(error))
        generated_summary = empty_summary("Summary generation failed")

    summary = deep_fill_summary(generated_summary or {}, fallback_summary)
    return {
        "summary": summary,
        "project_id": project_id or str(project_data.get("project_id", "")),
        "project_name": project_name or str(project_data.get("project_name", "")),
    }


@app.post("/api/query")
async def run_query(body: dict):
    try:
        sql = body.get("query")

        if not sql:
            return {"error": "Query is required"}

        sql_lower = sql.lower()

        if not sql_lower.strip().startswith("select"):
            return {"error": "Only SELECT queries allowed"}

        if not is_select_from_projects_only(sql):
            return {"error": "Only 'projects' table is allowed"}

        db = SessionLocal()
        result = db.execute(text(sql))
        rows = [dict(row._mapping) for row in result]
        db.close()

        return {
            "rows": rows,
            "count": len(rows)
        }
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/tables")
def list_tables():
    try:
        db = SessionLocal()
        result = db.execute(text("""
            SELECT name
            FROM sys.tables
            ORDER BY name
        """))
        tables = [row[0] for row in result]
        return {"tables": tables}
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/schema")
async def get_schema():
    try:
        db = SessionLocal()
        result = db.execute(text("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'projects'
        """)).fetchall()

        schema = {
            "projects": [
                {"column": row[0], "type": row[1]}
                for row in result
            ]
        }
        db.close()
        return schema
    except Exception as error:
        return {"error": str(error)}


@app.get("/api/projects")
async def list_projects_full():
    try:
        results = fetch_rows_sqlalchemy("SELECT * FROM projects ORDER BY project_name")
        return {"results": results}
    except Exception as error:
        return JSONResponse({"error": str(error)}, status_code=500)


@app.post("/api/db-proxy")
async def db_proxy(req: DBRequest):
    query_type = req.query_type
    filters = req.filters

    cfg = get_db_config()
    if not cfg["host"]:
        return JSONResponse({
            "error": "no_connection",
            "message": "No database configured. Set DB_* env vars"
        })

    try:
        if query_type == "test_connection":
            await query("SELECT 1 AS test")
            return {"success": True, "message": "Connection successful"}

        if query_type == "list_projects":
            results = fetch_rows_sqlalchemy("SELECT * FROM projects ORDER BY project_name")
            return {"results": results}

        if query_type == "search_projects":
            sql, params = build_search_sql(filters)
            if params:
                results = await query(sql, params)
                return {"results": make_json_safe(results)}

            results = fetch_rows_sqlalchemy(sql)
            return {"results": results}

        return JSONResponse({"error": f"Unknown query_type: {query_type}"}, status_code=400)

    except Exception as error:
        return JSONResponse({"error": str(error)}, status_code=500)


@app.post("/api/search-projects")
async def search_projects(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}

        filters = body.get("filters", {})
        _ = filters

        db = SessionLocal()
        result = db.execute(text("SELECT project_id,project_name FROM Projects"))
        rows = [dict(row._mapping) for row in result]
        db.close()

        return rows

    except Exception as error:
        print("ERROR:", str(error))
        return {"error": str(error)}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.messages or len(req.messages) == 0:
        return {"response": "No message received"}

    user_msg = req.messages[-1].content

    try:
        rag_use_case = is_pmo_rag_use_case(user_msg)
        # Prefer the existing SQL-backed timeline flow for the milestone summary use case.
        if rag_use_case == "timeline" and is_key_timeline_milestones_request(user_msg):
            rag_use_case = None
        if rag_use_case:
            idx = ensure_rag_index()
            if idx is None:
                return {
                    "message": "RAG is not available in this environment.",
                    "error": RAG_INDEX_ERROR or "rag_unavailable",
                }

            project_name = parse_project_name_from_query(user_msg)
            # Rebuild index lazily the first time to avoid a slow server import.
            if idx.size == 0:
                rebuild_rag_index(project_name=project_name or None)

            chunk_types = {"milestone"} if rag_use_case == "timeline" else ({"health", "governance"} if rag_use_case == "health" else {"risk", "health"})
            hits = idx.hybrid_search(
                user_msg,
                top_k=6,
                project_name=project_name or None,
                chunk_types=chunk_types,
            )

            context_docs = [
                {"chunk_type": (d.metadata or {}).get("chunk_type"), "text": d.text, "metadata": make_json_safe(d.metadata)}
                for d in hits
            ]
            prompt = build_rag_prompt(rag_use_case, project_name, context_docs)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            content = (response.choices[0].message.content or "").strip()
            return {"message": content or "No matching context found for this request."}

        if is_key_timeline_milestones_request(user_msg):
            sql = build_key_timeline_sql(user_msg)
        else:
            sql = generate_sql(user_msg)
            if not is_select_from_projects_only(sql):
                sql = f"SELECT TOP 20 {', '.join(get_project_table_columns())} FROM projects ORDER BY project_id"
            else:
                sql = normalize_projects_select(sql)
        print("Generated SQL:", sql)

        try:
            query_result = await run_query({"query": sql})
        except Exception as error:
            return {"response": f"Query failed: {str(error)}"}

        if "error" in query_result:
            return {"response": f"DB Error: {query_result['error']}"}

        rows = make_json_safe(query_result.get("rows", []) or [])
        answer = generate_answer_from_rows(user_msg, rows)

        message_parts: list[str] = []
        if answer:
            message_parts.append(answer)

        if rows_look_like_projects(rows) and should_render_project_table(user_msg):
            import json
            # Ensure the table renderer sees the exact expected fields.
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

        return {
            "message": message or "No matching data found.",
            "rows": rows,
            "count": len(rows),
            "sql": sql,
        }

    except Exception as error:
        return {"response": f"Error: {str(error)}"}


if __name__ == "__main__":
    import uvicorn

    load_dotenv()
    port = int(os.getenv("PORT", "8000"))
    print(f"FastAPI server running at http://localhost:{port}")
    print(f"   DB_TYPE: {os.getenv('DB_TYPE', 'sqlserver')}")
    print(f"   DB_HOST: {os.getenv('DB_HOST', '(not set)')}")
    uvicorn.run(app, host="0.0.0.0", port=port)
