from __future__ import annotations

from datetime import date, datetime
import re
from project_intel.core.config import OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import make_json_safe


def is_key_timeline_milestones_request(user_question: str) -> bool:
    q = (user_question or "").lower()
    triggers = [
        "key timeline milestones",
        "timeline milestones summary",
        "individual project milestones summary",
        "executive project summary",
    ]
    return any(t in q for t in triggers)


def pick_best_project_row(user_question: str, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    try:
        match = re.search(r"for\s+project\s+(.+?)(?:[\.\n\r]|$)", user_question or "", flags=re.IGNORECASE)
        requested_name = (match.group(1) if match else "").strip().strip('"').strip("'")
    except Exception:
        requested_name = ""

    if requested_name:
        requested_lower = requested_name.lower()
        for row in rows:
            row_name = str(row.get("project_name") or "").strip()
            if row_name and row_name.lower() == requested_lower:
                return row
        for row in rows:
            row_name = str(row.get("project_name") or "").strip()
            if row_name and (requested_lower in row_name.lower() or row_name.lower() in requested_lower):
                return row

    return rows[0]


def _parse_iso_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        # Handles "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS"
        if "t" in raw.lower():
            return datetime.fromisoformat(raw.replace("Z", "")).date()
        return date.fromisoformat(raw[:10])
    except Exception:
        return None


def _get_first(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return str(row.get(key))
        lk = key.lower()
        for actual in row.keys():
            if str(actual).lower() == lk and row.get(actual) not in (None, ""):
                return str(row.get(actual))
    return ""


def _fmt_date(value: str) -> str:
    d = _parse_iso_date(value)
    return d.isoformat() if d else ""


def _fmt_range(start: str, end: str) -> str:
    s = _fmt_date(start)
    e = _fmt_date(end)
    if s and e:
        return f"{s} → {e}"
    if s and not e:
        return f"{s} → Not available"
    if not s and e:
        return f"Not available → {e}"
    return ""


def _compute_timeline_health(missing: int, invalid_ranges: int) -> tuple[str, str]:
    if invalid_ranges > 0:
        return ("Red", "One or more milestone date ranges are inconsistent (end date earlier than start date).")
    if missing == 0:
        return ("Green", "All key milestones are clearly defined and scheduled.")
    if missing <= 2:
        return ("Amber", "Some key milestone details are missing; tracking should be monitored closely.")
    return ("Red", "Multiple key milestone details are missing, impacting timeline tracking and reporting.")


def render_timeline_milestones_summary(user_question: str, rows: list[dict]) -> str:
    safe_rows = make_json_safe(rows or [])
    selected = pick_best_project_row(user_question, safe_rows) or (safe_rows[0] if safe_rows else {})
    if not isinstance(selected, dict) or not selected:
        return "No matching project data found."

    project_name = str(selected.get("project_name") or "").strip()
    status = str(selected.get("status") or "").strip()

    start_date = _fmt_date(_get_first(selected, "start_date", "startdate"))
    fsd = _fmt_date(_get_first(selected, "fsd_sign_off", "fsd_signoff", "fsd_sign_off_date", "fsd_signoff_date"))
    dev_range = _fmt_range(_get_first(selected, "dev_start_date"), _get_first(selected, "dev_end_date"))
    sit_range = _fmt_range(_get_first(selected, "sit_start_date"), _get_first(selected, "sit_end_date"))
    uat_range = _fmt_range(_get_first(selected, "uat_start_date"), _get_first(selected, "uat_end_date"))
    go_live = _fmt_date(_get_first(selected, "go_live_date", "end_date", "enddate"))

    milestones = [
        ("Project Start Date", start_date),
        ("FSD Sign Off", fsd),
        ("Development Phase", dev_range),
        ("SIT Phase", sit_range),
        ("UAT Phase", uat_range),
        ("Go-Live Date", go_live),
    ]

    missing = sum(1 for _label, value in milestones if not value)

    invalid_ranges = 0
    for start_key, end_key in [("dev_start_date", "dev_end_date"), ("sit_start_date", "sit_end_date"), ("uat_start_date", "uat_end_date")]:
        s = _parse_iso_date(_get_first(selected, start_key))
        e = _parse_iso_date(_get_first(selected, end_key))
        if s and e and e < s:
            invalid_ranges += 1

    health, rationale = _compute_timeline_health(missing, invalid_ranges)

    highlights: list[str] = []
    if project_name:
        highlights.append(f"- **Project:** {project_name}{f' ({status})' if status else ''}.")
    if start_date and go_live:
        highlights.append(f"- Timeline spans from **{start_date}** to **{go_live}**.")
    if fsd:
        highlights.append(f"- FSD sign-off captured on **{fsd}**, enabling downstream delivery execution.")
    if not highlights:
        highlights = ["- Key timeline milestones are summarized below based on the available project data."]
    highlights = highlights[:3]

    def cell(value: str) -> str:
        return value if value else "Not available"

    lines = []
    lines.append("🗓️ Milestones Overview")
    lines.append("")
    lines.append("| Milestone | Date/Range |")
    lines.append("|---|---|")
    for label, value in milestones:
        lines.append(f"| {label} | {cell(value)} |")
    lines.append("")
    lines.append("🔎 Summary Highlights")
    lines.extend(highlights)
    lines.append("")
    lines.append(f"Overall Timeline Health: {health} — {rationale}")
    return "\n".join(lines).strip()


def generate_answer_from_rows(user_question: str, rows: list[dict]) -> str:
    import json

    safe_rows = make_json_safe(rows or [])
    preview_rows = safe_rows[:50]
    rows_json = json.dumps(preview_rows, ensure_ascii=False, indent=2)
    truncated_note = ""
    if len(safe_rows) > len(preview_rows):
        truncated_note = f"\n\nNote: Only the first {len(preview_rows)} rows are shown (of {len(safe_rows)} total)."

    # Fast-path: avoid LLM latency for milestone summaries by rendering deterministically from the row data.
    if is_key_timeline_milestones_request(user_question) and safe_rows:
        return render_timeline_milestones_summary(user_question, safe_rows)
    else:
        prompt = f"""
You are a helpful project intelligence assistant.

Answer the user's question using ONLY the data in the JSON rows below.
- If the rows are empty, say you couldn't find any matching data.
- If the user asks for a "two liner" summary, respond in 2 short lines max.
- Do not invent fields that are not present in the rows.
- If the question asks for a short summary, do not paste raw rows.

User question:
{user_question}

Rows (JSON):
{rows_json}{truncated_note}
"""

    clients = get_openai_clients()
    if not clients:
        return "" if safe_rows else "No matching data found."

    last_error = ""
    for client in clients:
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as error:
            last_error = str(error)
            status_code = getattr(error, "status_code", None)
            if status_code is None:
                resp = getattr(error, "response", None)
                status_code = getattr(resp, "status_code", None)
            if status_code in (401, 403, 404, 429):
                continue
            # If OpenAI errors, degrade gracefully; chat_service can still render the rows payload.
            return ""

    # All keys failed; degrade gracefully.
    _ = last_error
    return ""
