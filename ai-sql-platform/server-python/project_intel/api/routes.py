from __future__ import annotations

import os
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy import text

import re

from db import SessionLocal

from project_intel.core.config import OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import (
    build_search_sql,
    fetch_rows_sqlalchemy,
    fetch_schema_text,
    get_db_config,
    get_project_table_name,
    get_project_columns,
    get_project_id_column,
    get_project_name_column,
    get_project_status_column,
    get_project_go_live_column,
    normalize_project_row,
    patch_project_row,
    make_json_safe,
    query,
)
from project_intel.schemas import (
    AIRequest,
    ChatRequest,
    DBRequest,
    RagRebuildRequest,
    RagSearchRequest,
    ProjectPatchRequest,
    TimesheetFillRequest,
    TimesheetCommandRequest,
    SpeechTranscribeRequest,
)
from project_intel.services.chat_service import handle_chat
from project_intel.services.rag_service import ensure_rag_index, rebuild_rag_index
from project_intel.services.summary_service import build_executive_summary, empty_summary
from project_intel.services.sql_service import is_select_from_projects_only
from project_intel.data.timesheet_access import (
    fill_timesheet_entry,
    list_allocated_projects,
    search_employees,
    list_timesheet_options,
    list_timesheet_templates,
    describe_table_columns,
)

from datetime import date as date_type, datetime as datetime_type, timedelta
import re


router = APIRouter()


def _normalize_transcribe_language(lang: str | None) -> str | None:
    """
    OpenAI transcription `language` expects an ISO-639-1 code like "en".
    Browsers often provide BCP-47 tags like "en-US" – normalize to the base language.
    """
    if not lang:
        return None
    raw = str(lang).strip()
    if not raw:
        return None
    raw = raw.replace("_", "-")
    base = raw.split("-", 1)[0].lower()
    if re.fullmatch(r"[a-z]{2}", base):
        return base
    return None

@router.get("/project-options")
async def list_project_options(q: str = "", limit: int = 200, offset: int = 0):
    """
    Lightweight project list for the sidebar.
    Supports server-side search to avoid fetching thousands of rows.
    """
    cfg = get_db_config()
    db_type = (cfg.get("db_type") or "sqlserver").strip().lower()
    table_name = get_project_table_name()

    safe_limit = max(1, min(int(limit or 200), 500))
    safe_offset = max(0, int(offset or 0))

    available_cols = set(get_project_columns())
    id_col = get_project_id_column()
    name_col = get_project_name_column()
    status_col = get_project_status_column()
    go_live_col = get_project_go_live_column()

    # Always return stable keys expected by the UI: project_id, project_name.
    select_cols = [f"{id_col} AS project_id", f"{name_col} AS project_name"]
    if status_col in available_cols:
        select_cols.append(f"{status_col} AS status")
    if go_live_col in available_cols:
        select_cols.append(f"{go_live_col} AS go_live_date")

    cols_csv = ", ".join(select_cols)

    params: dict = {}
    where_sql = ""
    if q and q.strip():
        term = q.strip()
        params["q"] = f"%{term}%"
        if db_type == "postgres":
            where_sql = f" WHERE {name_col} ILIKE :q OR CAST({id_col} AS TEXT) ILIKE :q"
        else:
            where_sql = f" WHERE {name_col} LIKE :q OR CAST({id_col} AS NVARCHAR(255)) LIKE :q"

    if db_type == "postgres":
        sql = f"SELECT {cols_csv} FROM {table_name}{where_sql} ORDER BY project_name LIMIT {safe_limit} OFFSET {safe_offset}"
    else:
        # SQL Server: TOP without OFFSET for simplicity (sidebar search narrows results).
        sql = f"SELECT TOP {safe_limit} {cols_csv} FROM {table_name}{where_sql} ORDER BY project_name"

    try:
        results = fetch_rows_sqlalchemy(sql, params) or []
        normalized = [normalize_project_row(row) for row in results if isinstance(row, dict)]
        return {"results": normalized, "count": len(normalized), "limit": safe_limit, "offset": safe_offset}
    except Exception as error:
        return JSONResponse(
            {"error": str(error), "db_type": db_type, "table": table_name, "hint": "Verify the project table and columns exist."},
            status_code=500,
        )


