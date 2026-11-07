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
from app.i18n import format_money
from app.models import BudgetMonth, MonthlyReview, Recommendation
from app.modules.budgets import services as budgets
from app.modules.expenses import services as expenses
from app.modules.expenses.presentation import today_vn
from . import rules

READ_ONLY_IMPACT = "Gợi ý chỉ để tham khảo khi bạn xem lại kế hoạch; hệ thống không tự thay đổi ngân sách hay khoản chi."


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
    draft_plan: object | None


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
        draft_plans = [plan for plan in budgets.list_plans(user_id, month.id) if plan.status == "GENERATED"]
        draft_plan = next((plan for plan in draft_plans if plan.plan_type == "BALANCED"), None)
        draft_plan = draft_plan or (draft_plans[0] if draft_plans else None)
        state = expenses.get_schedule_state(user_id, month.id)
        tasks = [adapter.raw_task for adapter in expenses.list_tasks(user_id, month.tracking_start_date, end)]
        if any(type(task.current_limit) is not int or not 0 <= task.current_limit <= rules.MAX_VND for task in tasks):
            raise RecommendationServiceError("Saved task limits must be known nonnegative integer VND.", 409)
        records = [adapter.raw_record for adapter in expenses.list_records(user_id, month.tracking_start_date, as_of)]
    except (budgets.BudgetError, expenses.ValidationError, expenses.NotFoundError) as exc:
        raise RecommendationServiceError("Saved Budget/Expense references need correction before analysis.", 409) from exc
    return AnalysisData(month, as_of, end, as_of < today, allocations, tasks, records, state, draft_plan)


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


def _allocation_totals(data):
    totals = {}
    for allocation in data.allocations:
        expense = allocation.budget_expense
        key = (expense.category.id, expense.priority)
        row = totals.setdefault(key, {"monthly_allocation": 0, "minimum_amount": 0})
        row["monthly_allocation"] += allocation.allocated_amount
        if expense.priority == "P1" and expense.minimum_amount is not None:
            row["minimum_amount"] += expense.minimum_amount
    return totals


def _category_rows(data, *, closed_only=False):
    rows = {}
    allocation_totals = _allocation_totals(data)

    def row(category, priority, *, has_task=False):
        key = (category.id, priority)
        if key not in rows:
            rows[key] = dict(category_id=str(category.id), category_name=category.category_name,
                             priority=priority, planned_amount=0 if not closed_only and data.schedule_state.code == "READY" else None,
                             actual_amount=0, transaction_count=0,
                             evidence=[], **allocation_totals.get(key, {"monthly_allocation": 0, "minimum_amount": 0}))
        if has_task and rows[key]["planned_amount"] is None:
            rows[key]["planned_amount"] = 0
        return rows[key]

    eligible_ids = set()
    eligible_periods = []
    for task in data.tasks:
        if closed_only and not (task.period_end < data.as_of or data.closed and task.period_end == data.as_of):
            continue
        if closed_only and task.task_status not in {"RECORDED", "NO_EXPENSE"}:
            continue
        if closed_only:
            task_records = [record for record in data.records if record.task_id == task.id]
            if (task.task_status == "NO_EXPENSE" and task_records
                    or task.task_status == "RECORDED"
                    and (not any(record.record_type == "PLANNED" for record in task_records)
                         or any(not rules.is_complete_expense_record(record) for record in task_records))):
                continue
        eligible_ids.add(task.id)
        expense = task.allocation.budget_expense
        eligible_periods.append((expense.category.id, expense.priority, task.assigned_date, task.period_end))
        item = row(expense.category, expense.priority, has_task=True)
        item["planned_amount"] += task.current_limit
    for record in data.records:
        if not rules.is_complete_expense_record(record):
            continue
        if closed_only:
            if record.task_id:
                if record.task_id not in eligible_ids:
                    continue
            elif not any(
                category_id == record.category_id
                and (record.priority is None or priority == record.priority)
                and start <= record.expense_date <= end
                for category_id, priority, start, end in eligible_periods
            ):
                continue
        priority = record.priority or (record.task.allocation.budget_expense.priority if record.task else None)
        item = row(record.category, priority)
        item["actual_amount"] += record.amount
        item["transaction_count"] += 1
        item["evidence"].append({
            "record_id": str(record.id), "title": record.title, "amount": record.amount,
            "expense_date": record.expense_date.isoformat(), "record_type": record.record_type,
        })
    return sorted(rows.values(), key=lambda item: (item["category_name"], item["priority"] or ""))


