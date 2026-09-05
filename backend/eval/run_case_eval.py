"""Eval harness for labeled historic retrospective case packs."""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.persist import import_historic_case_data
from app.core.config import DATA_DIR
from app.core.database import Base, SessionLocal, engine
from app.scripts.seed import seed
from app.tools.reconcile import reconcile_transactions

DEFAULT_CASE = "aether_2018q3"


def _near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def evaluate_case(case_id: str = DEFAULT_CASE) -> dict:
    gt_path = DATA_DIR / "cases" / case_id / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    period = gt["period"]
    expected_gap = float(gt["expected_bank_minus_ledger"])
    tol = float(gt.get("tolerance_usd", 1.0))

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
        imported = import_historic_case_data(db, case_id=case_id)
        recon = reconcile_transactions(db, period=period, persist=False)
        data = recon.data
        gap = float(data["bank_minus_ledger"])

        unmatched_bank = [
            r for r in data["results"] if r["match_category"] in ("unmatched", "needs_review")
        ]
        unmatched_gl = data.get("unmatched_gl") or []

        break_results = []
        breaks_hit = 0
        for br in gt["breaks"]:
            amount = float(br["amount"])
            side = br["side"]
            found = False
            evidence = None
            if side == "gl_only":
                for g in unmatched_gl:
                    if _near(float(g["amount"]), amount, tol) or _near(float(g["amount"]), -amount, tol):
                        found = True
                        evidence = g
                        break
            elif side == "bank_only":
                for r in unmatched_bank:
                    bank_amt = float(r.get("bank_amount") or 0)
                    if _near(bank_amt, amount, tol):
                        found = True
                        evidence = {
                            "bank_amount": bank_amt,
                            "bank_description": r.get("bank_description"),
                            "match_category": r.get("match_category"),
                        }
                        break
            if found:
                breaks_hit += 1
            break_results.append(
                {
                    "id": br["id"],
                    "expected_amount": amount,
                    "side": side,
                    "detected": found,
                    "evidence": evidence,
                }
            )

        matched = int(data["counts"].get("matched", 0))
        min_matched = int(gt.get("matched_ops_count_min", 5))
        report = {
            "case_id": case_id,
            "period": period,
            "title": gt.get("title"),
            "gap": {
                "expected": expected_gap,
                "actual": gap,
                "abs_error": round(abs(gap - expected_gap), 2),
                "pass": _near(gap, expected_gap, tol),
            },
            "breaks": {
                "total": len(gt["breaks"]),
                "detected": breaks_hit,
                "recall": round(breaks_hit / max(1, len(gt["breaks"])), 4),
                "pass": breaks_hit == len(gt["breaks"]),
                "detail": break_results,
            },
            "matched_ops": {"count": matched, "min_required": min_matched, "pass": matched >= min_matched},
            "import": imported.get("created"),
            "pass": _near(gap, expected_gap, tol)
            and breaks_hit == len(gt["breaks"])
            and matched >= min_matched,
        }
        return report
    finally:
        db.close()


def main() -> None:
    report = evaluate_case()
    out = Path(__file__).resolve().parent / "case_eval_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
