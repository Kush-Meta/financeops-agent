"""Sandbox bank-feed connector — Plaid/QBO-shaped nightly ingest.

Without customer API keys this connector reads a versioned fixture feed and
advances a cursor so each sync can land *new* transactions — the same
operational shape as a real Plaid Transactions sync or QBO BankTransactions
pull. Swap the fetch body for live credentials later; persistence + sync
receipts stay identical.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, get_settings
from app.models import BankTransaction, ConnectorSyncRun, Organization

FEED_PATH = DATA_DIR / "connectors" / "sandbox_bank_feed.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_demo_orgs(db: Session) -> None:
    demos = [
        ("org_demo", "FinanceOps Demo Co"),
        ("org_acme", "Acme Industrial (sandbox tenant)"),
    ]
    for org_id, name in demos:
        exists = db.execute(select(Organization).where(Organization.org_id == org_id)).scalar_one_or_none()
        if not exists:
            db.add(Organization(org_id=org_id, name=name, plan="demo"))
    db.commit()


def _load_feed() -> dict[str, Any]:
    if not FEED_PATH.exists():
        raise FileNotFoundError(f"Sandbox bank feed missing: {FEED_PATH}")
    return json.loads(FEED_PATH.read_text(encoding="utf-8"))


def _last_cursor(db: Session, org_id: str, connector: str) -> int:
    row = (
        db.execute(
            select(ConnectorSyncRun)
            .where(
                ConnectorSyncRun.org_id == org_id,
                ConnectorSyncRun.connector == connector,
                ConnectorSyncRun.status == "succeeded",
            )
            .order_by(ConnectorSyncRun.finished_at.desc())
        )
        .scalars()
        .first()
    )
    if not row or not row.cursor:
        return 0
    try:
        return int(row.cursor)
    except ValueError:
        return 0


def sync_sandbox_bank_feed(
    db: Session,
    *,
    org_id: str = "org_demo",
    trigger: str = "manual",
    bank_account_code: str = "1000",
    batch_size: int = 3,
) -> dict:
    """Pull the next batch of sandbox bank txns for this org and persist them."""
    ensure_demo_orgs(db)
    connector = "sandbox_bank_feed"
    run_id = f"sync-{uuid.uuid4().hex[:12]}"
    run = ConnectorSyncRun(
        run_id=run_id,
        org_id=org_id,
        connector=connector,
        status="running",
        trigger=trigger,
        started_at=_utcnow(),
    )
    db.add(run)
    db.commit()

    try:
        feed = _load_feed()
        items: list[dict] = feed.get("transactions") or []
        cursor = _last_cursor(db, org_id, connector)
        slice_ = items[cursor : cursor + batch_size]
        created = 0
        skipped = 0
        fetched = len(slice_)

        for raw in slice_:
            external_id = f"{org_id}:{raw['transaction_id']}"
            exists = db.execute(
                select(BankTransaction).where(BankTransaction.external_id == external_id)
            ).scalar_one_or_none()
            if exists:
                skipped += 1
                continue
            txn_date = date.fromisoformat(raw["date"])
            db.add(
                BankTransaction(
                    bank_account_code=bank_account_code,
                    txn_date=txn_date,
                    posted_date=txn_date,
                    amount=float(raw["amount"]),
                    description=raw.get("name") or raw.get("description") or "Bank feed txn",
                    counterparty=raw.get("merchant_name") or raw.get("counterparty"),
                    reference=raw.get("payment_meta", {}).get("reference") if isinstance(raw.get("payment_meta"), dict) else raw.get("reference"),
                    txn_type=raw.get("payment_channel") or raw.get("txn_type") or "ach",
                    currency=raw.get("iso_currency_code") or "USD",
                    source_system=f"sandbox_bank:{org_id}",
                    external_id=external_id,
                    reconciliation_status="unmatched",
                )
            )
            created += 1

        new_cursor = cursor + fetched
        run.status = "succeeded"
        run.records_fetched = fetched
        run.records_created = created
        run.records_skipped = skipped
        run.cursor = str(new_cursor)
        run.finished_at = _utcnow()
        run.details = {
            "provider": feed.get("provider", "sandbox"),
            "feed_version": feed.get("version"),
            "org_id": org_id,
            "cursor_before": cursor,
            "cursor_after": new_cursor,
            "exhausted": new_cursor >= len(items),
            "next_schedule_hint": "0 6 * * *  # daily 06:00 UTC cron hitting POST /api/connectors/bank-feed/sync",
        }
        db.commit()
        return {
            "run_id": run_id,
            "org_id": org_id,
            "connector": connector,
            "status": run.status,
            "records_fetched": fetched,
            "records_created": created,
            "records_skipped": skipped,
            "cursor": run.cursor,
            "exhausted": new_cursor >= len(items),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = _utcnow()
        db.commit()
        raise