def _open_period_rows(data):
    """Verified spending in periods that are still open on today's cutoff."""
    if data.closed or not data.allocations or data.schedule_state.code != "READY":
        return []
    rows = {}
    allocation_totals = _allocation_totals(data)
    seen_record_ids = set()
    for task in data.tasks:
        if not task.assigned_date <= data.as_of <= task.period_end or task.task_status != "RECORDED":
            continue
        task_records = [record for record in data.records if record.task_id == task.id]
        if (not any(record.record_type == "PLANNED" for record in task_records)
                or any(not rules.is_complete_expense_record(record) for record in task_records)):
            continue
        expense = task.allocation.budget_expense
        key = (expense.category.id, expense.priority)
        unlinked_records = [
            record for record in data.records
            if record.task_id is None and record.category_id == expense.category.id
            and (record.priority is None or record.priority == expense.priority)
            and task.assigned_date <= record.expense_date <= task.period_end
            and rules.is_complete_expense_record(record)
        ]
        actual_records = [*task_records, *unlinked_records]
        row = rows.setdefault(key, dict(
            category_id=str(expense.category.id), category_name=expense.category.category_name,
            priority=expense.priority, planned_amount=0, actual_amount=0, transaction_count=0,
            evidence=[], **allocation_totals.get(key, {"monthly_allocation": 0, "minimum_amount": 0}),
        ))
        row["planned_amount"] += task.current_limit
        new_records = [record for record in actual_records if record.id not in seen_record_ids]
        seen_record_ids.update(record.id for record in new_records)
        row["actual_amount"] += sum(record.amount for record in new_records)
        row["transaction_count"] += len(new_records)
        row["evidence"].extend({
            "record_id": str(record.id), "title": record.title, "amount": record.amount,
            "expense_date": record.expense_date.isoformat(), "record_type": record.record_type,
        } for record in new_records if rules.is_complete_expense_record(record))
    return sorted(rows.values(), key=lambda item: (item["category_name"], item["priority"] or ""))


def _review(data, completeness):
    # F19's reliable monthly balance differs from F18's personalized-readiness
    # thresholds: a fully resolved month can be known with fewer than 10 buys.
    known = bool(data.allocations and data.schedule_state.code == "READY" and data.closed
                 and data.as_of == data.end and not completeness["inconsistent_task_count"]
                 and not completeness["incomplete_transaction_count"]
                 and all(task.task_status in {"RECORDED", "NO_EXPENSE"} for task in data.tasks))
    planned = sum(task.current_limit for task in data.tasks) if known else None
    observed = sum(record.amount for record in data.records if rules.is_complete_expense_record(record))
    rows = _category_rows(data)
    for row in rows:
        row["variance"] = row["planned_amount"] - row["actual_amount"] if known else None
        if not known:
            row["planned_amount"] = None
    feedback = db.session.scalar(db.select(MonthlyReview).where(
        MonthlyReview.budget_month_id == data.month.id,
    ))
    return dict(month=data.month.month_start.strftime("%Y-%m"), as_of=data.as_of.isoformat(),
                review_status="COMPLETE" if known else "INCOMPLETE_DATA", data_complete=known,
                summary_note=None if known else (
                    "Chỉ bao gồm các khoản chi hợp lệ đã ghi nhận; đây chưa phải tổng chi cuối tháng "
                    "và không xác định số ngân sách còn lại."
                ),
                planned_task_total=planned, recorded_expense_total=observed,
                recorded_expense_count=completeness["complete_transaction_count"],
                remaining_vs_plan=planned - observed if known else None,
                confirmed_allocation_total=sum(a.allocated_amount for a in data.allocations) if data.allocations else None,
                category_review=rows, task_status_counts=completeness["task_status_counts"],
                rating=feedback.rating if feedback else None,
                comment=feedback.comment if feedback else None)


def _draft_plan_suggestion(plan):
    """Turn the user's saved draft allocations into an immediate review prompt."""
    plan_name = {"SAVING": "Tiết kiệm", "BALANCED": "Cân bằng", "LIFESTYLE": "Linh hoạt"}.get(
        plan.plan_type, "Tham khảo",
    )
    allocations = [
        f"{allocation.budget_expense.expense_name}: {format_money(allocation.allocated_amount, 'vi')} đồng"
        for allocation in sorted(plan.allocations, key=lambda item: item.budget_expense.expense_name.casefold())
    ]
    allocation_text = "; ".join(allocations) if allocations else "chưa có khoản phân bổ"
    savings = format_money(plan.planned_savings, "vi")
    return {
        "code": "REVIEW_DRAFT_PLAN",
        "kind": "EARLY_SIGNAL",
        "title": f"Gợi ý sơ bộ: xem lại phương án {plan_name}",
        "message": (
            f"Từ các khoản chi bạn đã nhập, phương án {plan_name.lower()} đang phân bổ: "
            f"{allocation_text}; dự kiến để dành {savings} đồng. "
            "Hãy đối chiếu từng mức với chi phí thực tế của bạn rồi xác nhận nếu phù hợp."
        ),
        "basis": "Được tính từ các khoản chi, mức ước tính và ưu tiên bạn đã nhập ở phần ngân sách.",
        "expected_impact": "Đây là phương án dự thảo để bạn xem xét; chưa thay đổi ngân sách hoặc lịch chi tiêu.",
        "personalized": False,
    }


