"""Customer-shaped data connectors (bank feed, ERP)."""

from app.connectors.sandbox_bank import sync_sandbox_bank_feed

__all__ = ["sync_sandbox_bank_feed"]
