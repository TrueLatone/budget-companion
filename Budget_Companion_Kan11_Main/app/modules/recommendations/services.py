"""KAN-27 adapts 3e6c3bc's F16/F18/F19 services to canonical Budget/Expense.

Financially read-only: only Recommendation and optional MonthlyReview metadata
are written. No budget allocation, task, adjustment or transaction is changed.
"""

import calendar
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import BudgetMonth, MonthlyReview, Recommendation
from app.modules.budgets import services as budgets
from app.modules.expenses import services as expenses
from app.modules.expenses.presentation import today_vn
from . import rules

BASELINE_GUIDANCE = [
    "Keep required P0 bills and any P1 minimums covered. Review future setup before changing spending priorities.",
    "Record real purchases and unexpected expenses. Use NO_EXPENSE only when you can confirm no spending for that whole task period.",
    "Confirm a Budget plan and create/verify its Expense schedule. Missing tasks and check-ins remain unknown, not zero.",
]
READ_ONLY_IMPACT = "Review this category when planning a future month. This guidance changes no saved allocation, task limit or transaction."


class RecommendationServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _uuid(value):
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise RecommendationServiceError("Resource not found.", 404) from None


def parse_month(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
        raise RecommendationServiceError("month must use YYYY-MM format")
    try:
        return date.fromisoformat(value + "-01")
    except ValueError:
        raise RecommendationServiceError("Invalid calendar month") from None


def parse_date(value, fallback=None):
    if value is None or value == "":
        return fallback or today_vn()
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise RecommendationServiceError("as_of must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise RecommendationServiceError("Invalid as_of date") from None


def get_budget_month(user_id, month_value):
    month = db.session.scalar(db.select(BudgetMonth).where(
        BudgetMonth.user_id == _uuid(user_id), BudgetMonth.month_start == parse_month(month_value),
    ))
    if month is None:
        raise RecommendationServiceError("Budget month was not found for this user", 404)
    return month


@contextmanager
def _write_month(user_id, month_id):
    try:
        yield budgets.get_month(user_id, month_id, lock=True)
        db.session.commit()
    except budgets.BudgetNotFound:
        db.session.rollback()
        raise RecommendationServiceError("Budget month not found", 404) from None
    except IntegrityError as exc:
        db.session.rollback()
        raise RecommendationServiceError("Concurrent metadata write; reload and retry.", 409) from exc
    except Exception:
        db.session.rollback()
        raise


@dataclass
class AnalysisData:
    month: object
    as_of: date
    end: date
    closed: bool
    allocations: list
    tasks: list
    records: list
    schedule_state: object


def _load(user_id, month_value, as_of_value=None):
    month = get_budget_month(user_id, month_value)
    end = date(month.month_start.year, month.month_start.month,
               calendar.monthrange(month.month_start.year, month.month_start.month)[1])
    today = today_vn()
    as_of = parse_date(as_of_value, min(today, end))
    if as_of_value not in (None, "") and (as_of.replace(day=1) != month.month_start or as_of > today):
        raise RecommendationServiceError("as_of must be within the selected month and cannot be a future date")
    try:
        allocations = budgets.get_confirmed_allocations(user_id, month.id)
        state = expenses.get_schedule_state(user_id, month.id)
        tasks = [adapter.raw_task for adapter in expenses.list_tasks(user_id, month.tracking_start_date, end)]
        if any(type(task.current_limit) is not int or not 0 <= task.current_limit <= rules.MAX_VND for task in tasks):
            raise RecommendationServiceError("Saved task limits must be known nonnegative integer VND.", 409)
        records = [adapter.raw_record for adapter in expenses.list_records(user_id, month.tracking_start_date, as_of)]
    except (budgets.BudgetError, expenses.ValidationError, expenses.NotFoundError) as exc:
        raise RecommendationServiceError("Saved Budget/Expense references need correction before analysis.", 409) from exc
    return AnalysisData(month, as_of, end, as_of < today, allocations, tasks, records, state)


def _completeness(data):
    result = rules.build_completeness_result(data.records, data.tasks, data.as_of, as_of_closed=data.closed)
    result["checks"].update({
        "confirmed_plan": bool(data.allocations), "complete_schedule": data.schedule_state.code == "READY",
        "tracking_started": data.as_of >= data.month.tracking_start_date,
    })
    descriptions = {
        "minimum_complete_transactions": f"Need at least 10 complete actual transactions; found {result['complete_transaction_count']}.",
        "minimum_categories": f"Need at least 3 categories with actual transactions; found {result['category_count']}.",
        "minimum_coverage_days": f"Need at least 30 calendar days between first and last actual transactions; found {result['coverage_days']}.",
        "minimum_completeness_rate": f"Need at least 80% completeness; observed {result['completeness_rate'] * 100:.2f}%.",
        "no_unresolved_tasks": "Completed periods have missing or inconsistent check-ins; resolve them without inventing spending.",
        "no_incomplete_transactions": "Some transactions have incomplete or invalid required data.",
        "confirmed_plan": "A confirmed Budget plan with allocations is required.",
        "complete_schedule": data.schedule_state.message,
        "tracking_started": "Tracking has not started for this month.",
    }
    sufficient = all(result["checks"].values())
    result.update({
        "status": "SUFFICIENT" if sufficient else "INSUFFICIENT",
        "guidance_mode": "PERSONALIZED_GUIDANCE" if sufficient else "BASELINE_GUIDANCE",
        "insufficient_reasons": [descriptions[key] for key, passed in result["checks"].items() if not passed],
        "month": data.month.month_start.strftime("%Y-%m"), "as_of": data.as_of.isoformat(),
        "schedule_state": data.schedule_state.code,
    })
    return result


def get_completeness(user_id, month_value, as_of_value=None):
    return _completeness(_load(user_id, month_value, as_of_value))


def _category_rows(data, *, closed_only=False):
    rows = {}

    def row(category, priority, *, has_task=False):
        key = (category.id, priority)
        if key not in rows:
            rows[key] = dict(category_id=str(category.id), category_name=category.category_name,
                             priority=priority, planned_amount=0 if not closed_only and data.schedule_state.code == "READY" else None,
                             actual_amount=0, transaction_count=0)
        if has_task and rows[key]["planned_amount"] is None:
            rows[key]["planned_amount"] = 0
        return rows[key]

    eligible_ids = set()
    for task in data.tasks:
        if closed_only and not (task.period_end < data.as_of or data.closed and task.period_end == data.as_of):
            continue
        eligible_ids.add(task.id)
        expense = task.allocation.budget_expense
        item = row(expense.category, expense.priority, has_task=True)
        item["planned_amount"] += task.current_limit
    for record in data.records:
        if not rules.is_complete_expense_record(record):
            continue
        if closed_only and record.task_id and record.task_id not in eligible_ids:
            continue
        priority = record.priority or (record.task.allocation.budget_expense.priority if record.task else None)
        item = row(record.category, priority)
        item["actual_amount"] += record.amount
        item["transaction_count"] += 1
    return sorted(rows.values(), key=lambda item: (item["category_name"], item["priority"] or ""))


def _review(data, completeness):
    # F19's reliable monthly balance differs from F18's personalized-readiness
    # thresholds: a fully resolved month can be known with fewer than 10 buys.
    known = bool(data.allocations and data.schedule_state.code == "READY" and data.closed
                 and data.as_of == data.end and not completeness["inconsistent_task_count"]
                 and not completeness["incomplete_transaction_count"]
                 and all(task.task_status in {"RECORDED", "NO_EXPENSE"} for task in data.tasks))
    planned = sum(task.current_limit for task in data.tasks) if data.tasks else None
    observed = sum(record.amount for record in data.records if rules.is_complete_expense_record(record))
    rows = _category_rows(data)
    for row in rows:
        row["variance"] = row["planned_amount"] - row["actual_amount"] if known else None
    return dict(month=data.month.month_start.strftime("%Y-%m"), as_of=data.as_of.isoformat(),
                review_status="COMPLETE" if known else "INCOMPLETE_DATA", data_complete=known,
                planned_task_total=planned, recorded_expense_total=observed,
                remaining_vs_plan=planned - observed if known else None,
                confirmed_allocation_total=sum(a.allocated_amount for a in data.allocations) if data.allocations else None,
                category_review=rows, task_status_counts=completeness["task_status_counts"])


def _analysis(data):
    completeness = _completeness(data)
    findings = []
    if completeness["status"] == "SUFFICIENT":
        for row in _category_rows(data, closed_only=True):
            if row["planned_amount"] is None:
                continue  # No comparable completed-period budget, not a zero limit.
            direction = rules.choose_category_adjustment(row["actual_amount"], row["planned_amount"], row["priority"])
            if direction is None:
                continue
            relation = "at least 110% of" if direction == "REVIEW_OVER_BUDGET" else "at most 80% of"
            findings.append({**row, "direction": direction,
                "reason": f"{row['category_name']} ({row['priority']}): recorded {row['actual_amount']} VND against {row['planned_amount']} VND in completed scheduled periods, {relation} their limits.",
                "expected_impact": READ_ONLY_IMPACT})
    fingerprint = {
        "algorithm": "KAN27-read-only-v1", "month": str(data.month.id), "as_of": data.as_of.isoformat(), "as_of_closed": data.closed,
        "allocations": sorted((str(a.id), a.allocated_amount) for a in data.allocations),
        "tasks": sorted((str(t.id), t.task_status, t.original_limit, t.current_limit,
                         t.assigned_date.isoformat(), t.period_end.isoformat()) for t in data.tasks),
        "records": sorted((str(r.id), r.amount, str(r.category_id), r.priority, r.expense_date.isoformat()) for r in data.records),
        "findings": findings, "completeness": completeness,
    }
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    return dict(status="ANALYZED" if completeness["status"] == "SUFFICIENT" else "SKIPPED_INSUFFICIENT_DATA",
                month=data.month.month_start.strftime("%Y-%m"), budget_month_id=str(data.month.id),
                as_of=data.as_of.isoformat(), adjustments_enabled=False, completeness=completeness,
                baseline_guidance=list(BASELINE_GUIDANCE) if completeness["status"] != "SUFFICIENT" else [],
                review=_review(data, completeness), findings=findings, analysis_key=key, recommendations=[])


def _saved(month_id, analysis_key):
    return [item for item in db.session.scalars(db.select(Recommendation).where(
        Recommendation.budget_month_id == month_id).order_by(Recommendation.id))
        if isinstance(item.proposed_changes, dict) and item.proposed_changes.get("analysis_key") == analysis_key]


def analyze_spending(user_id, month_value, as_of_value=None):
    data = _load(user_id, month_value, as_of_value)
    result = _analysis(data)
    if result["completeness"]["status"] == "SUFFICIENT":
        result["recommendations"] = [serialize_recommendation(item) for item in _saved(data.month.id, result["analysis_key"])]
    return result


def generate_recommendations(user, month_value, as_of_value=None):
    month = get_budget_month(user.id, month_value)
    with _write_month(user.id, month.id):
        data = _load(user.id, month_value, as_of_value)
        result = _analysis(data)
        result.update(created_count=0, reused_count=0)
        if result["completeness"]["status"] != "SUFFICIENT":
            return result
        existing = {item.proposed_changes.get("signal_key"): item for item in _saved(month.id, result["analysis_key"])}
        saved = []
        for finding in result["findings"]:
            signal_key = f"{finding['category_id']}:{finding['priority']}:{finding['direction']}"
            item = existing.get(signal_key)
            if item is None:
                item = Recommendation(budget_month_id=month.id, reason=finding["reason"],
                    expected_impact=finding["expected_impact"], status="PENDING",
                    proposed_changes={**finding, "mode": "READ_ONLY", "changes": [],
                                      "as_of": result["as_of"], "analysis_key": result["analysis_key"], "signal_key": signal_key})
                db.session.add(item)
                result["created_count"] += 1
            else:
                result["reused_count"] += 1
            saved.append(item)
        db.session.flush()
        result["recommendations"] = [serialize_recommendation(item) for item in saved]
        result["status"] = "GENERATED" if result["created_count"] else "UNCHANGED" if saved else "NO_ACTION_REQUIRED"
    return result


def serialize_recommendation(recommendation):
    proposal = recommendation.proposed_changes
    # Old source proposals can contain unchecked foreign task IDs and a promise
    # of automatic edits. Never expose those as an actionable integration API.
    if not isinstance(proposal, dict) or proposal.get("mode") != "READ_ONLY" or proposal.get("changes") != []:
        proposal = {"mode": "READ_ONLY", "changes": [], "legacy_proposal_withheld": True}
    return dict(id=str(recommendation.id), budget_month_id=str(recommendation.budget_month_id),
                reason=recommendation.reason, expected_impact=READ_ONLY_IMPACT,
                proposed_changes=proposal, status=recommendation.status, adjustments_enabled=False)


def _recommendation(user_id, recommendation_id):
    item = db.session.scalar(db.select(Recommendation).join(BudgetMonth).where(
        Recommendation.id == _uuid(recommendation_id), BudgetMonth.user_id == _uuid(user_id),
    ).execution_options(populate_existing=True))
    if item is None:
        raise RecommendationServiceError("Recommendation was not found", 404)
    return item


def get_recommendation(user_id, recommendation_id):
    result = serialize_recommendation(_recommendation(user_id, recommendation_id))
    result["snapshot_notice"] = "Saved analysis snapshot; current data may differ. Financial adjustments are disabled."
    return result


def decide_recommendation(user_id, recommendation_id, decision, as_of_value=None):
    item = _recommendation(user_id, recommendation_id)
    with _write_month(user_id, item.budget_month_id):
        item = _recommendation(user_id, recommendation_id)
        if not isinstance(decision, str) or decision.upper() not in {"ACCEPT", "REJECT"}:
            raise RecommendationServiceError("decision must be ACCEPT or REJECT")
        if as_of_value is not None:
            _load(user_id, item.budget_month.month_start.strftime("%Y-%m"), as_of_value)
        if decision.upper() == "ACCEPT":
            raise RecommendationServiceError("Financial adjustments are disabled. Recommendations are read-only; no allocation or task limit was changed.", 409)
        if item.status not in {"PENDING", "REJECTED"}:
            raise RecommendationServiceError("This recommendation has already been decided", 409)
        item.status = "REJECTED"
    return {"status": "REJECTED", "recommendation_id": str(item.id), "adjustments_enabled": False}


def get_monthly_review(user_id, month_value, as_of_value=None):
    data = _load(user_id, month_value, as_of_value)
    return _review(data, _completeness(data))


def save_monthly_feedback(user_id, month_value, rating, comment):
    month = get_budget_month(user_id, month_value)
    if rating is not None and (type(rating) is not int or not 1 <= rating <= 5):
        raise RecommendationServiceError("rating must be an integer from 1 to 5")
    if comment is not None and (not isinstance(comment, str) or len(comment) > 2000):
        raise RecommendationServiceError("comment must be text of at most 2000 characters")
    with _write_month(user_id, month.id):
        review = db.session.scalar(db.select(MonthlyReview).where(MonthlyReview.budget_month_id == month.id))
        if review is None:
            review = MonthlyReview(budget_month_id=month.id)
            db.session.add(review)
        review.rating = rating
        review.comment = (comment or "").strip() or None
    return dict(status="SAVED", month=month.month_start.strftime("%Y-%m"), rating=review.rating, comment=review.comment)
