"""Multi-tenant request context (demo-grade).

Production: map IdP `org_id` claim → tenant. Demo: `X-Org-Id` header with
fallback `org_demo`. Data plane filters should use `get_org_id()`.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Header

DEMO_ORG_IDS = {"org_demo", "org_acme"}


async def get_org_id(x_org_id: Annotated[Optional[str], Header()] = None) -> str:
    if x_org_id and x_org_id in DEMO_ORG_IDS:
        return x_org_id
    if x_org_id and len(x_org_id) <= 64 and x_org_id.replace("_", "").replace("-", "").isalnum():
        # Allow custom org ids in demos without crashing; isolation still applies
        return x_org_id
    return "org_demo"
