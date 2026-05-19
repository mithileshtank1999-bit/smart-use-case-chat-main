"""
Organisation-level data access.

All queries aggregate across the entire database — no project or portfolio filter.
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
    if isinstance(v, datetime):
        return (v + IST).strftime("%Y-%m-%d")
    return v


# ---------------------------------------------------------------------------
# Org KPI snapshot
# ---------------------------------------------------------------------------

def get_org_summary() -> dict:
    """
    Top-level org KPIs: headcount, portfolios, projects, revenue, billing.
    """
    db = SessionLocal()
    try:
        # Headcount
        headcount = 0
        try:
            headcount = db.execute(text(
                f"SELECT COUNT(*) FROM {_s('employee')}"
            )).scalar() or 0
        except Exception:
            db.rollback()

        # Portfolio count
        portfolio_count = 0
        try:
            portfolio_count = db.execute(text(
                f"SELECT COUNT(*) FROM {_s('myportfolio')}"
            )).scalar() or 0
        except Exception:
            db.rollback()

        # Project counts by status
        total_projects = active_projects = escalated_count = billable_count = 0
        try:
            proj_rows = db.execute(text(f"""
                SELECT
                    COUNT(*)                                            AS total,
                    SUM(CASE WHEN LOWER(statuscode) NOT IN
                        ('closed','completed','cancelled','inactive','dropped')
                        THEN 1 ELSE 0 END)                              AS active,
                    SUM(CASE WHEN isescalated IS TRUE OR isescalated::text = '1' THEN 1 ELSE 0 END) AS escalated,
                    SUM(CASE WHEN billable    IS TRUE OR billable::text    = '1' THEN 1 ELSE 0 END) AS billable
                FROM {_s('project')}
            """)).fetchone()
            if proj_rows:
                total_projects  = int(proj_rows[0] or 0)
                active_projects = int(proj_rows[1] or 0)
                escalated_count = int(proj_rows[2] or 0)
                billable_count  = int(proj_rows[3] or 0)
        except Exception:
            db.rollback()

        # Financial rollup from project_revenue VIEW
        financials: dict = {k: None for k in [
            "total_service_value", "total_recognized",
            "total_invoiced", "total_unbilled", "total_advance"
        ]}
        try:
            fin = db.execute(text(f"""
                SELECT
                    SUM(project_service_value) AS total_service_value,
                    SUM(revenue_recognized)    AS total_recognized,
                    SUM(cumulative_invoice)    AS total_invoiced,
                    SUM(unbilled)              AS total_unbilled,
                    SUM(advance)               AS total_advance
                FROM {_s('project_revenue')}
            """)).fetchone()
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

        # Client / account count
        client_count = 0
        try:
            client_count = db.execute(text(
                f"SELECT COUNT(*) FROM {_s('accounts')}"
            )).scalar() or 0
        except Exception:
            db.rollback()

        # Contract value
        contract_count = 0
        contract_value = None
        try:
            contract = db.execute(text(f"""
                SELECT COUNT(*), SUM(amount)
                FROM {_s('contracts')}
                WHERE LOWER(status) NOT IN ('cancelled','expired')
            """)).fetchone()
            if contract:
                contract_count = int(contract[0] or 0)
                contract_value = _safe(contract[1])
        except Exception:
            db.rollback()

        # Total timesheet hours logged (last 90 days)
        hours_90d = 0.0
        try:
            ts = db.execute(text(f"""
                SELECT SUM(effort)
                FROM {_s('timesheet')}
                WHERE createdon >= NOW() - INTERVAL '90 days'
            """)).scalar()
            hours_90d = round(float(ts or 0) / 60, 1)
        except Exception:
            db.rollback()

        return {
            "headcount":          int(headcount),
            "portfolio_count":    int(portfolio_count),
            "total_projects":     total_projects,
            "active_projects":    active_projects,
            "escalated_projects": escalated_count,
            "billable_projects":  billable_count,
            "client_count":       int(client_count),
            "contract_count":     contract_count,
            "contract_value":     contract_value,
            "hours_last_90d":     hours_90d,
            "financials":         financials,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Org headcount breakdown
# ---------------------------------------------------------------------------

def get_org_headcount() -> dict:
    """
    Employee distribution by department, band, grade, and location.
    """
    db = SessionLocal()
    try:
        dept_rows = db.execute(text(f"""
            SELECT departmentid, COUNT(*) AS cnt
            FROM {_s('employee')}
            WHERE departmentid IS NOT NULL
            GROUP BY departmentid ORDER BY cnt DESC LIMIT 15
        """)).fetchall()

        band_rows = db.execute(text(f"""
            SELECT bandid, COUNT(*) AS cnt
            FROM {_s('employee')}
            WHERE bandid IS NOT NULL
            GROUP BY bandid ORDER BY cnt DESC LIMIT 10
        """)).fetchall()

        grade_rows = db.execute(text(f"""
            SELECT gradeid, COUNT(*) AS cnt
            FROM {_s('employee')}
            WHERE gradeid IS NOT NULL
            GROUP BY gradeid ORDER BY cnt DESC LIMIT 10
        """)).fetchall()

        location_rows = db.execute(text(f"""
            SELECT locationid, COUNT(*) AS cnt
            FROM {_s('employee')}
            WHERE locationid IS NOT NULL
            GROUP BY locationid ORDER BY cnt DESC LIMIT 10
        """)).fetchall()

        total = db.execute(text(
            f"SELECT COUNT(*) FROM {_s('employee')}"
        )).scalar() or 0

        return {
            "total":     int(total),
            "by_department": [{"id": str(r[0]), "count": int(r[1])} for r in dept_rows],
            "by_band":       [{"id": str(r[0]), "count": int(r[1])} for r in band_rows],
            "by_grade":      [{"id": str(r[0]), "count": int(r[1])} for r in grade_rows],
            "by_location":   [{"id": str(r[0]), "count": int(r[1])} for r in location_rows],
        }
    except Exception as e:
        db.rollback()
        return {"total": 0, "error": str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Org utilization (timesheet)
# ---------------------------------------------------------------------------

def get_org_utilization(days: int = 30) -> dict:
    """
    Org-wide timesheet effort over the last N days broken down by role.
    """
    db = SessionLocal()
    try:
        role_rows = db.execute(text(f"""
            SELECT
                er.name             AS role_name,
                COUNT(DISTINCT ts.assigntoid) AS employee_count,
                SUM(ts.effort)      AS total_minutes
            FROM {_s('timesheet')} ts
            LEFT JOIN {_s('engagementrole')} er ON er.engagementroleid = ts.engagementroleid
            WHERE ts.createdon >= NOW() - INTERVAL '{days} days'
            GROUP BY er.name
            ORDER BY total_minutes DESC
            LIMIT 15
        """)).fetchall()

        by_role = [{
            "role":      str(r[0] or "Unclassified"),
            "employees": int(r[1] or 0),
            "hours":     round(float(r[2] or 0) / 60, 1),
        } for r in role_rows]

        account_rows = db.execute(text(f"""
            SELECT
                ts.accountid,
                COUNT(DISTINCT ts.assigntoid) AS employee_count,
                SUM(ts.effort) AS total_minutes
            FROM {_s('timesheet')} ts
            WHERE ts.createdon >= NOW() - INTERVAL '{days} days'
              AND ts.accountid IS NOT NULL
            GROUP BY ts.accountid
            ORDER BY total_minutes DESC
            LIMIT 10
        """)).fetchall()

        by_account = [{
            "account_id": str(r[0]),
            "employees":  int(r[1] or 0),
            "hours":      round(float(r[2] or 0) / 60, 1),
        } for r in account_rows]

        total = db.execute(text(f"""
            SELECT SUM(effort)
            FROM {_s('timesheet')}
            WHERE createdon >= NOW() - INTERVAL '{days} days'
        """)).scalar()

        return {
            "period_days": days,
            "total_hours": round(float(total or 0) / 60, 1),
            "by_role":     by_role,
            "by_account":  by_account,
        }
    except Exception as e:
        db.rollback()
        return {"period_days": days, "total_hours": 0, "by_role": [], "by_account": [], "error": str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Org portfolio health grid
# ---------------------------------------------------------------------------

def get_org_portfolio_health() -> list[dict]:
    """
    One row per portfolio showing project status counts — the org-level grid.
    """
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT
                p.customobjectid,
                p.subject                                           AS portfolio_name,
                COUNT(proj.projectid)                               AS total,
                SUM(CASE WHEN LOWER(proj.statuscode) NOT IN
                    ('closed','completed','cancelled','inactive')
                    THEN 1 ELSE 0 END)                              AS active,
                SUM(CASE WHEN proj.isescalated IS TRUE OR proj.isescalated::text = '1' THEN 1 ELSE 0 END) AS escalated,
                SUM(CASE WHEN LOWER(proj.statuscode) IN
                    ('closed','completed') THEN 1 ELSE 0 END)      AS closed
            FROM {_s('myportfolio')} p
            LEFT JOIN {_s('project')} proj ON proj.portfolioid = p.customobjectid
            GROUP BY p.customobjectid, p.subject
            HAVING COUNT(proj.projectid) > 0
            ORDER BY active DESC, total DESC
        """)).fetchall()

        return [{
            "portfolio_id":   str(r[0]),
            "portfolio_name": str(r[1] or ""),
            "total":      int(r[2] or 0),
            "active":     int(r[3] or 0),
            "escalated":  int(r[4] or 0),
            "closed":     int(r[5] or 0),
        } for r in rows]
    except Exception as e:
        db.rollback()
        return []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Text formatters for chat responses
