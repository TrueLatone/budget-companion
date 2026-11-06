"""KAN-25 read-only Dashboard projections over verified canonical services."""

from app.modules.budgets import services as budgets
from app.modules.budgets.rules import split_integer
from app.modules.expenses import services as expenses
from app.modules.recommendations import services as recommendations

PALETTE = ("#6358d5", "#b9b1ed", "#e8a18e", "#95c9b8")


def build_dashboard(user_id, month_id):
    month = budgets.get_month(user_id, month_id)
    allocations = budgets.get_confirmed_allocations(user_id, month.id)
    plans = budgets.list_plans(user_id, month.id)
    plan = next((budgets.get_plan(user_id, month.id, item.id) for item in plans if item.status == "CONFIRMED"), None)
    period = expenses.resolve_period("month", month.month_start.isoformat())
    summary = expenses.build_summary(user_id, period)
    state = expenses.get_schedule_state(user_id, month.id)
    completeness = recommendations.get_completeness(user_id, month.month_start.strftime("%Y-%m"))

    # Confirmed allocations are monthly totals. Never add them to the scheduled
    # limits: those tasks are a distribution of the very same money.
    planned = sum(a.allocated_amount for a in allocations) if allocations else None
    savings = plan.planned_savings if plan else None
    saved_total = planned + savings if planned is not None else None
    actual = summary["actual_total"]  # Observed PLANNED/UNEXPECTED purchases only.
    known = bool(summary["data_complete"] and state.code == "READY")
    funding_difference = month.available_vnd - saved_total if saved_total is not None else None

    groups = {priority: dict(id=priority.lower(), priority=priority,
                            planned=0 if allocations else None, spent=0, records=0)
              for priority in ("P0", "P1", "P2")}
    for allocation in allocations:
        groups[allocation.budget_expense.priority]["planned"] += allocation.allocated_amount
    categories = {}
    records = []
    for record in summary["records"]:
        priority = record.priority  # Adapter resolves nullable PLANNED priority from its canonical task.
        if priority not in groups:
            raise expenses.ValidationError("A spending record has no valid priority.")
        groups[priority]["spent"] += record.amount
        groups[priority]["records"] += 1
        category_id = str(record.category_id)
        if category_id not in categories:
            categories[category_id] = dict(id=category_id, name=record.category_name, amount=0)
        categories[category_id]["amount"] += record.amount
        records.append(dict(id=str(record.id), title=record.title or record.category_name,
                            category_name=record.category_name, priority=priority, amount=record.amount,
                            date=record.expense_date, record_type=record.record_type))

    for row in groups.values():
        row["bar_percent"] = min(100, row["spent"] * 100 // row["planned"]) if row["planned"] else 0
        row["remaining"] = row["planned"] - row["spent"] if known else None

    # Thien's four-color donut: three leading real categories plus an explicit
    # aggregate. Integer tenths conserve 100.0%, including at BIGINT amounts.
    breakdown = sorted(categories.values(), key=lambda row: (-row["amount"], row["id"]))
    if len(breakdown) > 4:
        breakdown = breakdown[:3] + [dict(id="other", name=None, amount=sum(row["amount"] for row in breakdown[3:]))]
    shares = split_integer(1000, [row["amount"] for row in breakdown]) if actual else []
    offset = 0
    for row, share, color in zip(breakdown, shares, PALETTE):
        row.update(share=share, percent=f"{share // 10}.{share % 10}%", color=color, offset=offset)
        offset += share
    records.sort(key=lambda row: (row["date"], row["id"]), reverse=True)
    counts = summary["counts"]
    return dict(
        month=month, plan=plan, schedule_state=state, completeness=completeness,
        planned=planned, savings=savings, saved_total=saved_total, spent=actual,
        remaining=planned - actual if known else None, data_complete=known,
        available=month.available_vnd, funding_difference=funding_difference,
        unallocated=max(0, funding_difference) if funding_difference is not None else month.available_vnd if plan is None else None,
        funding_shortfall=max(0, -funding_difference) if funding_difference is not None else None,
        groups=list(groups.values()), breakdown=breakdown, recent=records[:5], records=records,
        counts=counts, task_count=len(summary["tasks"]), missing=counts["pending"] + counts["unrecorded"],
        period=period, cutoff=min(expenses.today_vn(), period.end),
    )
