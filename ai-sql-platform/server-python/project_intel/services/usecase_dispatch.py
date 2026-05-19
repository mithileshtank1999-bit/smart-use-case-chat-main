from __future__ import annotations

from project_intel.services.handlers import (
    action_handlers,
    portal_handlers,
    qa_handlers,
    timesheet_handlers,
)
from project_intel.services.handlers.portfolio_handlers import handle_portfolio, handle_org
from project_intel.services.handlers.helpers import detect_stage
from project_intel.services.intent_router import intent_router

# Indices here must stay in sync with IntentRouter._CATALOGUE handler_index values.
_HANDLER_CHAIN = [
    timesheet_handlers.handle,   # 0
    action_handlers.handle,      # 1
    qa_handlers.handle,          # 2
    portal_handlers.handle,      # 3
    handle_portfolio,            # 4
    handle_org,                  # 5
]


def dispatch_usecase_chat(user_msg: str) -> dict | None:
    """
    Two-tier router:
      1. Semantic: embedding-based intent match → jump directly to the right
         handler with the canonical phrase prepended so keyword checks pass.
      2. Keyword fallback: full chain scan (original behavior, always runs if
         semantic routing misses or the matched handler returns None).
    """
    text = (user_msg or "").strip()
    if not text:
        return None

    stage = detect_stage(text)
    lower = text.lower()

    # --- Tier 1: semantic routing ---
    match = intent_router.match(text)
    if match:
        canonical, handler_idx = match
        # Prepend the canonical phrase so the handler's `in lower` checks
        # reliably trigger even when the user paraphrased the request.
        aug = f"{canonical}. {text}"
        result = _HANDLER_CHAIN[handler_idx](aug, aug.lower(), stage)
        if result:
            return result
        # Matched semantically but handler returned None (e.g. missing slot) —
        # fall through so the user gets an error message from the right handler.

    # --- Tier 2: keyword chain (original behaviour) ---
    for handler in _HANDLER_CHAIN:
        result = handler(text, lower, stage)
        if result:
            return result

    return None
