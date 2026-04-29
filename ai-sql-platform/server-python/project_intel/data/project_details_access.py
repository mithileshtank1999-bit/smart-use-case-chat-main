from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA
from project_intel.data.db_access import (
    get_project_id_column,
    get_project_table_name,
    make_json_safe,
    normalize_project_row,
)


IST_OFFSET = timedelta(hours=5, minutes=30)

_CLOSED_STATUSES = {
    "completed",
    "closed",
    "cancelled",
    "canceled",
    "inactive",
    "dropped",
}


def _qualified(table: str) -> str:
    schema = (DB_SCHEMA or "").strip() or "dbo"
    return f"{schema}.{table}"


def _to_ist_date(value) -> date | None:
    if isinstance(value, datetime):
        # DB timestamps are stored without timezone; in our MyPortal dummy DB the
        # "date" values are frequently persisted as UTC midnight (18:30 previous day).
        # Convert to IST for display consistency with the portal UI.
        return (value + IST_OFFSET).date()
    if isinstance(value, date):
        return value
    return None


def _fmt_date(value) -> str:
    d = _to_ist_date(value)
    return d.strftime("%d-%m-%Y") if d else ""


def _fmt_number(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    try:
        return f"{float(value):.2f}"
    except Exception:
        return str(value)


def _best_effort_int(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _extract_kv_from_text(blob: str) -> dict[str, str]:
    """
    Best-effort extraction of key/value pairs from semi-structured text.
    Supports lines like:
      Key: Value
      Key - Value
      Key = Value
    """
    if not blob:
        return {}
    raw = blob.strip()
    if not raw:
        return {}

    # Try JSON first.
    if raw.startswith("{") or raw.startswith("["):
        try:
            import json

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k).strip().lower(): str(v).strip() for k, v in parsed.items() if v not in (None, "")}
        except Exception:
            pass

    kv: dict[str, str] = {}
    for line in raw.splitlines():
        ln = line.strip().strip("-").strip()
        if not ln or len(ln) < 3:
            continue
        for sep in (":", " - ", "=", "\t"):
            if sep in ln:
                left, right = ln.split(sep, 1)
                key = left.strip().lower()
                val = right.strip()
                if key and val and key not in kv:
                    kv[key] = val
                break
    return kv


def _rag_from_offset_days(offset_days) -> str:
    try:
        if offset_days in (None, ""):
            return ""
        off = float(offset_days)
        if off <= 0:
            return "Green"
        if off <= 7:
            return "Amber"
        return "Red"
    except Exception:
        return ""


