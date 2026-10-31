# To be developed
from collections import Counter, defaultdict
from datetime import date


MIN_COMPLETE_TRANSACTIONS = 10
MIN_CATEGORIES = 3
MIN_COVERAGE_DAYS = 30
MIN_COMPLETENESS_RATE = 0.80
OVER_BUDGET_THRESHOLD = 1.10
UNDER_BUDGET_THRESHOLD = 0.80
ADJUSTMENT_RATE = 0.10


def is_complete_expense_record(record):
    return bool(
        getattr(record, "id", None)
        and getattr(record, "amount", None) is not None
        and record.amount > 0
        and getattr(record, "category_id", None)
        and isinstance(getattr(record, "expense_date", None), date)
        and getattr(record, "record_type", None) in {"PLANNED", "UNEXPECTED"}
    )


def build_completeness_result(records, tasks, as_of):
    expense_records = [r for r in records if r.record_type in {"PLANNED", "UNEXPECTED"}]
    complete_records = [r for r in expense_records if is_complete_expense_record(r)]
    incomplete_records = [r for r in expense_records if not is_complete_expense_record(r)]

    records_by_task = defaultdict(list)
    for record in expense_records:
        if record.task_id:
            records_by_task[record.task_id].append(record)

    issues = []
    no_expense_count = 0
    pending_count = 0
    inconsistent_task_count = 0

    for task in tasks:
        linked_records = records_by_task.get(task.id, [])
        status = task.task_status
        if status == "NO_EXPENSE":
            no_expense_count += 1
            if linked_records:
                inconsistent_task_count += 1
                issues.append({
                    "type": "NO_EXPENSE_WITH_RECORD",
                    "task_id": str(task.id),
                    "message": "Task is marked NO_EXPENSE but has linked expense records.",
                })
        elif status == "RECORDED":
            if not any(r.record_type == "PLANNED" for r in linked_records):
                inconsistent_task_count += 1
                issues.append({
                    "type": "RECORDED_WITHOUT_TRANSACTION",
                    "task_id": str(task.id),
                    "message": "Task is marked RECORDED but has no linked PLANNED transaction.",
                })
        elif status == "PENDING" and task.assigned_date <= as_of:
            pending_count += 1
            issues.append({
                "type": "UNRECORDED_TASK",
                "task_id": str(task.id),
                "assigned_date": task.assigned_date.isoformat(),
                "message": "Task is still PENDING on or before the review date.",
            })

    for record in incomplete_records:
        issues.append({
            "type": "INCOMPLETE_TRANSACTION",
            "record_id": str(record.id),
            "message": "Transaction is missing a valid amount, category, date, or record type.",
        })

    expected_items = len(complete_records) + len(incomplete_records) + no_expense_count + pending_count + inconsistent_task_count
    complete_items = len(complete_records) + no_expense_count
    completeness_rate = complete_items / expected_items if expected_items else 0.0

    valid_dates = [r.expense_date for r in complete_records]
    coverage_days = (max(valid_dates) - min(valid_dates)).days + 1 if valid_dates else 0
    category_count = len({r.category_id for r in complete_records})

    checks = {
        "minimum_complete_transactions": len(complete_records) >= MIN_COMPLETE_TRANSACTIONS,
        "minimum_categories": category_count >= MIN_CATEGORIES,
        "minimum_coverage_days": coverage_days >= MIN_COVERAGE_DAYS,
        "minimum_completeness_rate": completeness_rate >= MIN_COMPLETENESS_RATE,
        "no_unresolved_tasks": pending_count == 0 and inconsistent_task_count == 0,
        "no_incomplete_transactions": len(incomplete_records) == 0,
    }
    sufficient = all(checks.values())

    return {
        "status": "SUFFICIENT" if sufficient else "INSUFFICIENT",
        "guidance_mode": "PERSONALIZED_GUIDANCE" if sufficient else "BASELINE_GUIDANCE",
        "complete_transaction_count": len(complete_records),
        "incomplete_transaction_count": len(incomplete_records),
        "category_count": category_count,
        "coverage_days": coverage_days,
        "completeness_rate": round(completeness_rate, 4),
        "unrecorded_task_count": pending_count,
        "no_expense_task_count": no_expense_count,
        "task_status_counts": dict(Counter(t.task_status for t in tasks)),
        "checks": checks,
        "issues": issues,
    }


def choose_category_adjustment(actual_amount, planned_amount, priority):
    if planned_amount <= 0:
        return None
    ratio = actual_amount / planned_amount
    if ratio >= OVER_BUDGET_THRESHOLD:
        return None if priority == "P0" else "INCREASE"
    if ratio <= UNDER_BUDGET_THRESHOLD:
        return "DECREASE"
    return None


def calculate_new_limit(current_limit, direction):
    if direction == "INCREASE":
        return int(round(current_limit * (1 + ADJUSTMENT_RATE)))
    if direction == "DECREASE":
        return int(round(current_limit * (1 - ADJUSTMENT_RATE)))
    raise ValueError("Unknown adjustment direction")
