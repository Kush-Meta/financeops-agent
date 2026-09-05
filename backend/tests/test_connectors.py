"""Connector / tenancy tests."""

from __future__ import annotations

from sqlalchemy import func, select

from app.connectors.sandbox_bank import ensure_demo_orgs, sync_sandbox_bank_feed
from app.core.database import Base, SessionLocal, engine
from app.models import BankTransaction, ConnectorSyncRun, Organization
from app.scripts.seed import seed


def _db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    ensure_demo_orgs(db)
    return db


def test_demo_orgs_seeded():
    db = _db()
    orgs = {o.org_id for o in db.execute(select(Organization)).scalars()}
    assert "org_demo" in orgs and "org_acme" in orgs
    db.close()


def test_bank_feed_sync_advances_cursor_and_isolates_tenants():
    db = _db()
    a = sync_sandbox_bank_feed(db, org_id="org_demo", batch_size=3)
    b = sync_sandbox_bank_feed(db, org_id="org_demo", batch_size=3)
    assert a["records_created"] == 3
    assert b["records_created"] == 3
    assert int(b["cursor"]) == 6

    sync_sandbox_bank_feed(db, org_id="org_acme", batch_size=2)
    demo_n = db.execute(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.source_system == "sandbox_bank:org_demo"
        )
    ).scalar()
    acme_n = db.execute(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.source_system == "sandbox_bank:org_acme"
        )
    ).scalar()
    assert demo_n == 6
    assert acme_n == 2

    demo_syncs = db.execute(
        select(func.count()).select_from(ConnectorSyncRun).where(ConnectorSyncRun.org_id == "org_demo")
    ).scalar()
    assert demo_syncs == 2
    db.close()


def test_idempotent_replay_skips_duplicates():
    db = _db()
    sync_sandbox_bank_feed(db, org_id="org_demo", batch_size=3)
    # Force cursor reset attempt by creating overlapping external ids via second org path only
    # Re-running same cursor window is prevented by cursor advance; simulate skip by re-importing
    # already-created ids through a manual second call after cursor rewind in DB
    run = db.execute(
        select(ConnectorSyncRun).where(ConnectorSyncRun.org_id == "org_demo")
    ).scalars().first()
    run.cursor = "0"
    db.commit()
    again = sync_sandbox_bank_feed(db, org_id="org_demo", batch_size=3)
    assert again["records_skipped"] == 3
    assert again["records_created"] == 0
    db.close()
