from __future__ import annotations

import logging
import os

from project_intel.core.config import EMBEDDING_MODEL_NAME, OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import (
    fetch_rows_sqlalchemy,
    get_project_columns,
    get_project_id_column,
    get_project_name_column,
    get_project_table_name,
    make_json_safe,
    normalize_project_row,
)
from project_intel.services.rag_core import (
    ChromaRagIndex,
    HybridRagIndex,
    LocalSentenceTransformerEmbedder,
    chunk_project_row,
    parse_project_name_from_query,
)

logger = logging.getLogger(__name__)

_CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "").strip()


def is_pmo_rag_use_case(user_question: str) -> str | None:
    q = (user_question or "").lower()
    if any(k in q for k in ["milestones summary", "timeline milestones", "key timeline milestones"]):
        return "timeline"
    if any(k in q for k in ["health status", "health summary", "project health"]):
        return "health"
    if any(k in q for k in ["risk indicators", "risk summary", "project risk"]):
        return "risk"
    return None


RAG_INDEX: HybridRagIndex | ChromaRagIndex | None = None
RAG_INDEX_ERROR: str | None = None


def ensure_rag_index() -> HybridRagIndex | ChromaRagIndex | None:
    global RAG_INDEX, RAG_INDEX_ERROR
    if RAG_INDEX is not None:
        return RAG_INDEX
    if RAG_INDEX_ERROR:
        return None

    try:
        embedder = LocalSentenceTransformerEmbedder(EMBEDDING_MODEL_NAME)
        if _CHROMA_PERSIST_DIR:
            RAG_INDEX = ChromaRagIndex(_CHROMA_PERSIST_DIR, embedder)
            logger.info(
                "RAG: ChromaDB persistent index at %s (docs=%d)",
                _CHROMA_PERSIST_DIR,
                RAG_INDEX.size,
            )
        else:
            RAG_INDEX = HybridRagIndex(embedder)
            logger.info("RAG: in-memory FAISS index (set CHROMA_PERSIST_DIR for persistence)")
        return RAG_INDEX
    except Exception as exc:
        RAG_INDEX_ERROR = str(exc)
        logger.error("RAG init error: %s", RAG_INDEX_ERROR)
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

    table_name = get_project_table_name()
    id_col = get_project_id_column()
    name_col = get_project_name_column()

    if project_id:
        where_sql = f" WHERE {id_col} = :pid"
        params["pid"] = project_id
    elif project_name:
        where_sql = f" WHERE {name_col} LIKE :pname"
        params["pname"] = f"%{project_name}%"
    if available:
        sql = f"SELECT {', '.join(available)} FROM {table_name}{where_sql} ORDER BY {id_col}"
    else:
        sql = f"SELECT * FROM {table_name}{where_sql} ORDER BY {id_col}"

    rows = fetch_rows_sqlalchemy(sql, params)
    if not isinstance(rows, list):
        rows = []

    idx.clear()
    docs_added = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        docs = chunk_project_row(normalize_project_row(row))
        idx.add_documents(docs)
        docs_added += len(docs)

    return {
        "ok": True,
        "projects": len(rows),
        "documents": docs_added,
        "embedding_model": EMBEDDING_MODEL_NAME,
    }


def build_rag_prompt(use_case: str, project_name: str, context_docs: list[dict]) -> str:
    """
    Builds the instruction prompt for the LLM.

    Keep this prompt ASCII-safe: some terminals and file encodings produced mojibake
    for emoji + special dash characters, which degrades model responses and UX.
    """
    import json

    context_json = json.dumps(context_docs, ensure_ascii=False, indent=2)
    project_label = project_name or "Selected project"

    if use_case == "timeline":
        return f"""
You are a PMO AI Assistant responsible for generating a Key Timeline Milestones Summary for an individual project for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). Do not guess missing dates; use "Not available".

Output (markdown):
## Milestones Overview
| Milestone | Date/Range |
|---|---|
| Project Start Date | ... |
| FSD Sign Off | ... |
| Development Phase | ... |
| SIT Phase | ... |
| UAT Phase | ... |
| Go-Live Date | ... |

## Summary Highlights
- <2-3 bullets, 1 sentence each>

The LAST line must be exactly:
Overall Timeline Health: <Green/Amber/Red> - <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""

    if use_case == "health":
        return f"""
You are a PMO AI Assistant generating an Executive Project Health Summary for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). Do not infer numbers or dates that are not present.

Output (markdown):
## Health Snapshot
- Overall: ...
- Schedule: ...
- Financial: ...
- Delivery: ...
- Risk: ...

## Key Drivers
- <2-4 bullets, 1 sentence each>

The LAST line must be exactly:
Overall Health: <Green/Amber/Red> - <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""

    return f"""
You are a PMO AI Assistant generating a concise Risk Indicators Summary for leadership review.

Use ONLY the evidence in the Context Chunks (JSON). If risks are missing, say so clearly.

Output (markdown):
## Risk Indicators
- <3-6 bullets; include severity/impact when available>

## Mitigation Focus
- <2-4 bullets; actionable, ownership-oriented>

The LAST line must be exactly:
Overall Risk Posture: <Green/Amber/Red> - <1 sentence rationale>

Project: {project_label}

Context Chunks (JSON):
{context_json}
"""


def chat_via_rag(user_msg: str) -> dict:
    rag_use_case = is_pmo_rag_use_case(user_msg)
    if not rag_use_case:
        return {"handled": False}

    idx = ensure_rag_index()
    if idx is None:
        return {
            "handled": True,
            "message": "RAG is not available in this environment.",
            "error": RAG_INDEX_ERROR or "rag_unavailable",
        }

    project_name = parse_project_name_from_query(user_msg)
    if idx.size == 0:
        rebuild_rag_index(project_name=project_name or None)

    chunk_types = (
        {"milestone"}
        if rag_use_case == "timeline"
        else ({"health", "governance"} if rag_use_case == "health" else {"risk", "health"})
    )
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

    clients = get_openai_clients()
    if not clients:
        return {
            "handled": True,
            "message": "OpenAI is not configured for RAG responses. Set OPENAI_API_KEY (or OPENAI_API_KEYS) and restart the server.",
            "error": "missing_openai_api_key",
        }

    last_error = ""
    for client in clients:
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            content = (response.choices[0].message.content or "").strip()
            return {"handled": True, "message": content or "No matching context found for this request."}
        except Exception as error:
            last_error = str(error)
            status_code = getattr(error, "status_code", None)
            if status_code is None:
                resp = getattr(error, "response", None)
                status_code = getattr(resp, "status_code", None)
            if status_code in (401, 403, 404, 429):
                continue
            return {"handled": True, "message": "RAG request failed.", "error": last_error or "rag_error"}

    return {"handled": True, "message": "RAG request failed.", "error": last_error or "rag_error"}
