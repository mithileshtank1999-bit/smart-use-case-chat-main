from __future__ import annotations

import asyncio
import logging
import os
from fastapi import APIRouter, BackgroundTasks, Request, UploadFile, File, Form
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
    DocumentSearchRequest,
    MeetingAnalyzeRequest,
    RagRebuildRequest,
    RagSearchRequest,
    ProjectPatchRequest,
    TimesheetFillRequest,
    TimesheetCommandRequest,
    SpeechTranscribeRequest,
    WSRRequest,
    WSRFromTextRequest,
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
from project_intel.data.qa_access import get_case_rows, get_test_case_rows
from project_intel.data.action_access import get_action_point_rows, get_risk_rows
from project_intel.data.schema_access import build_schema_overview_text, list_tables, list_columns
from project_intel.data.portfolio_access import (
    list_portfolios,
    get_portfolio_summary,
    get_portfolio_timesheet,
)
from project_intel.data.org_access import (
    get_org_summary,
    get_org_headcount,
    get_org_utilization,
    get_org_portfolio_health,
)
from project_intel.core.config import N8N_API_KEY, N8N_BASE_URL
from project_intel.data.n8n_access import (
    ensure_tables,
    get_dashboard_metrics,
    get_executions,
    get_execution_detail,
    get_workflow_list,
)
from project_intel.services.n8n_service import (
    N8nClient,
    generate_ai_report,
    process_webhook_payload,
    sync_from_n8n,
)
from project_intel.core.rate_limit import limiter, chat_limit, transcribe_limit, sql_gen_limit
from project_intel.core.jobs import job_store
from project_intel.services.document_service import (
    index_document,
    list_documents,
    delete_document,
    search_documents,
    answer_from_documents,
)
from project_intel.services.meeting_service import extract_meeting_intelligence
from project_intel.services.wsr_service import (
    WSRData,
    _from_schema as _wsr_from_schema,
    parse_wsr_text,
    render_html as wsr_html,
    render_pdf as wsr_pdf,
    send_email as wsr_send_email,
)

logger = logging.getLogger(__name__)

from datetime import date as date_type, datetime as datetime_type, timedelta
import re


router = APIRouter()

def _db_not_configured_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "db_not_configured",
            "hint": "Set DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD (and DB_TYPE) in ai-sql-platform/server-python/.env or process environment, then restart the server.",
        },
        status_code=503,
    )


@router.get("/healthz")
async def healthz():
    """
    Liveness probe: the process is up and serving requests.
    Keep this fast and dependency-free.
    """
    return {"ok": True}


@router.get("/readyz")
async def readyz():
    """
    Readiness probe: verifies critical dependencies are reachable.
    """
    cfg = get_db_config()
    if not (cfg.get("host") or "").strip():
        return _db_not_configured_response()

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return {"ok": True}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=503)


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
        return _db_not_configured_response()

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
@limiter.limit(chat_limit())
async def chat(request: Request, req: ChatRequest):
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
@limiter.limit(transcribe_limit())
async def speech_transcribe(request: Request, req: SpeechTranscribeRequest):
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


# ---------------------------------------------------------------------------
# Meeting intelligence endpoints
# ---------------------------------------------------------------------------

@router.post("/speech/analyze")
async def speech_analyze(req: MeetingAnalyzeRequest):
    """
    Extract structured meeting intelligence from a transcript string.

    Input:  { transcript: "...", project_name?: "..." }
    Output: { ok, summary, action_items, decisions, risks, participants,
              transcript_chars, segments_processed }
    """
    result = await asyncio.to_thread(
        extract_meeting_intelligence,
        req.transcript,
        project_name=req.project_name,
    )
    status = 200 if result.get("ok") else 422
    return JSONResponse(result, status_code=status)


