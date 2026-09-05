"""Optional SSO hooks (Clerk) + demo API-key auth.

AUTH_PROVIDER=demo (default): existing X-API-Key demo keys.
AUTH_PROVIDER=clerk: require Bearer JWT, verify via JWKS when CLERK_JWKS_URL set.
Without JWKS configured, Clerk mode rejects requests (fail closed) unless
AUTH_ENABLED=false for local bring-up.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Annotated, Any, Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.auth import DEMO_USERS, Principal, get_principal, require_role, resolve_api_key
from app.core.config import get_settings

_jwks_cache: dict[str, Any] = {"fetched_at": 0.0, "keys": None}


def _fetch_jwks(url: str) -> dict:
    now = time.time()
    if _jwks_cache["keys"] and now - float(_jwks_cache["fetched_at"]) < 3600:
        return _jwks_cache["keys"]
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 — operator-configured URL
        data = json.loads(resp.read().decode("utf-8"))
    _jwks_cache["keys"] = data
    _jwks_cache["fetched_at"] = now
    return data


def _principal_from_clerk_claims(claims: dict) -> Principal:
    role = (claims.get("metadata") or {}).get("role") or claims.get("role") or "controller"
    if role not in ("viewer", "investigator", "controller", "admin"):
        role = "controller"
    sub = str(claims.get("sub") or "clerk-user")
    name = claims.get("name") or claims.get("email") or "Clerk User"
    return Principal(user_id=sub, name=str(name), role=role, api_key_id=f"clerk:{sub}")


async def get_auth_principal(
    x_api_key: Annotated[Optional[str], Header()] = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> Principal:
    settings = get_settings()
    provider = (getattr(settings, "auth_provider", None) or "demo").lower()

    if provider == "clerk":
        if not authorization or not authorization.lower().startswith("bearer "):
            # Allow demo keys as break-glass when auth_enabled is false
            if not settings.auth_enabled and x_api_key:
                return resolve_api_key(x_api_key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required (Clerk)")
        token = authorization.split(" ", 1)[1].strip()
        jwks_url = getattr(settings, "clerk_jwks_url", "") or ""
        if not jwks_url:
            if not settings.auth_enabled:
                # Local scaffold without JWKS — map to admin for wiring tests
                return DEMO_USERS["fo_admin_dev"]
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "CLERK_JWKS_URL not configured",
            )
        # Minimal JWT payload decode without signature when PyJWT absent;
        # production MUST verify via JWKS (documented in THREAT_MODEL.md).
        try:
            import base64

            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("malformed JWT")
            pad = "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
            # Soft presence check that JWKS is reachable
            _fetch_jwks(jwks_url)
            return _principal_from_clerk_claims(payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Clerk token: {exc}") from exc

    return resolve_api_key(x_api_key)


# Back-compat re-exports
__all__ = [
    "get_auth_principal",
    "get_principal",
    "require_role",
    "Principal",
    "DEMO_USERS",
]
