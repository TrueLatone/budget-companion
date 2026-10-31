# Business logic for recommendations
from collections import defaultdict
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func

from app.extensions import db
from app.models import (
    AssignedExpenseTask,
    BudgetAdjustment,
    BudgetAdjustmentDetail,
    BudgetAllocation,
    BudgetMonth,
    BudgetPlan,
    ExpenseRecord,
    MonthlyReview,
    Recommendation,
)
from . import rules


class RecommendationServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def parse_month(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except (TypeError, ValueError):
        raise RecommendationServiceError("month must use YYYY-MM format")
    return parsed.replace(day=1)


def parse_date(value, fallback=None):
    if not value:
        return fallback or date.today()
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise RecommendationServiceError("as_of must use YYYY-MM-DD format")


def get_budget_month(user_id, month_value):
    month_start = parse_month(month_value)
    month = BudgetMonth.query.filter_by(user_id=user_id, month_start=month_start).first()
    if month is None:
        raise RecommendationServiceError("Budget month was not found for this user", 404)
    return month


def _month_tasks(month):
    query = (
        db.session.query(AssignedExpenseTask)
        .join(BudgetAllocation, AssignedExpenseTask.allocation_id == BudgetAllocation.id)
        .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
        .filter(BudgetPlan.budget_month_id == month.id)
    )
    confirmed_exists = (
        db.session.query(BudgetPlan.id)
        .filter(BudgetPlan.budget_month_id == month.id, BudgetPlan.status == "CONFIRMED")
        .first()
    )
    if confirmed_exists:
        query = query.filter(BudgetPlan.status == "CONFIRMED")
    return query.filter(
        AssignedExpenseTask.assigned_date >= month.month_start,
        AssignedExpenseTask.assigned_date < _next_month(month.month_start),
    ).all()


def _next_month(month_start):
    return date(month_start.year + (month_start.month == 12), 1 if month_start.month == 12 else month_start.month + 1, 1)


def _month_records(month):
    start = month.month_start
    end = _next_month(start)
    return ExpenseRecord.query.filter(
        ExpenseRecord.budget_month_id == month.id,
        ExpenseRecord.expense_date >= start,
        ExpenseRecord.expense_date < end,
    ).all()


def _category_name(task):
    expense = task.allocation.budget_expense
    category = expense.category
    return category.category_name if category else expense.expense_name


def get_completeness(user_id, month_value, as_of_value=None):
    month = get_budget_month(user_id, month_value)
    as_of = parse_date(as_of_value)
    result = rules.build_completeness_result(_month_records(month), _month_tasks(month), as_of)
    result.update({"month": month.month_start.strftime("%Y-%m"), "as_of": as_of.isoformat()})
    return result


def generate_recommendations(user, month_value, as_of_value=None):
    month = get_budget_month(user.id, month_value)
    as_of = parse_date(as_of_value)
    records = _month_records(month)
    tasks = _month_tasks(month)
    completeness = rules.build_completeness_result(records, tasks, as_of)

    preference = user.preference.preferred_plan_type if user.preference else None
    if completeness["status"] != "SUFFICIENT":
        return {
            "status": "SKIPPED_INSUFFICIENT_DATA",
            "message": "F16 did not generate recommendations because F18 data checks were not passed.",
            "preference": preference,
            "completeness": completeness,
            "recommendations": [],
        }

    actual_by_category = defaultdict(int)
    planned_by_category = defaultdict(int)
    priority_by_category = {}
    future_tasks_by_category = defaultdict(list)

    for record in records:
        if record.record_type in {"PLANNED", "UNEXPECTED"}:
            actual_by_category[record.category_id] += int(record.amount)

    for task in tasks:
        expense = task.allocation.budget_expense
        category_id = expense.category_id
        planned_by_category[category_id] += int(task.current_limit or 0)
        priority_by_category[category_id] = expense.priority
        if task.task_status == "PENDING" and task.assigned_date >= as_of:
            future_tasks_by_category[category_id].append(task)

    category_ids = set(planned_by_category) | set(actual_by_category)
    created = []
    for category_id in category_ids:
        planned = planned_by_category.get(category_id, 0)
        actual = actual_by_category.get(category_id, 0)
        priority = priority_by_category.get(category_id)
        direction = rules.choose_category_adjustment(actual, planned, priority)
        target_tasks = future_tasks_by_category.get(category_id, [])
        if direction is None or not target_tasks:
            continue

        changes = []
        for task in target_tasks:
            previous = int(task.current_limit or 0)
            new = rules.calculate_new_limit(previous, direction)
            if new == previous:
                continue
            changes.append({
                "task_id": str(task.id),
                "category_id": str(category_id),
                "category_name": _category_name(task),
                "previous_limit": previous,
                "new_limit": new,
            })
        if not changes:
            continue

        category_name = _category_name(target_tasks[0])
        variance = ((actual - planned) / planned) * 100 if planned else 0
        if direction == "INCREASE":
            reason = f"{category_name} spending is {variance:.1f}% above its assigned task limits."
            impact = "Increase the limits of future pending tasks in this category by 10%."
        else:
            reason = f"{category_name} spending is {abs(variance):.1f}% below its assigned task limits."
            impact = "Decrease the limits of future pending tasks in this category by 10%."

        recommendation = Recommendation(
            budget_month_id=month.id,
            reason=reason,
            expected_impact=impact,
            proposed_changes={
                "direction": direction,
                "adjustment_rate": rules.ADJUSTMENT_RATE,
                "category_id": str(category_id),
                "category_name": category_name,
                "actual_amount": actual,
                "planned_amount": planned,
                "preference": preference,
                "changes": changes,
            },
            status="PENDING",
        )
        db.session.add(recommendation)
        created.append(recommendation)

    db.session.commit()
    return {
        "status": "GENERATED" if created else "NO_ACTION_REQUIRED",
        "month": month.month_start.strftime("%Y-%m"),
        "as_of": as_of.isoformat(),
        "preference": preference,
        "recommendations": [serialize_recommendation(r) for r in created],
        "completeness": completeness,
    }


def serialize_recommendation(recommendation):
    return {
        "id": str(recommendation.id),
        "budget_month_id": str(recommendation.budget_month_id),
        "reason": recommendation.reason,
        "expected_impact": recommendation.expected_impact,
        "proposed_changes": recommendation.proposed_changes,
        "status": recommendation.status,
    }


def get_recommendation(user_id, recommendation_id):
    try:
        recommendation_uuid = UUID(str(recommendation_id))
    except (TypeError, ValueError, AttributeError):
        raise RecommendationServiceError("Invalid recommendation id")
    recommendation = (
        Recommendation.query.join(BudgetMonth)
        .filter(Recommendation.id == recommendation_uuid, BudgetMonth.user_id == user_id)
        .first()
    )
    if recommendation is None:
        raise RecommendationServiceError("Recommendation was not found", 404)
    data = serialize_recommendation(recommendation)
    data["explanation"] = {
        "reason": recommendation.reason,
        "expected_impact": recommendation.expected_impact,
        "direction": (recommendation.proposed_changes or {}).get("direction"),
        "category_name": (recommendation.proposed_changes or {}).get("category_name"),
        "changes": (recommendation.proposed_changes or {}).get("changes", []),
    }
    return data


def decide_recommendation(user_id, recommendation_id, decision, as_of_value=None):
    decision = str(decision or "").upper()
    if decision not in {"ACCEPT", "REJECT"}:
        raise RecommendationServiceError("decision must be ACCEPT or REJECT")

    detail = get_recommendation(user_id, recommendation_id)
    recommendation = db.session.get(Recommendation, UUID(detail["id"]))
    if recommendation.status != "PENDING":
        raise RecommendationServiceError("This recommendation has already been decided", 409)

    as_of = parse_date(as_of_value)
    try:
        if decision == "REJECT":
            recommendation.status = "REJECTED"
            db.session.commit()
            return {"status": "REJECTED", "recommendation_id": str(recommendation.id)}

        month = recommendation.budget_month
        proposed = recommendation.proposed_changes or {}
        changes = proposed.get("changes", [])
        if not changes:
            raise RecommendationServiceError("Recommendation has no task changes", 409)

        task_ids = []
        expected_by_id = {}
        for change in changes:
            task_id = UUID(str(change["task_id"]))
            task_ids.append(task_id)
            expected_by_id[task_id] = change

        tasks = (
            db.session.query(AssignedExpenseTask)
            .join(BudgetAllocation, AssignedExpenseTask.allocation_id == BudgetAllocation.id)
            .join(BudgetPlan, BudgetAllocation.plan_id == BudgetPlan.id)
            .filter(
                AssignedExpenseTask.id.in_(task_ids),
                BudgetPlan.budget_month_id == month.id,
            ).all()
        )
        tasks_by_id = {task.id: task for task in tasks}
        if len(tasks_by_id) != len(task_ids):
            raise RecommendationServiceError("One or more proposed tasks no longer exist", 409)

        adjustment = BudgetAdjustment(
            recommendation_id=recommendation.id,
            effective_date=as_of,
            reason=recommendation.reason,
            adjustment_type="RECOMMENDATION",
        )
        db.session.add(adjustment)
        db.session.flush()

        for task_id in task_ids:
            task = tasks_by_id[task_id]
            change = expected_by_id[task_id]
            if task.task_status != "PENDING" or task.assigned_date < as_of:
                raise RecommendationServiceError("A proposed task is no longer pending/future; regenerate recommendations", 409)
            if int(task.current_limit or 0) != int(change["previous_limit"]):
                raise RecommendationServiceError("A task limit changed after this recommendation was generated", 409)
            previous = int(task.current_limit or 0)
            new = int(change["new_limit"])
            task.current_limit = new
            db.session.add(BudgetAdjustmentDetail(
                adjustment_id=adjustment.id,
                task_id=task.id,
                previous_limit=previous,
                new_limit=new,
            ))

        recommendation.status = "ACCEPTED"
        db.session.commit()
        return {
            "status": "ACCEPTED",
            "recommendation_id": str(recommendation.id),
            "adjustment_id": str(adjustment.id),
            "updated_task_count": len(task_ids),
        }
    except Exception:
        db.session.rollback()
        raise


def get_monthly_review(user_id, month_value, as_of_value=None):
    month = get_budget_month(user_id, month_value)
    as_of = parse_date(as_of_value)
    tasks = _month_tasks(month)
    records = _month_records(month)

    planned_total = sum(int(t.current_limit or 0) for t in tasks)
    expense_records = [r for r in records if r.record_type in {"PLANNED", "UNEXPECTED"}]
    actual_total = sum(int(r.amount) for r in expense_records)
    unexpected = [r for r in expense_records if r.record_type == "UNEXPECTED"]

    category_rows = defaultdict(lambda: {"planned_amount": 0, "actual_amount": 0})
    for task in tasks:
        category_id = str(task.allocation.budget_expense.category_id)
        category_rows[category_id]["category_name"] = _category_name(task)
        category_rows[category_id]["planned_amount"] += int(task.current_limit or 0)
    for record in expense_records:
        if record.category_id:
            row = category_rows[str(record.category_id)]
            row["actual_amount"] += int(record.amount)

    pending_count = sum(1 for task in tasks if task.task_status == "PENDING" and task.assigned_date <= as_of)
    no_expense_count = sum(1 for task in tasks if task.task_status == "NO_EXPENSE")
    recorded_count = sum(1 for task in tasks if task.task_status == "RECORDED")
    invalid_records = [r for r in expense_records if not rules.is_complete_expense_record(r)]
    data_complete = pending_count == 0 and not invalid_records

    return {
        "month": month.month_start.strftime("%Y-%m"),
        "as_of": as_of.isoformat(),
        "review_status": "COMPLETE" if data_complete else "INCOMPLETE_DATA",
        "planned_task_total": planned_total,
        "recorded_expense_total": actual_total if data_complete else None,
        "remaining_vs_plan": planned_total - actual_total if data_complete else None,
        "task_status_counts": {
            "RECORDED": recorded_count,
            "NO_EXPENSE": no_expense_count,
            "PENDING": pending_count,
        },
        "category_review": [
            {"category_id": key, **value, "variance": value["planned_amount"] - value["actual_amount"]}
            for key, value in category_rows.items()
        ],
        "unexpected_transactions": [
            {
                "record_id": str(r.id),
                "title": r.title,
                "category_id": str(r.category_id) if r.category_id else None,
                "amount": int(r.amount),
                "expense_date": r.expense_date.isoformat(),
                "priority": r.priority,
            }
            for r in unexpected
        ],
    }


def save_monthly_feedback(user_id, month_value, rating, comment):
    month = get_budget_month(user_id, month_value)
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise RecommendationServiceError("rating must be an integer from 1 to 5")
        if rating < 1 or rating > 5:
            raise RecommendationServiceError("rating must be between 1 and 5")

    review = MonthlyReview.query.filter_by(budget_month_id=month.id).first()
    if review is None:
        review = MonthlyReview(budget_month_id=month.id)
        db.session.add(review)
    review.rating = rating
    review.comment = (comment or "").strip() or None
    db.session.commit()
    return {
        "status": "SAVED",
        "month": month.month_start.strftime("%Y-%m"),
        "rating": review.rating,
        "comment": review.comment,
    }
