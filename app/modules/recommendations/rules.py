"""F18 and category signals adapted from recommendations-f16-f19 3e6c3bc.

Readiness thresholds are unchanged. Period deadlines replace assignment-start
deadlines, and contradictory check-ins never count as confirmed zero spending.
"""

from collections import Counter, defaultdict
from datetime import date

from app.modules.budgets.rules import MAX_VND

MIN_COMPLETE_TRANSACTIONS = 10
MIN_CATEGORIES = 3
MIN_COVERAGE_DAYS = 30
MIN_COMPLETENESS_RATE = 0.80
OVER_BUDGET_PERCENT = 110
UNDER_BUDGET_PERCENT = 80


def is_complete_expense_record(record):
    amount = getattr(record, "amount", None)
    return bool(
        getattr(record, "id", None) and type(amount) is int and 0 < amount <= MAX_VND
        and getattr(record, "category_id", None) and type(getattr(record, "expense_date", None)) is date
        and getattr(record, "record_type", None) in {"PLANNED", "UNEXPECTED"}
    )


def build_completeness_result(records, tasks, as_of, *, as_of_closed=False):
    expense_records = [r for r in records if r.record_type in {"PLANNED", "UNEXPECTED"}
                       and (type(r.expense_date) is not date or r.expense_date <= as_of)]
    complete = [r for r in expense_records if is_complete_expense_record(r)]
    incomplete = [r for r in expense_records if not is_complete_expense_record(r)]
    linked = defaultdict(list)
    for record in expense_records:
        if record.task_id:
            linked[record.task_id].append(record)
    issues = []
    no_expense = pending = inconsistent = 0
    visible_tasks = [task for task in tasks if task.assigned_date <= as_of]
    for task in visible_tasks:
        records_for_task = linked[task.id]
        status = task.task_status
        contradictory = (
            status == "NO_EXPENSE" and bool(records_for_task)
            or status == "RECORDED" and not any(r.record_type == "PLANNED" for r in records_for_task)
            or status == "PENDING" and bool(records_for_task)
            or status not in {"PENDING", "RECORDED", "NO_EXPENSE"}
        )
        if contradictory:
            inconsistent += 1
            issues.append({"type": "INCONSISTENT_CHECKIN", "task_id": str(task.id),
                           "message": "Task status and visible transactions disagree; spending remains unknown."})
        elif status == "NO_EXPENSE":
            no_expense += 1
        elif status == "PENDING" and (task.period_end < as_of or as_of_closed and task.period_end == as_of):
            pending += 1
            issues.append({"type": "UNRECORDED_TASK", "task_id": str(task.id),
                           "message": "A completed task period has no check-in."})
    for record in incomplete:
        issues.append({"type": "INCOMPLETE_TRANSACTION", "record_id": str(record.id),
                       "message": "Transaction requires positive integer VND, category, date and spending type."})
    complete_items = len(complete) + no_expense
    expected_items = complete_items + len(incomplete) + pending + inconsistent
    rate = complete_items / expected_items if expected_items else 0.0
    valid_dates = [r.expense_date for r in complete]
    coverage = (max(valid_dates) - min(valid_dates)).days + 1 if valid_dates else 0
    categories = len({r.category_id for r in complete})
    checks = {
        "minimum_complete_transactions": len(complete) >= MIN_COMPLETE_TRANSACTIONS,
        "minimum_categories": categories >= MIN_CATEGORIES,
        "minimum_coverage_days": coverage >= MIN_COVERAGE_DAYS,
        "minimum_completeness_rate": rate >= MIN_COMPLETENESS_RATE,
        "no_unresolved_tasks": pending == 0 and inconsistent == 0,
        "no_incomplete_transactions": not incomplete,
    }
    sufficient = all(checks.values())
    return {
        "status": "SUFFICIENT" if sufficient else "INSUFFICIENT",
        "guidance_mode": "PERSONALIZED_GUIDANCE" if sufficient else "BASELINE_GUIDANCE",
        "complete_transaction_count": len(complete), "incomplete_transaction_count": len(incomplete),
        "category_count": categories, "coverage_days": coverage,
        "completeness_rate": round(rate, 4), "complete_item_count": complete_items,
        "expected_item_count": expected_items, "unrecorded_task_count": pending,
        "inconsistent_task_count": inconsistent, "no_expense_task_count": no_expense,
        "task_status_counts": dict(Counter(t.task_status for t in visible_tasks)),
        "checks": checks, "issues": issues,
        "thresholds": {"complete_transactions": MIN_COMPLETE_TRANSACTIONS, "categories": MIN_CATEGORIES,
                       "coverage_days": MIN_COVERAGE_DAYS, "completeness_rate": MIN_COMPLETENESS_RATE},
    }


def choose_category_adjustment(actual_amount, planned_amount, priority):
    """Source 110%/80% signals, using exact integer comparisons; no limit edits."""
    if planned_amount <= 0 or priority == "P0":
        return None
    if actual_amount * 100 >= planned_amount * OVER_BUDGET_PERCENT:
        return "REVIEW_OVER_BUDGET"
    if actual_amount * 100 <= planned_amount * UNDER_BUDGET_PERCENT:
        return "REVIEW_UNDER_BUDGET"
    return None
