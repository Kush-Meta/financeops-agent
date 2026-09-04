"""Variance analysis and period comparison."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountBalance
from app.tools.base import ToolResult, register_tool


@register_tool("calculate_variance")
def calculate_variance(
    db: Session,
    period: str,
    compare_to_period: Optional[str] = None,
    account_type: str = "expense",
    top_n: int = 10,
) -> ToolResult:
    if compare_to_period is None:
        year, month = map(int, period.split("-"))
        if month == 1:
            compare_to_period = f"{year - 1}-12"
        else:
            compare_to_period = f"{year}-{month - 1:02d}"

    rows = (
        db.execute(
            select(AccountBalance, Account)
            .join(Account)
            .where(
                AccountBalance.period.in_([period, compare_to_period]),
                Account.account_type == account_type,
            )
        )
        .all()
    )

    by_account: dict[str, dict] = {}
    for bal, acc in rows:
        slot = by_account.setdefault(
            acc.account_code,
            {
                "account_code": acc.account_code,
                "account_name": acc.name,
                "current": None,
                "prior": None,
                "budget": None,
            },
        )
        if bal.period == period:
            slot["current"] = bal.ending_balance
            slot["budget"] = bal.budget_amount
        else:
            slot["prior"] = bal.ending_balance

    variances = []
    for slot in by_account.values():
        current = slot["current"] if slot["current"] is not None else 0.0
        prior = slot["prior"] if slot["prior"] is not None else 0.0
        # expenses stored as positive debit-heavy balances in our seed
        mom = current - prior
        mom_pct = (mom / abs(prior)) * 100 if prior else None
        budget = slot["budget"]
        budget_var = (current - budget) if budget is not None else None
        variances.append(
            {
                **slot,
                "mom_change": round(mom, 2),
                "mom_pct": round(mom_pct, 2) if mom_pct is not None else None,
                "budget_variance": round(budget_var, 2) if budget_var is not None else None,
                "abs_mom_change": abs(mom),
            }
        )

    variances.sort(key=lambda x: x["abs_mom_change"], reverse=True)
    top = variances[:top_n]
    total_mom = round(sum(v["mom_change"] for v in variances), 2)

    return ToolResult(
        tool="calculate_variance",
        ok=True,
        data={
            "period": period,
            "compare_to_period": compare_to_period,
            "account_type": account_type,
            "total_mom_change": total_mom,
            "variances": top,
            "all_count": len(variances),
        },
        summary=(
            f"Top MoM {account_type} variances for {period} vs {compare_to_period}; "
            f"largest driver {top[0]['account_name']} ${top[0]['mom_change']:,.2f}"
            if top
            else f"No {account_type} balances for {period}"
        ),
        records_accessed=[{"type": "account", "id": v["account_code"]} for v in top],
        calculations=[
            {"name": "total_mom_change", "value": total_mom},
            *[{"name": f"mom_{v['account_code']}", "value": v["mom_change"]} for v in top[:5]],
        ],
    )


@register_tool("compare_periods")
def compare_periods(
    db: Session,
    period_a: str,
    period_b: str,
    account_codes: Optional[list[str]] = None,
) -> ToolResult:
    q = (
        select(AccountBalance, Account)
        .join(Account)
        .where(AccountBalance.period.in_([period_a, period_b]))
    )
    if account_codes:
        q = q.where(Account.account_code.in_(account_codes))
    rows = db.execute(q).all()
    data: dict[str, dict] = {}
    for bal, acc in rows:
        slot = data.setdefault(
            acc.account_code,
            {
                "account_code": acc.account_code,
                "account_name": acc.name,
                "account_type": acc.account_type,
                period_a: None,
                period_b: None,
            },
        )
        slot[bal.period] = bal.ending_balance

    comparisons = []
    for slot in data.values():
        a = slot.get(period_a) or 0.0
        b = slot.get(period_b) or 0.0
        comparisons.append(
            {
                "account_code": slot["account_code"],
                "account_name": slot["account_name"],
                "account_type": slot["account_type"],
                "period_a": period_a,
                "period_b": period_b,
                "balance_a": a,
                "balance_b": b,
                "difference": round(b - a, 2),
            }
        )
    comparisons.sort(key=lambda x: abs(x["difference"]), reverse=True)
    return ToolResult(
        tool="compare_periods",
        ok=True,
        data=comparisons,
        summary=f"Compared {len(comparisons)} accounts between {period_a} and {period_b}",
        records_accessed=[{"type": "account", "id": c["account_code"]} for c in comparisons],
        calculations=[{"name": "diff_" + c["account_code"], "value": c["difference"]} for c in comparisons[:10]],
    )
