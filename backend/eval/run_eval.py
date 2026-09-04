"""Objective evaluation harness against synthetic ground truth."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.agent.planner import deterministic_plan
from app.agent.workflow import run_investigation
from app.core.config import DATA_DIR
from app.core.database import Base, SessionLocal, engine
from app.scripts.seed import seed
from app.tools.anomalies import detect_anomalies
from app.tools.reconcile import reconcile_transactions


BENCHMARK_QUESTIONS = [
    {
        "id": "bank_gap",
        "question": "Why is the August bank account $82,000 higher than the ledger?",
        "expected_tools": {"reconcile_transactions"},
        "expected_intent": "reconciliation",
        "must_mention": ["45000", "22000", "15000"],
    },
    {
        "id": "variances",
        "question": "Explain the largest month-over-month expense variances for August.",
        "expected_tools": {"calculate_variance"},
        "expected_intent": "variance_analysis",
        "must_mention": ["marketing"],
    },
    {
        "id": "anomalies",
        "question": "Find suspicious or unusual journal entries in August.",
        "expected_tools": {"detect_anomalies"},
        "expected_intent": "anomaly_detection",
        "must_mention": ["weekend"],
    },
]


def _normalize_money_text(s: str) -> str:
    return s.replace(",", "").replace("$", "").lower()


def run_eval() -> dict:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    gt = json.loads((DATA_DIR / "ground_truth.json").read_text())

    # Reconciliation metrics
    recon = reconcile_transactions(db, period="2024-08", persist=True)
    predicted = {r["bank_txn_id"] for r in recon.data["results"] if r["match_category"] == "matched"}
    expected = {m["bank_txn_id"] for m in gt["recon_expected"]["matched"] if "bank_txn_id" in m}
    run_ids = {r["bank_txn_id"] for r in recon.data["results"]}
    expected = expected & run_ids
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0

    # Anomaly metrics (type-level against ground truth)
    detected = detect_anomalies(db, period="2024-08")
    det_keys = {(f["entity_type"], str(f["entity_id"]), f["anomaly_type"]) for f in detected.data["findings"]}
    gt_keys = {(a["entity_type"], str(a["entity_id"]), a["anomaly_type"]) for a in gt["anomaly_ids"]}
    # Match on entity+type; allow entity_id string/int
    atp = len(det_keys & gt_keys)
    # Also score by anomaly_type coverage
    type_recall = len({k[2] for k in det_keys} & {k[2] for k in gt_keys}) / max(1, len({k[2] for k in gt_keys}))

    # Calculation accuracy for gap
    gap_error = abs(recon.data["bank_minus_ledger"] - gt["bank_vs_ledger_gap"]["expected_gap"])

    task_results = []
    latencies = []
    costs = []
    unsupported_rates = []
    tool_correct = 0

    for case in BENCHMARK_QUESTIONS:
        t0 = time.perf_counter()
        plan = deterministic_plan(case["question"])
        result = run_investigation(db, case["question"], auto_propose_actions=False)
        latency = (time.perf_counter() - t0) * 1000
        latencies.append(latency)
        costs.append(result.get("estimated_cost_usd") or 0)
        unsupported_rates.append(result["verification"]["unsupported_claim_rate"])

        tools = set(result["tools_used"])
        tool_ok = case["expected_tools"].issubset(tools) and plan["intent"] == case["expected_intent"]
        if tool_ok:
            tool_correct += 1

        norm = _normalize_money_text(result["answer"])
        mentions_ok = all(m.lower() in norm for m in case["must_mention"])
        completed = result["status"] == "completed" and mentions_ok
        task_results.append(
            {
                "id": case["id"],
                "tool_selection_ok": tool_ok,
                "completed": completed,
                "latency_ms": round(latency, 2),
                "unsupported_claim_rate": result["verification"]["unsupported_claim_rate"],
            }
        )

    report = {
        "reconciliation": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "gap_abs_error": round(gap_error, 2),
            "calculation_accuracy": gap_error < 1.0,
        },
        "anomaly_detection": {
            "ground_truth_hits": atp,
            "ground_truth_total": len(gt_keys),
            "type_recall": round(type_recall, 4),
            "precision_proxy": round(atp / max(1, len(det_keys)), 4),
        },
        "agent": {
            "tool_selection_accuracy": round(tool_correct / len(BENCHMARK_QUESTIONS), 4),
            "task_completion_rate": round(sum(1 for t in task_results if t["completed"]) / len(task_results), 4),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "avg_cost_usd": round(sum(costs) / len(costs), 6),
            "avg_unsupported_claim_rate": round(sum(unsupported_rates) / len(unsupported_rates), 4),
            "tasks": task_results,
        },
    }

    out = DATA_DIR / "eval_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    db.close()
    return report


def main() -> None:
    report = run_eval()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
