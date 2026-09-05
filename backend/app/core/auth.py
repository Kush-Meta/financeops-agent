"""AuthN/Z: API keys, demo users, and role checks."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings

ROLE_ORDER = {"viewer": 0, "investigator": 1, "controller": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    role: str  # viewer | investigator | controller | admin
    api_key_id: str

    def can(self, min_role: str) -> bool:
        return ROLE_ORDER.get(self.role, -1) >= ROLE_ORDER.get(min_role, 99)


# Demo principals — replace with IdP in production
DEMO_USERS: dict[str, Principal] = {
    "fo_investigator_dev": Principal("u-inv", "Alex Investigator", "investigator", "fo_investigator_dev"),
    "fo_controller_dev": Principal("u-ctrl", "Casey Controller", "controller", "fo_controller_dev"),
    "fo_admin_dev": Principal("u-adm", "Riley Admin", "admin", "fo_admin_dev"),
    "fo_viewer_dev": Principal("u-view", "Sam Viewer", "viewer", "fo_viewer_dev"),
}


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_api_key(api_key: Optional[str]) -> Principal:
    """Resolve the caller.

    When auth is disabled we still honor known demo keys so the UI role
    switcher and admin-only import paths work in local demos. Missing key
    falls back to controller.
    """
    settings = get_settings()

    if api_key and api_key in DEMO_USERS:
        return DEMO_USERS[api_key]

    expected = settings.admin_api_key_hash
    if api_key and expected and hmac.compare_digest(_hash_key(api_key), expected):
        return DEMO_USERS["fo_admin_dev"]

    if not settings.auth_enabled:
        return DEMO_USERS["fo_controller_dev"]

    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


async def get_principal(x_api_key: Annotated[Optional[str], Header()] = None) -> Principal:
    return resolve_api_key(x_api_key)


def require_role(min_role: str):
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(min_role):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{principal.role}' cannot perform action requiring '{min_role}'",
            )
        return principal

    return _dep


def mint_demo_key(role: str = "controller") -> str:
    """Helper for tests — returns a known demo key for role."""
    for key, p in DEMO_USERS.items():
        if p.role == role:
            return key
    return secrets.token_urlsafe(16)
