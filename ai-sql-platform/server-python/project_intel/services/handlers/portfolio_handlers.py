"""
Portfolio-level and Organisation-level chat handlers.

handler_index = 4  (portfolio)
handler_index = 5  (org)
"""
from __future__ import annotations

import re

from project_intel.data.portfolio_access import (
    list_portfolios,
    get_portfolio_summary,
    get_portfolio_timesheet,
    format_portfolio_summary_text,
)
from project_intel.data.org_access import (
    get_org_summary,
    get_org_headcount,
    get_org_utilization,
    get_org_portfolio_health,
    format_org_summary_text,
    format_portfolio_health_text,
    format_utilization_text,
)

HandlerResult = dict | None


def _extract_portfolio_id(text: str) -> int | None:
    """Pull a numeric portfolio id from the text, e.g. 'portfolio 42' or 'id 42'."""
    m = re.search(r"portfolio\s*(?:id\s*)?[:\-]?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\bid\s*[:\-]?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def handle_portfolio(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes portfolio-level queries."""

    # ----- list portfolios -----
    if any(kw in lower for kw in [
        "list portfolio", "show portfolio", "all portfolio",
        "portfolio list", "portfolios available", "portfolios in system",
    ]):
        rows = list_portfolios()
        if not rows:
            return {"handled": True, "message": "No portfolios found in the system."}
        lines = ["## Portfolios", "",
                 "| Portfolio | Projects | Active | Escalated |",
                 "|---|---|---|---|"]
        for r in rows:
            esc = f"**{r['escalated_projects']}** ⚠️" if r["escalated_projects"] else str(r["escalated_projects"])
            lines.append(f"| {r['portfolio_name']} (ID {r['portfolio_id']}) "
                         f"| {r['project_count']} | {r['active_projects']} | {esc} |")
        return {"handled": True, "message": "\n".join(lines)}

    # ----- portfolio summary / health -----
    if any(kw in lower for kw in [
        "portfolio summary", "portfolio health", "portfolio status",
        "portfolio overview", "portfolio report", "portfolio details",
        "show portfolio", "portfolio dashboard",
    ]):
        pid = _extract_portfolio_id(text)
        if pid is None:
            # Return the portfolio list so the user can pick one
            rows = list_portfolios()
            if not rows:
                return {"handled": True, "message": "No portfolios found."}
            lines = ["## Select a Portfolio", "",
                     "Please include the portfolio ID in your query, e.g. `portfolio summary portfolio id 12`", "",
                     "| ID | Portfolio | Projects | Active |",
                     "|---|---|---|---|"]
            for r in rows:
                lines.append(f"| {r['portfolio_id']} | {r['portfolio_name']} "
                             f"| {r['project_count']} | {r['active_projects']} |")
            return {"handled": True, "message": "\n".join(lines)}

        data = get_portfolio_summary(pid)
        if data is None:
            return {"handled": True, "message": f"Portfolio ID {pid} not found."}
        return {"handled": True, "message": format_portfolio_summary_text(data)}

    # ----- portfolio timesheet / utilization -----
    if any(kw in lower for kw in [
        "portfolio timesheet", "portfolio utilization", "portfolio hours",
        "portfolio effort", "portfolio resource hours",
    ]):
        pid = _extract_portfolio_id(text)
        if pid is None:
            return {"handled": True,
                    "message": "Please provide a portfolio ID, e.g. `portfolio timesheet portfolio id 12`."}
        data = get_portfolio_timesheet(pid)
        lines = [f"## Portfolio {pid} — Timesheet Summary",
                 f"**Total hours logged:** {data['total_hours']:,.1f} hrs",
                 "", "### By Project"]
        for r in data.get("by_project", []):
            lines.append(f"- {r['project']}: **{r['hours']:,.1f} hrs**")
        if data.get("by_role"):
            lines.append("\n### By Engagement Role")
            for r in data["by_role"]:
                lines.append(f"- {r['role']}: **{r['hours']:,.1f} hrs**")
        return {"handled": True, "message": "\n".join(lines)}

    # ----- portfolio financials -----
    if any(kw in lower for kw in [
        "portfolio revenue", "portfolio billing", "portfolio financials",
        "portfolio financial", "portfolio invoice", "portfolio unbilled",
    ]):
        pid = _extract_portfolio_id(text)
        if pid is None:
            return {"handled": True,
                    "message": "Please provide a portfolio ID, e.g. `portfolio revenue portfolio id 12`."}
        data = get_portfolio_summary(pid)
        if data is None:
            return {"handled": True, "message": f"Portfolio ID {pid} not found."}
        f = data.get("financials", {})
        lines = [f"## Portfolio {data['portfolio_name']} — Financials"]
        for label, key in [
            ("Service Value", "total_service_value"),
            ("Revenue Recognised", "total_recognized"),
            ("Cumulative Invoiced", "total_invoiced"),
            ("Unbilled", "total_unbilled"),
            ("Advance", "total_advance"),
        ]:
            v = f.get(key)
            if v is not None:
                lines.append(f"- **{label}:** {float(v):,.2f}")
        return {"handled": True, "message": "\n".join(lines)}

    return None


def handle_org(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes organisation-level queries."""

    # ----- org summary -----
    if any(kw in lower for kw in [
        "org summary", "organisation summary", "organization summary",
        "org overview", "org dashboard", "org kpi", "org report",
        "overall summary", "company summary", "enterprise summary",
    ]):
        data = get_org_summary()
        if "error" in data:
            return {"handled": True, "message": f"Error fetching org summary: {data['error']}"}
        return {"handled": True, "message": format_org_summary_text(data)}

    # ----- headcount -----
    if any(kw in lower for kw in [
        "how many employee", "total employee", "headcount", "total staff",
        "employee count", "org headcount", "workforce size",
        "how many people", "total workforce",
    ]):
        data = get_org_headcount()
        lines = [f"## Organisation Headcount",
                 f"**Total employees:** {data.get('total', 0):,}"]
        if data.get("by_department"):
            lines.append("\n### By Department")
            for r in data["by_department"][:10]:
                lines.append(f"- Dept {r['id']}: {r['count']} employees")
        if data.get("by_band"):
            lines.append("\n### By Band")
            for r in data["by_band"]:
                lines.append(f"- Band {r['id']}: {r['count']} employees")
        return {"handled": True, "message": "\n".join(lines)}

    # ----- org revenue / financials -----
    if any(kw in lower for kw in [
        "total revenue", "org revenue", "organisation revenue", "overall revenue",
        "org billing", "total billing", "org financial", "org unbilled",
        "org invoice", "total service value", "revenue pipeline",
    ]):
        data = get_org_summary()
        f = data.get("financials", {})
        lines = ["## Organisation — Revenue Pipeline"]
        for label, key in [
            ("Total Service Value", "total_service_value"),
            ("Revenue Recognised", "total_recognized"),
            ("Cumulative Invoiced", "total_invoiced"),
            ("Unbilled", "total_unbilled"),
            ("Advance", "total_advance"),
        ]:
            v = f.get(key)
            if v is not None:
                lines.append(f"- **{label}:** {float(v):,.2f}")
        return {"handled": True, "message": "\n".join(lines)}

    # ----- org utilization -----
    if any(kw in lower for kw in [
        "org utilization", "organisation utilization", "overall utilization",
        "org hours", "total hours logged", "org timesheet", "overall timesheet",
        "billable hours", "org effort",
    ]):
        days = 30
        m = re.search(r"(\d+)\s*day", lower)
        if m:
            days = min(int(m.group(1)), 365)
        data = get_org_utilization(days=days)
        return {"handled": True, "message": format_utilization_text(data)}

    # ----- org portfolio health grid -----
    if any(kw in lower for kw in [
        "portfolio health", "all portfolio", "portfolio grid",
        "portfolio status overview", "portfolio overview",
        "org portfolio", "organisation portfolio",
    ]):
        rows = get_org_portfolio_health()
        if not rows:
            return {"handled": True, "message": "No portfolio data found."}
        return {"handled": True, "message": format_portfolio_health_text(rows)}

    # ----- org project count -----
    if any(kw in lower for kw in [
        "how many project", "total project", "org project count",
        "all project count", "number of project",
    ]):
        data = get_org_summary()
        msg = (f"## Organisation — Project Overview\n"
               f"- **Total projects:** {data.get('total_projects', 0):,}\n"
               f"- **Active:** {data.get('active_projects', 0)}\n"
               f"- **Escalated:** {data.get('escalated_projects', 0)}\n"
               f"- **Billable:** {data.get('billable_projects', 0)}\n"
               f"- **Total portfolios:** {data.get('portfolio_count', 0)}")
        return {"handled": True, "message": msg}

    return None
