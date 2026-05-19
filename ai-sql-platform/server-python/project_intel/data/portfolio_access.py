"""
Portfolio-level data access.

All queries aggregate across the projects that belong to a portfolio.
Join key:  dbo.project.portfolioid  →  dbo.myportfolio.customobjectid
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA

IST = timedelta(hours=5, minutes=30)


def _s(table: str) -> str:
    schema = (DB_SCHEMA or "").strip() or "dbo"
    return f'"{schema}"."{table}"'


def _safe(v) -> object:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime,)):
        return (v + IST).strftime("%Y-%m-%d") if v else None
    return v


# ---------------------------------------------------------------------------
# Portfolio list
# ---------------------------------------------------------------------------

def list_portfolios() -> list[dict]:
    """
    Returns all portfolios with basic metadata and their project count.
    """
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT
                p.customobjectid        AS portfolio_id,
                p.subject               AS portfolio_name,
                p.statusid              AS status_id,
                p.startdate             AS start_date,
                p.closedate             AS close_date,
                COUNT(proj.projectid)   AS project_count,
                SUM(CASE WHEN LOWER(proj.statuscode) NOT IN
                    ('closed','completed','cancelled','inactive') THEN 1 ELSE 0 END)
                                        AS active_projects,
                SUM(CASE WHEN proj.isescalated = 1 THEN 1 ELSE 0 END)
                                        AS escalated_projects
            FROM {_s("myportfolio")} p
            LEFT JOIN {_s("project")} proj ON proj.portfolioid = p.customobjectid
            GROUP BY p.customobjectid, p.subject, p.statusid, p.startdate, p.closedate
            ORDER BY p.subject
        """)).fetchall()

        out = []
        for r in rows:
            out.append({
                "portfolio_id":      str(r[0] or ""),
                "portfolio_name":    str(r[1] or ""),
                "status_id":         r[2],
                "start_date":        _safe(r[3]),
                "close_date":        _safe(r[4]),
                "project_count":     int(r[5] or 0),
                "active_projects":   int(r[6] or 0),
                "escalated_projects": int(r[7] or 0),
            })
        return out
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Single portfolio summary
# ---------------------------------------------------------------------------

