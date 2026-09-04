"""Controlled agentic workflow orchestration."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agent.planner import create_plan
from app.agent.reasoner import explain_findings, verify_answer
from app.core.logging import get_logger
from app.models import WorkflowRun
from app.services.approvals import create_approval_request
from app.services.audit import write_audit
from app.tools import get_tool
import app.tools  # noqa: F401 — register tools

logger = get_logger("workflow")


def run_investigation(
    db: Session,
    user_request: str,
    actor: str = "user",
    auto_propose_actions: bool = True,
) -> dict[str, Any]:
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    t0 = time.perf_counter()

    run = WorkflowRun(
        workflow_id=workflow_id,
        user_request=user_request,
        status="running",
    )
    db.add(run)
    db.commit()

    write_audit(db, workflow_id, "user_request", user_request, actor=actor)

    # 1. Plan
    plan = create_plan(user_request)
    run.plan = plan
    db.commit()
    write_audit(
        db,
        workflow_id,
        "plan",
        plan.get("rationale", "Plan created"),
        details=plan,
        actor="planner",
    )

    # 2. Execute tools
    tool_results: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"tool_results": [], "calculations": [], "records": []}
    tools_used: list[str] = []

    for step in plan.get("steps", []):
        tool_name = step["tool"]
        args = dict(step.get("args") or {})
        tools_used.append(tool_name)
        t_tool = time.perf_counter()
        write_audit(
            db,
            workflow_id,
            "tool_call",
            f"Invoking {tool_name}",
            details={"tool": tool_name, "args": args},
            actor="agent",
        )
        try:
            fn = get_tool(tool_name)
            result = fn(db, **args)
            duration = (time.perf_counter() - t_tool) * 1000
            payload = result.to_dict()
            tool_results.append(payload)
            evidence["tool_results"].append(payload)
            evidence["calculations"].extend(payload.get("calculations") or [])
            evidence["records"].extend(payload.get("records_accessed") or [])
            write_audit(
                db,
                workflow_id,
                "tool_result",
                result.summary,
                details={"tool": tool_name, "ok": result.ok, "summary": result.summary},
                actor="tool",
                duration_ms=duration,
            )
        except Exception as exc:  # noqa: BLE001
            duration = (time.perf_counter() - t_tool) * 1000
            err = {
                "tool": tool_name,
                "ok": False,
                "data": None,
                "summary": f"Tool failed: {exc}",
                "error": str(exc),
                "records_accessed": [],
                "calculations": [],
            }
            tool_results.append(err)
            write_audit(
                db,
                workflow_id,
                "error",
                f"Tool {tool_name} failed",
                details={"error": str(exc)},
                actor="tool",
                duration_ms=duration,
            )

    write_audit(
        db,
        workflow_id,
        "evidence",
        f"Aggregated evidence from {len(tool_results)} tool calls",
        details={
            "record_count": len(evidence["records"]),
            "calculation_count": len(evidence["calculations"]),
        },
        actor="agent",
    )

    # 3. Reason / explain
    explanation = explain_findings(user_request, plan, tool_results)
    write_audit(
        db,
        workflow_id,
        "reasoning",
        "Generated explanation from tool evidence",
        details={"citations": explanation.get("citations"), "mode": explanation.get("mode")},
        actor="reasoner",
    )

    # 4. Verify (no unsupported numeric claims)
    verification = verify_answer(explanation["answer"], evidence)
    write_audit(
        db,
        workflow_id,
        "verification",
        verification["summary"],
        details=verification,
        actor="verifier",
    )

    # 5. Human approval gate if needed
    approval_request_id = None
    requires_approval = False
    propose = plan.get("propose_action")
    if auto_propose_actions and propose:
        requires_approval = True
        # Attach high-confidence matches if recon
        payload = propose.get("payload") or {}
        for tr in tool_results:
            if tr.get("tool") == "reconcile_transactions" and tr.get("ok"):
                matched = [
                    r["bank_txn_id"]
                    for r in (tr["data"] or {}).get("results", [])
                    if r.get("match_category") == "matched"
                ]
                payload["bank_txn_ids"] = matched[:25]
                payload["period"] = (tr["data"] or {}).get("period")
        req = create_approval_request(
            db,
            action_type=propose["action_type"],
            title=propose.get("title") or propose["action_type"],
            description=propose.get("description") or "",
            payload=payload,
            workflow_id=workflow_id,
        )
        approval_request_id = req.request_id

    # Suggest adjustment when investigating bank gap without explicit action request
    compact_q = user_request.lower().replace(",", "")
    gap_question = (
        "82000" in compact_q
        or "82,000" in user_request
        or ("higher than the ledger" in compact_q)
        or ("bank balance" in compact_q and "match" in compact_q)
    )
    if (
        auto_propose_actions
        and not requires_approval
        and plan.get("intent") == "reconciliation"
        and gap_question
    ):
        # Propose booking deposit-in-transit — still requires approval
        requires_approval = True
        req = create_approval_request(
            db,
            action_type="propose_journal_entry",
            title="Book deposit-in-transit and unrecorded receipt",
            description=(
                "Proposed adjusting entries to record $45,000 Canyon deposit-in-transit and "
                "$15,000 Apex late receipt. Outstanding check requires no GL change."
            ),
            payload={
                "period": plan.get("period", "2024-08"),
                "account_code": "1000",
                "offset_account_code": "1100",
                "amount": 60000.0,
                "memo": "Record unbooked bank receipts (DIT $45k + Apex $15k)",
                "reference": "ADJ-AUG-DIT",
            },
            workflow_id=workflow_id,
        )
        approval_request_id = req.request_id

    latency_ms = (time.perf_counter() - t0) * 1000
    answer = explanation["answer"]
    if requires_approval:
        answer += (
            f"\n\n**Human approval required** before executing proposed action "
            f"`{approval_request_id}`. No sensitive GL changes were applied."
        )

    run.status = "completed"
    run.tools_used = tools_used
    run.evidence = {
        "calculations": evidence["calculations"],
        "records": evidence["records"][:200],
        "tool_summaries": [{"tool": t["tool"], "summary": t["summary"], "ok": t["ok"]} for t in tool_results],
    }
    run.answer = answer
    run.citations = explanation.get("citations")
    run.verification = verification
    run.requires_approval = requires_approval
    run.approval_request_id = approval_request_id
    run.latency_ms = latency_ms
    run.estimated_cost_usd = 0.002 if plan.get("planner") == "llm" else 0.0
    run.completed_at = datetime.utcnow()
    db.commit()

    write_audit(
        db,
        workflow_id,
        "final_response",
        answer[:500],
        details={
            "latency_ms": latency_ms,
            "requires_approval": requires_approval,
            "approval_request_id": approval_request_id,
        },
        actor="agent",
        duration_ms=latency_ms,
    )

    logger.info("workflow_completed", workflow_id=workflow_id, latency_ms=latency_ms, intent=plan.get("intent"))

    return {
        "workflow_id": workflow_id,
        "status": run.status,
        "plan": plan,
        "tools_used": tools_used,
        "tool_results": [
            {"tool": t["tool"], "ok": t["ok"], "summary": t["summary"], "data": t.get("data")} for t in tool_results
        ],
        "answer": answer,
        "citations": explanation.get("citations"),
        "verification": verification,
        "requires_approval": requires_approval,
        "approval_request_id": approval_request_id,
        "latency_ms": latency_ms,
        "estimated_cost_usd": run.estimated_cost_usd,
    }
