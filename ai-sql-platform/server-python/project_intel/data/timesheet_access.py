from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import os
import re
import uuid

from sqlalchemy import text

from db import SessionLocal
from project_intel.core.config import DB_SCHEMA, TIMESHEET_ITEMS
from project_intel.data.db_access import (
    get_db_config,
    get_project_account_name_column,
    get_project_columns,
    get_project_id_column,
    get_project_name_column,
    get_project_portfolio_name_column,
    get_project_status_column,
    get_project_table_name,
    make_json_safe,
)


@dataclass(frozen=True)
class EmployeeIdentity:
    ownerid: int
    userid: int
    employee_customobjectid: int | None = None


def _qualified(table: str) -> str:
    schema = DB_SCHEMA or "dbo"
    return f"{schema}.{table}"


def _schema_search_path() -> list[str]:
    raw = (os.getenv("DB_SEARCH_PATH", "") or "").strip()
    schemas = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
    # Ensure DB_SCHEMA is present and first-choice.
    preferred = (DB_SCHEMA or "").strip()
    if preferred:
        schemas = [preferred] + [s for s in schemas if s != preferred]
    # Reasonable fallback for Postgres installs.
    if "public" not in schemas:
        schemas.append("public")
    # De-dup preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for s in schemas:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def describe_table_columns(table: str) -> dict:
    """
    Returns column metadata for a table across the configured schema search path.
    Helpful for aligning the app's timesheet insert with the *actual* DB schema.
    """
    table = (table or "").strip()
    if not table:
        return {"ok": False, "error": "missing_table"}

    schemas = _schema_search_path()
    db = SessionLocal()
    try:
        for schema in schemas:
            rows = db.execute(
                text(
                    """
                    SELECT column_name, data_type, is_nullable, column_default, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = :table
                    ORDER BY ordinal_position
                    """
                ),
                {"schema": schema, "table": table},
            ).fetchall()
            if rows:
                return {
                    "ok": True,
                    "schema": schema,
                    "table": table,
                    "columns": [
                        {
                            "name": r[0],
                            "type": r[1],
                            "nullable": (str(r[2] or "").upper() == "YES"),
                            "default": r[3],
                            "position": int(r[4]) if r[4] is not None else None,
                        }
                        for r in rows
                    ],
                }
        return {"ok": False, "error": "table_not_found", "table": table, "schemas_tried": schemas}
    finally:
        db.close()


def find_employee_identity(employee_name: str) -> EmployeeIdentity | None:
    """
    Resolve the application's 'employee name' into the identifiers used by timesheet rows.
    Observed mapping in this DB:
    - dbo.employee.subject == employee display name
    - dbo.employee.userid == timesheet.assigntoid / createdby
    - dbo.employee.ownerid == timesheet.ownerid
    """
    name = (employee_name or "").strip()
    if not name:
        return None

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT ownerid, userid, customobjectid
                FROM {_qualified('employee')}
                WHERE subject ILIKE :name
                ORDER BY lastmodifiedon DESC NULLS LAST, createdon DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"name": f"%{name}%"},
        ).fetchone()
        if not row:
            return None
        ownerid, userid, customobjectid = row[0], row[1], row[2]
        return EmployeeIdentity(int(ownerid), int(userid), int(customobjectid) if customobjectid is not None else None)
    finally:
        db.close()


def search_employees(q: str, limit: int = 20) -> list[str]:
    """
    Lightweight employee name autocomplete.
    Returns employee display names (employee.subject) matching the query substring.
    """
    needle = (q or "").strip()
    if len(needle) < 2:
        return []

    db_type = (get_db_config().get("db_type") or "sqlserver").strip().lower()
    schema = DB_SCHEMA or "dbo"
    table = f"{schema}.employee"

    # Prefer case-insensitive matching across DBs.
    if db_type == "postgres":
        where = "subject ILIKE :q"
    else:
        where = "LOWER(subject) LIKE LOWER(:q)"

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                f"""
                SELECT DISTINCT subject
                FROM {table}
                WHERE subject IS NOT NULL
                  AND {where}
                ORDER BY subject
                LIMIT :limit
                """
            ),
            {"q": f"%{needle}%", "limit": max(1, min(int(limit), 50))},
        ).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]
    finally:
        db.close()