def get_portfolio_summary(portfolio_id: str | int) -> dict | None:
    """
    Full summary for one portfolio.
    Each sub-query is isolated in its own try/except so a single bad column
    type never kills the whole response.
    """
    pid = int(portfolio_id)
    db = SessionLocal()
    try:
        # --- 1. Portfolio metadata ---
        meta = db.execute(text(f"""
            SELECT customobjectid, subject, statusid, startdate, closedate
            FROM {_s("myportfolio")}
            WHERE customobjectid = :pid
        """), {"pid": pid}).fetchone()
        if not meta:
            return None

        # --- 2. Project status breakdown ---
        project_status: list[dict] = []
        total_projects = total_escalated = total_billable = 0
        try:
            status_rows = db.execute(text(f"""
                SELECT
                    statuscode,
                    COUNT(*) AS cnt,
                    SUM(CASE WHEN isescalated IS TRUE OR isescalated::text = '1' THEN 1 ELSE 0 END) AS escalated,
                    SUM(CASE WHEN billable    IS TRUE OR billable::text    = '1' THEN 1 ELSE 0 END) AS billable
                FROM {_s("project")}
                WHERE portfolioid = :pid
                GROUP BY statuscode
                ORDER BY cnt DESC
            """), {"pid": pid}).fetchall()
            for r in status_rows:
                c, e, b = int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)
                project_status.append({"status": str(r[0] or "Unknown"),
                                        "count": c, "escalated": e, "billable": b})
                total_projects += c; total_escalated += e; total_billable += b
        except Exception:
            db.rollback()

        # --- 3. Financial rollup from project_revenue VIEW ---
        financials: dict = {k: None for k in [
            "total_service_value", "total_recognized",
            "total_invoiced", "total_unbilled", "total_advance"
        ]}
        try:
            fin = db.execute(text(f"""
                SELECT
                    SUM(pr.project_service_value) AS total_service_value,
                    SUM(pr.revenue_recognized)    AS total_recognized,
                    SUM(pr.cumulative_invoice)    AS total_invoiced,
                    SUM(pr.unbilled)              AS total_unbilled,
                    SUM(pr.advance)               AS total_advance
                FROM {_s("project_revenue")} pr
                JOIN {_s("project")} proj ON proj.projectid = pr.project_id
                WHERE proj.portfolioid = :pid
            """), {"pid": pid}).fetchone()
            if fin:
                financials = {
                    "total_service_value": _safe(fin[0]),
                    "total_recognized":    _safe(fin[1]),
                    "total_invoiced":      _safe(fin[2]),
                    "total_unbilled":      _safe(fin[3]),
                    "total_advance":       _safe(fin[4]),
                }
        except Exception:
            db.rollback()

        # --- 4. Milestone health ---
        milestone_health = {"total_modules": 0, "completed_golive": 0, "delayed_modules": 0}
        try:
            today = datetime.utcnow().date()
            milestone = db.execute(text(f"""
                SELECT
                    COUNT(*) AS total_modules,
                    SUM(CASE WHEN pm.golive IS NOT NULL
                        AND pm.golive <= :today THEN 1 ELSE 0 END) AS completed_golive,
                    SUM(CASE WHEN pm.golive IS NOT NULL
                        AND pm.golive > :today
                        AND NULLIF(TRIM(pm.trailgolive::text), '') IS NOT NULL
                        AND pm.golive > NULLIF(TRIM(pm.trailgolive::text), '')::timestamp
                        THEN 1 ELSE 0 END) AS delayed_modules
                FROM {_s("projectmodule")} pm
                JOIN {_s("project")} proj ON proj.projectid = pm.relatedtoid
                WHERE proj.portfolioid = :pid
            """), {"pid": pid, "today": today}).fetchone()
            if milestone:
                milestone_health = {
                    "total_modules":    int(milestone[0] or 0),
                    "completed_golive": int(milestone[1] or 0),
                    "delayed_modules":  int(milestone[2] or 0),
                }
        except Exception:
            db.rollback()

        # --- 5. Resource allocation ---
        resources = {"allocated_employees": 0, "total_allocated_hours": None, "avg_allocation_perc": None}
        try:
            resource = db.execute(text(f"""
                SELECT
                    COUNT(DISTINCT ea.employeeid) AS allocated_employees,
                    SUM(NULLIF(ea.allocated_hr::text,   '')::numeric) AS total_allocated_hours,
                    AVG(NULLIF(ea.allocated_perc::text, '')::numeric) AS avg_allocation_perc
                FROM {_s("employeeallocation")} ea
                JOIN {_s("project")} proj ON proj.projectid = ea.projectid
                WHERE proj.portfolioid = :pid
            """), {"pid": pid}).fetchone()
            if resource:
                resources = {
                    "allocated_employees":   int(resource[0] or 0),
                    "total_allocated_hours": _safe(resource[1]),
                    "avg_allocation_perc":   _safe(resource[2]),
                }
        except Exception:
            db.rollback()

        # --- 6. Case / defect summary ---
        case_summary = {"total_cases": 0, "high_severity": 0,
                        "medium_severity": 0, "low_severity": 0, "total_reopens": 0}
        try:
            defects = db.execute(text(f"""
                SELECT
                    COUNT(*) AS total_cases,
                    SUM(CASE WHEN LOWER(severity::text) = 'high'   THEN 1 ELSE 0 END) AS high,
                    SUM(CASE WHEN LOWER(severity::text) = 'medium' THEN 1 ELSE 0 END) AS medium,
                    SUM(CASE WHEN LOWER(severity::text) = 'low'    THEN 1 ELSE 0 END) AS low,
                    SUM(COALESCE(NULLIF(reopencount::text, '')::integer, 0))           AS total_reopens
                FROM {_s("cases")} c
                JOIN {_s("project")} proj ON proj.projectid = c.relatedtoid
                WHERE proj.portfolioid = :pid
            """), {"pid": pid}).fetchone()
            if defects:
                case_summary = {
                    "total_cases":    int(defects[0] or 0),
                    "high_severity":  int(defects[1] or 0),
                    "medium_severity": int(defects[2] or 0),
                    "low_severity":   int(defects[3] or 0),
                    "total_reopens":  int(defects[4] or 0),
                }
        except Exception:
            db.rollback()

        # --- 7. Top projects ---
        projects: list[dict] = []
        try:
            proj_rows = db.execute(text(f"""
                SELECT projectid, projectname, statuscode, isescalated,
                       startdate, enddate, companyname, assigntoname
                FROM {_s("project")}
                WHERE portfolioid = :pid
                ORDER BY lastmodifiedon DESC NULLS LAST
                LIMIT 15
            """), {"pid": pid}).fetchall()
            for r in proj_rows:
                esc = r[3]
                projects.append({
                    "project_id":   str(r[0] or ""),
                    "project_name": str(r[1] or ""),
                    "status":       str(r[2] or ""),
                    "escalated":    bool(esc) if not isinstance(esc, str) else esc == "1",
                    "start_date":   _safe(r[4]),
                    "end_date":     _safe(r[5]),
                    "client":       str(r[6] or ""),
                    "pm":           str(r[7] or ""),
                })
        except Exception:
            db.rollback()

        return {
            "portfolio_id":            str(meta[0]),
            "portfolio_name":          str(meta[1] or ""),
            "status_id":               meta[2],
            "start_date":              _safe(meta[3]),
            "close_date":              _safe(meta[4]),
            "total_projects":          total_projects,
            "total_escalated":         total_escalated,
            "total_billable":          total_billable,
            "project_status_breakdown": project_status,
            "financials":              financials,
            "milestone_health":        milestone_health,
            "resources":               resources,
            "case_summary":            case_summary,
            "top_projects":            projects,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Portfolio timesheet summary
# ---------------------------------------------------------------------------

def get_portfolio_timesheet(portfolio_id: str | int, limit_employees: int = 10) -> dict:
    """
    Effort hours summary across all projects in a portfolio.
    """
    pid = int(portfolio_id)
    db = SessionLocal()
    try:
        # Total hours by engagement role
        role_rows = db.execute(text(f"""
            SELECT
                er.name         AS role_name,
                SUM(ts.effort)  AS total_minutes
            FROM {_s("timesheet")} ts
            JOIN {_s("project")} proj ON proj.projectid = ts.projectid
            LEFT JOIN {_s("engagementrole")} er ON er.engagementroleid = ts.engagementroleid
            WHERE proj.portfolioid = :pid
            GROUP BY er.name
            ORDER BY total_minutes DESC
            LIMIT 10
        """), {"pid": pid}).fetchall()

        by_role = [{"role": str(r[0] or "Unknown"),
                    "hours": round(float(r[1] or 0) / 60, 1)} for r in role_rows]

        # Total hours by project
        proj_rows = db.execute(text(f"""
            SELECT
                proj.projectname,
                SUM(ts.effort) AS total_minutes
            FROM {_s("timesheet")} ts
            JOIN {_s("project")} proj ON proj.projectid = ts.projectid
            WHERE proj.portfolioid = :pid
            GROUP BY proj.projectname
            ORDER BY total_minutes DESC
            LIMIT 10
        """), {"pid": pid}).fetchall()

        by_project = [{"project": str(r[0] or ""),
                       "hours": round(float(r[1] or 0) / 60, 1)} for r in proj_rows]

        # Grand total
        total = db.execute(text(f"""
            SELECT SUM(ts.effort)
            FROM {_s("timesheet")} ts
            JOIN {_s("project")} proj ON proj.projectid = ts.projectid
            WHERE proj.portfolioid = :pid
        """), {"pid": pid}).scalar()

        return {
            "portfolio_id": str(pid),
            "total_hours":  round(float(total or 0) / 60, 1),
            "by_role":      by_role,
            "by_project":   by_project,
        }
    except Exception:
        db.rollback()
        return {"portfolio_id": str(pid), "total_hours": 0, "by_role": [], "by_project": []}
    finally:
        db.close()


def format_portfolio_summary_text(s: dict) -> str:
    """Formats a portfolio summary dict into markdown for the chat response."""
    lines = [f"## Portfolio: {s['portfolio_name']}"]
    lines.append(f"**Projects:** {s['total_projects']} total | "
                 f"{s['total_escalated']} escalated | {s['total_billable']} billable")

    if s["project_status_breakdown"]:
        lines.append("\n### Project Status Breakdown")
        for b in s["project_status_breakdown"]:
            lines.append(f"- **{b['status']}**: {b['count']} projects"
                         + (f" ({b['escalated']} escalated)" if b["escalated"] else ""))

    f = s.get("financials", {})
    if any(v is not None for v in f.values()):
        lines.append("\n### Financials")
        if f.get("total_service_value") is not None:
            lines.append(f"- Service Value: **{f['total_service_value']:,.2f}**")
        if f.get("total_recognized") is not None:
            lines.append(f"- Revenue Recognised: **{f['total_recognized']:,.2f}**")
        if f.get("total_invoiced") is not None:
            lines.append(f"- Cumulative Invoiced: **{f['total_invoiced']:,.2f}**")
        if f.get("total_unbilled") is not None:
            lines.append(f"- Unbilled: **{f['total_unbilled']:,.2f}**")

    m = s.get("milestone_health", {})
    if m.get("total_modules"):
        lines.append("\n### Milestone Health")
        lines.append(f"- Total modules: {m['total_modules']}")
        lines.append(f"- Go-lives completed: {m['completed_golive']}")
        lines.append(f"- Delayed modules: {m['delayed_modules']}")

    r = s.get("resources", {})
    if r.get("allocated_employees"):
        lines.append("\n### Resource Allocation")
        lines.append(f"- Allocated employees: {r['allocated_employees']}")
        if r.get("total_allocated_hours"):
            lines.append(f"- Total allocated hours: {r['total_allocated_hours']:,.0f}")
        if r.get("avg_allocation_perc"):
            lines.append(f"- Avg allocation %: {r['avg_allocation_perc']:.1f}%")

    c = s.get("case_summary", {})
    if c.get("total_cases"):
        lines.append("\n### QA / Defect Summary")
        lines.append(f"- Total cases: {c['total_cases']}")
        lines.append(f"- High: {c['high_severity']} | Medium: {c['medium_severity']} | Low: {c['low_severity']}")
        lines.append(f"- Total reopens: {c['total_reopens']}")

    if s.get("top_projects"):
        lines.append("\n### Recent Projects")
        for p in s["top_projects"][:8]:
            esc = " ⚠️" if p["escalated"] else ""
            lines.append(f"- **{p['project_name']}**{esc} — {p['status']} | Client: {p['client'] or 'N/A'}")

    return "\n".join(lines)
