"""Interpretable anomaly detection for finance data."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import AnomalyFlag, BankTransaction, Invoice, JournalEntry, JournalLine, Vendor
from app.tools.base import ToolResult, register_tool

STANDARD_VENDOR_CATEGORIES = {
    "saas",
    "cogs",
    "logistics",
    "opex",
    "security",
    "payroll",
    "utilities",
    "facilities",
    "marketing",
    "professional",
}


def _zscores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mu = mean(values)
    sigma = pstdev(values) or 1.0
    return [(v - mu) / sigma for v in values]


@register_tool("detect_anomalies")
def detect_anomalies(
    db: Session,
    period: Optional[str] = "2024-08",
    persist_flags: bool = False,
) -> ToolResult:
    settings = get_settings()
    findings: list[dict] = []

    # Bank transactions
    q = select(BankTransaction)
    if period:
        from datetime import date

        year, month = map(int, period.split("-"))
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        q = q.where(BankTransaction.txn_date >= start, BankTransaction.txn_date < end)
    txns = db.execute(q).scalars().all()
    amounts = [abs(t.amount) for t in txns]
    z = _zscores(amounts)

    vendors = {v.name.lower(): v for v in db.execute(select(Vendor)).scalars().all()}

    for txn, zscore in zip(txns, z):
        if txn.txn_date.weekday() >= 5:
            findings.append(
                {
                    "entity_type": "bank_transaction",
                    "entity_id": str(txn.id),
                    "anomaly_type": "weekend_entry",
                    "severity": "high" if abs(txn.amount) >= 10000 else "medium",
                    "score": 0.9 if abs(txn.amount) >= 10000 else 0.6,
                    "explanation": f"Bank transaction on weekend ({txn.txn_date.isoformat()}) for ${txn.amount:,.2f}.",
                    "evidence": {"date": txn.txn_date.isoformat(), "amount": txn.amount, "description": txn.description},
                }
            )
        if abs(txn.amount) >= 1000 and abs(txn.amount) % 1000 == 0 and abs(txn.amount) % 10000 == 0:
            findings.append(
                {
                    "entity_type": "bank_transaction",
                    "entity_id": str(txn.id),
                    "anomaly_type": "rounded_amount",
                    "severity": "medium",
                    "score": 0.65,
                    "explanation": f"Large rounded amount ${txn.amount:,.2f}.",
                    "evidence": {"amount": txn.amount},
                }
            )
        if zscore >= settings.anomaly_zscore_threshold:
            findings.append(
                {
                    "entity_type": "bank_transaction",
                    "entity_id": str(txn.id),
                    "anomaly_type": "unusual_amount",
                    "severity": "high",
                    "score": min(0.99, 0.5 + abs(zscore) / 10),
                    "explanation": f"Amount ${abs(txn.amount):,.2f} is {zscore:.1f}σ from period mean.",
                    "evidence": {"amount": txn.amount, "zscore": round(zscore, 2)},
                }
            )
        cp = (txn.counterparty or "").lower()
        vendor = vendors.get(cp)
        if vendor and vendor.category == "unknown":
            findings.append(
                {
                    "entity_type": "bank_transaction",
                    "entity_id": str(txn.id),
                    "anomaly_type": "unusual_vendor",
                    "severity": "high",
                    "score": 0.9,
                    "explanation": f"Unexpected vendor category for {txn.counterparty}.",
                    "evidence": {"vendor": txn.counterparty, "category": vendor.category},
                }
            )
        elif cp and not any(cp in name or name in cp for name in vendors):
            # only flag large unknown counterparties
            if abs(txn.amount) >= 25000:
                findings.append(
                    {
                        "entity_type": "bank_transaction",
                        "entity_id": str(txn.id),
                        "anomaly_type": "unusual_vendor",
                        "severity": "medium",
                        "score": 0.7,
                        "explanation": f"Counterparty '{txn.counterparty}' not in vendor master.",
                        "evidence": {"counterparty": txn.counterparty},
                    }
                )

    # Duplicate invoices
    invoices = db.execute(select(Invoice).options(joinedload(Invoice.vendor))).scalars().unique().all()
    groups: dict[tuple, list[Invoice]] = defaultdict(list)
    for inv in invoices:
        groups[(inv.vendor_id, round(inv.amount, 2))].append(inv)
    for (_, _), group in groups.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda x: x.invoice_date)
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if abs((a.invoice_date - b.invoice_date).days) <= 7:
                    findings.append(
                        {
                            "entity_type": "invoice",
                            "entity_id": str(b.id),
                            "anomaly_type": "duplicate_invoice",
                            "severity": "high",
                            "score": 0.95,
                            "explanation": f"Possible duplicate of {a.invoice_number} (same vendor/amount within 7 days).",
                            "evidence": {
                                "original": a.invoice_number,
                                "duplicate": b.invoice_number,
                                "amount": a.amount,
                            },
                        }
                    )

    # Weekend journal entries
    je_q = select(JournalEntry)
    if period:
        je_q = je_q.where(JournalEntry.period == period)
    entries = db.execute(je_q).scalars().all()
    for entry in entries:
        if entry.entry_date.weekday() >= 5:
            findings.append(
                {
                    "entity_type": "journal_entry",
                    "entity_id": str(entry.id),
                    "anomaly_type": "weekend_entry",
                    "severity": "high" if entry.source == "manual" else "medium",
                    "score": 0.85,
                    "explanation": f"Journal {entry.entry_number} posted on weekend ({entry.entry_date.isoformat()}).",
                    "evidence": {"entry_number": entry.entry_number, "source": entry.source},
                }
            )

    # Expense spike via MoM (simple rule)
    from app.tools.variance import calculate_variance

    var = calculate_variance(db, period=period or "2024-08", account_type="expense", top_n=20)
    for v in var.data["variances"]:
        if v["mom_pct"] is not None and v["mom_pct"] >= 50 and abs(v["mom_change"]) >= 5000:
            findings.append(
                {
                    "entity_type": "account_balance",
                    "entity_id": f"{v['account_code']}:{period}",
                    "anomaly_type": "expense_spike",
                    "severity": "medium",
                    "score": min(0.95, 0.5 + v["mom_pct"] / 200),
                    "explanation": (
                        f"{v['account_name']} increased {v['mom_pct']:.0f}% MoM "
                        f"(${v['mom_change']:,.2f})."
                    ),
                    "evidence": v,
                }
            )

    if persist_flags:
        for f in findings:
            db.add(
                AnomalyFlag(
                    entity_type=f["entity_type"],
                    entity_id=f["entity_id"],
                    anomaly_type=f["anomaly_type"],
                    severity=f["severity"],
                    score=f["score"],
                    explanation=f["explanation"],
                    evidence=f.get("evidence"),
                    is_ground_truth=False,
                )
            )
        db.commit()

    findings.sort(key=lambda x: x["score"], reverse=True)
    return ToolResult(
        tool="detect_anomalies",
        ok=True,
        data={"period": period, "findings": findings, "count": len(findings)},
        summary=f"Detected {len(findings)} anomal{'y' if len(findings) == 1 else 'ies'} for {period}",
        records_accessed=[{"type": f["entity_type"], "id": f["entity_id"]} for f in findings],
    )
