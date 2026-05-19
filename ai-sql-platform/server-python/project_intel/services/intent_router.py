from __future__ import annotations

"""
Embedding-based intent router for usecase_dispatch.

At startup, builds a small vector index from canonical use-case phrases.
On each query, finds the nearest phrase by cosine similarity.
If similarity >= INTENT_ROUTING_THRESHOLD (default 0.55) the dispatcher:
  1. Prepends the matched canonical phrase to the query text so the
     downstream handler's keyword checks reliably trigger.
  2. Calls the matched handler directly, skipping the rest of the chain.

If the router is unavailable (sentence-transformers not installed, or
similarity below threshold), the existing keyword chain runs unchanged.

Environment variables
---------------------
  INTENT_ROUTING_THRESHOLD   float, default 0.55
  INTENT_ROUTING_ENABLED     "0" to disable entirely (default: enabled)
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_THRESHOLD = float(os.getenv("INTENT_ROUTING_THRESHOLD", "0.55") or "0.55")
_ENABLED = os.getenv("INTENT_ROUTING_ENABLED", "1").strip().lower() not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# Intent catalogue
#
# handler_index maps to _HANDLER_CHAIN in usecase_dispatch.py:
#   0 = timesheet_handlers
#   1 = action_handlers
#   2 = qa_handlers
#   3 = portal_handlers
#
# canonical  — the phrase the handler's `in lower` checks expect.
#              Prepended to the user text when this intent fires so the
#              keyword checks inside the handler always pass.
# phrases    — natural-language paraphrases used only for embedding.
#              Add more to improve fuzzy coverage without changing handlers.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Intent:
    canonical: str
    handler_index: int
    phrases: tuple[str, ...]


_CATALOGUE: list[_Intent] = [
    # ---- Timesheet (0) ----
    _Intent(
        canonical="individual employee timesheet summary",
        handler_index=0,
        phrases=(
            "individual employee timesheet summary",
            "retrieve employee timesheet summary",
            "show timesheet for employee",
            "employee timesheet data",
            "timesheet history for a person",
        ),
    ),
    _Intent(
        canonical="model wise timesheet booking summary",
        handler_index=0,
        phrases=(
            "model wise timesheet booking summary",
            "model-wise timesheet booking summary",
            "timesheet summary by model",
            "booking hours per model",
            "model timesheet overview",
        ),
    ),
    _Intent(
        canonical="project wise timesheet booking summary",
        handler_index=0,
        phrases=(
            "project wise timesheet booking summary",
            "project-wise timesheet booking summary",
            "timesheet by project",
            "hours logged per project",
            "project timesheet breakdown",
        ),
    ),
    _Intent(
        canonical="account wise timesheet booking summary",
        handler_index=0,
        phrases=(
            "account wise timesheet booking summary",
            "account-wise timesheet booking summary",
            "timesheet by account",
            "booking summary per account",
            "account timesheet breakdown",
        ),
    ),
    _Intent(
        canonical="portfolio wise timesheet booking summary",
        handler_index=0,
        phrases=(
            "portfolio wise timesheet booking summary",
            "portfolio-wise timesheet booking summary",
            "timesheet by portfolio",
            "hours per portfolio",
            "portfolio timesheet overview",
        ),
    ),
    _Intent(
        canonical="organisation wise timesheet booking summary",
        handler_index=0,
        phrases=(
            "organisation wise timesheet booking summary",
            "org wise timesheet booking summary",
            "organisation timesheet summary",
            "overall org timesheet",
            "company wide timesheet booking",
        ),
    ),
    _Intent(
        canonical="auto generate pending timesheet report",
        handler_index=0,
        phrases=(
            "auto generate pending timesheet report",
            "pending timesheet report",
            "who has not filled timesheet",
            "missing timesheet entries",
            "incomplete timesheet report",
            "generate pending timesheets",
        ),
    ),

    # ---- Action / Risk (1) ----
    _Intent(
        canonical="retrieve action centre points",
        handler_index=1,
        phrases=(
            "retrieve action centre points",
            "show action centre points",
            "list action items for project",
            "project action points",
            "what are the action points",
        ),
    ),
    _Intent(
        canonical="retrieve risk",
        handler_index=1,
        phrases=(
            "retrieve risk",
            "show project risks",
            "list risks for project",
            "what are the risks",
            "risk register for project",
            "project risk items",
        ),
    ),

    # ---- QA / Cases (2) ----
    _Intent(
        canonical="case id summary",
        handler_index=2,
        phrases=(
            "case id summary",
            "case ID list DEV SIT UAT",
            "show case ids",
            "list of case IDs",
        ),
    ),
    _Intent(
        canonical="module wise case summary",
        handler_index=2,
        phrases=(
            "module wise case summary",
            "module-wise case summary",
            "cases by module",
            "case count per module",
            "defects per module",
        ),
    ),
    _Intent(
        canonical="journey wise case summary",
        handler_index=2,
        phrases=(
            "journey wise case summary",
            "journey-wise case summary",
            "cases by journey",
            "defects by journey",
        ),
    ),
    _Intent(
        canonical="project wise case summary",
        handler_index=2,
        phrases=(
            "project wise case summary",
            "project-wise case summary",
            "cases by project",
            "defect count per project",
        ),
    ),
    _Intent(
        canonical="module wise defect summary report",
        handler_index=2,
        phrases=(
            "module wise defect summary report",
            "defect summary report by module",
            "defect report per module",
            "module defect breakdown",
            "how many defects per module",
        ),
    ),
    _Intent(
        canonical="project wise defect summary report",
        handler_index=2,
        phrases=(
            "project wise defect summary report",
            "defect report by project",
            "defect summary across projects",
            "project defect overview",
        ),
    ),
    _Intent(
        canonical="test case id summary",
        handler_index=2,
        phrases=(
            "test case id summary",
            "test case IDs",
            "list test cases",
            "test case list",
        ),
    ),
    _Intent(
        canonical="module wise test case summary",
        handler_index=2,
        phrases=(
            "module wise test case summary",
            "test cases by module",
            "module test case count",
            "test case breakdown per module",
        ),
    ),
    _Intent(
        canonical="project wise test case summary",
        handler_index=2,
        phrases=(
            "project wise test case summary",
            "test cases by project",
            "test case count per project",
        ),
    ),

    # ---- Portal / Travel / HelpDesk (3) ----
    _Intent(
        canonical="my portal request summary",
        handler_index=3,
        phrases=(
            "my portal request summary",
            "portal requests",
            "show portal requests",
            "portal summary",
            "what portal requests do I have",
        ),
    ),
    _Intent(
        canonical="travel desk request summary",
        handler_index=3,
        phrases=(
            "travel desk request summary",
            "travel requests",
            "travel desk summary",
            "show travel requests",
            "travel booking status",
        ),
    ),
    _Intent(
        canonical="help desk IT request summary",
        handler_index=3,
        phrases=(
            "help desk IT request summary",
            "IT helpdesk requests",
            "help desk tickets",
            "IT support requests",
            "show helpdesk items",
        ),
    ),
    # ── Portfolio intents (handler_index = 4) ──────────────────────────────
    _Intent(
        canonical="list portfolio",
        handler_index=4,
        phrases=(
            "list portfolio",
            "show all portfolios",
            "portfolios available",
            "show portfolios in system",
            "portfolio list",
            "what portfolios exist",
        ),
    ),
    _Intent(
        canonical="portfolio summary",
        handler_index=4,
        phrases=(
            "portfolio summary",
            "portfolio health",
            "portfolio status",
            "portfolio overview",
            "portfolio report",
            "portfolio dashboard",
            "show portfolio details",
            "portfolio project status",
        ),
    ),
    _Intent(
        canonical="portfolio timesheet",
        handler_index=4,
        phrases=(
            "portfolio timesheet",
            "portfolio utilization",
            "portfolio effort hours",
            "hours logged for portfolio",
            "portfolio resource hours",
            "timesheet summary for portfolio",
        ),
    ),
    _Intent(
        canonical="portfolio revenue",
        handler_index=4,
        phrases=(
            "portfolio revenue",
            "portfolio billing",
            "portfolio financials",
            "portfolio financial summary",
            "portfolio invoiced amount",
            "portfolio unbilled",
        ),
    ),
    # ── Organisation intents (handler_index = 5) ───────────────────────────
    _Intent(
        canonical="org summary",
        handler_index=5,
        phrases=(
            "org summary",
            "organisation summary",
            "organization summary",
            "overall summary",
            "enterprise summary",
            "org overview",
            "company summary",
            "org kpi",
            "org dashboard",
        ),
    ),
    _Intent(
        canonical="how many employees",
        handler_index=5,
        phrases=(
            "how many employees",
            "total employee count",
            "org headcount",
            "total staff",
            "workforce size",
            "how many people work here",
            "employee count organisation",
            "total workforce",
        ),
    ),
    _Intent(
        canonical="total revenue",
        handler_index=5,
        phrases=(
            "total revenue",
            "org revenue",
            "overall revenue",
            "organisation revenue",
            "org billing summary",
            "total billing org",
            "total service value",
            "revenue pipeline organisation",
            "org financial summary",
        ),
    ),
    _Intent(
        canonical="org utilization",
        handler_index=5,
        phrases=(
            "org utilization",
            "organisation utilization",
            "overall utilization",
            "total hours logged org",
            "org timesheet summary",
            "overall timesheet summary",
            "org effort hours",
            "billable hours organisation",
        ),
    ),
    _Intent(
        canonical="portfolio health",
        handler_index=5,
        phrases=(
            "portfolio health grid",
            "all portfolios status",
            "org portfolio overview",
            "portfolio status overview",
            "show all portfolio health",
            "organisation portfolio grid",
        ),
    ),
    _Intent(
        canonical="how many projects",
        handler_index=5,
        phrases=(
            "how many projects",
            "total project count",
            "org project count",
            "number of projects in organisation",
            "all projects count",
            "total projects org",
        ),
    ),
]

# Flat list of (phrase, intent) for embedding — each intent contributes all its phrases.
_FLAT_PHRASES: list[str] = []
_FLAT_INTENTS: list[_Intent] = []
for _intent in _CATALOGUE:
    for _phrase in _intent.phrases:
        _FLAT_PHRASES.append(_phrase)
        _FLAT_INTENTS.append(_intent)


# ---------------------------------------------------------------------------
# Router class
# ---------------------------------------------------------------------------

class IntentRouter:
    """Lazy-initialised embedding-based intent classifier."""

    def __init__(self):
        self._ready = False
        self._error: str | None = None
        self._embedder = None
        self._vectors: list[list[float]] = []

    def _init(self) -> None:
        if self._ready or self._error:
            return
        try:
            from project_intel.core.config import EMBEDDING_MODEL_NAME
            from project_intel.services.rag_core import LocalSentenceTransformerEmbedder
            self._embedder = LocalSentenceTransformerEmbedder(EMBEDDING_MODEL_NAME)
            self._vectors = self._embedder.embed(_FLAT_PHRASES)
            self._ready = True
            logger.info(
                "IntentRouter ready: %d phrases across %d intents (threshold=%.2f)",
                len(_FLAT_PHRASES), len(_CATALOGUE), _THRESHOLD,
            )
        except Exception as exc:
            self._error = str(exc)
            logger.warning("IntentRouter unavailable (%s) — keyword chain only", exc)

    def match(
        self,
        user_msg: str,
        threshold: float = _THRESHOLD,
    ) -> tuple[str, int] | None:
        """
        Returns (canonical_phrase, handler_index) or None.

        Lazy-initialises the embedder on first call.
        Returns None if the router is disabled, unavailable, or no phrase
        reaches the similarity threshold.
        """
        if not _ENABLED:
            return None
        self._init()
        if not self._ready or not self._vectors:
            return None

        q_vec = self._embedder.embed([user_msg])[0]

        best_score = -1.0
        best_intent: _Intent | None = None

        for intent, vec in zip(_FLAT_INTENTS, self._vectors):
            score = sum(a * b for a, b in zip(q_vec, vec))
            if score > best_score:
                best_score = score
                best_intent = intent

        if best_score >= threshold and best_intent is not None:
            logger.debug(
                "IntentRouter: %.3f → '%s' | query='%s'",
                best_score, best_intent.canonical, user_msg[:80],
            )
            return best_intent.canonical, best_intent.handler_index

        logger.debug(
            "IntentRouter: no match (best=%.3f < %.2f) | query='%s'",
            best_score, threshold, user_msg[:80],
        )
        return None


# Module-level singleton — shared across all requests.
intent_router = IntentRouter()