@router.post("/speech/transcribe-and-analyze")
async def speech_transcribe_and_analyze(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    project_name: str | None = Form(None),
):
    """
    One-shot endpoint: upload an audio file, get back both the transcript
    and the structured meeting intelligence (action items, decisions, risks).

    Input:  multipart/form-data — file, optional language, optional project_name
    Output: { ok, transcript, summary, action_items, decisions, risks,
              participants, model, transcript_chars, segments_processed }
    """
    import io as _io
    from project_intel.core.config import TRANSCRIBE_MODEL

    clients = get_openai_clients()
    if not clients:
        return JSONResponse(
            {"ok": False, "error": "missing_openai_api_key"},
            status_code=500,
        )

    try:
        audio_bytes = await file.read()
    except Exception:
        return JSONResponse({"ok": False, "error": "unable_to_read_file"}, status_code=400)

    if not audio_bytes:
        return JSONResponse({"ok": False, "error": "empty_audio"}, status_code=400)

    bio = _io.BytesIO(audio_bytes)
    bio.name = (file.filename or "audio.webm").strip() or "audio.webm"

    # --- Step 1: transcribe ---
    models_to_try = list(dict.fromkeys(filter(None, [
        (TRANSCRIBE_MODEL or "").strip(),
        "gpt-4o-mini-transcribe",
        "gpt-4o-transcribe",
        "whisper-1",
    ])))

    transcript_text = ""
    transcribe_model_used = ""
    last_error = ""
    normalized_language = _normalize_transcribe_language(language)

    for client in clients:
        for model_name in models_to_try:
            try:
                bio.seek(0)
                resp = client.audio.transcriptions.create(
                    model=model_name,
                    file=bio,
                    language=normalized_language,
                )
                transcript_text = getattr(resp, "text", "") or ""
                transcribe_model_used = model_name
                break
            except Exception as exc:
                last_error = str(exc)
                status_code = getattr(exc, "status_code", None) or getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                lowered = last_error.lower()
                if status_code in (401, 403, 404, 429) or "model_not_found" in lowered or "not have access" in lowered:
                    continue
                return JSONResponse({"ok": False, "error": last_error, "step": "transcribe"}, status_code=500)
        if transcript_text:
            break

    if not transcript_text:
        return JSONResponse(
            {"ok": False, "error": last_error or "transcription_failed", "step": "transcribe"},
            status_code=502,
        )

    # --- Step 2: extract intelligence ---
    intel = await asyncio.to_thread(
        extract_meeting_intelligence,
        transcript_text,
        project_name=project_name,
    )

    return {
        "ok": intel.get("ok", False),
        "transcript": transcript_text,
        "model": transcribe_model_used,
        **{k: intel[k] for k in ("summary", "action_items", "decisions", "risks", "participants") if k in intel},
        "transcript_chars": intel.get("transcript_chars", len(transcript_text)),
        "segments_processed": intel.get("segments_processed", 1),
        "error": intel.get("error"),
    }


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
@limiter.limit(sql_gen_limit())
async def ai_query(request: Request, req: AIRequest):
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


async def _run_rag_rebuild(job_id: str, project_name: str, project_id: str) -> None:
    job_store.mark_running(job_id)
    try:
        result = await asyncio.to_thread(
            rebuild_rag_index,
            project_name=project_name or None,
            project_id=project_id or None,
        )
        if result.get("ok"):
            job_store.mark_done(job_id, result)
        else:
            job_store.mark_failed(job_id, result.get("error") or result.get("message") or "rebuild_failed")
    except Exception as exc:
        logger.exception("RAG rebuild job %s failed", job_id)
        job_store.mark_failed(job_id, str(exc))


@router.post("/rag/rebuild")
async def rag_rebuild(req: RagRebuildRequest, background_tasks: BackgroundTasks):
    """
    Enqueues a RAG index rebuild and returns immediately.
    Poll GET /api/rag/rebuild/status/{job_id} to track progress.
    """
    job_id = job_store.create(label="rag_rebuild")
    background_tasks.add_task(
        _run_rag_rebuild,
        job_id,
        req.project_name or "",
        req.project_id or "",
    )
    return {"ok": True, "job_id": job_id, "status": "queued"}