def _parse_hhmm(value: str, default: time) -> time:
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        hour_s, minute_s = raw.split(":")
        return time(hour=int(hour_s), minute=int(minute_s))
    except Exception:
        return default


def _dateid(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _get_next_timesheet_id(db, ownerid: int) -> int:
    # Uses the platform's id allocator; itemid 363 is Timesheet (as per comments in DB procedure).
    result = db.execute(text(f"CALL {_qualified('getnextidblock')}(:ownerid, 363, 1, NULL)"), {"ownerid": ownerid})
    row = result.fetchone()
    if not row or row[0] is None:
        raise RuntimeError("Failed to allocate timesheetid")
    return int(row[0])


def _find_template_timesheet(db, ownerid: int, projectid: int, userid: int, item: str) -> dict | None:
    # Prefer a row matching the same project+user+item ("Config") so IDs (role/location/task etc.) are consistent.
    row = db.execute(
        text(
            f"""
            SELECT *
            FROM {_qualified('timesheet')}
            WHERE ownerid = :ownerid
              AND projectid = :projectid
              AND assigntoid = :userid
              AND COALESCE(LOWER(relatedtoname), '') = LOWER(:item)
            ORDER BY createdon DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"ownerid": ownerid, "projectid": projectid, "userid": userid, "item": item},
    ).mappings().fetchone()
    if row:
        return dict(row)

    # Fallback: any row for the project (still helps set relatedtotype/task/team/location defaults).
    row = db.execute(
        text(
            f"""
            SELECT *
            FROM {_qualified('timesheet')}
            WHERE ownerid = :ownerid
              AND projectid = :projectid
            ORDER BY createdon DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"ownerid": ownerid, "projectid": projectid},
    ).mappings().fetchone()
    return dict(row) if row else None


def list_allocated_projects(employee_name: str, q: str = "", limit: int = 200) -> list[dict]:
    identity = find_employee_identity(employee_name)
    if identity is None or identity.employee_customobjectid is None:
        return []

    table_name = get_project_table_name()
    project_cols = set(get_project_columns() or [])
    id_col = get_project_id_column()
    name_col = get_project_name_column()
    status_col = get_project_status_column()

    # Default schema-qualified project table.
    project_table = f"{DB_SCHEMA}.{table_name}"
    alloc_table = _qualified("employeeallocation")

    where = ""
    params = {"eid": identity.employee_customobjectid, "ownerid": identity.ownerid, "limit": max(1, min(int(limit), 500))}
    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        where = f" AND (CAST(p.{id_col} AS TEXT) ILIKE :q OR p.{name_col} ILIKE :q)"

    select_status = f", p.{status_col} AS status" if status_col in project_cols else ""

    sql = f"""
      SELECT DISTINCT
        p.{id_col} AS project_id,
        p.{name_col} AS project_name
        {select_status}
      FROM {alloc_table} ea
      JOIN {project_table} p ON p.{id_col} = ea.projectid
      WHERE ea.ownerid = :ownerid
        AND ea.employeeid = :eid
        {where}
      ORDER BY project_name
      LIMIT :limit
    """

    db = SessionLocal()
    try:
        rows = db.execute(text(sql), params).mappings().fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def list_timesheet_templates(employee_name: str, projectid: int, limit: int = 10) -> list[dict]:
    identity = find_employee_identity(employee_name)
    if identity is None:
        return []

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                f"""
                SELECT timesheetid, subject, relatedtoname, effort, projecttaskid, engagementroleid, engagementlocationid,
                       CAST(startdate AS TIME) AS start_time, CAST(enddate AS TIME) AS end_time, createdon
                FROM {_qualified('timesheet')}
                WHERE ownerid = :ownerid AND projectid = :projectid AND assigntoid = :userid
                ORDER BY createdon DESC NULLS LAST
                LIMIT 50
                """
            ),
            {"ownerid": identity.ownerid, "projectid": int(projectid), "userid": identity.userid},
        ).mappings().fetchall()

        seen: set[tuple] = set()
        templates: list[dict] = []
        for r in rows:
            key = (
                r.get("subject"),
                r.get("relatedtoname"),
                r.get("effort"),
                r.get("projecttaskid"),
                r.get("engagementroleid"),
                r.get("engagementlocationid"),
                str(r.get("start_time")),
                str(r.get("end_time")),
            )
            if key in seen:
                continue
            seen.add(key)
            templates.append(dict(r))
            if len(templates) >= max(1, min(int(limit), 25)):
                break
        return templates
    finally:
        db.close()


