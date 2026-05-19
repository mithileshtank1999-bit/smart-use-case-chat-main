from __future__ import annotations

import json


def fmt_tabular(*, title: str, table: str, rows: list[dict]) -> str:
    """Raw JSON preview — used for case/test-case summaries."""
    if not rows:
        return f"{title}\n\nNo matching rows found (table `{table}`)."
    preview = rows[:10]
    payload = json.dumps(preview, ensure_ascii=False, indent=2)
    more = "" if len(rows) <= 10 else f"\n\nShowing 10 of {len(rows)} rows."
    return f"{title}\n\n```json\n{payload}\n```{more}"


def fmt_report(*, title: str, table: str, rows: list[dict], group_col_candidates: list[str]) -> str:
    """
    Aggregated markdown report: groups rows by the first matching column,
    counts by status and severity within each group.
    """
    if not rows:
        return f"## {title}\n\nNo data found (table `{table}`)."

    first = rows[0]
    group_col = next((c for c in group_col_candidates if c in first), None)
    status_col = next(
        (c for c in ["status", "statuscode", "state", "defect_status", "case_status"] if c in first), None
    )
    severity_col = next((c for c in ["severity", "priority", "criticality"] if c in first), None)

    if not group_col:
        preview = rows[:20]
        payload = json.dumps(preview, ensure_ascii=False, indent=2)
        more = "" if len(rows) <= 20 else f"\n\nShowing 20 of {len(rows)} rows."
        return f"## {title}\n\nTotal records: **{len(rows)}**\n\n```json\n{payload}\n```{more}"

    groups: dict[str, dict] = {}
    for row in rows:
        gval = str(row.get(group_col) or "Unknown")
        if gval not in groups:
            groups[gval] = {"total": 0, "by_status": {}, "by_severity": {}}
        groups[gval]["total"] += 1
        if status_col:
            sv = str(row.get(status_col) or "Unknown")
            groups[gval]["by_status"][sv] = groups[gval]["by_status"].get(sv, 0) + 1
        if severity_col:
            sev = str(row.get(severity_col) or "Unknown")
            groups[gval]["by_severity"][sev] = groups[gval]["by_severity"].get(sev, 0) + 1

    lines: list[str] = [
        f"## {title}",
        f"\nTotal: **{len(rows)} records** across **{len(groups)}** group(s)\n",
    ]
    for gname, data in sorted(groups.items()):
        lines.append(f"\n### {gname}  ({data['total']} record(s))")
        if data["by_status"]:
            lines.append("\n| Status | Count |")
            lines.append("|--------|------:|")
            for s, c in sorted(data["by_status"].items(), key=lambda x: -x[1]):
                lines.append(f"| {s} | {c} |")
        if data["by_severity"]:
            lines.append("\n| Severity | Count |")
            lines.append("|----------|------:|")
            for s, c in sorted(data["by_severity"].items(), key=lambda x: -x[1]):
                lines.append(f"| {s} | {c} |")
    return "\n".join(lines)


def fmt_timesheet_table(*, title: str, rows: list[dict], note: str | None = None) -> str:
    """Markdown table for timesheet summary results."""
    if not rows:
        msg = f"## {title}\n\nNo timesheet entries found."
        if note:
            msg += f"\n\n_{note}_"
        return msg

    headers = list(rows[0].keys())
    header_row = "| " + " | ".join(str(h).replace("_", " ").title() for h in headers) + " |"
    sep_row = "|" + "|".join("---" for _ in headers) + "|"
    data_rows = [
        "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |"
        for row in rows[:50]
    ]
    more = "" if len(rows) <= 50 else f"\n\n_Showing 50 of {len(rows)} rows._"
    note_line = f"\n\n_{note}_" if note else ""
    return f"## {title}\n\n{header_row}\n{sep_row}\n" + "\n".join(data_rows) + more + note_line


def fmt_action(*, title: str, table: str, schema: str | None, rows: list[dict]) -> str:
    """JSON preview for action points and risks."""
    if not rows:
        qualified = f"{schema}.{table}" if schema else table
        return f"## {title}\n\nNo records found (table `{qualified}`)."
    preview = rows[:15]
    payload = json.dumps(preview, ensure_ascii=False, indent=2)
    qualified = f"{schema}.{table}" if schema else table
    more = "" if len(rows) <= 15 else f"\n\nShowing 15 of {len(rows)} rows."
    return f"## {title}\n\nSource: `{qualified}`\n\n```json\n{payload}\n```{more}"
