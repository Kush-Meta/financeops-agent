"""Import real public finance datasets (USAspending + SEC company facts + FX)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.adapters.base import (
    AdapterResult,
    NormalizedBankTxn,
    NormalizedDocument,
    NormalizedInvoice,
    NormalizedJournalEntry,
    NormalizedJournalLine,
    NormalizedVendor,
)
from app.core.config import DATA_DIR, get_settings


def _slug(name: str, prefix: str = "V") -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "", name.upper())[:10] or "UNKNOWN"
    return f"{prefix}-{cleaned[:8]}"


def load_usaspending(path: Path) -> AdapterResult:
    rows = json.loads(path.read_text(encoding="utf-8"))
    result = AdapterResult(source="usaspending")
    seen_vendors: set[str] = set()

    for i, row in enumerate(rows):
        recipient = (row.get("recipient") or "Unknown Recipient").strip()
        amount = float(row.get("amount") or 0)
        if amount <= 0:
            continue
        start = row.get("start_date") or "2024-07-15"
        try:
            txn_date = date.fromisoformat(start[:10])
        except ValueError:
            txn_date = date(2024, 7, 15)
        # Keep demo ops period coherent: map into Jun–Aug 2024 window
        if txn_date.year != 2024 or txn_date.month not in (6, 7, 8):
            txn_date = date(2024, 6 + (i % 3), 5 + (i % 20))

        code = _slug(recipient)
        if code not in seen_vendors:
            seen_vendors.add(code)
            result.vendors.append(
                NormalizedVendor(vendor_code=code, name=recipient, category="federal_contractor")
            )

        award_id = str(row.get("award_id") or f"AWARD-{i}")
        inv_no = f"USA-{award_id}"[:48]
        result.invoices.append(
            NormalizedInvoice(
                invoice_number=inv_no,
                vendor_code=code,
                invoice_date=txn_date,
                due_date=txn_date + timedelta(days=30),
                amount=round(amount, 2),
                description=(row.get("description") or f"Federal award {award_id}")[:500],
                reference=award_id,
                status="paid" if i % 4 else "open",
            )
        )

        # Treasury disbursement (bank withdrawal) when marked paid
        if i % 4 == 0:
            result.bank_txns.append(
                NormalizedBankTxn(
                    txn_date=txn_date + timedelta(days=2),
                    amount=-round(amount, 2),
                    description=f"ACH TREASURY PAY {recipient[:40]} {award_id}",
                    counterparty=recipient,
                    reference=award_id,
                    txn_type="ach",
                    external_id=f"usa-{award_id}",
                    source_system="usaspending",
                )
            )
            # Matching GL cash credit
            result.journal_entries.append(
                NormalizedJournalEntry(
                    entry_number=f"JE-USA-{i:04d}",
                    entry_date=txn_date + timedelta(days=2),
                    period=txn_date.strftime("%Y-%m"),
                    memo=f"Disburse federal award {award_id}",
                    source="usaspending_import",
                    lines=[
                        NormalizedJournalLine("2000", debit=amount, description=f"Clear AP {award_id}", reference=award_id),
                        NormalizedJournalLine("1000", credit=amount, description=f"Bank payment {award_id}", reference=award_id),
                    ],
                )
            )
        else:
            # Accrue expense / AP only
            result.journal_entries.append(
                NormalizedJournalEntry(
                    entry_number=f"JE-USA-{i:04d}",
                    entry_date=txn_date,
                    period=txn_date.strftime("%Y-%m"),
                    memo=f"Accrue award {award_id}",
                    source="usaspending_import",
                    lines=[
                        NormalizedJournalLine("5500", debit=amount, description=row.get("description") or award_id, reference=award_id),
                        NormalizedJournalLine("2000", credit=amount, description=f"AP {recipient[:40]}", reference=award_id),
                    ],
                )
            )

        agency = row.get("agency") or "Federal Agency"
        result.documents.append(
            NormalizedDocument(
                doc_type="award",
                title=f"USAspending award {award_id}",
                filename=f"usa_{re.sub(r'[^a-zA-Z0-9]+','_', award_id).lower()}.md",
                content=(
                    f"# USAspending Award {award_id}\n\n"
                    f"Recipient: {recipient}\n"
                    f"Agency: {agency}\n"
                    f"Amount: ${amount:,.2f}\n"
                    f"Start: {start}\n\n"
                    f"Description: {row.get('description')}\n\n"
                    f"Source: https://www.usaspending.gov/ (public federal spending data)\n"
                ),
                period=txn_date.strftime("%Y-%m"),
                tags=["usaspending", "real-data", agency.lower()[:40]],
                related_entity_type="invoice",
                related_entity_id=inv_no,
            )
        )

    result.meta = {"award_count": len(rows), "vendors": len(result.vendors)}
    return result


def load_sec_benchmarks(paths: list[Path]) -> AdapterResult:
    result = AdapterResult(source="sec_edgar")
    lines = ["# Public company financial benchmarks (SEC company facts)\n"]
    je_idx = 0
    for path in paths:
        slim = json.loads(path.read_text(encoding="utf-8"))
        ticker = slim.get("ticker", path.stem)
        entity = slim.get("entity", ticker)
        lines.append(f"\n## {entity} ({ticker})\n")
        metrics = slim.get("metrics") or {}
        for metric, points in metrics.items():
            if not points:
                continue
            latest = points[-1]
            val = latest.get("val")
            end = latest.get("end")
            form = latest.get("form")
            lines.append(f"- **{metric}** @ {end} ({form}): ${val:,.0f}" if isinstance(val, (int, float)) else f"- {metric}: {latest}")

            # Map selected opex metrics into synthetic budget/benchmark journal notes for Aug 2024
            if ticker == "AAPL" and metric in (
                "ResearchAndDevelopmentExpense",
                "SellingGeneralAndAdministrativeExpense",
            ):
                # Scale down to demo ledger magnitude (divide by 1e6)
                if not isinstance(val, (int, float)):
                    continue
                scaled = round(val / 1_000_000, 2)  # millions → dollars in demo CoA
                period = "2024-08"
                account = "5100" if "Research" in metric else "5400"
                je_idx += 1
                result.journal_entries.append(
                    NormalizedJournalEntry(
                        entry_number=f"JE-SEC-{ticker}-{je_idx}",
                        entry_date=date(2024, 8, 15),
                        period=period,
                        memo=f"SEC-scaled benchmark allocation for {metric}",
                        source="sec_import",
                        created_by="sec_adapter",
                        lines=[
                            NormalizedJournalLine(account, debit=scaled, description=f"{ticker} {metric} scaled", reference=f"SEC-{ticker}"),
                            NormalizedJournalLine("3000", credit=scaled, description="Benchmark contra / retained offset", reference=f"SEC-{ticker}"),
                        ],
                    )
                )

        result.documents.append(
            NormalizedDocument(
                doc_type="benchmark",
                title=f"SEC company facts — {entity}",
                filename=f"sec_{ticker.lower()}_benchmarks.md",
                content="\n".join(lines[-40:]) if False else None,  # placeholder replaced below
                period="2024-08",
                tags=["sec", "real-data", ticker.lower()],
                related_entity_type="ticker",
                related_entity_id=ticker,
            )
        )
        # fix content properly per company
        result.documents[-1].content = (
            f"# SEC EDGAR company facts — {entity}\n\n"
            f"Source: data.sec.gov companyfacts (public filings).\n\n"
            + "\n".join(
                f"- **{m}**: "
                + (
                    f"${points[-1]['val']:,.0f} as of {points[-1].get('end')} ({points[-1].get('form')})"
                    if points and isinstance(points[-1].get("val"), (int, float))
                    else "n/a"
                )
                for m, points in metrics.items()
            )
        )

    result.meta = {"tickers": [p.stem for p in paths]}
    return result


def load_fx(path: Path) -> AdapterResult:
    fx = json.loads(path.read_text(encoding="utf-8"))
    rates = fx.get("rates") or {}
    content = (
        f"# FX rates (Frankfurter / ECB reference)\n\n"
        f"Base: {fx.get('base')}  \n"
        f"Date: {fx.get('date')}\n\n"
        + "\n".join(f"- USD/{k}: {v}" for k, v in rates.items())
        + "\n\nUsed for multi-currency probable-match tolerance demos.\n"
    )
    return AdapterResult(
        source="frankfurter",
        documents=[
            NormalizedDocument(
                doc_type="fx",
                title=f"FX rates {fx.get('date')}",
                filename="fx_rates.md",
                content=content,
                period="2024-08",
                tags=["fx", "real-data"],
            )
        ],
        meta={"rates": rates, "as_of": fx.get("date")},
        # Seed a small EUR bank fee txn to exercise fee-tolerant matching
        bank_txns=[
            NormalizedBankTxn(
                txn_date=date(2024, 8, 20),
                amount=-1520.0,
                description="WIRE EUR SUPPLIER INVOICE NET OF FEE",
                counterparty="Global Freight Co",
                reference="FX-EUR-1520",
                txn_type="wire",
                currency="EUR",
                fee_amount=12.50,
                external_id="fx-demo-1",
                source_system="fx_demo",
            )
        ],
    )


def merge_results(*results: AdapterResult) -> AdapterResult:
    out = AdapterResult(source="merged")
    for r in results:
        out.vendors.extend(r.vendors)
        out.invoices.extend(r.invoices)
        out.bank_txns.extend(r.bank_txns)
        out.documents.extend(r.documents)
        out.journal_entries.extend(r.journal_entries)
        out.meta[r.source] = r.meta
    return out


def default_real_bundle() -> AdapterResult:
    settings = get_settings()
    real = Path(settings.real_data_dir)
    if not real.exists():
        real = DATA_DIR / "real"
    parts: list[AdapterResult] = []
    usa = real / "usaspending_awards.json"
    if usa.exists():
        parts.append(load_usaspending(usa))
    sec_paths = sorted(real.glob("sec_*_slim.json"))
    if sec_paths:
        parts.append(load_sec_benchmarks(sec_paths))
    fx = real / "fx_rates.json"
    if fx.exists():
        parts.append(load_fx(fx))
    if not parts:
        raise FileNotFoundError(f"No real data files found under {real}")
    return merge_results(*parts)