def list_timesheet_options(projectid: int, limit: int = 50) -> dict:
    db = SessionLocal()
    try:
        items = db.execute(
            text(
                f"""
                SELECT DISTINCT relatedtoname
                FROM {_qualified('timesheet')}
                WHERE projectid = :projectid AND relatedtoname IS NOT NULL
                ORDER BY relatedtoname
                LIMIT :limit
                """
            ),
            {"projectid": int(projectid), "limit": max(1, min(int(limit), 200))},
        ).fetchall()

        roles = db.execute(
            text(
                f"""
                SELECT DISTINCT engagementroleid
                FROM {_qualified('timesheet')}
                WHERE projectid = :projectid AND engagementroleid IS NOT NULL
                ORDER BY engagementroleid
                LIMIT :limit
                """
            ),
            {"projectid": int(projectid), "limit": max(1, min(int(limit), 200))},
        ).fetchall()

        locations = db.execute(
            text(
                f"""
                SELECT DISTINCT engagementlocationid
                FROM {_qualified('timesheet')}
                WHERE projectid = :projectid AND engagementlocationid IS NOT NULL
                ORDER BY engagementlocationid
                LIMIT :limit
                """
            ),
            {"projectid": int(projectid), "limit": max(1, min(int(limit), 200))},
        ).fetchall()

        observed_items = [r[0] for r in items if r and r[0]]
        combined_items = [*TIMESHEET_ITEMS, *observed_items]
        # de-dup preserving order
        seen: set[str] = set()
        dedup_items: list[str] = []
        for it in combined_items:
            s = str(it).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            dedup_items.append(s)

        return {
            "items": dedup_items,
            "engagementroleids": [int(r[0]) for r in roles if r and r[0] is not None],
            "engagementlocationids": [int(r[0]) for r in locations if r and r[0] is not None],
        }
    finally:
        db.close()


