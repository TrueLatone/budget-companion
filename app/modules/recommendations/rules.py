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


def propose_category_adjustment(
    actual_amount, planned_amount, priority, current_allocation, minimum_amount=0,
    available_savings=0,
):
    """Build a review-only allocation proposal from a confirmed variance.

    Overspend is funded only from the plan's current savings. Underspend is
    returned to savings, while P1 allocations stay at or above their minimum.
    P0 is never adjusted.
    """
    direction = choose_category_adjustment(actual_amount, planned_amount, priority)
    if direction is None or priority == "P0":
        return None

    if direction == "REVIEW_OVER_BUDGET":
        change = min(actual_amount - planned_amount, max(0, available_savings))
        source = "PLANNED_SAVINGS"
    else:
        reducible = max(0, current_allocation - (minimum_amount if priority == "P1" else 0))
        change = -min(planned_amount - actual_amount, reducible)
        source = "UNSPENT_CATEGORY_ALLOCATION"

    if change == 0:
        return {
            "direction": direction,
            "current_monthly_amount": current_allocation,
            "suggested_monthly_amount": current_allocation,
            "change_amount": 0,
            "funding_source": source,
            "constraint_applied": "P1_MINIMUM" if priority == "P1" else "NO_AVAILABLE_SAVINGS",
        }
    return {
        "direction": direction,
        "current_monthly_amount": current_allocation,
        "suggested_monthly_amount": current_allocation + change,
        "change_amount": change,
        "funding_source": source,
        "constraint_applied": None,
    }


def _guidance_item(code, title, message, *, kind="BASELINE_GUIDANCE", basis=None):
    return {
        "code": code,
        "kind": kind,
        "title": title,
        "message": message,
        "basis": basis or "General guidance based on the currently available confirmed data.",
        "personalized": False,
    }


