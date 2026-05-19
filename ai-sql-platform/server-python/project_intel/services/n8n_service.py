"""
n8n service layer.

Responsibilities:
- N8nClient: thin httpx wrapper around n8n REST API v1
- sync_from_n8n: pull workflows + recent executions → upsert into DB
- process_webhook_payload: validate + store an incoming execution event
- generate_ai_report: build an LLM-powered daily automation summary
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from project_intel.core.config import N8N_API_KEY, N8N_BASE_URL, N8N_WEBHOOK_SECRET
from project_intel.core.openai_client import get_openai_clients
from project_intel.core.config import OPENAI_MODEL
from project_intel.data.n8n_access import (
    ensure_tables,
    get_dashboard_metrics,
    get_recent_failures,
    upsert_execution,
    upsert_workflow,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# n8n REST API client
# ---------------------------------------------------------------------------

class N8nClient:
    """Synchronous httpx client for n8n REST API v1."""

    def __init__(self) -> None:
        if not N8N_BASE_URL:
            raise RuntimeError("N8N_BASE_URL is not configured.")
        if not N8N_API_KEY:
            raise RuntimeError("N8N_API_KEY is not configured.")
        self._base = N8N_BASE_URL
        self._headers = {
            "X-N8N-API-KEY": N8N_API_KEY,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base}/api/v1{path}"
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=self._headers, params=params or {})
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, body: dict | None = None) -> Any:
        url = f"{self._base}/api/v1{path}"
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=self._headers, json=body or {})
            resp.raise_for_status()
            return resp.json()

    def list_workflows(self) -> list[dict]:
        data = self._get("/workflows")
        return data.get("data") or data if isinstance(data, list) else []

    def list_executions(
        self,
        workflow_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        data = self._get("/executions", params=params)
        return data.get("data") or data if isinstance(data, list) else []

    def get_execution(self, execution_id: str) -> dict:
        return self._get(f"/executions/{execution_id}")

    def trigger_workflow(self, workflow_id: str) -> dict:
        return self._post(f"/workflows/{workflow_id}/run")


# ---------------------------------------------------------------------------
# Sync: pull from n8n REST API → upsert into DB
# ---------------------------------------------------------------------------

def sync_from_n8n(db: Session) -> dict:
    """
    Pull all workflows and up to 200 recent executions from n8n and store
    them locally. Returns a summary dict.
    """
    ensure_tables(db)
    client = N8nClient()

    # Sync workflows
    workflows = client.list_workflows()
    wf_count = 0
    for wf in workflows:
        try:
            upsert_workflow(db, wf)
            wf_count += 1
        except Exception as exc:
            logger.warning("Failed to upsert workflow %s: %s", wf.get("id"), exc)
            db.rollback()

    db.commit()

    # Sync recent executions (last 200)
    executions = client.list_executions(limit=200)
    ex_count = 0
    for ex in executions:
        try:
            upsert_execution(db, ex)
            ex_count += 1
        except Exception as exc:
            logger.warning("Failed to upsert execution %s: %s", ex.get("id"), exc)
            db.rollback()

    db.commit()

    return {
        "workflows_synced": wf_count,
        "executions_synced": ex_count,
    }


# ---------------------------------------------------------------------------
# Webhook: receive and store an execution event pushed by n8n
# ---------------------------------------------------------------------------

def process_webhook_payload(
    db: Session,
    payload: dict,
    secret_header: str | None,
) -> dict:
    """
    Validate the incoming webhook, normalise it into an execution row, upsert.
    Returns {"ok": True} or raises ValueError on auth failure.
    """
    # Validate shared secret (simple equality; n8n sends it as a custom header)
    if N8N_WEBHOOK_SECRET:
        if not secret_header or not hmac.compare_digest(
            secret_header.strip(), N8N_WEBHOOK_SECRET
        ):
            raise ValueError("Invalid webhook secret.")

    ensure_tables(db)

    # n8n webhook payload shape can vary by node type; normalise here
    execution_data = payload.get("execution") or payload
    upsert_execution(db, execution_data)
    db.commit()

    return {"ok": True, "execution_id": str(execution_data.get("id", ""))}


# ---------------------------------------------------------------------------
# AI report
# ---------------------------------------------------------------------------

def generate_ai_report(db: Session, days: int = 1) -> str:
    """Generate a markdown automation health report using OpenAI."""
    clients = get_openai_clients()
    if not clients:
        return "_AI report unavailable: OPENAI_API_KEY not configured._"

    metrics = get_dashboard_metrics(db)
    failures = get_recent_failures(db, days=days)

    failure_lines = "\n".join(
        f"- [{f['workflow_name']}] at {f['started_at']}: {f['error_message'][:200]}"
        for f in failures[:10]
    ) or "None"

    prompt = f"""You are an automation operations analyst. Write a concise markdown report (under 300 words) summarising the n8n workflow automation health for the last {days} day(s).

**Key Metrics (last {days}d):**
- Total runs: {metrics['total_runs_24h']}
- Failed runs: {metrics['total_errors_24h']}
- Failure rate: {metrics['failure_rate_24h']}%
- Avg execution time: {metrics['avg_duration_ms']} ms
- Active workflows: {metrics['active_workflows']} / {metrics['total_workflows']}

**Recent Failures:**
{failure_lines}

Write sections: Executive Summary, Notable Failures (with likely root cause), Recommendations.
Use bullet points. Be direct and actionable. Output markdown only."""

    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("AI report generation failed: %s", exc)

    return "_AI report generation failed. Check OPENAI_API_KEY and model access._"
