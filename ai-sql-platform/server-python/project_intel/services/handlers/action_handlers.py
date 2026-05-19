from __future__ import annotations

import re

from project_intel.data.action_access import get_action_point_rows, get_risk_rows
from project_intel.services.handlers.formatters import fmt_action
from project_intel.services.handlers.helpers import extract_after

HandlerResult = dict | None


def handle(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes action-points and risk use cases. Returns None if not matched."""

    if "action centre points" in lower or "action center points" in lower:
        project_name = extract_after(text, "for project")
        module_name = extract_after(text, "module")
        result = get_action_point_rows(project_name=project_name, module_name=module_name)
        if not result.ok:
            note = f"\n\n_{result.note}_" if result.note else ""
            return {"handled": True, "message": f"Action points lookup failed: `{result.error}`{note}"}
        title_parts = ["Action Centre Points"]
        if project_name:
            title_parts.append(f"– Project: {project_name}")
        if module_name:
            title_parts.append(f"/ Module: {module_name}")
        return {
            "handled": True,
            "message": fmt_action(
                title=" ".join(title_parts),
                table=result.table or "actionpoints",
                schema=result.schema,
                rows=result.rows or [],
            ),
        }

    # "Retrieve Risk" — but NOT "risk indicators" which goes to RAG
    if re.search(r"\bretrieve\s+risk\b", lower):
        project_name = extract_after(text, "for project")
        module_name = extract_after(text, "module")
        result = get_risk_rows(project_name=project_name, module_name=module_name)
        if not result.ok:
            note = f"\n\n_{result.note}_" if result.note else ""
            return {"handled": True, "message": f"Risk lookup failed: `{result.error}`{note}"}
        title_parts = ["Project Risks"]
        if project_name:
            title_parts.append(f"– Project: {project_name}")
        if module_name:
            title_parts.append(f"/ Module: {module_name}")
        return {
            "handled": True,
            "message": fmt_action(
                title=" ".join(title_parts),
                table=result.table or "risks",
                schema=result.schema,
                rows=result.rows or [],
            ),
        }

    return None