def build_baseline_guidance(
    *,
    has_confirmed_plan,
    has_draft_plan=False,
    schedule_code,
    schedule_message,
    available_vnd,
    tracking_started=True,
    tracking_start_date=None,
    complete_transaction_count,
    category_count,
    coverage_days,
    completeness_rate,
    unrecorded_task_count,
    inconsistent_task_count,
    incomplete_transaction_count,
    minimum_transactions=MIN_COMPLETE_TRANSACTIONS,
    minimum_categories=MIN_CATEGORIES,
    minimum_coverage_days=MIN_COVERAGE_DAYS,
    minimum_completeness_rate=MIN_COMPLETENESS_RATE,
):
    """Return actionable, non-personalized guidance with limited history.

    These items are display guidance, not persisted financial adjustment
    proposals. They never infer that missing transactions mean zero spending.
    """
    suggestions = []

    if not tracking_started and tracking_start_date:
        suggestions.append(_guidance_item(
            "WAIT_FOR_TRACKING_START",
            "Chưa đến ngày bắt đầu theo dõi",
            f"Tháng này bắt đầu theo dõi từ ngày {tracking_start_date}. Bạn chỉ cần ghi lại các khoản chi thực tế kể từ ngày đó.",
            basis="Ngày phân tích đang trước ngày bắt đầu theo dõi của tháng.",
        ))

    # F18 baseline: keep a useful amount-based tip visible until the data is
    # sufficient for personalized analysis, whether or not a plan was drafted.
    if type(available_vnd) is int and available_vnd > 0:
        needs = available_vnd * 50 // 100
        wants = available_vnd * 30 // 100
        savings = available_vnd - needs - wants
        needs_text, wants_text, savings_text = (
            f"{amount:,}".replace(",", ".") for amount in (needs, wants, savings)
        )
        suggestions.append(_guidance_item(
            "BASELINE_AMOUNT_SPLIT",
            "Gợi ý sơ bộ cho số tiền tháng",
            f"Bạn có thể tham khảo mốc 50/30/20: {needs_text} đồng cho nhu cầu thiết yếu, "
            f"{wants_text} đồng cho chi tiêu linh hoạt và {savings_text} đồng để dành. "
            "Nếu tiền trọ, học phí hoặc hóa đơn bắt buộc cao hơn, hãy ưu tiên các khoản đó "
            "và điều chỉnh phần linh hoạt/để dành theo thực tế.",
            basis="Đây là quy tắc tham khảo chung, không phải phân tích cá nhân hóa hay yêu cầu phân bổ cố định.",
        ))

    if not has_confirmed_plan:
        available_text = f"{available_vnd:,}".replace(",", ".") if type(available_vnd) is int and available_vnd >= 0 else None
        if has_draft_plan:
            suggestions.append(_guidance_item(
                "CONFIRM_DRAFT_PLAN",
                "Xem lại và xác nhận kế hoạch chi tiêu",
                f"Bạn đã lập phương án phân bổ dự thảo cho ngân sách {available_text + ' đồng' if available_text else 'tháng này'}. Hãy kiểm tra các khoản bắt buộc như tiền trọ, học phí, điện nước; điều chỉnh theo chi phí thực tế của bạn rồi xác nhận để hệ thống có thể so sánh chi tiêu.",
                basis="Phương án dự thảo chưa được xác nhận nên chưa thể dùng để so sánh chi tiêu.",
            ))
        else:
            suggestions.append(_guidance_item(
                "CREATE_CONFIRMED_PLAN",
                "Bắt đầu phân bổ ngân sách tháng",
                (f"Bạn có {available_text} đồng cho tháng này, nhưng số tiền đó chưa được chia theo từng khoản chi. " if available_text else "Tổng ngân sách tháng chưa được chia theo từng khoản chi. ")
                + "Hãy nhập các khoản bắt buộc bạn thực sự có (như tiền trọ, học phí, điện nước), rồi chia phần còn lại cho ăn uống, đi lại và khoản dự phòng. Không cần thêm khoản không phù hợp với hoàn cảnh của bạn; sau đó lập và xác nhận kế hoạch.",
                basis="Tháng này chưa có kế hoạch chi tiêu được xác nhận để làm căn cứ so sánh.",
            ))

    elif schedule_code != "READY":
        schedule_guidance = {
            "NO_ALLOCATIONS": "Kế hoạch tháng chưa có khoản ngân sách nào để theo dõi. Hãy kiểm tra lại kế hoạch.",
            "NOT_SCHEDULED": "Ngân sách đã xác nhận nhưng chưa có lịch theo dõi chi tiêu. Hãy tạo lịch để bắt đầu.",
            "CONFLICT": "Lịch chi tiêu chưa khớp với kế hoạch đã xác nhận. Hãy kiểm tra lại ngân sách và lịch.",
            "INCOMPLETE": "Lịch theo dõi còn thiếu một số kỳ. Hãy cập nhật lịch để việc ghi nhận được đầy đủ.",
        }
        suggestions.append(_guidance_item(
            "COMPLETE_EXPENSE_SCHEDULE",
            "Hoàn tất lịch theo dõi chi tiêu",
            schedule_guidance.get(schedule_code, "Hãy kiểm tra lịch chi tiêu từ ngân sách đã xác nhận để bắt đầu theo dõi."),
            basis="Lịch theo dõi chi tiêu chưa sẵn sàng.",
        ))

    if unrecorded_task_count:
        suggestions.append(_guidance_item(
            "RESOLVE_UNRECORDED_TASKS",
            "Bổ sung các khoản chi còn thiếu",
            f"Bạn còn {unrecorded_task_count} kỳ chi tiêu đã qua chưa được xác nhận. Hãy ghi lại khoản đã chi hoặc xác nhận không phát sinh nếu chắc chắn trong cả kỳ không có khoản chi nào.",
            basis="Kỳ chưa xác nhận không được xem là kỳ không phát sinh chi tiêu.",
        ))

    if inconsistent_task_count:
        suggestions.append(_guidance_item(
            "RESOLVE_INCONSISTENT_CHECKINS",
            "Kiểm tra dữ liệu chi tiêu chưa khớp",
            f"Có {inconsistent_task_count} kỳ chi tiêu có thông tin ghi nhận chưa khớp. Hãy kiểm tra lại trước khi xem các so sánh.",
            basis="Dữ liệu chưa khớp chưa thể dùng làm căn cứ so sánh.",
        ))

    if incomplete_transaction_count:
        suggestions.append(_guidance_item(
            "COMPLETE_TRANSACTION_DETAILS",
            "Bổ sung thông tin khoản chi",
            f"Có {incomplete_transaction_count} khoản chi còn thiếu thông tin. Hãy kiểm tra số tiền, ngày chi, danh mục và loại chi tiêu.",
            basis="Khoản chi thiếu thông tin chưa thể dùng để so sánh chính xác.",
        ))

    history_gaps = []
    if has_confirmed_plan and complete_transaction_count < minimum_transactions:
        history_gaps.append(f"{complete_transaction_count}/{minimum_transactions} khoản chi hợp lệ")
    if has_confirmed_plan and category_count < minimum_categories:
        history_gaps.append(f"{category_count}/{minimum_categories} danh mục có chi tiêu")
    if has_confirmed_plan and coverage_days < minimum_coverage_days:
        history_gaps.append(f"{coverage_days}/{minimum_coverage_days} ngày dữ liệu chi tiêu")
    if has_confirmed_plan and completeness_rate < minimum_completeness_rate:
        history_gaps.append(f"độ đầy đủ dữ liệu {completeness_rate * 100:.0f}%/{minimum_completeness_rate * 100:.0f}%")

    if history_gaps:
        suggestions.append(_guidance_item(
            "BUILD_CONFIRMED_SPENDING_HISTORY",
            "Ghi thêm chi tiêu để nhận gợi ý sát hơn",
            "Hãy ghi các khoản chi thực tế trong Lịch chi tiêu và xác nhận những kỳ đã kết thúc. "
            "Để có phân tích cá nhân hóa đầy đủ hơn, hiện cần thêm: "
            + ", ".join(dict.fromkeys(history_gaps)) + ".",
            basis="Gợi ý sớm theo từng kỳ vẫn có thể xuất hiện trước khi đạt đủ các điều kiện này.",
        ))

    if not suggestions:
        suggestions.append(_guidance_item(
            "CONTINUE_TRACKING",
            "Tiếp tục theo dõi chi tiêu",
            "Ghi lại các khoản chi thực tế và xác nhận những kỳ chi tiêu đã qua. Khi có thêm dữ liệu, hãy xem lại để nhận gợi ý phù hợp hơn.",
            basis="Tháng này chưa có đủ dữ liệu để đưa ra gợi ý cụ thể hơn.",
        ))

    return suggestions[:4]


def build_no_adjustment_guidance():
    """Explain a safe no-change outcome when data is sufficient but no rule fires."""
    return _guidance_item(
        "KEEP_CURRENT_PLAN",
        "Tiếp tục theo dõi theo kế hoạch hiện tại",
        "Dữ liệu hiện tại chưa cho thấy nhóm chi tiêu nào cần lưu ý đặc biệt. Hãy tiếp tục ghi nhận chi tiêu và xem lại sau các kỳ tiếp theo.",
        kind="NO_ADJUSTMENT",
        basis="Các khoản chi đã ghi nhận chưa cho thấy điểm cần điều chỉnh rõ ràng.",
    )
