"""
n8n data access layer.

Manages two tables:
  n8n_workflows   – registry of known workflows (synced from n8n REST API)
  n8n_executions  – execution history (from webhook push + REST API polling)

Tables are created automatically on first use.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL helpers
# ---------------------------------------------------------------------------

_TABLES_DDL = """
CREATE TABLE IF NOT EXISTS n8n_workflows (
    workflow_id   TEXT PRIMARY KEY,
    name          TEXT,
    active        BOOLEAN DEFAULT FALSE,
    trigger_type  TEXT,
    tags          JSONB,
    synced_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n8n_executions (
    execution_id  TEXT PRIMARY KEY,
    workflow_id   TEXT,
    status        TEXT,
    mode          TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    duration_ms   INTEGER,
    error_message TEXT,
    node_data     JSONB,
    environment   TEXT DEFAULT 'prod',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_n8n_exec_workflow ON n8n_executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_n8n_exec_started  ON n8n_executions(started_at DESC);
"""


def ensure_tables(db: Session) -> None:
    """Create n8n tables if they don't exist. Safe to call multiple times."""
    try:
        for stmt in _TABLES_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.execute(text(stmt))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("n8n table creation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_workflow(db: Session, wf: dict) -> None:
    """Insert or update a workflow row."""
    db.execute(text("""
        INSERT INTO n8n_workflows (workflow_id, name, active, trigger_type, tags, synced_at)
        VALUES (:wid, :name, :active, :trigger_type, :tags, NOW())
        ON CONFLICT (workflow_id) DO UPDATE SET
            name         = EXCLUDED.name,
            active       = EXCLUDED.active,
            trigger_type = EXCLUDED.trigger_type,
            tags         = EXCLUDED.tags,
            synced_at    = NOW()
    """), {
        "wid":          str(wf.get("id", "")),
        "name":         str(wf.get("name", "")),
        "active":       bool(wf.get("active", False)),
        "trigger_type": _extract_trigger_type(wf),
        "tags":         json.dumps(wf.get("tags") or []),
    })


def upsert_execution(db: Session, ex: dict) -> None:
    """Insert or update an execution row."""
    started_at  = _parse_ts(ex.get("startedAt") or ex.get("started_at"))
    finished_at = _parse_ts(ex.get("stoppedAt") or ex.get("finished_at"))
    duration_ms: int | None = None
    if started_at and finished_at:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    elif ex.get("duration_ms") is not None:
        duration_ms = int(ex["duration_ms"])

    error_msg = _extract_error(ex)
    node_data = ex.get("data") or ex.get("node_data")

    db.execute(text("""
        INSERT INTO n8n_executions
            (execution_id, workflow_id, status, mode,
             started_at, finished_at, duration_ms,
             error_message, node_data, environment)
        VALUES
            (:eid, :wid, :status, :mode,
             :started_at, :finished_at, :duration_ms,
             :error_message, :node_data, :env)
        ON CONFLICT (execution_id) DO UPDATE SET
            status        = EXCLUDED.status,
            finished_at   = EXCLUDED.finished_at,
            duration_ms   = EXCLUDED.duration_ms,
            error_message = EXCLUDED.error_message,
            node_data     = EXCLUDED.node_data
    """), {
        "eid":           str(ex.get("id", "")),
        "wid":           str(ex.get("workflowId") or ex.get("workflow_id") or ""),
        "status":        str(ex.get("status") or ex.get("finished") and "success" or "unknown"),
        "mode":          str(ex.get("mode") or ""),
        "started_at":    started_at,
        "finished_at":   finished_at,
        "duration_ms":   duration_ms,
        "error_message": error_msg,
        "node_data":     json.dumps(node_data) if node_data else None,
        "env":           str(ex.get("environment") or "prod"),
    })


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_dashboard_metrics(db: Session) -> dict:
    """Aggregated KPIs for the last 24 hours."""
    try:
        totals = db.execute(text("""
            SELECT
                COUNT(*)                                          AS total_workflows,
                SUM(CASE WHEN active THEN 1 ELSE 0 END)          AS active_workflows
            FROM n8n_workflows
        """)).fetchone()

        runs = db.execute(text("""
            SELECT
                COUNT(*)                                                AS total_runs,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END)      AS total_errors,
                AVG(duration_ms)                                        AS avg_duration_ms,
                COUNT(DISTINCT workflow_id)                             AS workflows_ran
            FROM n8n_executions
            WHERE started_at >= NOW() - INTERVAL '24 hours'
        """)).fetchone()

        total_runs   = int(runs[0] or 0)
        total_errors = int(runs[1] or 0)
        avg_duration = float(runs[2] or 0)
        failure_rate = round(total_errors / total_runs * 100, 1) if total_runs else 0.0

        # Hourly breakdown for chart (last 24h)
        hourly = db.execute(text("""
            SELECT
                date_trunc('hour', started_at)                          AS hour,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)    AS success,
                SUM(CASE WHEN status = 'error'   THEN 1 ELSE 0 END)    AS error
            FROM n8n_executions
            WHERE started_at >= NOW() - INTERVAL '24 hours'
            GROUP BY 1
            ORDER BY 1
        """)).fetchall()

        return {
            "total_workflows":  int(totals[0] or 0),
            "active_workflows": int(totals[1] or 0),
            "total_runs_24h":   total_runs,
            "total_errors_24h": total_errors,
            "failure_rate_24h": failure_rate,
            "avg_duration_ms":  round(avg_duration),
            "hourly_chart":     [
                {"hour": str(r[0]), "success": int(r[1] or 0), "error": int(r[2] or 0)}
                for r in hourly
            ],
        }
    except Exception as exc:
        db.rollback()
        logger.warning("get_dashboard_metrics failed: %s", exc)
        return {
            "total_workflows": 0, "active_workflows": 0,
            "total_runs_24h": 0, "total_errors_24h": 0,
            "failure_rate_24h": 0.0, "avg_duration_ms": 0,
            "hourly_chart": [],
        }


def get_workflow_list(db: Session) -> list[dict]:
    """Workflows with their last-24h stats."""
    try:
        rows = db.execute(text("""
            SELECT
                w.workflow_id,
                w.name,
                w.active,
                w.trigger_type,
                w.synced_at,
                MAX(e.started_at)                                       AS last_run,
                COUNT(e.execution_id)                                   AS run_count,
                SUM(CASE WHEN e.status = 'error' THEN 1 ELSE 0 END)    AS failure_count,
                AVG(e.duration_ms)                                      AS avg_duration_ms
            FROM n8n_workflows w
            LEFT JOIN n8n_executions e
                ON e.workflow_id = w.workflow_id
               AND e.started_at >= NOW() - INTERVAL '24 hours'
            GROUP BY w.workflow_id, w.name, w.active, w.trigger_type, w.synced_at
            ORDER BY last_run DESC NULLS LAST
        """)).fetchall()

        return [{
            "workflow_id":   str(r[0]),
            "name":          str(r[1] or ""),
            "active":        bool(r[2]),
            "trigger_type":  str(r[3] or ""),
            "synced_at":     _fmt_ts(r[4]),
            "last_run":      _fmt_ts(r[5]),
            "run_count":     int(r[6] or 0),
            "failure_count": int(r[7] or 0),
            "avg_duration_ms": round(float(r[8] or 0)),
        } for r in rows]
    except Exception as exc:
        db.rollback()
        logger.warning("get_workflow_list failed: %s", exc)
        return []


def get_executions(
    db: Session,
    workflow_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Recent executions, optionally filtered."""
    try:
        where = "WHERE 1=1"
        params: dict[str, Any] = {"limit": min(limit, 200)}
        if workflow_id:
            where += " AND workflow_id = :wid"
            params["wid"] = workflow_id
        if status:
            where += " AND status = :status"
            params["status"] = status

        rows = db.execute(text(f"""
            SELECT execution_id, workflow_id, status, mode,
                   started_at, finished_at, duration_ms, error_message
            FROM n8n_executions
            {where}
            ORDER BY started_at DESC
            LIMIT :limit
        """), params).fetchall()

        return [{
            "execution_id": str(r[0]),
            "workflow_id":  str(r[1] or ""),
            "status":       str(r[2] or ""),
            "mode":         str(r[3] or ""),
            "started_at":   _fmt_ts(r[4]),
            "finished_at":  _fmt_ts(r[5]),
            "duration_ms":  int(r[6] or 0),
            "error_message": str(r[7] or ""),
        } for r in rows]
    except Exception as exc:
        db.rollback()
        logger.warning("get_executions failed: %s", exc)
        return []


def get_execution_detail(db: Session, execution_id: str) -> dict | None:
    """Single execution with full node_data."""
    try:
        row = db.execute(text("""
            SELECT execution_id, workflow_id, status, mode,
                   started_at, finished_at, duration_ms,
                   error_message, node_data, environment
            FROM n8n_executions
            WHERE execution_id = :eid
        """), {"eid": execution_id}).fetchone()
        if not row:
            return None
        node_data = row[8]
        if isinstance(node_data, str):
            try:
                node_data = json.loads(node_data)
            except Exception:
                pass
        return {
            "execution_id":  str(row[0]),
            "workflow_id":   str(row[1] or ""),
            "status":        str(row[2] or ""),
            "mode":          str(row[3] or ""),
            "started_at":    _fmt_ts(row[4]),
            "finished_at":   _fmt_ts(row[5]),
            "duration_ms":   int(row[6] or 0),
            "error_message": str(row[7] or ""),
            "node_data":     node_data,
            "environment":   str(row[9] or "prod"),
        }
    except Exception as exc:
        db.rollback()
        logger.warning("get_execution_detail failed: %s", exc)
        return None


def get_recent_failures(db: Session, days: int = 1) -> list[dict]:
    """Recent failed executions for AI report context."""
    try:
        rows = db.execute(text("""
            SELECT e.execution_id, w.name AS workflow_name,
                   e.started_at, e.error_message, e.duration_ms
            FROM n8n_executions e
            LEFT JOIN n8n_workflows w ON w.workflow_id = e.workflow_id
            WHERE e.status = 'error'
              AND e.started_at >= NOW() - INTERVAL '1 day' * :days
            ORDER BY e.started_at DESC
            LIMIT 20
        """), {"days": days}).fetchall()

        return [{
            "execution_id":   str(r[0]),
            "workflow_name":  str(r[1] or "Unknown"),
            "started_at":     _fmt_ts(r[2]),
            "error_message":  str(r[3] or ""),
            "duration_ms":    int(r[4] or 0),
        } for r in rows]
    except Exception as exc:
        db.rollback()
        logger.warning("get_recent_failures failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value).strip().rstrip("Z")
        if "T" in s:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _fmt_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _extract_trigger_type(wf: dict) -> str:
    nodes = wf.get("nodes") or []
    for node in nodes:
        t = (node.get("type") or "").lower()
        if "cron" in t or "schedule" in t:
            return "cron"
        if "webhook" in t:
            return "webhook"
        if "trigger" in t:
            return "trigger"
    return "manual"


def _extract_error(ex: dict) -> str:
    data = ex.get("data") or {}
    if isinstance(data, dict):
        result_data = data.get("resultData") or {}
        if isinstance(result_data, dict):
            err = result_data.get("error") or {}
            if isinstance(err, dict):
                return str(err.get("message") or "")
            if isinstance(err, str):
                return err
    return str(ex.get("error_message") or "")