# ---------------------------------------------------------------------------

def format_org_summary_text(s: dict) -> str:
    lines = ["## Organisation Summary"]
    lines.append(f"- **Employees:** {s.get('headcount', 0):,}")
    lines.append(f"- **Portfolios:** {s.get('portfolio_count', 0)}")
    lines.append(f"- **Projects:** {s.get('total_projects', 0):,} total | "
                 f"{s.get('active_projects', 0)} active | "
                 f"{s.get('escalated_projects', 0)} escalated")
    lines.append(f"- **Clients / Accounts:** {s.get('client_count', 0):,}")
    if s.get("contract_count"):
        lines.append(f"- **Active Contracts:** {s['contract_count']:,}")
    if s.get("hours_last_90d"):
        lines.append(f"- **Hours logged (last 90 days):** {s['hours_last_90d']:,.1f} hrs")
    f = s.get("financials", {})
    if f.get("total_service_value") is not None:
        lines.append("\n### Revenue Pipeline")
        lines.append(f"- Service Value: **{f['total_service_value']:,.2f}**")
        if f.get("total_recognized") is not None:
            lines.append(f"- Revenue Recognised: **{f['total_recognized']:,.2f}**")
        if f.get("total_invoiced") is not None:
            lines.append(f"- Cumulative Invoiced: **{f['total_invoiced']:,.2f}**")
        if f.get("total_unbilled") is not None:
            lines.append(f"- Unbilled: **{f['total_unbilled']:,.2f}**")
    return "\n".join(lines)


def format_portfolio_health_text(rows: list[dict]) -> str:
    lines = ["## Organisation — Portfolio Health Grid",
             "",
             "| Portfolio | Total | Active | Escalated | Closed |",
             "|---|---|---|---|---|"]
    for r in rows:
        esc = f"**{r['escalated']}** ⚠️" if r["escalated"] else str(r["escalated"])
        lines.append(f"| {r['portfolio_name']} | {r['total']} | {r['active']} | {esc} | {r['closed']} |")
    return "\n".join(lines)


def format_utilization_text(u: dict) -> str:
    lines = [f"## Org Utilization — Last {u['period_days']} Days",
             f"**Total hours logged:** {u['total_hours']:,.1f} hrs",
             "",
             "### By Engagement Role"]
    for r in u.get("by_role", []):
        lines.append(f"- {r['role']}: **{r['hours']:,.1f} hrs** ({r['employees']} employees)")
    return "\n".join(lines)
