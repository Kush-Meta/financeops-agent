"""Planner: map user requests to tool plans (LLM optional, deterministic fallback)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("planner")

TOOL_CATALOG = """
Available tools:
- query_ledger(account_code?, period?, entry_number?, reference?, limit?)
- search_transactions(query?, period?, min_amount?, max_amount?, status?, limit?)
- retrieve_invoice(invoice_number?, vendor_name?, status?, unreconciled_only?, limit?)
- search_documents(query, doc_type?, period?, limit?)
- calculate_variance(period, compare_to_period?, account_type?, top_n?)
- reconcile_transactions(period, bank_account_code?, persist?)
- detect_duplicates(lookback_days?)
- detect_anomalies(period?, persist_flags?)
- compare_periods(period_a, period_b, account_codes?)
- get_account_balances(period?, account_code?, account_type?)
"""


def _extract_period(text: str) -> str | None:
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    m = re.search(r"(20\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    lower = text.lower()
    for name, num in months.items():
        if name in lower:
            year_m = re.search(r"20\d{2}", lower)
            year = year_m.group(0) if year_m else "2024"
            return f"{year}-{num}"
    return None


def deterministic_plan(user_request: str) -> dict[str, Any]:
    text = user_request.lower()
    period = _extract_period(user_request) or "2024-08"
    steps: list[dict[str, Any]] = []
    intent = "general_investigation"
    propose_action = None

    if any(k in text for k in ("reconcil", "bank balance", "match the", "unmatched", "bank account")):
        intent = "reconciliation"
        steps = [
            {"tool": "get_account_balances", "args": {"period": period, "account_code": "1000"}},
            {"tool": "reconcile_transactions", "args": {"period": period, "bank_account_code": "1000"}},
            {"tool": "search_documents", "args": {"query": f"bank reconciliation {period}", "period": period}},
            {"tool": "search_transactions", "args": {"period": period, "status": "unmatched"}},
        ]
        if "mark" in text or "approve match" in text:
            propose_action = {
                "action_type": "approve_match",
                "title": f"Approve reconciliation matches for {period}",
                "description": "Mark probable/high-confidence matches as reconciled after controller review.",
            }
    elif any(k in text for k in ("variance", "month-over-month", "mom", "budget", "expense")):
        intent = "variance_analysis"
        steps = [
            {"tool": "calculate_variance", "args": {"period": period, "account_type": "expense", "top_n": 10}},
            {"tool": "compare_periods", "args": {"period_a": "2024-07", "period_b": period}},
            {"tool": "search_documents", "args": {"query": f"variance marketing expense {period}"}},
        ]
    elif any(k in text for k in ("anomal", "suspicious", "unusual", "duplicate", "manual review")):
        intent = "anomaly_detection"
        steps = [
            {"tool": "detect_anomalies", "args": {"period": period}},
            {"tool": "detect_duplicates", "args": {"lookback_days": 7}},
            {"tool": "search_transactions", "args": {"period": period, "min_amount": 50000}},
        ]
    elif "invoice" in text and ("unreconcil" in text or "open" in text):
        intent = "invoice_review"
        steps = [
            {"tool": "retrieve_invoice", "args": {"unreconciled_only": True, "limit": 50}},
            {"tool": "detect_duplicates", "args": {}},
        ]
    elif any(k in text for k in ("month-end", "summary", "close")):
        intent = "month_end_summary"
        steps = [
            {"tool": "reconcile_transactions", "args": {"period": period}},
            {"tool": "calculate_variance", "args": {"period": period, "account_type": "expense"}},
            {"tool": "detect_anomalies", "args": {"period": period}},
            {"tool": "search_documents", "args": {"query": "month-end close policy"}},
        ]
    elif "journal" in text:
        intent = "journal_review"
        steps = [
            {"tool": "query_ledger", "args": {"period": period, "limit": 40}},
            {"tool": "detect_anomalies", "args": {"period": period}},
        ]
    else:
        steps = [
            {"tool": "search_documents", "args": {"query": user_request[:120]}},
            {"tool": "get_account_balances", "args": {"period": period}},
            {"tool": "search_transactions", "args": {"period": period, "limit": 20}},
        ]

    # Augmentation for the classic $82k question
    if "82000" in text.replace(",", "") or "82,000" in text or "82k" in text:
        intent = "reconciliation"
        steps = [
            {"tool": "reconcile_transactions", "args": {"period": period, "bank_account_code": "1000"}},
            {"tool": "search_documents", "args": {"query": "82,000 bank reconciliation deposit in transit"}},
            {"tool": "search_transactions", "args": {"period": period, "query": "deposit"}},
            {"tool": "query_ledger", "args": {"account_code": "1000", "period": period, "limit": 30}},
        ]

    return {
        "intent": intent,
        "period": period,
        "steps": steps,
        "propose_action": propose_action,
        "planner": "deterministic",
        "rationale": f"Mapped request to {intent} workflow for period {period}.",
    }


def llm_plan(user_request: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.llm_enabled or not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        prompt = (
            "You are the planner for FinanceOps Agent. Return ONLY valid JSON with keys: "
            "intent, period, steps (list of {tool, args}), propose_action (null or object), rationale.\n"
            f"{TOOL_CATALOG}\nUser request: {user_request}"
        )
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        # strip markdown fences if present
        content = re.sub(r"^```json\s*|```$", "", content.strip(), flags=re.I | re.M)
        plan = json.loads(content)
        plan["planner"] = "llm"
        return plan
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_plan_failed", error=str(exc))
        return None


def create_plan(user_request: str) -> dict[str, Any]:
    return llm_plan(user_request) or deterministic_plan(user_request)