def fill_timesheet_entry(
    *,
    projectid: int,
    employee_name: str,
    work_date: date,
    start_time_hhmm: str = "09:00",
    end_time_hhmm: str = "17:00",
    effort_minutes: int = 480,
    description: str = "SDG development",
    item: str = "Config",
    template_timesheetid: int | None = None,
    engagementroleid: int | None = None,
    engagementlocationid: int | None = None,
    projecttaskid: int | None = None,
) -> dict:
    identity = find_employee_identity(employee_name)
    if identity is None:
        raise ValueError(f"Employee not found for name: {employee_name}")

    ownerid = identity.ownerid
    userid = identity.userid

    start_t = _parse_hhmm(start_time_hhmm, time(9, 0))
    end_t = _parse_hhmm(end_time_hhmm, time(17, 0))
    start_dt = datetime.combine(work_date, start_t)
    end_dt = datetime.combine(work_date, end_t)
    if end_dt <= start_dt:
        raise ValueError("end_time must be after start_time")

    db = SessionLocal()
    try:
        # Avoid duplicates for the same day/project/user.
        exists = db.execute(
            text(
                f"""
                SELECT timesheetid
                FROM {_qualified('timesheet')}
                WHERE ownerid = :ownerid
                  AND projectid = :projectid
                  AND assigntoid = :userid
                  AND CAST(startdate AS DATE) = :work_date
                LIMIT 1
                """
            ),
            {"ownerid": ownerid, "projectid": int(projectid), "userid": userid, "work_date": work_date},
        ).fetchone()
        if exists and exists[0] is not None:
            return {"already_exists": True, "timesheetid": int(exists[0])}

        template = {}
        if template_timesheetid:
            row = db.execute(
                text(
                    f"""
                    SELECT *
                    FROM {_qualified('timesheet')}
                    WHERE ownerid = :ownerid AND timesheetid = :tid
                    LIMIT 1
                    """
                ),
                {"ownerid": ownerid, "tid": int(template_timesheetid)},
            ).mappings().fetchone()
            template = dict(row) if row else {}
        if not template:
            template = _find_template_timesheet(db, ownerid, int(projectid), userid, item) or {}
        if not template:
            raise ValueError(
                "No existing timesheet template found for this employee+project. "
                "To ensure 100% accuracy, create one entry in the portal first or pass template_timesheetid."
            )
        timesheetid = _get_next_timesheet_id(db, ownerid)

        # Use template values where they exist to preserve platform-required IDs.
        statuscodeid = template.get("statuscodeid", 6935)
        statusid = template.get("statusid", 3)
        relatedtotypeid = template.get("relatedtotypeid", 100062)
        relatedtoid = template.get("relatedtoid", 118900)
        relatedtoname = (item or "").strip() or template.get("relatedtoname", "Config")
        accountid = template.get("accountid", 0)
        projecttaskid = projecttaskid if projecttaskid is not None else template.get("projecttaskid", 202)
        teamid = template.get("teamid", 7)
        engagementroleid = engagementroleid if engagementroleid is not None else template.get("engagementroleid", 2)
        engagementlocationid = engagementlocationid if engagementlocationid is not None else template.get("engagementlocationid", 2)
        createdbytype = template.get("createdbytype", -1)
        lastmodifiedbytype = template.get("lastmodifiedbytype", 2)
        layoutid = template.get("layoutid", -1)
        processid = template.get("processid", 0)

        now = datetime.now()
        uniqueid = str(uuid.uuid4())

        db.execute(
            text(
                f"""
                INSERT INTO {_qualified('timesheet')}
                (ownerid, timesheetid, subject, statuscodeid, statusid, relatedtotypeid, relatedtoid,
                 startdate, enddate, createdby, createdon, lastmodifiedby, lastmodifiedon, layoutid, processid,
                 createdbytype, lastmodifiedbytype, previousstatuscodeid, uniqueid, projectid, accountid, relatedtoname,
                 effort, assigntoid, isescalated, escalatedcount, openescalatedcount, lastactionid, ipaddress,
                 projecttaskid, teamid, engagementroleid, engagementlocationid, employeeid)
                VALUES
                (:ownerid, :timesheetid, :subject, :statuscodeid, :statusid, :relatedtotypeid, :relatedtoid,
                 :startdate, :enddate, :createdby, :createdon, :lastmodifiedby, :lastmodifiedon, :layoutid, :processid,
                 :createdbytype, :lastmodifiedbytype, 0, :uniqueid, :projectid, :accountid, :relatedtoname,
                 :effort, :assigntoid, 0, 0, 0, 0, :ipaddress,
                 :projecttaskid, :teamid, :engagementroleid, :engagementlocationid, 0)
                """
            ),
            {
                "ownerid": ownerid,
                "timesheetid": timesheetid,
                "subject": description,
                "statuscodeid": statuscodeid,
                "statusid": statusid,
                "relatedtotypeid": relatedtotypeid,
                "relatedtoid": relatedtoid,
                "startdate": start_dt,
                "enddate": end_dt,
                "createdby": userid,
                "createdon": now,
                "lastmodifiedby": userid,
                "lastmodifiedon": now,
                "layoutid": layoutid,
                "processid": processid,
                "createdbytype": createdbytype,
                "lastmodifiedbytype": lastmodifiedbytype,
                "uniqueid": uniqueid,
                "projectid": int(projectid),
                "accountid": accountid,
                "relatedtoname": relatedtoname,
                "effort": int(effort_minutes),
                "assigntoid": userid,
                "ipaddress": template.get("ipaddress", "127.0.0.1"),
                "projecttaskid": projecttaskid,
                "teamid": teamid,
                "engagementroleid": engagementroleid,
                "engagementlocationid": engagementlocationid,
            },
        )
        db.commit()

        inserted = db.execute(
            text(
                f"""
                SELECT *
                FROM {_qualified('timesheet')}
                WHERE ownerid = :ownerid AND timesheetid = :timesheetid
                """
            ),
            {"ownerid": ownerid, "timesheetid": timesheetid},
        ).mappings().fetchone()
        return {"ok": True, "timesheet": dict(inserted) if inserted else {"ownerid": ownerid, "timesheetid": timesheetid}}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Read-only timesheet summary helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimesheetSummaryResult:
    ok: bool
    rows: list[dict] | None = None
    count: int = 0
    error: str | None = None
    note: str | None = None


