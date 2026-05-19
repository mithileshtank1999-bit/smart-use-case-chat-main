from __future__ import annotations

"""
Optional JWT authentication + RBAC.

Environment variables
---------------------
REQUIRE_AUTH          Set to "1" to reject unauthenticated requests (default: off).
JWT_SECRET            HS256 secret (Supabase: Settings → API → JWT Secret).
JWT_AUDIENCE          Expected 'aud' claim (Supabase default: "authenticated").
JWT_ALGORITHM         Signing algorithm (default: HS256).

Role-based access
-----------------
JWT payload is expected to contain an 'app_metadata.role' or 'role' claim.
Supported roles: admin, pmo, qa, employee, readonly.
Use the require_role() dependency to restrict specific routes.

Usage in routes
---------------
    from project_intel.core.auth import get_current_user, require_role

    @router.post("/admin-only")
    async def admin_route(user=Depends(require_role("admin"))):
        ...

    @router.post("/any-authenticated")
    async def auth_route(user=Depends(get_current_user)):
        ...
"""

import logging
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes", "y")
_JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
_JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "authenticated").strip() or "authenticated"
_JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"


def _decode(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        import jwt as _jwt  # python-jose or PyJWT
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="JWT library not installed. Run: pip install python-jose[cryptography]",
        )

    if not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET is not configured on the server.",
        )

    try:
        # python-jose API
        payload = _jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            audience=_JWT_AUDIENCE,
        )
        return payload
    except Exception as exc:
        lowered = str(exc).lower()
        if "expired" in lowered:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict | None:
    """
    FastAPI dependency.
    - If REQUIRE_AUTH=1 and no token → 401.
    - If token present → decode and return payload dict.
    - If REQUIRE_AUTH is off and no token → returns None (anonymous allowed).
    """
    if not credentials:
        if _REQUIRE_AUTH:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None  # anonymous access

    return _decode(credentials.credentials)


def _extract_role(user: dict) -> str:
    """Pull role from app_metadata.role (Supabase) or top-level role claim."""
    if not user:
        return "anonymous"
    app_meta = user.get("app_metadata") or {}
    return str(app_meta.get("role") or user.get("role") or "authenticated").lower()


def require_role(*allowed_roles: str):
    """
    Returns a FastAPI dependency that enforces one of the allowed roles.

    Usage:
        Depends(require_role("admin", "pmo"))
    """
    allowed = {r.lower() for r in allowed_roles}

    async def _check(user: dict | None = Depends(get_current_user)) -> dict:
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        role = _extract_role(user)
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not allowed. Required: {sorted(allowed)}",
            )
        return user

    return _check
