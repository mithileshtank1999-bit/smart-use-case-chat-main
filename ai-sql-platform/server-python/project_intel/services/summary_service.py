from __future__ import annotations

from project_intel.core.config import OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import make_json_safe
from sqlalchemy import text
from db import SessionLocal
from project_intel.data.db_access import (
    get_project_id_column,
    get_project_name_column,
    get_project_table_name,
    normalize_project_row,
)
from project_intel.data.project_details_access import enrich_project_data


def empty_summary(governance_message: str = ""):
    return {
        "overview": {},
        "health": {},
        "timeline": {},
        "governance": {"summary": governance_message} if governance_message else {},
        "financial": {},
        "risks": {},
        "highlights": {},
        "milestones": [],
        "key_information": {},
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
    customer_name = pick_first(project_data, "customer_name", "account_name", "companyname")
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
    left_over = pick_first(project_data, "left_over", "unbilled")
    contract_id = pick_first(project_data, "contract_id")
    contract_title = pick_first(project_data, "contract_title")
    project_currency = pick_first(project_data, "project_currency", "currency", "currencyid")
    billable_flag = pick_first(project_data, "billable_flag")
    actual_effort = pick_first(project_data, "actual_effort")
    is_active = pick_first(project_data, "is_active")
    monitor_project = pick_first(project_data, "monitor_project")
    troubled = pick_first(project_data, "troubled")
    completion_pct = pick_first(project_data, "completion_pct")
    days_elapsed = pick_first(project_data, "days_elapsed")
    days_to_go_live = pick_first(project_data, "days_to_go_live")
    start_date_history = pick_first(project_data, "start_date_history")
    sit_date_history = pick_first(project_data, "sit_date_history")
    uat_date_history = pick_first(project_data, "uat_date_history")
    uat_release_date_history = pick_first(project_data, "uat_release_date_history")
    go_live_date_history = pick_first(project_data, "go_live_date_history")
    expected_uat_completion = pick_first(project_data, "expected_uat_completion")
    uat_release = pick_first(project_data, "uat_release")
    revenue_area = pick_first(project_data, "revenue_area")
    revenue_type = pick_first(project_data, "revenue_type")
    product_focus = pick_first(project_data, "product_focus")
    delivery_rag = pick_first(project_data, "delivery_rag")
    product_rag = pick_first(project_data, "product_rag")
    revenue_risk = pick_first(project_data, "revenue_risk")
    forecasted_project_hours = pick_first(project_data, "forecasted_project_hours")
    budgeted_project_hours = pick_first(project_data, "budgeted_project_hours")
    efforts_remaining = pick_first(project_data, "efforts_remaining")
    budgeted_man_months = pick_first(project_data, "budgeted_man_months")
    project_criticality = pick_first(project_data, "project_criticality")
    sa_spoc = pick_first(project_data, "sa_spoc")
    sdg_spoc = pick_first(project_data, "sdg_spoc")
    product_spoc = pick_first(project_data, "product_spoc")
    pipeline_remarks = pick_first(project_data, "pipeline_remarks")
    lowlights = pick_first(project_data, "lowlights")
    financial_documents = pick_first(project_data, "financial_documents")
    comments = pick_first(project_data, "comments")
    reopened_cases = pick_first(project_data, "reopened_cases")
    untouched_cases = pick_first(project_data, "untouched_cases")
    total_cases = pick_first(project_data, "total_cases")
    untouched_requirements = pick_first(project_data, "untouched_requirements")
    total_requirements = pick_first(project_data, "total_requirements")
    highlights_feed = project_data.get("highlights_feed") if isinstance(project_data.get("highlights_feed"), list) else []
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
            "completion": pick_first(project_data, "completion", "delivery_progress"),
            "billing_model": billing_model,
            "modules_delivered": pick_first(project_data, "modules_delivered"),
            "objective": objective,
            "portfolio": portfolio,
            "portfolio_owner": portfolio_owner,
            "customer_name": customer_name,
            "contract_id": contract_id,
            "contract_title": contract_title,
            "project_currency": project_currency,
            "billable": billable_flag,
            "assign_to": project_manager,
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
            "actual_effort": actual_effort,
            "fsd_sign_off": pick_first(project_data, "fsd_sign_off"),
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
            "left_over": left_over,
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
            "key_win": customer_name or portfolio or "No additional highlight data yet.",
        },
        "milestones": [m for m in milestones if m["date"] or m["status"] == "No data"],
        "key_information": {
            "active": is_active,
            "monitor_project": monitor_project,
            "troubled": troubled,
            "percent_completion": completion_pct,
            "days_elapsed": days_elapsed,
            "days_to_go_live": days_to_go_live,
            "expected_uat_completion": expected_uat_completion,
            "uat_release": uat_release,
            "revenue_area": revenue_area,
            "revenue_type": revenue_type,
            "product_focus": product_focus,
            "delivery_rag": delivery_rag,
            "product_rag": product_rag,
            "revenue_risk": revenue_risk,
            "forecasted_project_hours": forecasted_project_hours,
            "budgeted_project_hours": budgeted_project_hours,
            "efforts_remaining": efforts_remaining,
            "budgeted_man_months": budgeted_man_months,
            "start_date_history": start_date_history,
            "sit_date_history": sit_date_history,
            "uat_date_history": uat_date_history,
            "uat_release_date_history": uat_release_date_history,
            "go_live_date_history": go_live_date_history,
            "project_criticality": project_criticality,
            "sa_spoc": sa_spoc,
            "sdg_spoc": sdg_spoc,
            "product_spoc": product_spoc,
            "pipeline_remarks": pipeline_remarks,
            "lowlights": lowlights,
            "financial_documents": financial_documents,
            "comments": comments,
            "reopened_cases": reopened_cases,
            "untouched_cases": untouched_cases,
            "total_cases": total_cases,
            "untouched_requirements": untouched_requirements,
            "total_requirements": total_requirements,
            "highlights_feed": highlights_feed,
        },
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
    "portfolio_owner": "",
    "customer_name": "",
    "contract_id": "",
    "contract_title": "",
    "project_currency": "",
    "billable": "",
    "assign_to": ""
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
    "go_live_date": "",
    "fsd_sign_off": "",
    "actual_effort": ""
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
    "revenue_available": "",
    "left_over": ""
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
  ],
  "key_information": {{
    "active": "",
    "monitor_project": "",
    "troubled": "",
    "percent_completion": "",
    "days_elapsed": "",
    "days_to_go_live": "",
    "expected_uat_completion": "",
    "uat_release": "",
    "revenue_area": "",
    "revenue_type": "",
    "product_focus": "",
    "delivery_rag": "",
    "product_rag": "",
    "revenue_risk": "",
    "forecasted_project_hours": "",
    "budgeted_project_hours": "",
    "efforts_remaining": "",
    "budgeted_man_months": "",
    "start_date_history": "",
    "sit_date_history": "",
    "uat_date_history": "",
    "uat_release_date_history": "",
    "go_live_date_history": "",
    "project_criticality": "",
    "sa_spoc": "",
    "sdg_spoc": "",
    "product_spoc": "",
    "pipeline_remarks": "",
    "lowlights": "",
    "financial_documents": "",
    "comments": "",
    "reopened_cases": "",
    "untouched_cases": "",
    "total_cases": "",
    "untouched_requirements": "",
    "total_requirements": "",
    "highlights_feed": [
      {{
        "module": "",
        "text": "",
        "last_modified_by": "",
        "last_modified_on": ""
      }}
    ]
  }}
}}
"""

    clients = get_openai_clients()
    if not clients:
        return empty_summary("OpenAI is not configured. Set OPENAI_API_KEY (or OPENAI_API_KEYS) and restart the server.")

    last_error = ""
    raw = ""
    for client in clients:
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (response.choices[0].message.content or "").strip()
            break
        except Exception as error:
            last_error = str(error)
            status_code = getattr(error, "status_code", None)
            if status_code is None:
                resp = getattr(error, "response", None)
                status_code = getattr(resp, "status_code", None)
            if status_code in (401, 403, 404, 429):
                continue
            return empty_summary("Error generating summary")

    if not raw:
        _ = last_error
        return empty_summary("Error generating summary")

    import json

    try:
        return json.loads(raw)
    except Exception:
        return empty_summary("Error generating summary")


def build_executive_summary(project_id: str = "", project_name: str = "", project_data: dict | None = None) -> dict:
    project_id = (project_id or "").strip()
    project_name = (project_name or "").strip()
    project_data = make_json_safe(project_data or {}) if isinstance(project_data, dict) else {}

    if not project_data:
        table_name = get_project_table_name()
        id_col = get_project_id_column()
        name_col = get_project_name_column()
        db = SessionLocal()
        try:
            if project_id:
                result = db.execute(text(f"SELECT * FROM {table_name} WHERE {id_col} = :id"), {"id": project_id})
            elif project_name:
                result = db.execute(text(f"SELECT * FROM {table_name} WHERE {name_col} = :name"), {"name": project_name})
            else:
                result = None
            row = result.fetchone() if result else None
        finally:
            db.close()

        if row:
            project_data = normalize_project_row(make_json_safe(dict(row._mapping)))
            project_id = project_id or str(project_data.get("project_id", "")).strip()
            project_name = project_name or str(project_data.get("project_name", "")).strip()

    if not project_data:
        return {"error": "project_not_found", "summary": empty_summary("Project lookup failed")}

    project_data = enrich_project_data(project_data)

    fallback_summary = build_fallback_summary(project_data)
    try:
        generated_summary = generate_summary(project_data)
    except Exception:
        generated_summary = empty_summary("Summary generation failed")

    summary = deep_fill_summary(generated_summary or {}, fallback_summary)
    return {"summary": summary, "project_id": project_id or str(project_data.get("project_id", "")), "project_name": project_name or str(project_data.get("project_name", ""))}