def _ts_db_type() -> str:
    return (get_db_config().get("db_type") or "sqlserver").strip().lower()


def _ts_like(col: str, param: str) -> str:
    if _ts_db_type() == "postgres":
        return f"{col} ILIKE :{param}"
    return f"LOWER({col}) LIKE LOWER(:{param})"


def _ts_limit(sql: str, limit: int) -> str:
    safe = max(1, min(int(limit), 500))
    s = sql.strip()
    if _ts_db_type() == "postgres":
        return f"{s} LIMIT {safe}"
    m = re.match(r"^(select\s+)(distinct\s+)?", s, re.IGNORECASE)
    if not m:
        return s
    distinct = (m.group(2) or "").strip()
    rest = s[m.end():]
    if distinct:
        return f"SELECT DISTINCT TOP {safe} {rest}"
    return f"SELECT TOP {safe} {rest}"


def _ts_fetch(sql: str, params: dict) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.execute(text(sql), params).mappings().fetchall()
        return make_json_safe([dict(r) for r in rows])
    finally:
        db.close()


def _ts_tables() -> tuple[str, str, str, str, str]:
    """Returns (ts, emp, proj, id_col, name_col) qualified table references."""
    schema = DB_SCHEMA or "dbo"
    ts = f"{schema}.timesheet"
    emp = f"{schema}.employee"
    proj = f"{schema}.{get_project_table_name()}"
    id_col = get_project_id_column()
    name_col = get_project_name_column()
    return ts, emp, proj, id_col, name_col


def get_employee_timesheet_summary(*, employee_name: str, limit: int = 200) -> TimesheetSummaryResult:
    """Timesheet entries grouped by project and date for one employee."""
    ts, emp, proj, id_col, name_col = _ts_tables()
    sql = f"""
        SELECT
            e.subject AS employee_name,
            p.{name_col} AS project_name,
            CAST(t.startdate AS DATE) AS work_date,
            COUNT(*) AS entries,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        JOIN {proj} p ON p.{id_col} = t.projectid
        WHERE {_ts_like("e.subject", "emp_name")}
        GROUP BY e.subject, p.{name_col}, CAST(t.startdate AS DATE)
        ORDER BY work_date DESC, project_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {"emp_name": f"%{employee_name}%"})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc), note="Ensure timesheet, employee, and project tables exist.")


def get_project_timesheet_summary(*, project_name: str, limit: int = 200) -> TimesheetSummaryResult:
    """Timesheet entries grouped by employee and date for one project."""
    ts, emp, proj, id_col, name_col = _ts_tables()
    sql = f"""
        SELECT
            p.{name_col} AS project_name,
            e.subject AS employee_name,
            CAST(t.startdate AS DATE) AS work_date,
            COUNT(*) AS entries,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        JOIN {proj} p ON p.{id_col} = t.projectid
        WHERE {_ts_like("p." + name_col, "proj_name")}
        GROUP BY p.{name_col}, e.subject, CAST(t.startdate AS DATE)
        ORDER BY work_date DESC, employee_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {"proj_name": f"%{project_name}%"})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc), note="Ensure timesheet, employee, and project tables exist.")