def _adjustment_impact(proposal, category_name):
    change = proposal["change_amount"]
    if not change:
        if proposal["constraint_applied"] == "P1_MINIMUM":
            return "Không giảm phân bổ: mức tối thiểu P1 đang bảo vệ khoản này. Ngân sách không bị thay đổi."
        return "Không tăng phân bổ vì kế hoạch hiện không còn khoản tiết kiệm để cấp thêm. Ngân sách không bị thay đổi."
    amount = format_money(abs(change), "vi")
    if change > 0:
        return f"Nếu bạn tự cập nhật kế hoạch, {amount} đồng sẽ được chuyển từ khoản tiết kiệm sang nhóm {category_name}; tổng ngân sách giữ nguyên. Chưa có thay đổi nào được áp dụng."
    return f"Nếu bạn tự cập nhật kế hoạch, {amount} đồng sẽ được giảm khỏi nhóm {category_name} và chuyển vào khoản tiết kiệm; tổng ngân sách giữ nguyên. Chưa có thay đổi nào được áp dụng."


def _analysis(data):
    completeness = _completeness(data)
    findings = []
    is_sufficient = completeness["status"] == "SUFFICIENT"
    # Closed expense periods can produce useful early category signals even
    # while the month is still in progress. Keep them clearly provisional;
    # the month-level review remains gated on a fully resolved month.
    if data.allocations and data.schedule_state.code == "READY":
        remaining_savings = max(0, data.allocations[0].plan.planned_savings)
        for row in _category_rows(data, closed_only=True):
            if row["planned_amount"] is None:
                continue
            proposal = rules.propose_category_adjustment(
                row["actual_amount"], row["planned_amount"], row["priority"],
                row["monthly_allocation"], row["minimum_amount"],
                remaining_savings,
            )
            if proposal is None:
                continue
            if proposal["change_amount"] > 0:
                remaining_savings -= proposal["change_amount"]
            direction = proposal["direction"]
            relation = "cao hơn" if direction == "REVIEW_OVER_BUDGET" else "thấp hơn"
            findings.append({**row, "direction": direction,
                "adjustment": proposal,
                "reason": f"Trong các kỳ đã hoàn tất, bạn đã ghi nhận {format_money(row['actual_amount'], 'vi')} đồng cho nhóm {row['category_name']}, {relation} mức dự kiến {format_money(row['planned_amount'], 'vi')} đồng. Hãy kiểm tra lại các khoản đã ghi trước khi thay đổi kế hoạch.",
                "expected_impact": _adjustment_impact(proposal, row["category_name"])})

        # A confirmed over-limit amount is already actionable during an open
        # period. Under-budget signals wait until the period closes so a partial
        # day's spending is not mistaken for a completed low-spend period.
        completed_signals = {(item.get("category_id"), item.get("priority"), item["direction"])
                             for item in findings}
        for row in _open_period_rows(data):
            proposal = rules.propose_category_adjustment(
                row["actual_amount"], row["planned_amount"], row["priority"],
                row["monthly_allocation"], row["minimum_amount"],
                remaining_savings,
            )
            direction = proposal["direction"] if proposal else None
            if direction != "REVIEW_OVER_BUDGET":
                continue
            if (row["category_id"], row["priority"], direction) in completed_signals:
                continue
            remaining_savings -= max(0, proposal["change_amount"])
            findings.append({**row, "direction": direction,
                "adjustment": proposal,
                "reason": f"Trong kỳ đang diễn ra, nhóm {row['category_name']} đã ghi nhận {format_money(row['actual_amount'], 'vi')} đồng, vượt mức dự kiến {format_money(row['planned_amount'], 'vi')} đồng. Hãy kiểm tra lại khoản chi; số liệu còn có thể thay đổi trước khi kỳ kết thúc.",
                "expected_impact": _adjustment_impact(proposal, row["category_name"])})

    # When there is no confirmed plan yet, still surface a simple observation
    # from actual purchases instead of showing setup steps alone.
    if not data.allocations:
        totals = {}
        for record in data.records:
            if not rules.is_complete_expense_record(record):
                continue
            category = record.category.category_name if record.category else "Khác"
            totals[category] = totals.get(category, 0) + record.amount
        if totals:
            category, amount = max(totals.items(), key=lambda item: (item[1], item[0]))
            findings.append({
                "direction": "OBSERVE_CATEGORY_SPENDING",
                "category_name": category,
                "reason": f"Tính đến {data.as_of.strftime('%d/%m/%Y')}, bạn đã ghi nhận {format_money(amount, 'vi')} đồng ở nhóm {category}. Hãy xem lại các khoản chi trong nhóm này để cân nhắc có khoản nào chưa thật sự cần thiết.",
                "expected_impact": "Đây là gợi ý tham khảo từ các khoản đã ghi nhận, không thay đổi ngân sách hay giao dịch.",
            })

    if findings:
        suggestions = [{
            "code": finding["direction"],
            "kind": "PERSONALIZED_RECOMMENDATION" if is_sufficient else "EARLY_SIGNAL",
            "title": (f"Chi tiêu nhóm {finding['category_name']} đang {'cao' if finding['direction'] == 'REVIEW_OVER_BUDGET' else 'thấp'} hơn kế hoạch" if finding['direction'] in {'REVIEW_OVER_BUDGET', 'REVIEW_UNDER_BUDGET'} else f"Xem lại chi tiêu nhóm {finding['category_name']}"),
            "message": finding["reason"],
            "basis": (
                f"Kế hoạch đã xác nhận; {finding.get('transaction_count', 0)} khoản chi hợp lệ trong các kỳ được xét; "
                f"mức kỳ dự kiến {format_money(finding.get('planned_amount') or 0, 'vi')} đồng, "
                f"thực tế {format_money(finding.get('actual_amount') or 0, 'vi')} đồng; "
                f"ưu tiên {finding.get('priority') or 'chưa phân loại'}."
                if finding.get("planned_amount") is not None else
                "Gợi ý sơ bộ dựa trên dữ liệu hiện có; nội dung có thể thay đổi khi bạn ghi thêm chi tiêu."
            ),
            "evidence": finding.get("evidence", []),
            "priority": finding.get("priority"),
            "adjustment": finding.get("adjustment"),
            "minimum_amount": finding.get("minimum_amount"),
            "expected_impact": finding["expected_impact"],
            "personalized": is_sufficient,
        } for finding in findings]
    elif is_sufficient:
        suggestions = [rules.build_no_adjustment_guidance()]
    else:
        suggestions = []

    if not is_sufficient:
        baseline = rules.build_baseline_guidance(
            has_confirmed_plan=bool(data.allocations),
            has_draft_plan=data.draft_plan is not None,
            schedule_code=data.schedule_state.code,
            schedule_message=data.schedule_state.message,
            available_vnd=data.month.available_vnd,
            tracking_started=data.as_of >= data.month.tracking_start_date,
            tracking_start_date=data.month.tracking_start_date.isoformat(),
            complete_transaction_count=completeness["complete_transaction_count"],
            category_count=completeness["category_count"],
            coverage_days=completeness["coverage_days"],
            completeness_rate=completeness["completeness_rate"],
            unrecorded_task_count=completeness["unrecorded_task_count"],
            inconsistent_task_count=completeness["inconsistent_task_count"],
            incomplete_transaction_count=completeness["incomplete_transaction_count"],
        )
        shown_codes = {item["code"] for item in suggestions}
        suggestions.extend(item for item in baseline if item["code"] not in shown_codes)

    if (not is_sufficient and not findings and data.allocations
            and data.schedule_state.code == "READY"):
        completed_rows = _category_rows(data, closed_only=True)
        open_rows = _open_period_rows(data)
        if not completed_rows and open_rows:
            checked_transactions = sum(row["transaction_count"] for row in open_rows)
            timely_guidance = {
                "code": "CURRENT_DAY_STATUS",
                "kind": "BASELINE_GUIDANCE",
                "title": "Các khoản đã ghi nhận chưa vượt kế hoạch",
                "message": f"Bạn đã ghi nhận chi tiêu ở {checked_transactions} giao dịch thuộc các kỳ đang diễn ra; hiện chưa có khoản nào vượt 110% mức dự kiến để cần báo sớm. Chi tiêu thấp hơn kế hoạch chỉ được đánh giá sau khi kỳ kết thúc.",
                "basis": "Các giao dịch đã check-in được so với hạn mức của chính kỳ đang diễn ra.",
                "personalized": False,
            }
        elif not completed_rows:
            upcoming_end = min(
                (task.period_end for task in data.tasks if task.period_end >= data.as_of),
                default=None,
            )
            when = (
                f" Kỳ gần nhất kết thúc ngày {upcoming_end.strftime('%d/%m/%Y')}; "
                "hãy xem lại gợi ý từ ngày hôm sau."
                if upcoming_end else " Hãy xem lại sau khi một kỳ chi tiêu kết thúc và được xác nhận."
            )
            timely_guidance = {
                "code": "WAIT_FOR_PERIOD_CLOSE",
                "kind": "BASELINE_GUIDANCE",
                "title": "Các kỳ chi tiêu hiện vẫn đang diễn ra",
                "message": "Bạn đã ghi nhận chi tiêu, nhưng chưa có kỳ hoàn tất để so sánh với kế hoạch." + when,
                "basis": "Gợi ý theo danh mục chỉ dùng các kỳ đã kết thúc và có check-in hợp lệ.",
                "personalized": False,
            }
        else:
            timely_guidance = {
                "code": "NO_EARLY_SIGNAL",
                "kind": "BASELINE_GUIDANCE",
                "title": "Chưa có khoản lệch đáng kể trong các kỳ đã xong",
                "message": "Các kỳ đã hoàn tất chưa có khoản chi vượt 110% hoặc thấp hơn 80% mức dự kiến để tạo gợi ý điều chỉnh. Nếu chi tiêu hiện khớp kế hoạch thì đây là kết quả bình thường; hãy xem lại sau kỳ tiếp theo.",
                "basis": "So sánh chỉ xét các kỳ đã kết thúc và được xác nhận.",
                "personalized": False,
            }
        suggestions.insert(1 if suggestions and suggestions[0]["code"] == "BASELINE_AMOUNT_SPLIT" else 0,
                          timely_guidance)
        suggestions = suggestions[:4]

    if not data.allocations and data.draft_plan is not None:
        suggestions = [item for item in suggestions if item["code"] != "CONFIRM_DRAFT_PLAN"]
        suggestions.insert(0, _draft_plan_suggestion(data.draft_plan))
        suggestions = suggestions[:4]

    fingerprint = {
        "algorithm": "KAN27-guidance-v6", "month": str(data.month.id), "as_of": data.as_of.isoformat(), "as_of_closed": data.closed,
        "allocations": sorted((str(a.id), a.allocated_amount) for a in data.allocations),
        "tasks": sorted((str(t.id), t.task_status, t.original_limit, t.current_limit,
                         t.assigned_date.isoformat(), t.period_end.isoformat()) for t in data.tasks),
        "records": sorted((str(r.id), r.amount, str(r.category_id), r.priority, r.expense_date.isoformat()) for r in data.records),
        "findings": findings, "suggestions": suggestions, "completeness": completeness,
    }
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    baseline_guidance = (
        [item["message"] for item in suggestions]
        if not is_sufficient else []
    )
    return dict(
        status="ANALYZED" if is_sufficient else "SKIPPED_INSUFFICIENT_DATA",
        month=data.month.month_start.strftime("%Y-%m"),
        budget_month_id=str(data.month.id),
        as_of=data.as_of.isoformat(),
        adjustments_enabled=False,
        completeness=completeness,
        recommendation_level="PERSONALIZED" if is_sufficient and findings else "BASELINE" if not is_sufficient else "NO_ADJUSTMENT",
        suggestions=suggestions,
        has_suggestions=bool(suggestions),
        baseline_guidance=baseline_guidance,
        review=_review(data, completeness),
        findings=findings,
        analysis_key=key,
        recommendations=[],
    )


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
        findings = result["findings"]
        if not findings:
            result["status"] = "NO_ACTION_REQUIRED"
            return result
        existing = {item.proposed_changes.get("signal_key"): item for item in _saved(month.id, result["analysis_key"])}
        saved = []
        for finding in findings:
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
                reason=recommendation.reason, expected_impact=recommendation.expected_impact or READ_ONLY_IMPACT,
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
            proposal = item.proposed_changes
            if not isinstance(proposal, dict) or proposal.get("mode") != "READ_ONLY" or proposal.get("changes") != []:
                raise RecommendationServiceError(
                    "This legacy proposal is read-only and cannot be accepted. Refresh recommendations from current data.", 409
                )
        if item.status not in {"PENDING", "REJECTED"}:
            raise RecommendationServiceError("This recommendation has already been decided", 409)
        item.status = "ACCEPTED" if decision.upper() == "ACCEPT" else "REJECTED"
    return {"status": item.status, "recommendation_id": str(item.id),
            "adjustments_enabled": False, "financial_adjustment_applied": False}


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
