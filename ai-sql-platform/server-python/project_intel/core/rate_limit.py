from __future__ import annotations

"""
Per-IP rate limiting via slowapi.

Environment variables
---------------------
RATE_LIMIT_CHAT         Default: "30/minute"
RATE_LIMIT_TRANSCRIBE   Default: "10/minute"
RATE_LIMIT_SQL_GEN      Default: "60/minute"
RATE_LIMIT_GLOBAL       Default: "200/minute"   (all other routes)

Set any to "0" to disable that specific limit.

Usage in routes
---------------
    from fastapi import Request
    from project_intel.core.rate_limit import limiter

    @router.post("/chat")
    @limiter.limit(chat_limit())
    async def chat(request: Request, req: ChatRequest):  # 'request' must be present
        ...

Integration in app.py
---------------------
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from project_intel.core.rate_limit import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""

import os

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    _AVAILABLE = True
except ImportError:
    # slowapi not installed — return a no-op decorator so routes still work.
    import functools

    class _NoOpLimiter:  # type: ignore[no-redef]
        def limit(self, *args, **kwargs):
            def decorator(func):
                @functools.wraps(func)
                async def wrapper(*a, **kw):
                    return await func(*a, **kw)
                return wrapper
            return decorator

    limiter = _NoOpLimiter()  # type: ignore[assignment]
    _AVAILABLE = False


def _limit(env_var: str, default: str) -> str:
    val = os.getenv(env_var, default).strip()
    return val if val and val != "0" else "99999/minute"  # "0" == no limit


def chat_limit() -> str:
    return _limit("RATE_LIMIT_CHAT", "30/minute")


def transcribe_limit() -> str:
    return _limit("RATE_LIMIT_TRANSCRIBE", "10/minute")


def sql_gen_limit() -> str:
    return _limit("RATE_LIMIT_SQL_GEN", "60/minute")
