from __future__ import annotations

import logging
import os
import re

from project_intel.core.config import OPENAI_MODEL
from project_intel.core.openai_client import get_openai_clients
from project_intel.data.db_access import get_db_config
from project_intel.data.schema_access import build_schema_overview_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex-based write-operation markers (first-pass, fast)
# ---------------------------------------------------------------------------

_UNSAFE_PATTERNS = [
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bmerge\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bexecute\b",
    r"\bexec\b",
    r"\bcall\b",
    r"\bcopy\b",
    r"\binto\s+#",
    r"\bselect\s+.*\s+into\b",
]

_UNSAFE_RE = re.compile("|".join(_UNSAFE_PATTERNS), flags=re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# AST-based validation (sqlglot — optional but strongly preferred)
# ---------------------------------------------------------------------------

try:
    import sqlglot  # type: ignore[import]
    import sqlglot.expressions as exp  # type: ignore[import]

    _SQLGLOT_AVAILABLE = True

    _WRITE_NODE_TYPES = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Create,
        exp.Drop,
        exp.Alter,
        exp.TruncateTable,
        exp.Grant,
        exp.Revoke,
        exp.Command,
    )

    def _ast_validate(sql: str, allowed_tables: set[str] | None = None) -> tuple[bool, str]:
        """
        Returns (is_safe, reason).
        allowed_tables: if provided, any table not in the set is rejected.
        """
        try:
            dialect = "tsql" if _db_type() != "postgres" else "postgres"
            parsed = sqlglot.parse_one(sql, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE)
        except Exception as parse_err:
            # Can't parse → fall back to regex result (already passed by caller)
            logger.debug("sqlglot parse failed: %s", parse_err)
            return True, ""

        for node_type in _WRITE_NODE_TYPES:
            if parsed.find(node_type):
                return False, f"Write operation detected: {node_type.__name__}"

        if allowed_tables:
            tables_in_query = {t.name.lower() for t in parsed.find_all(exp.Table) if t.name}
            disallowed = tables_in_query - {t.lower() for t in allowed_tables}
            if disallowed:
                return False, f"Tables not in allowlist: {disallowed}"

        return True, ""

except ImportError:
    _SQLGLOT_AVAILABLE = False

    def _ast_validate(sql: str, allowed_tables: set[str] | None = None) -> tuple[bool, str]:  # type: ignore[misc]
        return True, ""  # graceful degradation


def _db_type() -> str:
    return (get_db_config().get("db_type") or "sqlserver").strip().lower()


# ---------------------------------------------------------------------------
# Public safety checks
# ---------------------------------------------------------------------------

def is_safe_readonly_sql(sql: str, allowed_tables: set[str] | None = None) -> bool:
    """
    Two-layer check:
      1. Regex: fast rejection of write keywords.
      2. AST (sqlglot): structural validation and optional table allowlist.
    """
    raw = (sql or "").strip()
    if not raw:
        return False
    s = raw.rstrip(";").strip()
    lower = s.lower()

    # Must start with SELECT or WITH
    if not (lower.startswith("select") or lower.startswith("with")):
        return False

    # Reject multiple statements
    if ";" in s:
        return False

    # Regex pass
    if _UNSAFE_RE.search(lower):
        return False

    # AST pass
    ok, reason = _ast_validate(s, allowed_tables)
    if not ok:
        logger.warning("SQL rejected by AST guard: %s — SQL: %.200s", reason, s)
        return False

    return True


# ---------------------------------------------------------------------------
# Row-limit enforcement
# ---------------------------------------------------------------------------

def enforce_row_limit(sql: str, *, limit: int = 200) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    safe_limit = max(1, min(int(limit or 200), 500))
    db_type = _db_type()

    if re.search(r"\blimit\s+\d+\b", s, flags=re.IGNORECASE):
        return s
    if re.search(r"\btop\s+\d+\b", s, flags=re.IGNORECASE):
        return s

    if db_type == "postgres":
        return f"{s} LIMIT {safe_limit}"

    m = re.match(r"^\s*select\s+(distinct\s+)?", s, flags=re.IGNORECASE)
    if not m:
        return s
    distinct = (m.group(1) or "").strip()
    rest = s[m.end():]
    if distinct:
        return f"SELECT DISTINCT TOP {safe_limit} {rest}"
    return f"SELECT TOP {safe_limit} {rest}"


# ---------------------------------------------------------------------------
# LLM-powered SQL generation (any table)
# ---------------------------------------------------------------------------

def generate_sql_any_table(user_input: str) -> str | None:
    """
    Uses an LLM to produce a read-only SQL query against the connected database.
    Returns None when LLM is not configured or all clients fail.
    """
    clients = get_openai_clients()
    if not clients:
        return None

    db_type = _db_type()
    dialect_rule = (
        "Use SQL Server syntax (TOP, not LIMIT)."
        if db_type != "postgres"
        else "Use PostgreSQL syntax (LIMIT, not TOP)."
    )

    max_tables = int(os.getenv("DB_SCHEMA_OVERVIEW_MAX_TABLES", "40") or "40")
    max_cols = int(os.getenv("DB_SCHEMA_OVERVIEW_MAX_COLS", "25") or "25")
    schema_text = build_schema_overview_text(max_tables=max_tables, max_cols=max_cols)

    prompt = f"""You are an expert database developer.

Database schema overview:
{schema_text}

Rules:
- {dialect_rule}
- Output ONLY SQL (no explanation, no markdown fences).
- READ-ONLY: only SELECT / WITH queries. Absolutely no INSERT, UPDATE, DELETE, DDL.
- Single query only — no semicolons, no multiple statements.
- Cap result size: include TOP/LIMIT <= 200 unless the user explicitly asks for more.

User request:
{user_input}
"""

    last_error = ""
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            sql = (resp.choices[0].message.content or "").strip()
            sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()
            return sql
        except Exception as error:
            last_error = str(error)
            status_code = getattr(error, "status_code", None)
            if status_code is None:
                resp2 = getattr(error, "response", None)
                status_code = getattr(resp2, "status_code", None)
            if status_code in (401, 403, 404, 429):
                continue
            raise

    logger.warning("generate_sql_any_table: all clients failed — %s", last_error)
    return None