@router.get("/rag/rebuild/status/{job_id}")
async def rag_rebuild_status(job_id: str):
    """
    Returns the current state of a rebuild job.
    Possible statuses: queued | running | done | failed
    """
    job = job_store.get(job_id)
    if job is None:
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    return {
        "ok": True,
        "job_id": job.job_id,
        "status": job.status,
        "label": job.label,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


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
    cfg = get_db_config()
    if not (cfg.get("host") or "").strip():
        return _db_not_configured_response()
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
    cfg = get_db_config()
    if not (cfg.get("host") or "").strip():
        return _db_not_configured_response()
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


@router.get("/qa/cases")
async def qa_cases(
    stage: str | None = None,
    case_id: str | None = None,
    module_name: str | None = None,
    journey_name: str | None = None,
    project_name: str | None = None,
    limit: int = 50,
):
    """
    Read-only helper powering "Case summary" use cases.
    Requires `DB_QA_CASE_TABLE` to be configured to an existing table name.
    """
    result = get_case_rows(
        stage=stage,
        case_id=case_id,
        module_name=module_name,
        journey_name=journey_name,
        project_name=project_name,
        limit=limit,
    )
    if not result.ok:
        return JSONResponse({"ok": False, "error": result.error, "table": result.table, "schema": result.schema, "note": result.note}, status_code=400)
    return {"ok": True, "table": f"{result.schema}.{result.table}" if result.schema and result.table else result.table, "count": result.count, "rows": result.rows or []}


@router.get("/qa/testcases")
async def qa_testcases(
    stage: str | None = None,
    test_case_id: str | None = None,
    module_name: str | None = None,
    journey_name: str | None = None,
    project_name: str | None = None,
    limit: int = 50,
):
    """
    Read-only helper powering "Test case summary" use cases.
    Requires `DB_QA_TESTCASE_TABLE` to be configured to an existing table name.
    """
    result = get_test_case_rows(
        stage=stage,
        test_case_id=test_case_id,
        module_name=module_name,
        journey_name=journey_name,
        project_name=project_name,
        limit=limit,
    )
    if not result.ok:
        return JSONResponse({"ok": False, "error": result.error, "table": result.table, "schema": result.schema, "note": result.note}, status_code=400)
    return {"ok": True, "table": f"{result.schema}.{result.table}" if result.schema and result.table else result.table, "count": result.count, "rows": result.rows or []}


@router.get("/action/points")
async def action_points(
    project_name: str | None = None,
    module_name: str | None = None,
    limit: int = 50,
):
    """Read action centre points. Requires DB_ACTION_TABLE (default: actionpoints)."""
    result = get_action_point_rows(project_name=project_name, module_name=module_name, limit=limit)
    if not result.ok:
        return JSONResponse({"ok": False, "error": result.error, "table": result.table, "note": result.note}, status_code=400)
    return {"ok": True, "table": f"{result.schema}.{result.table}" if result.schema else result.table, "count": result.count, "rows": result.rows or []}


@router.get("/action/risks")
async def project_risks(
    project_name: str | None = None,
    module_name: str | None = None,
    limit: int = 50,
):
    """Read project risks. Requires DB_RISK_TABLE (default: risks)."""
    result = get_risk_rows(project_name=project_name, module_name=module_name, limit=limit)
    if not result.ok:
        return JSONResponse({"ok": False, "error": result.error, "table": result.table, "note": result.note}, status_code=400)
    return {"ok": True, "table": f"{result.schema}.{result.table}" if result.schema else result.table, "count": result.count, "rows": result.rows or []}


# ---------------------------------------------------------------------------
# Document upload / management endpoints
# ---------------------------------------------------------------------------

@router.post("/documents/upload")
async def document_upload(file: UploadFile = File(...)):
    """
    Upload a document (PDF, DOCX, TXT).
    The server extracts text, splits it into chunks, embeds them, and stores
    them for semantic search.  Returns {doc_id, filename, pages, chunks}.
    """
    if not file.filename:
        return JSONResponse({"ok": False, "error": "no_filename"}, status_code=400)
    try:
        content = await file.read()
        result = await asyncio.to_thread(index_document, file.filename, content)
        return result
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
    except Exception as exc:
        logger.exception("document_upload failed for %s", file.filename)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/documents")
async def documents_list():
    """List all uploaded documents with chunk counts."""
    try:
        docs = await asyncio.to_thread(list_documents)
        return {"ok": True, "count": len(docs), "documents": docs}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.delete("/documents/{doc_id}")
async def document_delete(doc_id: str):
    """Delete all chunks for a document by its doc_id."""
    try:
        removed = await asyncio.to_thread(delete_document, doc_id)
        return {"ok": True, "doc_id": doc_id, "chunks_removed": removed}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/documents/search")
async def document_search(req: DocumentSearchRequest):
    """
    Semantic search over uploaded documents.
    Returns matching chunks with source filename and page number.
    """
    try:
        hits = await asyncio.to_thread(search_documents, req.query, req.top_k or 5)
        if not hits:
            return {"ok": True, "answer": None, "hits": []}
        answer = await asyncio.to_thread(answer_from_documents, req.query, hits)
        return {
            "ok": True,
            "answer": answer,
            "hits": [
                {
                    "text": h["text"],
                    "filename": h["meta"].get("filename"),
                    "page": h["meta"].get("page"),
                    "doc_id": h["meta"].get("doc_id"),
                }
                for h in hits
            ],
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# WSR (Weekly Status Report) generation endpoints
# ---------------------------------------------------------------------------

def _wsr_response(data: WSRData, send_email_flag: bool = False) -> dict:
    """Build, optionally email, and return the WSR payload."""
    html = wsr_html(data)

    try:
        pdf_bytes = wsr_pdf(data)
        import base64
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
    except RuntimeError as exc:
        pdf_b64 = None
        logger.warning("WSR PDF generation skipped: %s", exc)

    email_result: dict | None = None
    if send_email_flag and data.report_recipients:
        if pdf_b64:
            import base64
            email_result = wsr_send_email(data, base64.b64decode(pdf_b64))
        else:
            email_result = {"ok": False, "error": "pdf_unavailable"}

    return {
        "ok": True,
        "project_name": data.project_name,
        "reporting_period": data.reporting_period,
        "html": html,
        "pdf_base64": pdf_b64,
        "email": email_result,
    }


@router.post("/reports/wsr")
async def report_wsr(req: WSRRequest):
    """
    Generate a WSR from structured JSON input.
    Returns { ok, html, pdf_base64, email? }.
    pdf_base64 can be decoded and saved as a .pdf file.
    """
    data = await asyncio.to_thread(_wsr_from_schema, req)
    return _wsr_response(data, send_email_flag=bool(req.report_recipients))


@router.post("/reports/wsr/from-text")
async def report_wsr_from_text(req: WSRFromTextRequest):
    """
    Paste raw WSR notes (free text) and get back a formatted HTML + PDF report.
    The LLM extracts the structure automatically.

    Input:  { text: "Project Name: ...", send_email: false }
    Output: { ok, project_name, reporting_period, html, pdf_base64, email? }
    """
    try:
        data = await asyncio.to_thread(parse_wsr_text, req.text)
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
    return _wsr_response(data, send_email_flag=req.send_email)


@router.get("/usecases/supported")
async def supported_usecases():
    """
    Lightweight discoverability endpoint: shows which sidebar prompts are currently wired to live DB handlers.
    """
    return {
        "ok": True,
        "chat_detected": {
            "pmo_rag": ["milestones summary (timeline)", "health status summary (health)", "risk indicators summary (risk)"],
            "qa_cases": [
                "Case ID Summary (DEV/SIT/UAT)",
                "Module-wise Case Summary (DEV/SIT/UAT)",
                "Journey Wise Case Summary (DEV/SIT/UAT)",
                "Project Wise Case Summary (DEV/SIT/UAT)",
                "Module-wise Defect Summary Report (DEV/SIT/UAT)",
                "Project-wise Defect Summary Report (DEV/SIT/UAT)",
            ],
            "qa_testcases": [
                "Test Case ID Summary (DEV/SIT/UAT)",
                "Module-wise Test Case Summary (DEV/SIT/UAT)",
                "Journey Wise Test Case Summary (DEV/SIT/UAT)",
                "Project Wise Test Case Summary (DEV/SIT/UAT)",
                "Module-wise Test Cases Summary Report (DEV/SIT/UAT)",
                "Project-wise Test Cases Summary Report (DEV/SIT/UAT)",
            ],
            "timesheet": [
                "Timesheet Entry & Submission (see /timesheet/*)",
                "Individual Employee Timesheet Summary",
                "Model-wise Timesheet Booking Summary",
                "Project-wise Timesheet Booking Summary",
                "Account-wise Timesheet Booking Summary",
                "Portfolio-wise Timesheet Booking Summary",
                "Organisation-wise Timesheet Booking Summary",
                "Auto-Generate Pending Timesheet Report",
            ],
            "action_risk": [
                "Retrieve Action Centre Points (project + module filters)",
                "Retrieve Risk (project + module filters)",
            ],
            "portal_general": [
                "My Portal Request Summary",
                "Travel Desk Request Summary",
                "Help Desk-IT Request Summary",
                "(and their Report variants — routed via AI SQL generator)",
            ],
        },
        "env": {
            "DB_QA_CASE_TABLE": "Cases table name (default: cases).",
            "DB_QA_TESTCASE_TABLE": "Testcases table name (default: testcases).",
            "DB_ACTION_TABLE": "Action points table name (default: actionpoints).",
            "DB_RISK_TABLE": "Risks table name (default: risks).",
            "DB_SCHEMA": "Default schema used in lookups (default: dbo).",
            "DB_SEARCH_PATH": "Comma-separated schema search path.",
            "CHROMA_PERSIST_DIR": "Directory path for ChromaDB persistent RAG store. Unset = in-memory FAISS (resets on restart).",
            "INTENT_ROUTING_THRESHOLD": "Cosine similarity threshold for semantic intent routing (default 0.55). Lower = more aggressive matching.",
            "INTENT_ROUTING_ENABLED": "Set to '0' to disable semantic routing and use keyword-only matching.",
        },
        "async_jobs": {
            "rag_rebuild": {
                "enqueue": "POST /api/rag/rebuild  →  {ok, job_id, status: queued}",
                "poll":    "GET  /api/rag/rebuild/status/{job_id}  →  {status: queued|running|done|failed, result, error}",
                "note": "Jobs expire after 1 hour. In multi-worker deployments, replace job_store with a Redis-backed store.",
            },
        },
    }


@router.get("/db/schema")
async def db_schema(max_tables: int = 40, max_cols: int = 25):
    """
    Debug/ops endpoint: returns a compact schema overview used by the SQL generator.
    """
    try:
        text_overview = build_schema_overview_text(max_tables=max_tables, max_cols=max_cols)
        return {"ok": True, "overview": text_overview}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/db/tables")
async def db_tables():
    """
    Debug/ops endpoint: lists tables in DB_SCHEMA/DB_SEARCH_PATH.
    """
    try:
        return {"ok": True, "results": list_tables()}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/db/explore")
async def db_explore():
    """
    Returns all tables in search path with row counts and columns.
    Used for schema exploration and level mapping.
    """
    try:
        tables = list_tables()
        out = []
        db = SessionLocal()
        try:
            for t in tables:
                schema = t["schema"] if isinstance(t, dict) else str(t[0])
                table = t["table"] if isinstance(t, dict) else str(t[1])
                try:
                    cnt = db.execute(
                        text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                    ).scalar()
                except Exception:
                    db.rollback()
                    cnt = None
                cols = list_columns(schema=schema, table=table, max_cols=200)
                out.append({
                    "schema": schema,
                    "table": table,
                    "row_count": cnt,
                    "columns": [{"name": c["name"], "type": c["type"]} for c in cols],
                })
        finally:
            db.close()
        return {"ok": True, "results": out}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


@router.get("/db/columns")
async def db_columns(schema: str, table: str, max_cols: int = 200):
    """
    Debug/ops endpoint: lists columns for a given schema.table.
    """
    try:
        return {"ok": True, "results": list_columns(schema=schema, table=table, max_cols=max_cols)}
    except Exception as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------

@router.get("/portfolios")
async def portfolios_list():
    """List all portfolios with project counts."""
    try:
        return {"ok": True, "results": list_portfolios()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/portfolios/{portfolio_id}/summary")
async def portfolio_summary(portfolio_id: int):
    """Full summary for one portfolio: status, financials, resources, milestones, cases."""
    try:
        data = get_portfolio_summary(portfolio_id)
        if data is None:
            return JSONResponse({"ok": False, "error": "portfolio_not_found"}, status_code=404)
        return {"ok": True, "summary": data}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/portfolios/{portfolio_id}/timesheet")
async def portfolio_timesheet(portfolio_id: int):
    """Effort hours breakdown for a portfolio."""
    try:
        return {"ok": True, "data": get_portfolio_timesheet(portfolio_id)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Organisation endpoints
# ---------------------------------------------------------------------------

@router.get("/org/summary")
async def org_summary():
    """Top-level org KPIs: headcount, portfolios, projects, revenue, utilization."""
    try:
        return {"ok": True, "summary": get_org_summary()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/org/headcount")
async def org_headcount():
    """Employee distribution by department, band, grade, location."""
    try:
        return {"ok": True, "data": get_org_headcount()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/org/utilization")
async def org_utilization(days: int = 30):
    """Org-wide timesheet effort breakdown over the last N days."""
    try:
        return {"ok": True, "data": get_org_utilization(days=days)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/org/portfolio-health")
async def org_portfolio_health():
    """Portfolio health grid for the org-level view."""
    try:
        return {"ok": True, "results": get_org_portfolio_health()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# n8n Automation endpoints
# ---------------------------------------------------------------------------

def _n8n_not_configured() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "n8n_not_configured",
            "hint": "Set N8N_BASE_URL and N8N_API_KEY in server-python/.env and restart.",
        },
        status_code=503,
    )


@router.get("/n8n/health")
async def n8n_health():
    """
    Check n8n connectivity: verifies env vars are set, then pings n8n REST API.
    Returns status: configured | reachable | unreachable | not_configured
    """
    if not N8N_BASE_URL or not N8N_API_KEY:
        return {
            "ok": False,
            "status": "not_configured",
            "n8n_url": N8N_BASE_URL or None,
            "hint": "Set N8N_BASE_URL and N8N_API_KEY in server-python/.env and restart.",
        }
    try:
        import httpx as _httpx
        url = f"{N8N_BASE_URL}/api/v1/workflows?limit=1"
        with _httpx.Client(timeout=6) as client:
            resp = client.get(url, headers={"X-N8N-API-KEY": N8N_API_KEY})
        if resp.status_code == 200:
            return {
                "ok": True,
                "status": "reachable",
                "n8n_url": N8N_BASE_URL,
                "http_status": resp.status_code,
            }
        return {
            "ok": False,
            "status": "unreachable",
            "n8n_url": N8N_BASE_URL,
            "http_status": resp.status_code,
            "hint": "n8n responded but returned an error. Check N8N_API_KEY and that the Public API is enabled in n8n Settings.",
        }
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "status": "unreachable",
            "n8n_url": N8N_BASE_URL,
            "error": str(exc),
            "hint": "Cannot reach n8n. Verify N8N_BASE_URL and that n8n is running.",
        }, status_code=503)


@router.post("/n8n/webhook")
async def n8n_webhook(request: Request):
    """
    Receive execution events pushed from n8n (via n8n Trigger / Error Trigger nodes).
    n8n should send header X-N8N-Secret matching N8N_WEBHOOK_SECRET.
    """
    db = SessionLocal()
    try:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

        secret_header = request.headers.get("X-N8N-Secret")
        result = await asyncio.to_thread(process_webhook_payload, db, payload, secret_header)
        return {"ok": True, **result}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=401)
    except Exception as exc:
        logger.exception("n8n webhook error")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/n8n/dashboard")
async def n8n_dashboard():
    """Aggregated KPIs: 24h run count, failures, failure rate, avg duration, hourly chart."""
    db = SessionLocal()
    try:
        await asyncio.to_thread(ensure_tables, db)
        data = await asyncio.to_thread(get_dashboard_metrics, db)
        return {"ok": True, "data": data}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/n8n/workflows")
async def n8n_workflows():
    """All known workflows with 24h run/failure stats."""
    db = SessionLocal()
    try:
        await asyncio.to_thread(ensure_tables, db)
        data = await asyncio.to_thread(get_workflow_list, db)
        return {"ok": True, "data": data, "count": len(data)}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/n8n/executions")
async def n8n_executions(
    workflow_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """Execution history, optionally filtered by workflow_id and/or status."""
    db = SessionLocal()
    try:
        await asyncio.to_thread(ensure_tables, db)
        data = await asyncio.to_thread(get_executions, db, workflow_id, status, limit)
        return {"ok": True, "data": data, "count": len(data)}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.get("/n8n/executions/{execution_id}")
async def n8n_execution_detail(execution_id: str):
    """Single execution with full node-level trace."""
    db = SessionLocal()
    try:
        data = await asyncio.to_thread(get_execution_detail, db, execution_id)
        if data is None:
            return JSONResponse({"ok": False, "error": "execution_not_found"}, status_code=404)
        return {"ok": True, "data": data}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/n8n/sync")
async def n8n_sync():
    """Pull latest workflows and executions from n8n REST API into the local DB."""
    if not N8N_BASE_URL or not N8N_API_KEY:
        return _n8n_not_configured()
    db = SessionLocal()
    try:
        result = await asyncio.to_thread(sync_from_n8n, db)
        return {"ok": True, **result}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()


@router.post("/n8n/workflows/{workflow_id}/trigger")
async def n8n_trigger_workflow(workflow_id: str):
    """Manually trigger a workflow execution via n8n REST API."""
    if not N8N_BASE_URL or not N8N_API_KEY:
        return _n8n_not_configured()
    try:
        client = N8nClient()
        result = await asyncio.to_thread(client.trigger_workflow, workflow_id)
        return {"ok": True, "data": result}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/n8n/report")
async def n8n_report(days: int = 1):
    """AI-generated automation health summary for the last N days."""
    db = SessionLocal()
    try:
        await asyncio.to_thread(ensure_tables, db)
        report = await asyncio.to_thread(generate_ai_report, db, days)
        return {"ok": True, "report": report, "days": days}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        db.close()