@router.get("/projects")
async def list_projects_full():
    try:
        table_name = get_project_table_name()
        name_col = get_project_name_column()
        results = fetch_rows_sqlalchemy(f"SELECT * FROM {table_name} ORDER BY {name_col}") or []
        normalized = [normalize_project_row(row) for row in results if isinstance(row, dict)]
        return {"results": normalized}
    except Exception as error:
        cfg = get_db_config()
        return JSONResponse(
            {
                "error": str(error),
                "db_type": cfg.get("db_type"),
                "db_host": cfg.get("host"),
                "db_port": cfg.get("port"),
                "table": get_project_table_name(),
                "hint": "Verify DB_TYPE/DB_HOST/DB_PORT/DB_NAME credentials and that DB_PROJECT_TABLE exists.",
            },
            status_code=500,
        )


@router.post("/db-proxy")
async def db_proxy(req: DBRequest):
    query_type = req.query_type
    filters = req.filters

    cfg = get_db_config()
    if not cfg["host"]:
        return JSONResponse({"error": "no_connection", "message": "No database configured. Set DB_* env vars"})

    try:
        if query_type == "test_connection":
            await query("SELECT 1 AS test")
            return {"success": True, "message": "Connection successful"}

        if query_type == "list_projects":
            table_name = get_project_table_name()
            name_col = get_project_name_column()
            results = fetch_rows_sqlalchemy(f"SELECT * FROM {table_name} ORDER BY {name_col}") or []
            normalized = [normalize_project_row(row) for row in results if isinstance(row, dict)]
            return {"results": normalized}

        if query_type == "search_projects":
            sql, params = build_search_sql(filters)
            if params:
                results = await query(sql, params)
                safe = make_json_safe(results) or []
                normalized = [normalize_project_row(row) for row in safe if isinstance(row, dict)]
                return {"results": normalized}
            results = fetch_rows_sqlalchemy(sql) or []
            normalized = [normalize_project_row(row) for row in results if isinstance(row, dict)]
            return {"results": normalized}

        return JSONResponse({"error": f"Unknown query_type: {query_type}"}, status_code=400)
    except Exception as error:
        cfg = get_db_config()
        return JSONResponse(
            {
                "error": str(error),
                "db_type": cfg.get("db_type"),
                "db_host": cfg.get("host"),
                "db_port": cfg.get("port"),
                "table": get_project_table_name(),
                "hint": "If this is Postgres, ensure psycopg2-binary is installed and the server is reachable from this machine.",
            },
            status_code=500,
        )


@router.post("/search-projects")
async def search_projects(request: Request):
    try:
        # Keep this endpoint DB-agnostic (works for both SQL Server and Postgres).
        table_name = get_project_table_name()
        id_col = get_project_id_column()
        name_col = get_project_name_column()
        results = fetch_rows_sqlalchemy(
            f"SELECT {id_col} AS project_id, {name_col} AS project_name FROM {table_name} ORDER BY {name_col}"
        )
        return results
    except Exception as error:
        return {"error": str(error)}


@router.post("/chat")
async def chat(req: ChatRequest):
    messages = [m.model_dump() for m in req.messages] if req.messages else []
    employee_name = (req.employee_name or "").strip() or None
    return await handle_chat(messages, employee_name=employee_name)