def get_model_timesheet_summary(*, model_name: str, limit: int = 200) -> TimesheetSummaryResult:
    """Timesheet entries grouped by engagement model/item (relatedtoname)."""
    ts, emp, _, _, _ = _ts_tables()
    sql = f"""
        SELECT
            t.relatedtoname AS model_name,
            e.subject AS employee_name,
            CAST(t.startdate AS DATE) AS work_date,
            COUNT(*) AS entries,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        WHERE {_ts_like("t.relatedtoname", "model_name")}
        GROUP BY t.relatedtoname, e.subject, CAST(t.startdate AS DATE)
        ORDER BY work_date DESC, employee_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {"model_name": f"%{model_name}%"})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc))


def get_account_timesheet_summary(*, account_name: str, limit: int = 200) -> TimesheetSummaryResult:
    """Timesheet hours grouped by project and employee for one account."""
    ts, emp, proj, id_col, name_col = _ts_tables()
    acct_col = get_project_account_name_column()
    sql = f"""
        SELECT
            p.{acct_col} AS account_name,
            p.{name_col} AS project_name,
            e.subject AS employee_name,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        JOIN {proj} p ON p.{id_col} = t.projectid
        WHERE {_ts_like("p." + acct_col, "account_name")}
        GROUP BY p.{acct_col}, p.{name_col}, e.subject
        ORDER BY account_name, project_name, employee_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {"account_name": f"%{account_name}%"})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc))


def get_portfolio_timesheet_summary(*, portfolio_name: str, limit: int = 200) -> TimesheetSummaryResult:
    """Timesheet hours grouped by project and employee for one portfolio."""
    ts, emp, proj, id_col, name_col = _ts_tables()
    portfolio_col = get_project_portfolio_name_column()
    sql = f"""
        SELECT
            p.{portfolio_col} AS portfolio_name,
            p.{name_col} AS project_name,
            e.subject AS employee_name,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        JOIN {proj} p ON p.{id_col} = t.projectid
        WHERE {_ts_like("p." + portfolio_col, "portfolio_name")}
        GROUP BY p.{portfolio_col}, p.{name_col}, e.subject
        ORDER BY portfolio_name, project_name, employee_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {"portfolio_name": f"%{portfolio_name}%"})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc))


def get_org_timesheet_summary(*, limit: int = 200) -> TimesheetSummaryResult:
    """Organisation-wide timesheet summary grouped by employee and project."""
    ts, emp, proj, id_col, name_col = _ts_tables()
    sql = f"""
        SELECT
            e.subject AS employee_name,
            p.{name_col} AS project_name,
            COUNT(*) AS entries,
            SUM(t.effort) AS total_effort_minutes,
            ROUND(CAST(SUM(t.effort) AS FLOAT) / 60.0, 1) AS total_hours
        FROM {ts} t
        JOIN {emp} e ON e.userid = t.assigntoid AND e.ownerid = t.ownerid
        JOIN {proj} p ON p.{id_col} = t.projectid
        GROUP BY e.subject, p.{name_col}
        ORDER BY employee_name, project_name
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {})
        return TimesheetSummaryResult(ok=True, rows=rows, count=len(rows))
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc))


def get_pending_timesheet_report(*, limit: int = 200) -> TimesheetSummaryResult:
    """Employees who have NOT submitted any timesheet entry for today."""
    schema = DB_SCHEMA or "dbo"
    ts = f"{schema}.timesheet"
    emp = f"{schema}.employee"
    db_type = _ts_db_type()
    today_expr = "CURRENT_DATE" if db_type == "postgres" else "CAST(GETDATE() AS DATE)"
    sql = f"""
        SELECT e.subject AS employee_name
        FROM {emp} e
        WHERE NOT EXISTS (
            SELECT 1 FROM {ts} t
            WHERE t.assigntoid = e.userid
              AND t.ownerid = e.ownerid
              AND CAST(t.startdate AS DATE) = {today_expr}
        )
        ORDER BY e.subject
    """
    sql = _ts_limit(sql, limit)
    try:
        rows = _ts_fetch(sql, {})
        return TimesheetSummaryResult(
            ok=True, rows=rows, count=len(rows),
            note="Employees with no timesheet entry submitted for today."
        )
    except Exception as exc:
        return TimesheetSummaryResult(ok=False, error=str(exc))
