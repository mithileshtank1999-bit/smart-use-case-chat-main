from __future__ import annotations

from project_intel.data.timesheet_access import (
    get_account_timesheet_summary,
    get_employee_timesheet_summary,
    get_model_timesheet_summary,
    get_org_timesheet_summary,
    get_pending_timesheet_report,
    get_portfolio_timesheet_summary,
    get_project_timesheet_summary,
)
from project_intel.services.handlers.formatters import fmt_timesheet_table
from project_intel.services.handlers.helpers import extract_after

HandlerResult = dict | None


def handle(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes timesheet summary use cases. Returns None if not matched."""

    if "individual employee timesheet summary" in lower or (
        "employee timesheet summary" in lower and "individual" in lower
    ):
        employee_name = extract_after(text, "for employee")
        if not employee_name:
            return {"handled": True, "message": "Please provide an employee name (e.g. `... for employee John Doe`)."}
        result = get_employee_timesheet_summary(employee_name=employee_name)
        if not result.ok:
            note = f"\n\n_{result.note}_" if result.note else ""
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`{note}"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title=f"Timesheet Summary – {employee_name}",
                rows=result.rows or [],
                note=result.note,
            ),
        }

    if "model-wise timesheet booking summary" in lower or "model wise timesheet booking summary" in lower:
        model_name = extract_after(text, "for model")
        if not model_name:
            return {"handled": True, "message": "Please provide a model name (e.g. `... for model Config`)."}
        result = get_model_timesheet_summary(model_name=model_name)
        if not result.ok:
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title=f"Model-wise Timesheet Summary – {model_name}",
                rows=result.rows or [],
            ),
        }

    if "project-wise timesheet booking summary" in lower or "project wise timesheet booking summary" in lower:
        project_name = extract_after(text, "for project")
        if not project_name:
            return {"handled": True, "message": "Please provide a project name (e.g. `... for project Apollo`)."}
        result = get_project_timesheet_summary(project_name=project_name)
        if not result.ok:
            note = f"\n\n_{result.note}_" if result.note else ""
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`{note}"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title=f"Project-wise Timesheet Summary – {project_name}",
                rows=result.rows or [],
                note=result.note,
            ),
        }

    if "account-wise timesheet booking summary" in lower or "account wise timesheet booking summary" in lower:
        account_name = extract_after(text, "for account")
        if not account_name:
            return {"handled": True, "message": "Please provide an account name (e.g. `... for account Acme Corp`)."}
        result = get_account_timesheet_summary(account_name=account_name)
        if not result.ok:
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title=f"Account-wise Timesheet Summary – {account_name}",
                rows=result.rows or [],
            ),
        }

    if "portfolio-wise timesheet booking summary" in lower or "portfolio wise timesheet booking summary" in lower:
        portfolio_name = extract_after(text, "for portfolio")
        if not portfolio_name:
            return {"handled": True, "message": "Please provide a portfolio name (e.g. `... for portfolio Digital`)."}
        result = get_portfolio_timesheet_summary(portfolio_name=portfolio_name)
        if not result.ok:
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title=f"Portfolio-wise Timesheet Summary – {portfolio_name}",
                rows=result.rows or [],
            ),
        }

    if (
        "organization-wise timesheet" in lower
        or "organisation-wise timesheet" in lower
        or "organization wise timesheet" in lower
        or "organisation wise timesheet" in lower
    ):
        result = get_org_timesheet_summary()
        if not result.ok:
            return {"handled": True, "message": f"Timesheet lookup failed: `{result.error}`"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(title="Organisation-wide Timesheet Summary", rows=result.rows or []),
        }

    if "pending timesheet" in lower and ("report" in lower or "booking" in lower or "auto" in lower):
        result = get_pending_timesheet_report()
        if not result.ok:
            return {"handled": True, "message": f"Pending timesheet lookup failed: `{result.error}`"}
        return {
            "handled": True,
            "message": fmt_timesheet_table(
                title="Pending Timesheet Report – Employees with no entry today",
                rows=result.rows or [],
                note=result.note,
            ),
        }

    return None
