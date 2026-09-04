"""Reconciliation and tool unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import DATA_DIR
from app.core.database import Base, SessionLocal, engine
from app.scripts.seed import seed
from app.tools.anomalies import detect_anomalies
from app.tools.reconcile import reconcile_transactions
from app.tools.variance import calculate_variance


@pytest.fixture(scope="module")
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


def test_august_bank_gap_near_82000(db):
    result = reconcile_transactions(db, period="2024-08", persist=False)
    gap = result.data["bank_minus_ledger"]
    assert abs(gap - 82000) < 1.0


def test_reconciliation_precision_recall(db):
    gt = json.loads((DATA_DIR / "ground_truth.json").read_text())
    result = reconcile_transactions(db, period="2024-08", persist=True)
    predicted_matched = {
        r["bank_txn_id"] for r in result.data["results"] if r["match_category"] == "matched"
    }
    expected = {m["bank_txn_id"] for m in gt["recon_expected"]["matched"] if "bank_txn_id" in m}
    # Only evaluate August expected matches that appear in this run's bank set
    run_bank_ids = {r["bank_txn_id"] for r in result.data["results"]}
    expected = expected & run_bank_ids
    tp = len(predicted_matched & expected)
    precision = tp / len(predicted_matched) if predicted_matched else 0
    recall = tp / len(expected) if expected else 0
    assert precision >= 0.85
    assert recall >= 0.85


def test_unmatched_includes_dit_and_late_receipt(db):
    result = reconcile_transactions(db, period="2024-08", persist=False)
    refs = {r.get("bank_reference") for r in result.data["results"] if r["match_category"] == "unmatched"}
    assert "DIT-AUG-45000" in refs
    assert "LATE-APEX-15K" in refs


def test_anomaly_detection_finds_weekend_wire_and_duplicate(db):
    result = detect_anomalies(db, period="2024-08")
    types = {f["anomaly_type"] for f in result.data["findings"]}
    assert "weekend_entry" in types
    assert "duplicate_invoice" in types
    assert "unusual_vendor" in types or "rounded_amount" in types


def test_variance_marketing_spike(db):
    result = calculate_variance(db, period="2024-08", account_type="expense")
    marketing = next(v for v in result.data["variances"] if v["account_code"] == "5400")
    assert marketing["mom_change"] == 26000.0
