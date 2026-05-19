from __future__ import annotations

from project_intel.data.qa_access import get_case_rows, get_test_case_rows
from project_intel.services.handlers.formatters import fmt_tabular, fmt_report
from project_intel.services.handlers.helpers import extract_after

HandlerResult = dict | None


def handle(text: str, lower: str, stage: str | None) -> HandlerResult:
    """Routes QA case and test-case use cases. Returns None if not matched."""

    # ---------------------------------------------------------------
    # DEFECT SUMMARY REPORTS (aggregated markdown)
    # ---------------------------------------------------------------

    if "module-wise defect summary report" in lower or "module wise defect summary report" in lower:
        result = get_case_rows(stage=stage, limit=200)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Defect report failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_report(
                title=f"{stage + ' ' if stage else ''}Module-wise Defect Summary Report",
                table=f"{result.schema}.{result.table}" if result.schema else (result.table or "cases"),
                rows=result.rows or [],
                group_col_candidates=["module_name", "modulename", "module"],
            ),
        }

    if "project-wise defect summary report" in lower or "project wise defect summary report" in lower:
        project_name = extract_after(text, "for project")
        result = get_case_rows(stage=stage, project_name=project_name, limit=200)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Defect report failed (`{result.error}`).{note}"}
        title = f"{stage + ' ' if stage else ''}Project-wise Defect Summary Report"
        if project_name:
            title += f" – {project_name}"
        return {
            "handled": True,
            "message": fmt_report(
                title=title,
                table=f"{result.schema}.{result.table}" if result.schema else (result.table or "cases"),
                rows=result.rows or [],
                group_col_candidates=["module_name", "modulename", "module", "status", "statuscode"],
            ),
        }

    # ---------------------------------------------------------------
    # TEST CASE SUMMARY REPORTS (aggregated markdown)
    # ---------------------------------------------------------------

    if (
        "module-wise test cases summary report" in lower
        or "module wise test cases summary report" in lower
        or "module-wise test case summary report" in lower
        or "module wise test case summary report" in lower
    ):
        result = get_test_case_rows(stage=stage, limit=200)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case report failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_report(
                title=f"{stage + ' ' if stage else ''}Module-wise Test Cases Summary Report",
                table=f"{result.schema}.{result.table}" if result.schema else (result.table or "testcases"),
                rows=result.rows or [],
                group_col_candidates=["module_name", "modulename", "module"],
            ),
        }

    if (
        "project-wise test cases summary report" in lower
        or "project wise test cases summary report" in lower
        or "project-wise test case summary report" in lower
        or "project wise test case summary report" in lower
    ):
        project_name = extract_after(text, "for project")
        result = get_test_case_rows(stage=stage, project_name=project_name, limit=200)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case report failed (`{result.error}`).{note}"}
        title = f"{stage + ' ' if stage else ''}Project-wise Test Cases Summary Report"
        if project_name:
            title += f" – {project_name}"
        return {
            "handled": True,
            "message": fmt_report(
                title=title,
                table=f"{result.schema}.{result.table}" if result.schema else (result.table or "testcases"),
                rows=result.rows or [],
                group_col_candidates=["module_name", "modulename", "module", "status", "statuscode"],
            ),
        }

    # ---------------------------------------------------------------
    # CASE SUMMARIES (raw row listings)
    # ---------------------------------------------------------------

    if "case id summary" in lower and "test case" not in lower:
        case_id = extract_after(text, "for case")
        if not case_id:
            return {"handled": True, "message": "Please provide a case id (e.g. `... for case 12345`)."}
        result = get_case_rows(stage=stage, case_id=case_id, limit=50)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Case {case_id}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "cases"),
                rows=result.rows or [],
            ),
        }

    if "module-wise case summary" in lower or "module wise case summary" in lower:
        module_name = extract_after(text, "for module")
        if not module_name:
            return {"handled": True, "message": "Please provide a module name (e.g. `... for module Payments`)."}
        result = get_case_rows(stage=stage, module_name=module_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Cases for module: {module_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "cases"),
                rows=result.rows or [],
            ),
        }

    if "journey wise case summary" in lower or "journey-wise case summary" in lower:
        journey_name = extract_after(text, "for journey")
        if not journey_name:
            return {"handled": True, "message": "Please provide a journey name (e.g. `... for journey Onboarding`)."}
        result = get_case_rows(stage=stage, journey_name=journey_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Cases for journey: {journey_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "cases"),
                rows=result.rows or [],
            ),
        }

    if "project wise case summary" in lower or "project-wise case summary" in lower:
        project_name = extract_after(text, "for project")
        if not project_name:
            return {"handled": True, "message": "Please provide a project name (e.g. `... for project Apollo`)."}
        result = get_case_rows(stage=stage, project_name=project_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Cases for project: {project_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "cases"),
                rows=result.rows or [],
            ),
        }

    # ---------------------------------------------------------------
    # TEST CASE SUMMARIES (raw row listings)
    # ---------------------------------------------------------------

    if "test case id summary" in lower:
        test_case_id = extract_after(text, "for test case") or extract_after(text, "for testcase")
        if not test_case_id:
            return {"handled": True, "message": "Please provide a test case id (e.g. `... for test case TC-123`)."}
        result = get_test_case_rows(stage=stage, test_case_id=test_case_id, limit=50)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Test case {test_case_id}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "testcases"),
                rows=result.rows or [],
            ),
        }

    if "module-wise test case summary" in lower or "module wise test case summary" in lower:
        module_name = extract_after(text, "for module")
        if not module_name:
            return {"handled": True, "message": "Please provide a module name (e.g. `... for module Payments`)."}
        result = get_test_case_rows(stage=stage, module_name=module_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Test cases for module: {module_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "testcases"),
                rows=result.rows or [],
            ),
        }

    if "journey wise test case summary" in lower or "journey-wise test case summary" in lower:
        journey_name = extract_after(text, "for journey")
        if not journey_name:
            return {"handled": True, "message": "Please provide a journey name (e.g. `... for journey Onboarding`)."}
        result = get_test_case_rows(stage=stage, journey_name=journey_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Test cases for journey: {journey_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "testcases"),
                rows=result.rows or [],
            ),
        }

    if "project wise test case summary" in lower or "project-wise test case summary" in lower:
        project_name = extract_after(text, "for project")
        if not project_name:
            return {"handled": True, "message": "Please provide a project name (e.g. `... for project Apollo`)."}
        result = get_test_case_rows(stage=stage, project_name=project_name, limit=100)
        if not result.ok:
            note = f"\n\nNote: {result.note}" if result.note else ""
            return {"handled": True, "message": f"Test case lookup failed (`{result.error}`).{note}"}
        return {
            "handled": True,
            "message": fmt_tabular(
                title=f"{stage + ' ' if stage else ''}Test cases for project: {project_name}",
                table=f"{result.schema}.{result.table}" if result.schema and result.table else (result.table or "testcases"),
                rows=result.rows or [],
            ),
        }

    return None