@router.post("/summary")
async def get_summary(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        return JSONResponse({"summary": empty_summary("Invalid request body"), "error": "invalid_body"}, status_code=400)

    project_id = str(body.get("project_id") or "").strip()
    project_name = str(body.get("project_name") or "").strip()
    project_data = body.get("project_data") if isinstance(body.get("project_data"), dict) else {}

    payload = build_executive_summary(project_id=project_id, project_name=project_name, project_data=project_data)
    if "error" in payload:
        code = 404 if payload.get("error") == "project_not_found" else 500
        return JSONResponse(payload, status_code=code)
    return payload


@router.post("/query")
async def run_query(body: dict):
    try:
        sql = body.get("query")
        if not sql:
            return {"error": "Query is required"}
        sql_lower = str(sql).lower()
        if not sql_lower.strip().startswith("select"):
            return {"error": "Only SELECT queries allowed"}
        if not is_select_from_projects_only(sql):
            return {"error": "Only 'projects' table is allowed"}
        rows = fetch_rows_sqlalchemy(sql)
        return {"rows": rows, "count": len(rows or [])}
    except Exception as error:
        return {"error": str(error)}


@router.post("/speech/transcribe")
async def speech_transcribe(req: SpeechTranscribeRequest):
    """
    Server-side speech-to-text. This avoids browser SpeechRecognition flakiness.

    Input: base64 audio payload (data URL or raw base64).
    Output: { ok: true, text: "..." }
    """
    import base64
    import io

    from project_intel.core.config import TRANSCRIBE_MODEL

    clients = get_openai_clients()
    if not clients:
        return JSONResponse(
            {
                "ok": False,
                "error": "missing_openai_api_key",
                "hint": "Set OPENAI_API_KEY (or OPENAI_API_KEYS) in ai-sql-platform/server-python/.env and restart the server.",
            },
            status_code=500,
        )

    raw = (req.audio_base64 or "").strip()
    if not raw:
        return JSONResponse({"ok": False, "error": "missing_audio"}, status_code=400)

    # Accept data URLs like: data:audio/webm;codecs=opus;base64,...
    if "base64," in raw:
        raw = raw.split("base64,", 1)[1].strip()

    try:
        audio_bytes = base64.b64decode(raw, validate=False)
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_base64"}, status_code=400)

    if not audio_bytes:
        return JSONResponse({"ok": False, "error": "empty_audio"}, status_code=400)

    bio = io.BytesIO(audio_bytes)
    bio.name = (req.filename or "audio.webm").strip() or "audio.webm"

    models_to_try = [
        (TRANSCRIBE_MODEL or "").strip(),
        "gpt-4o-mini-transcribe",
        "gpt-4o-transcribe",
        "whisper-1",
    ]
    # de-dup while preserving order
    seen: set[str] = set()
    models: list[str] = []
    for m in models_to_try:
        if not m:
            continue
        if m in seen:
            continue
        seen.add(m)
        models.append(m)

    last_error: str = ""
    attempt_errors: list[dict] = []
    debug = (os.getenv("TRANSCRIBE_DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")

    normalized_language = _normalize_transcribe_language(req.language)

    for key_index, client in enumerate(clients):
        for model_name in models:
            try:
                # Rewind for each attempt
                bio.seek(0)
                resp = client.audio.transcriptions.create(
                    model=model_name,
                    file=bio,
                    language=normalized_language,
                )
                text = getattr(resp, "text", "") or ""
                return {"ok": True, "text": text, "model": model_name}
            except Exception as error:
                last_error = str(error)
                status_code = getattr(error, "status_code", None)
                if status_code is None:
                    resp = getattr(error, "response", None)
                    status_code = getattr(resp, "status_code", None)

                if debug:
                    attempt_errors.append({"key_index": key_index, "model": model_name, "status_code": status_code, "error": last_error})

                # Try the next model/key on "no access"/"not found"/auth/quota errors.
                lowered = last_error.lower()
                if status_code in (401, 403, 404, 429):
                    continue
                if "model_not_found" in lowered or "does not have access to model" in lowered or "not have access" in lowered:
                    continue

                return JSONResponse(
                    {
                        "ok": False,
                        "error": last_error,
                        "model": model_name,
                        "hint": "Check OPENAI_API_KEY/OPENAI_API_KEYS and TRANSCRIBE_MODEL in server-python/.env, and ensure the OpenAI project has Audio enabled.",
                    },
                    status_code=500,
                )

    payload = {
        "ok": False,
        "error": last_error or "No transcription model available for this API key.",
        "models_tried": models,
        "hint": "Set TRANSCRIBE_MODEL to a model your OpenAI project can access (try whisper-1), and confirm your OpenAI project is enabled for Audio. If you have multiple keys, set OPENAI_API_KEYS to try them in order.",
    }
    if debug:
        payload["attempt_errors"] = attempt_errors

    # This is an upstream dependency/config issue, not an end-user authorization failure.
    return JSONResponse(payload, status_code=502)


@router.post("/speech/transcribe-file")
async def speech_transcribe_file(file: UploadFile = File(...), language: str | None = Form(None)):
    """
    Multipart alternative to /speech/transcribe that avoids sending large base64 payloads.

    Input: multipart/form-data with "file" and optional "language".
    Output: { ok: true, text: "..." }
    """
    try:
        import io

        from project_intel.core.config import TRANSCRIBE_MODEL

        clients = get_openai_clients()
        if not clients:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "missing_openai_api_key",
                    "hint": "Set OPENAI_API_KEY (or OPENAI_API_KEYS) in ai-sql-platform/server-python/.env and restart the server.",
                },
                status_code=500,
            )

        try:
            audio_bytes = await file.read()
        except Exception:
            return JSONResponse({"ok": False, "error": "unable_to_read_file"}, status_code=400)

        if not audio_bytes:
            return JSONResponse({"ok": False, "error": "empty_audio"}, status_code=400)

        bio = io.BytesIO(audio_bytes)
        bio.name = (file.filename or "audio.webm").strip() or "audio.webm"

        models_to_try = [
            (TRANSCRIBE_MODEL or "").strip(),
            "gpt-4o-mini-transcribe",
            "gpt-4o-transcribe",
            "whisper-1",
        ]
        seen: set[str] = set()
        models: list[str] = []
        for m in models_to_try:
            if not m:
                continue
            if m in seen:
                continue
            seen.add(m)
            models.append(m)

        last_error: str = ""
        attempt_errors: list[dict] = []
        debug = (os.getenv("TRANSCRIBE_DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")

        normalized_language = _normalize_transcribe_language(language)

        for key_index, client in enumerate(clients):
            for model_name in models:
                try:
                    bio.seek(0)
                    resp = client.audio.transcriptions.create(
                        model=model_name,
                        file=bio,
                        language=normalized_language,
                    )
                    text = getattr(resp, "text", "") or ""
                    return {"ok": True, "text": text, "model": model_name}
                except Exception as error:
                    last_error = str(error)
                    status_code = getattr(error, "status_code", None)
                    if status_code is None:
                        resp = getattr(error, "response", None)
                        status_code = getattr(resp, "status_code", None)

                    if debug:
                        attempt_errors.append({"key_index": key_index, "model": model_name, "status_code": status_code, "error": last_error})

                    lowered = last_error.lower()
                    if status_code in (401, 403, 404, 429):
                        continue
                    if "model_not_found" in lowered or "does not have access to model" in lowered or "not have access" in lowered:
                        continue

                    return JSONResponse(
                        {
                            "ok": False,
                            "error": last_error,
                            "model": model_name,
                            "hint": "Check OPENAI_API_KEY/OPENAI_API_KEYS and TRANSCRIBE_MODEL in server-python/.env, and ensure the OpenAI project has Audio enabled.",
                        },
                        status_code=500,
                    )

        payload = {
            "ok": False,
            "error": last_error or "No transcription model available for this API key.",
            "models_tried": models,
            "hint": "Set TRANSCRIBE_MODEL to a model your OpenAI project can access (try whisper-1), and confirm your OpenAI project is enabled for Audio. If you have multiple keys, set OPENAI_API_KEYS to try them in order.",
        }
        if debug:
            payload["attempt_errors"] = attempt_errors

        return JSONResponse(payload, status_code=502)
    except Exception as error:
        # Ensure the client gets a JSON response (and a clue) rather than a blank 500.
        return JSONResponse(
            {
                "ok": False,
                "error": str(error),
                "hint": "Set TRANSCRIBE_DEBUG=1 to include per-attempt errors, and check server logs for a traceback.",
            },
            status_code=500,
        )


@router.get("/tables")
def list_tables():
    try:
        cfg = get_db_config()
        db_type = (cfg.get("db_type") or "sqlserver").strip().lower()

        db = SessionLocal()
        try:
            if db_type == "postgres":
                result = db.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_type = 'BASE TABLE'
                        ORDER BY table_name
                        """
                    )
                )
                tables = [row[0] for row in result]
                return {"tables": tables}

            result = db.execute(text("SELECT name FROM sys.tables ORDER BY name"))
            tables = [row[0] for row in result]
            return {"tables": tables}
        finally:
            db.close()
    except Exception as error:
        return {"error": str(error)}


@router.get("/schema")
async def get_schema():
    try:
        table_name = get_project_table_name()
        db = SessionLocal()
        result = db.execute(
            text(
                """
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = :table_name
            """
            )
        , {"table_name": table_name}).fetchall()

        schema = {"projects": [{"column": row[0], "type": row[1]} for row in result]}
        db.close()
        return schema
    except Exception as error:
        return {"error": str(error)}


@router.post("/ai-query")
async def ai_query(req: AIRequest):
    try:
        clients = get_openai_clients()
        if not clients:
            return JSONResponse({"error": "missing_openai_api_key", "hint": "Set OPENAI_API_KEY or OPENAI_API_KEYS and restart the server."}, status_code=500)

        schema = await fetch_schema_text()
        prompt = f"""
You are an expert SQL Server developer.

Schema:
{schema}

User request:
{req.message}
"""
        last_error = ""
        response = None
        for client in clients:
            try:
                response = client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": prompt}])
                break
            except Exception as error:
                last_error = str(error)
                status_code = getattr(error, "status_code", None)
                if status_code is None:
                    resp = getattr(error, "response", None)
                    status_code = getattr(resp, "status_code", None)
                if status_code in (401, 403, 404, 429):
                    continue
                raise
        if response is None:
            return JSONResponse({"error": last_error or "OpenAI request failed."}, status_code=502)
        sql = (response.choices[0].message.content or "").strip()
        return {"query": sql}
    except Exception as error:
        return {"error": str(error)}


@router.post("/rag/rebuild")
async def rag_rebuild(req: RagRebuildRequest):
    result = rebuild_rag_index(project_name=req.project_name, project_id=req.project_id)
    status = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status)


@router.post("/rag/search")
async def rag_search(req: RagSearchRequest):
    idx = ensure_rag_index()
    if idx is None:
        return JSONResponse({"ok": False, "error": "rag_unavailable"}, status_code=500)

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
        "results": [{"doc_id": d.doc_id, "text": d.text, "metadata": make_json_safe(d.metadata)} for d in docs],
    }


@router.post("/project/patch")
async def patch_project(req: ProjectPatchRequest):
    """
    Controlled write endpoint: updates only whitelisted columns for one project.
    """
    try:
        updated = patch_project_row(req.project_id, req.updates)
        if not updated:
            return JSONResponse({"ok": False, "error": "not_found_or_not_updated"}, status_code=404)
        return {"ok": True, "project": updated}
    except ValueError as error:
        return JSONResponse({"ok": False, "error": "invalid_request", "message": str(error)}, status_code=400)
    except Exception as error:
        cfg = get_db_config()
        return JSONResponse(
            {
                "ok": False,
                "error": str(error),
                "db_type": cfg.get("db_type"),
                "table": get_project_table_name(),
            },
            status_code=500,
        )


@router.post("/timesheet/fill")
async def timesheet_fill(req: TimesheetFillRequest):
    """
    Create a single 8-hour timesheet entry for a project+employee via DB write.
    This endpoint is intentionally specific and guarded (no arbitrary SQL).
    """
    try:
        from datetime import date as date_type

        work_date = req.work_date or date_type.today()
        result = fill_timesheet_entry(
            projectid=int(req.project_id),
            employee_name=req.employee_name,
            work_date=work_date,
            start_time_hhmm=req.start_time or "09:00",
            end_time_hhmm=req.end_time or "17:00",
            effort_minutes=int(req.effort_minutes or 480),
            description=req.description or "SDG development",
            item=req.item or "Config",
            template_timesheetid=req.template_timesheetid,
            engagementroleid=req.engagementroleid,
            engagementlocationid=req.engagementlocationid,
            projecttaskid=req.projecttaskid,
        )
        return {"ok": True, **result}
    except ValueError as error:
        return JSONResponse({"ok": False, "error": "invalid_request", "message": str(error)}, status_code=400)
    except Exception as error:
        cfg = get_db_config()
        return JSONResponse(
            {"ok": False, "error": str(error), "db_type": cfg.get("db_type"), "table": "timesheet"},
            status_code=500,
        )


def _parse_timesheet_command(command: str) -> dict:
    """
    Parses a lightweight command string into fill_timesheet_entry arguments.

    Supported examples:
    - "today 8h item=Config desc=SDG development"
    - "2026-04-29 09:00-17:00 item=Config desc=\"SDG development\" template=123"
    - "date=2026-04-29 start=09:00 end=17:00 effort=480m item=Config desc=SDG"
    """
    raw = (command or "").strip()
    if not raw:
        raise ValueError("Empty timesheet command.")

    out: dict = {}

    m = re.search(r"\btemplate\s*=\s*(\d+)\b", raw, flags=re.IGNORECASE)
    if m:
        out["template_timesheetid"] = int(m.group(1))

    m = re.search(r"\bitem\s*=\s*([A-Za-z0-9 _\\-./]+)", raw, flags=re.IGNORECASE)
    if m:
        out["item"] = m.group(1).strip().strip('"').strip("'")

    m = re.search(r"\bdesc\s*=\s*(\"[^\"]+\"|'[^']+'|.+)$", raw, flags=re.IGNORECASE)
    if m:
        desc = m.group(1).strip()
        if (desc.startswith('"') and desc.endswith('"')) or (desc.startswith("'") and desc.endswith("'")):
            desc = desc[1:-1]
        out["description"] = desc.strip()

    # Date (explicit)
    m = re.search(r"\bdate\s*=\s*(\d{4}-\d{2}-\d{2})\b", raw, flags=re.IGNORECASE)
    if m:
        out["work_date"] = datetime_type.strptime(m.group(1), "%Y-%m-%d").date()
    else:
        # Date (shorthand tokens)
        if re.search(r"\btoday\b", raw, flags=re.IGNORECASE):
            out["work_date"] = date_type.today()
        elif re.search(r"\byesterday\b", raw, flags=re.IGNORECASE):
            out["work_date"] = date_type.today() - timedelta(days=1)
        elif re.search(r"\btomorrow\b", raw, flags=re.IGNORECASE):
            out["work_date"] = date_type.today() + timedelta(days=1)
        else:
            m2 = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
            if m2:
                out["work_date"] = datetime_type.strptime(m2.group(1), "%Y-%m-%d").date()

    # Time range
    m = re.search(r"\b(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\b", raw)
    if m:
        out["start_time_hhmm"] = m.group(1)
        out["end_time_hhmm"] = m.group(2)
    else:
        ms = re.search(r"\bstart\s*=\s*(\d{1,2}:\d{2})\b", raw, flags=re.IGNORECASE)
        me = re.search(r"\bend\s*=\s*(\d{1,2}:\d{2})\b", raw, flags=re.IGNORECASE)
        if ms:
            out["start_time_hhmm"] = ms.group(1)
        if me:
            out["end_time_hhmm"] = me.group(1)

    # Effort
    m = re.search(r"\beffort\s*=\s*(\d+)\s*m\b", raw, flags=re.IGNORECASE)
    if m:
        out["effort_minutes"] = int(m.group(1))
    else:
        mh = re.search(r"\b(\d+(?:\.\d+)?)\s*h\b", raw, flags=re.IGNORECASE)
        if mh:
            out["effort_minutes"] = int(round(float(mh.group(1)) * 60))

    return out


@router.post("/timesheet/command")
async def timesheet_command(req: TimesheetCommandRequest):
    """
    Single-string timesheet command runner (validated server-side).
    Intended for "minimum command" workflows in chat/voice.
    """
    try:
        parsed = _parse_timesheet_command(req.command)
        work_date = parsed.get("work_date") or date_type.today()
        result = fill_timesheet_entry(
            projectid=int(req.project_id),
            employee_name=req.employee_name,
            work_date=work_date,
            start_time_hhmm=str(parsed.get("start_time_hhmm") or "09:00"),
            end_time_hhmm=str(parsed.get("end_time_hhmm") or "17:00"),
            effort_minutes=int(parsed.get("effort_minutes") or 480),
            description=str(parsed.get("description") or "SDG development"),
            item=str(parsed.get("item") or "Config"),
            template_timesheetid=int(parsed["template_timesheetid"]) if "template_timesheetid" in parsed else None,
        )
        return {"ok": True, **result, "parsed": parsed}
    except ValueError as error:
        return JSONResponse({"ok": False, "error": "invalid_command", "message": str(error)}, status_code=400)
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/employee/projects")
async def employee_projects(name: str, q: str = "", limit: int = 200):
    """
    Given an employee display name, return allocated projects (employeeallocation -> project).
    """
    try:
        results = list_allocated_projects(name, q=q, limit=limit)
        return {"results": results, "count": len(results)}
    except Exception as error:
        return JSONResponse({"error": str(error)}, status_code=500)


@router.get("/employee/search")
async def employee_search(q: str, limit: int = 20):
    """
    Autocomplete helper for employee display names (employee.subject).
    """
    try:
        results = search_employees(q, limit=limit)
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/timesheet/options")
async def timesheet_options(project_id: int):
    try:
        return {"ok": True, "options": list_timesheet_options(int(project_id))}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/timesheet/templates")
async def timesheet_templates(employee_name: str, project_id: int, limit: int = 10):
    try:
        results = list_timesheet_templates(employee_name, int(project_id), limit=limit)
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/timesheet/schema")
async def timesheet_schema():
    """
    Introspection helper for aligning the app's timesheet insert with the actual DB schema.
    Returns column metadata for the key tables involved in the timesheet workflow.
    """
    try:
        project_table = get_project_table_name()
        return {
            "ok": True,
            "tables": {
                "employee": describe_table_columns("employee"),
                "employeeallocation": describe_table_columns("employeeallocation"),
                "timesheet": describe_table_columns("timesheet"),
                "project": describe_table_columns(project_table),
                "getnextidblock": {"ok": True, "note": "Used as a stored procedure to allocate IDs (not a table)."},
            },
        }
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)