def fetch_project_key_information(project_id: int) -> dict:
    """
    Best-effort enrichment for the Key Information fields shown in the legacy portal UI.

    This pulls data from:
    - dbo.<project table> (base project header)
    - dbo.project_revenue (financials)
    - dbo.projectmodule (milestone dates)
    - dbo.contracts (contract header)
    - dbo.timesheet (actual effort)
    - dbo.myportfolio (portfolio label)
    """
    pid = int(project_id)
    id_col = get_project_id_column()
    project_table = _qualified(get_project_table_name())

    db = SessionLocal()
    try:
        employee_name_cache: dict[int, str] = {}

        def resolve_employee_name(userid) -> str:
            uid = _best_effort_int(userid)
            if uid is None:
                return ""
            if uid in employee_name_cache:
                return employee_name_cache[uid]
            row = (
                db.execute(
                    text(
                        f"""
                        SELECT subject
                        FROM {_qualified('employee')}
                        WHERE userid = :uid
                        ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                        LIMIT 1
                        """
                    ),
                    {"uid": uid},
                )
                .mappings()
                .fetchone()
            )
            name = str(row.get("subject")) if row and row.get("subject") else ""
            employee_name_cache[uid] = name
            return name

        project_row = (
            db.execute(text(f"SELECT * FROM {project_table} WHERE {id_col} = :pid"), {"pid": pid})
            .mappings()
            .fetchone()
        )
        project_data = normalize_project_row(dict(project_row) if project_row else {})

        revenue_row = (
            db.execute(
                text(f"SELECT * FROM {_qualified('project_revenue')} WHERE project_id = :pid"),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        revenue_data = dict(revenue_row) if revenue_row else {}

        contract_row = (
            db.execute(
                text(
                    f"""
                    SELECT contractid, contracttitle, currencyid
                    FROM {_qualified('contracts')}
                    WHERE projectid = :pid
                    ORDER BY createdon DESC NULLS LAST, lastmodifiedon DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        contract_data = dict(contract_row) if contract_row else {}

        module_row = (
            db.execute(
                text(
                    f"""
                    SELECT
                      MIN(fsdsignoff) AS fsdsignoff,
                      MAX(devdelivery) AS devdelivery,
                      MIN(sitstartdate) AS sitstartdate,
                      MIN(uatstartdate) AS uatstartdate,
                      MAX(uatsignoff) AS uatsignoff,
                      MAX(golive) AS golive
                    FROM {_qualified('projectmodule')}
                    WHERE relatedtoid = :pid
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        module_data = dict(module_row) if module_row else {}

        effort_row = (
            db.execute(
                text(
                    f"""
                    SELECT COALESCE(SUM(effort), 0) AS actual_effort
                    FROM {_qualified('timesheet')}
                    WHERE projectid = :pid
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        actual_effort = effort_row.get("actual_effort") if effort_row else None

        portfolio_name = ""
        portfolio_id = _best_effort_int(project_data.get("portfolioid"))
        if portfolio_id:
            portfolio_row = (
                db.execute(
                    text(
                        f"""
                        SELECT subject
                        FROM {_qualified('myportfolio')}
                        WHERE customobjectid = :pid
                        ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                        LIMIT 1
                        """
                    ),
                    {"pid": portfolio_id},
                )
                .mappings()
                .fetchone()
            )
            if portfolio_row and portfolio_row.get("subject"):
                portfolio_name = str(portfolio_row.get("subject"))

        enriched = dict(project_data)

        # Parse any semi-structured detail blob for additional Key Information fields
        # (these vary between deployments).
        detail_blob = str(project_data.get("detail") or "").strip()
        if detail_blob:
            parsed = _extract_kv_from_text(detail_blob)
            # Common field aliases observed in portal UI labels.
            label_map = {
                "revenue area": "revenue_area",
                "revenue_area": "revenue_area",
                "revenuetype": "revenue_type",
                "revenue type": "revenue_type",
                "billing model": "billing_model",
                "billing_model": "billing_model",
                "product focus": "product_focus",
                "product_focus": "product_focus",
                "financial documents": "financial_documents",
                "pipeline remarks": "pipeline_remarks",
                "lowlights": "lowlights",
                "comments": "comments",
                "delivery rag": "delivery_rag",
                "product rag": "product_rag",
                "revenue risk": "revenue_risk",
                "% completion": "completion_pct",
                "completion": "completion_pct",
                "forecasted project hours": "forecasted_project_hours",
                "budgeted project hours": "budgeted_project_hours",
                "efforts remaining": "efforts_remaining",
                "budgeted man months": "budgeted_man_months",
                "project criticality": "project_criticality",
                "sa spoc": "sa_spoc",
                "sdg spoc": "sdg_spoc",
                "product spoc": "product_spoc",
            }
            for label, out_key in label_map.items():
                if out_key in enriched and enriched.get(out_key) not in (None, ""):
                    continue
                v = parsed.get(label)
                if v:
                    enriched[out_key] = v

        if portfolio_name:
            existing_portfolio = str(enriched.get("portfolio_name") or "").strip()
            # In some deployments portfolioid is mapped into `portfolio_name` (numeric).
            # Prefer the human label from dbo.myportfolio when available.
            if not existing_portfolio or existing_portfolio.isdigit():
                enriched["portfolio_name"] = portfolio_name
            if portfolio_id and not enriched.get("portfolio_id"):
                enriched["portfolio_id"] = str(portfolio_id)

        if project_data.get("companyname") and not enriched.get("customer_name"):
            enriched["customer_name"] = project_data.get("companyname")

        # Derive some boolean/display flags from dbo.project.
        status_text = str(project_data.get("statuscode") or project_data.get("status") or "").strip()
        if status_text and not enriched.get("is_active"):
            enriched["is_active"] = "No" if status_text.lower() in _CLOSED_STATUSES else "Yes"

        if "isescalated" in project_data and not enriched.get("troubled"):
            try:
                enriched["troubled"] = "Yes" if float(project_data.get("isescalated") or 0) else "No"
            except Exception:
                enriched["troubled"] = str(project_data.get("isescalated"))

        if "openescalatedcount" in project_data and not enriched.get("monitor_project"):
            try:
                enriched["monitor_project"] = "Yes" if int(project_data.get("openescalatedcount") or 0) > 0 else "No"
            except Exception:
                enriched["monitor_project"] = str(project_data.get("openescalatedcount"))

        if "reopencount" in project_data and not enriched.get("reopened_cases"):
            try:
                enriched["reopened_cases"] = int(project_data.get("reopencount") or 0)
            except Exception:
                enriched["reopened_cases"] = project_data.get("reopencount")

        if contract_data.get("contractid") and not enriched.get("contract_id"):
            enriched["contract_id"] = contract_data.get("contractid")
        if contract_data.get("contracttitle") and not enriched.get("contract_title"):
            enriched["contract_title"] = contract_data.get("contracttitle")
        if contract_data.get("currencyid") and not enriched.get("project_currency"):
            enriched["project_currency"] = contract_data.get("currencyid")

        # Financial metrics
        if revenue_data:
            if not enriched.get("project_service_value") and revenue_data.get("project_service_value") is not None:
                enriched["project_service_value"] = _fmt_number(revenue_data.get("project_service_value"))
            if not enriched.get("revenue_recognized") and revenue_data.get("revenue_recognized") is not None:
                enriched["revenue_recognized"] = _fmt_number(revenue_data.get("revenue_recognized"))
            if not enriched.get("cumulative_invoice") and revenue_data.get("cumulative_invoice") is not None:
                enriched["cumulative_invoice"] = _fmt_number(revenue_data.get("cumulative_invoice"))
            if not enriched.get("advance") and revenue_data.get("advance") is not None:
                enriched["advance"] = _fmt_number(revenue_data.get("advance"))
            if not enriched.get("revenue_available") and revenue_data.get("revenue_available_to") is not None:
                enriched["revenue_available"] = _fmt_number(revenue_data.get("revenue_available_to"))
            if not enriched.get("left_over") and revenue_data.get("unbilled") is not None:
                enriched["left_over"] = _fmt_number(revenue_data.get("unbilled"))

        # Timeline milestones (mapped to UI-friendly keys)
        if module_data:
            if module_data.get("fsdsignoff") and not enriched.get("fsd_sign_off"):
                enriched["fsd_sign_off"] = _fmt_date(module_data.get("fsdsignoff"))
            if module_data.get("devdelivery") and not enriched.get("dev_end_date"):
                enriched["dev_end_date"] = _fmt_date(module_data.get("devdelivery"))
            if module_data.get("sitstartdate") and not enriched.get("sit_start_date"):
                enriched["sit_start_date"] = _fmt_date(module_data.get("sitstartdate"))
            if module_data.get("uatstartdate") and not enriched.get("uat_start_date"):
                enriched["uat_start_date"] = _fmt_date(module_data.get("uatstartdate"))
            if module_data.get("uatsignoff") and not enriched.get("uat_end_date"):
                enriched["uat_end_date"] = _fmt_date(module_data.get("uatsignoff"))
            if module_data.get("golive") and not enriched.get("go_live_date"):
                enriched["go_live_date"] = _fmt_date(module_data.get("golive"))

        # Format base dates for display consistency (override the normalized datetime strings).
        if project_data.get("startdate"):
            enriched["start_date"] = _fmt_date(project_data.get("startdate"))
        if project_data.get("enddate"):
            enriched["end_date"] = _fmt_date(project_data.get("enddate"))
            enriched["go_live_date"] = _fmt_date(project_data.get("enddate"))

        # Effort (timesheet)
        if actual_effort not in (None, "") and not enriched.get("actual_effort"):
            enriched["actual_effort"] = _fmt_number(actual_effort)

        # Billable flag
        if "billable" in project_data and not enriched.get("billable_flag"):
            try:
                enriched["billable_flag"] = "Yes" if float(project_data.get("billable") or 0) else "No"
            except Exception:
                enriched["billable_flag"] = str(project_data.get("billable"))

        # UAT Release (best-effort): use dbo.build if present for this project.
        build_row = (
            db.execute(
                text(
                    f"""
                    SELECT planneduatrelease, actualuatrelease
                    FROM {_qualified('build')}
                    WHERE projectid = :pid
                    ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        if build_row:
            planned_uat = build_row.get("planneduatrelease")
            actual_uat = build_row.get("actualuatrelease")
            if planned_uat and not enriched.get("uat_release_planned"):
                enriched["uat_release_planned"] = _fmt_date(planned_uat)
            if actual_uat and not enriched.get("uat_release_actual"):
                enriched["uat_release_actual"] = _fmt_date(actual_uat)
            if (actual_uat or planned_uat) and not enriched.get("uat_release"):
                enriched["uat_release"] = _fmt_date(actual_uat or planned_uat)

        # Expected UAT completion (best-effort): dbo.workunit.
        workunit_row = (
            db.execute(
                text(
                    f"""
                    SELECT MAX(uatdeliveryexpecteddate) AS expected_uat_completion,
                           MAX(uatdeliveryactualdate) AS actual_uat_completion
                    FROM {_qualified('workunit')}
                    WHERE relatedtoid = :pid
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchone()
        )
        if workunit_row:
            expected_uat = workunit_row.get("expected_uat_completion")
            actual_uat = workunit_row.get("actual_uat_completion")
            if expected_uat and not enriched.get("expected_uat_completion"):
                enriched["expected_uat_completion"] = _fmt_date(expected_uat)
            if actual_uat and not enriched.get("actual_uat_completion"):
                enriched["actual_uat_completion"] = _fmt_date(actual_uat)

        # Delivery/Product RAG (best-effort): derive from schedule offsets if present.
        try:
            offsets = (
                db.execute(
                    text(
                        f"""
                        SELECT MAX(sitdeliveryoffset) AS sit_offset,
                               MAX(uatdeliveryoffset) AS uat_offset
                        FROM {_qualified('workunit')}
                        WHERE relatedtoid = :pid
                        """
                    ),
                    {"pid": pid},
                )
                .mappings()
                .fetchone()
            )
            if offsets:
                sit_offset = offsets.get("sit_offset")
                uat_offset = offsets.get("uat_offset")
                worst = None
                for off in (sit_offset, uat_offset):
                    if off is None:
                        continue
                    try:
                        off_f = float(off)
                    except Exception:
                        continue
                    worst = off_f if worst is None else max(worst, off_f)
                if worst is not None and not enriched.get("delivery_rag"):
                    enriched["delivery_rag"] = _rag_from_offset_days(worst)
                if worst is not None and not enriched.get("product_rag"):
                    # No better source found in this DB; keep aligned with schedule rag for now.
                    enriched["product_rag"] = _rag_from_offset_days(worst)
        except Exception:
            pass

        # Date histories (from *_history tables)
        project_hist = (
            db.execute(
                text(
                    f"""
                    SELECT startdate, enddate
                    FROM {_qualified('projecthistory')}
                    WHERE projectid = :pid
                    ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                    LIMIT 25
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchall()
        )
        if project_hist:
            start_dates: list[str] = []
            end_dates: list[str] = []
            for r in project_hist:
                sd = _fmt_date(r.get("startdate"))
                ed = _fmt_date(r.get("enddate"))
                if sd and sd not in start_dates:
                    start_dates.append(sd)
                if ed and ed not in end_dates:
                    end_dates.append(ed)
            if start_dates and not enriched.get("start_date_history"):
                enriched["start_date_history"] = " > ".join(start_dates[:6])
            if end_dates and not enriched.get("go_live_date_history"):
                enriched["go_live_date_history"] = " > ".join(end_dates[:6])

        module_hist = (
            db.execute(
                text(
                    f"""
                    SELECT sitstartdate, uatstartdate, uatsignoff, golive,
                           trailsitstartdate, trailuatstartdate, trailuatsignoff, trailgolive
                    FROM {_qualified('projectmodulehistory')}
                    WHERE relatedtoid = :pid
                    ORDER BY lastmodifiedon DESC NULLS LAST, historyid DESC
                    LIMIT 50
                    """
                ),
                {"pid": pid},
            )
            .mappings()
            .fetchall()
        )
        if module_hist:
            def _collect(field: str) -> list[str]:
                values: list[str] = []
                for r in module_hist:
                    v = _fmt_date(r.get(field))
                    if v and v not in values:
                        values.append(v)
                return values

            trail_sit = _collect("trailsitstartdate")
            sit = _collect("sitstartdate")
            trail_uat = _collect("trailuatstartdate")
            uat = _collect("uatstartdate")
            trail_uat_signoff = _collect("trailuatsignoff")
            uat_signoff = _collect("uatsignoff")
            trail_golive = _collect("trailgolive")
            golive = _collect("golive")

            sit_hist = trail_sit + [v for v in sit if v not in trail_sit]
            uat_hist = trail_uat + [v for v in uat if v not in trail_uat]
            uat_signoff_hist = trail_uat_signoff + [v for v in uat_signoff if v not in trail_uat_signoff]
            golive_hist = trail_golive + [v for v in golive if v not in trail_golive]

            if sit_hist and not enriched.get("sit_date_history"):
                enriched["sit_date_history"] = " > ".join(sit_hist[:6])
            if uat_hist and not enriched.get("uat_date_history"):
                enriched["uat_date_history"] = " > ".join(uat_hist[:6])
            if uat_signoff_hist and not enriched.get("uat_release_date_history"):
                enriched["uat_release_date_history"] = " > ".join(uat_signoff_hist[:6])
            if golive_hist and not enriched.get("go_live_module_date_history"):
                enriched["go_live_module_date_history"] = " > ".join(golive_hist[:6])

        # Case + Requirement counts (views exist in this DB)
        try:
            case_counts = (
                db.execute(
                    text(
                        f"""
                        SELECT
                          COUNT(DISTINCT caseid) AS total_cases,
                          COUNT(DISTINCT CASE WHEN case_lastmodifiedon IS NULL OR case_lastmodifiedon = case_createdon THEN caseid END) AS untouched_cases
                        FROM {_qualified('projectwithcasesview')}
                        WHERE projectid = :pid
                        """
                    ),
                    {"pid": pid},
                )
                .mappings()
                .fetchone()
            )
            if case_counts:
                if not enriched.get("untouched_cases"):
                    enriched["untouched_cases"] = int(case_counts.get("untouched_cases") or 0)
                if not enriched.get("total_cases"):
                    enriched["total_cases"] = int(case_counts.get("total_cases") or 0)
        except Exception:
            pass

        try:
            req_counts = (
                db.execute(
                    text(
                        f"""
                        SELECT
                          COUNT(DISTINCT issue_itemid) AS total_requirements,
                          COUNT(DISTINCT CASE WHEN issue_lastmodifiedon IS NULL OR issue_lastmodifiedon = issue_createdon THEN issue_itemid END) AS untouched_requirements
                        FROM {_qualified('projectwithreqview')}
                        WHERE projectid = :pid
                        """
                    ),
                    {"pid": pid},
                )
                .mappings()
                .fetchone()
            )
            if req_counts:
                if not enriched.get("untouched_requirements"):
                    enriched["untouched_requirements"] = int(req_counts.get("untouched_requirements") or 0)
                if not enriched.get("total_requirements"):
                    enriched["total_requirements"] = int(req_counts.get("total_requirements") or 0)
        except Exception:
            pass

        # Completion %, Days elapsed/to-go-live (derived)
        try:
            start_dt = project_data.get("startdate")
            end_dt = project_data.get("enddate")
            start_d = _to_ist_date(start_dt)
            end_d = _to_ist_date(end_dt)
            today_ist = (datetime.utcnow() + IST_OFFSET).date()
            if start_d:
                enriched.setdefault("days_elapsed", max(0, (today_ist - start_d).days))
            if end_d:
                enriched.setdefault("days_to_go_live", (end_d - today_ist).days)
            if start_d and end_d and end_d != start_d and not enriched.get("completion_pct"):
                pct = int(round(((today_ist - start_d).days / max(1, (end_d - start_d).days)) * 100))
                pct = max(0, min(100, pct))
                enriched["completion_pct"] = f"{pct:.2f} %"
        except Exception:
            pass

        # Highlights (best-effort): parse projectmodule.detail notes if available.
        try:
            highlights_rows = (
                db.execute(
                    text(
                        f"""
                        SELECT subject, detail, lastmodifiedon, lastmodifiedby
                        FROM {_qualified('projectmodule')}
                        WHERE relatedtoid = :pid AND COALESCE(detail, '') <> ''
                        ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                        LIMIT 10
                        """
                    ),
                    {"pid": pid},
                )
                .mappings()
                .fetchall()
            )
            items: list[dict] = []
            for r in highlights_rows:
                raw = str(r.get("detail") or "").strip()
                if not raw:
                    continue
                author = resolve_employee_name(r.get("lastmodifiedby")) or str(r.get("lastmodifiedby") or "")
                last_modified = _fmt_date(r.get("lastmodifiedon")) or ""
                # keep last few meaningful lines
                lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                for ln in lines[-5:]:
                    items.append(
                        {
                            "module": str(r.get("subject") or ""),
                            "text": ln,
                            "last_modified_by": author,
                            "last_modified_on": last_modified,
                        }
                    )
                if len(items) >= 10:
                    break
            if items and not enriched.get("highlights_feed"):
                enriched["highlights_feed"] = items[:10]
        except Exception:
            pass

        return make_json_safe(enriched)
    finally:
        db.close()


def enrich_project_data(project_data: dict) -> dict:
    """
    Merge Key Information fields into the provided project_data.
    Never clears any existing values.
    """
    if not isinstance(project_data, dict) or not project_data:
        return project_data

    pid = _best_effort_int(project_data.get("project_id") or project_data.get("projectid"))
    if pid is None:
        return project_data

    try:
        enriched = fetch_project_key_information(pid)
    except Exception:
        return project_data

    merged = dict(project_data)
    date_like_keys = {
        "start_date",
        "end_date",
        "go_live_date",
        "dev_start_date",
        "dev_end_date",
        "sit_start_date",
        "sit_end_date",
        "uat_start_date",
        "uat_end_date",
        "fsd_sign_off",
    }
    for key, value in enriched.items():
        if key in merged and merged.get(key) not in (None, ""):
            if key in date_like_keys:
                existing = str(merged.get(key))
                incoming = str(value)
                # Prefer the dd-MM-YYYY display string over ISO timestamps coming from raw DB rows.
                if ("T" in existing or ":" in existing) and len(incoming) == 10 and incoming[2] == "-" and incoming[5] == "-":
                    merged[key] = value
            continue
        if value in (None, ""):
            continue
        merged[key] = value
    return merged
