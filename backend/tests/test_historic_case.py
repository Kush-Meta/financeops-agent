"""Historic retrospective case pack tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.adapters.csv_erp import list_historic_cases, load_historic_case_bundle
from app.adapters.persist import import_historic_case_data
from app.core.database import Base, SessionLocal, engine
from app.models import Document
from app.scripts.seed import seed
from app.tools.reconcile import reconcile_transactions
from eval.run_case_eval import evaluate_case

CASE_DIR = Path(__file__).resolve().parents[1] / "data" / "cases" / "aether_2018q3"


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


def test_historic_case_listed():
    cases = list_historic_cases()
    assert any(c["case_id"] == "aether_2018q3" for c in cases)


def test_historic_bundle_loads_documents():
    bundle = load_historic_case_bundle("aether_2018q3")
    assert bundle.meta["counts"]["bank_txns"] >= 9
    assert bundle.meta["counts"]["journal_entries"] >= 10
    assert len(bundle.documents) >= 1
    gt = json.loads((CASE_DIR / "ground_truth.json").read_text())
    assert bundle.meta["ground_truth"]["expected_bank_minus_ledger"] == gt["expected_bank_minus_ledger"]


def test_aether_september_gap_and_breaks(db):
    import_historic_case_data(db, "aether_2018q3")
    recon = reconcile_transactions(db, period="2018-09", persist=False)
    gap = recon.data["bank_minus_ledger"]
    assert abs(gap - (-2440035.0)) < 1.0

    unmatched_gl_amts = {round(float(g["amount"]), 2) for g in recon.data["unmatched_gl"]}
    assert 2100000.0 in unmatched_gl_amts
    assert 340000.0 in unmatched_gl_amts

    bank_unmatched = [
        round(float(r["bank_amount"]), 2)
        for r in recon.data["results"]
        if r["match_category"] == "unmatched"
    ]
    assert -35.0 in bank_unmatched

    docs = db.execute(select(Document)).scalars().all()
    assert any("aether" in (d.filename or "").lower() or "case" in (d.title or "").lower() for d in docs)


def test_case_eval_harness_passes():
    report = evaluate_case("aether_2018q3")
    assert report["gap"]["pass"] is True
    assert report["breaks"]["pass"] is True
    assert report["pass"] is True
