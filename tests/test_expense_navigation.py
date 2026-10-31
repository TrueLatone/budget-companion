from datetime import date
import re

from app.extensions import db
from app.models import (
    AssignedExpenseTask,
    BudgetAllocation,
    BudgetExpense,
    BudgetMonth,
    BudgetPlan,
    ExpenseCategory,
    User,
)
from app.modules.expenses import services

USER = services.DEMO_USER_ID


def _seed_canonical_task(
    user_id: str,
    assigned_date: date,
    amount: int = 50000,
    title: str = "Hằng ngày",
    schedule_tag: str = "DAILY",
    payment_due_date: date | None = None,
    period_end: date | None = None,
    task_status: str = "PENDING",
) -> AssignedExpenseTask:
    user_uuid = services.to_uuid(user_id)
    user = db.session.get(User, user_uuid)
    if not user:
        user = User(
            id=user_uuid,
            email=f"{user_id}@example.com",
            password_hash="fake-hash",
        )
        db.session.add(user)
        db.session.flush()

    month_start = date(assigned_date.year, assigned_date.month, 1)
    month = BudgetMonth.query.filter_by(
        user_id=user_uuid, month_start=month_start
    ).first()
    if not month:
        month = BudgetMonth(
            user_id=user_uuid,
            month_start=month_start,
            tracking_start_date=month_start,
            available_vnd=50000000,
        )
        db.session.add(month)
        db.session.flush()

    category = ExpenseCategory.query.filter_by(
        user_id=user_uuid, category_name="Chi tiêu chung"
    ).first()
    if not category:
        category = ExpenseCategory(user_id=user_uuid, category_name="Chi tiêu chung")
        db.session.add(category)
        db.session.flush()

    alloc_freq = "DAILY"
    is_recurring = True
    due_day = None
    if schedule_tag == "DAILY":
        alloc_freq = "DAILY"
    elif schedule_tag == "WEEKLY":
        alloc_freq = "WEEKLY"
    elif schedule_tag == "MONTHLY":
        alloc_freq = "MONTHLY"
    elif schedule_tag == "DAY_OF_MONTH":
        alloc_freq = "MONTHLY"
        due_day = 15
    elif schedule_tag == "DATE":
        alloc_freq = "MONTHLY"
        is_recurring = False

    expense = BudgetExpense.query.filter_by(
        budget_month_id=month.id, expense_name=title
    ).first()
    if not expense:
        expense = BudgetExpense(
            budget_month=month,
            category=category,
            expense_name=title,
            priority="P1",
            allocation_frequency=alloc_freq,
            is_recurring=is_recurring,
            due_day=due_day,
        )
        db.session.add(expense)
        db.session.flush()

    plan = BudgetPlan.query.filter_by(
        budget_month_id=month.id, status="CONFIRMED"
    ).first()
    if not plan:
        plan = BudgetPlan(
            budget_month=month, plan_type="BALANCED", status="CONFIRMED"
        )
        db.session.add(plan)
        db.session.flush()

    allocation = BudgetAllocation.query.filter_by(
        plan_id=plan.id, budget_expense_id=expense.id
    ).first()
    if not allocation:
        allocation = BudgetAllocation(
            plan=plan, budget_expense=expense, allocated_amount=amount
        )
        db.session.add(allocation)
        db.session.flush()

    task = AssignedExpenseTask(
        allocation=allocation,
        assigned_date=assigned_date,
        period_end=period_end or assigned_date,
        original_limit=amount,
        current_limit=amount,
        task_status=task_status,
        payment_due_date=payment_due_date,
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_year_period_and_navigation_boundaries(app):
    period = services.resolve_period("year", "2026-10-21")
    assert period.start == date(2026, 1, 1)
    assert period.end == date(2026, 12, 31)
    assert period.label == "Năm 2026"

    navigation = services.build_navigation(period)
    assert navigation["prev"].year == 2025
    assert navigation["next"].year == 2027
    assert navigation["prev_month"] == date(2026, 9, 21)

    month = services.resolve_period("month", "2026-01-31")
    navigation = services.build_navigation(month)
    assert navigation["next"] == date(2026, 2, 28)
    assert navigation["prev"] == date(2025, 12, 31)


def test_week_navigation_moves_by_seven_days():
    period = services.resolve_period("week", "2026-10-07")
    assert period.start == date(2026, 10, 5)
    assert period.end == date(2026, 10, 11)

    navigation = services.build_navigation(period)
    assert navigation["prev"] == date(2026, 9, 30)
    assert navigation["next"] == date(2026, 10, 14)

    previous_week = services.resolve_period(
        "week", navigation["prev"].isoformat()
    )
    next_week = services.resolve_period("week", navigation["next"].isoformat())
    assert (previous_week.start, previous_week.end) == (
        date(2026, 9, 28),
        date(2026, 10, 4),
    )
    assert (next_week.start, next_week.end) == (
        date(2026, 10, 12),
        date(2026, 10, 18),
    )


def test_calendar_uses_real_days_and_marks_selected_day(app):
    leap_calendar = services.build_month_calendar([], [], 2028, 2)
    days = [cell.day for week in leap_calendar for cell in week if cell]
    assert len(days) == 29
    assert days[0] == date(2028, 2, 1)
    assert days[-1] == date(2028, 2, 29)
    assert all(len(week) == 7 for week in leap_calendar)

    _seed_canonical_task(USER, date(2026, 10, 5), amount=50000, title="Hằng ngày", schedule_tag="DAILY")
    summary = services.build_summary(
        USER, services.resolve_period("month", "2026-10-05")
    )
    calendar = services.build_month_calendar(
        summary["tasks"], summary["records"], 2026, 10
    )
    selected = [cell for week in calendar for cell in week if cell and cell.day.day == 5]
    assert selected[0].task_count == 1
    assert selected[0].plan_total == 50000


def test_day_items_include_due_task_once_and_assigned_task(app):
    _seed_canonical_task(
        USER,
        date(2026, 10, 5),
        amount=50000,
        title="Hằng ngày",
        schedule_tag="DAILY",
        payment_due_date=date(2026, 10, 5),
    )
    _seed_canonical_task(
        USER,
        date(2026, 10, 7),
        amount=70000,
        title="Đến hạn riêng",
        schedule_tag="DATE",
        payment_due_date=date(2026, 10, 5),
    )

    summary = services.build_summary(USER, services.resolve_period("day", "2026-10-05"))
    items = services.build_day_items(summary, date(2026, 10, 5))

    assert len(items) == 2
    assert len({entry.task.task_id for entry in items}) == 2
    by_title = {entry.task.plan_item.title: entry for entry in items}
    assert by_title["Hằng ngày"].assigned_in_period is True
    assert by_title["Hằng ngày"].due_in_period is True
    assert by_title["Đến hạn riêng"].assigned_in_period is False
    assert by_title["Đến hạn riêng"].due_in_period is True

    totals = services.summarize_day_items(items)
    assert totals.assigned_count == 1
    assert totals.due_only_count == 1
    assert totals.assigned_plan_total == 50000
    assert totals.due_only_plan_total == 70000
    assert totals.assigned_plan_total == summary["plan_total"]


def test_monthly_task_is_only_on_last_day_but_stays_in_month_overview(app):
    _seed_canonical_task(
        USER, date(2026, 10, 31), amount=4500000, title="Tiền nhà", schedule_tag="MONTHLY"
    )

    before = services.build_summary(
        USER, services.resolve_period("day", "2026-10-30")
    )
    last_day = services.build_summary(
        USER, services.resolve_period("day", "2026-10-31")
    )
    month = services.build_summary(
        USER, services.resolve_period("month", "2026-10-15")
    )

    assert services.build_day_items(before, date(2026, 10, 30)) == []
    last_items = services.build_day_items(last_day, date(2026, 10, 31))
    assert [entry.task.plan_item.title for entry in last_items] == ["Tiền nhà"]
    assert "Tiền nhà" in {
        entry.task.plan_item.title for entry in services.build_month_items(month)
    }


def test_month_items_skip_daily_tasks_but_include_monthly_date_and_due_only(app):
    _seed_canonical_task(USER, date(2026, 10, 5), amount=50000, title="Hằng ngày", schedule_tag="DAILY")
    _seed_canonical_task(USER, date(2026, 10, 31), amount=300000, title="Cuối tháng", schedule_tag="MONTHLY")
    _seed_canonical_task(USER, date(2026, 10, 20), amount=100000, title="Ngày cụ thể", schedule_tag="DATE")
    _seed_canonical_task(
        USER,
        date(2026, 9, 10),
        amount=80000,
        title="Đến hạn từ tháng khác",
        schedule_tag="DATE",
        payment_due_date=date(2026, 10, 15),
    )

    summary = services.build_summary(
        USER, services.resolve_period("month", "2026-10-15")
    )
    items = services.build_month_items(summary)
    titles = {entry.task.plan_item.title for entry in items}

    assert "Hằng ngày" not in titles
    assert "Cuối tháng" in titles
    assert "Ngày cụ thể" in titles
    assert "Đến hạn từ tháng khác" in titles
    assert sum(1 for entry in items if not entry.assigned_in_period) == 1


def test_year_schedule_filter_matches_all_five_tags(app):
    _seed_canonical_task(USER, date(2026, 6, 1), 1000, "Hằng ngày", "DAILY")
    _seed_canonical_task(USER, date(2026, 6, 8), 2000, "Hằng tuần", "WEEKLY")
    _seed_canonical_task(USER, date(2026, 6, 30), 3000, "Cuối tháng", "MONTHLY")
    _seed_canonical_task(USER, date(2026, 6, 15), 4000, "Ngày cố định", "DAY_OF_MONTH")
    _seed_canonical_task(USER, date(2026, 6, 15), 5000, "Một ngày", "DATE")

    period = services.resolve_period("year", "2026-06-15")
    all_tasks = services.list_tasks(USER, period.start, period.end)

    for tag in ("DAILY", "WEEKLY", "MONTHLY", "DAY_OF_MONTH", "DATE"):
        summary = services.build_summary(USER, period, schedule_tag=tag)
        assert {task.plan_item.schedule_tag for task in summary["tasks"]} == {tag}
        assert summary["plan_total"] == sum(
            task.planned_amount
            for task in all_tasks
            if task.plan_item.schedule_tag == tag
        )


def test_year_filter_groups_date_task_in_its_month_without_losing_other_tasks(app):
    _seed_canonical_task(USER, date(2026, 10, 5), 50000, "Hằng ngày", "DAILY")
    _seed_canonical_task(USER, date(2026, 10, 31), 300000, "Cuối tháng", "MONTHLY")
    _seed_canonical_task(USER, date(2026, 12, 20), 100000, "Ngày cụ thể", "DATE")

    period = services.resolve_period("year", "2026-10-15")
    all_summary = services.build_summary(USER, period)
    all_cards = services.build_year_months(all_summary, 2026)
    december = next(card for card in all_cards if card.month == 12)
    assert "Ngày cụ thể" in {task.plan_item.title for task in december.highlights}

    date_summary = services.build_summary(
        USER, period, schedule_tag="DATE"
    )
    date_cards = services.build_year_months(
        date_summary, 2026, schedule_tag="DATE"
    )
    non_empty = [card for card in date_cards if card.task_count]
    assert len(non_empty) == 1
    assert non_empty[0].month == 12
    assert [task.plan_item.title for task in non_empty[0].highlights] == [
        "Ngày cụ thể"
    ]
    assert date_summary["plan_total"] == 100000


def test_month_and_year_pickers_keep_the_current_day_and_clamp(client):
    month_body = client.get(
        "/expenses?view=month&month=2026-02&date=2026-01-31"
    ).data.decode("utf-8")
    assert 'value="2026-02-28"' in month_body

    year_body = client.get(
        "/expenses?view=year&year=2027&date=2024-02-29"
    ).data.decode("utf-8")
    assert 'value="2027-02-28"' in year_body


def test_day_view_keeps_actual_for_due_only_task_assigned_elsewhere(client, app):
    task = _seed_canonical_task(
        USER,
        date(2026, 9, 10),
        amount=70000,
        title="Đến hạn khác tháng",
        schedule_tag="DATE",
        payment_due_date=date(2026, 10, 5),
    )
    services.checkin_task(
        USER,
        task.id,
        action="actual",
        amount_raw="80000",
        expense_date_raw="2026-10-05",
    )

    response = client.get("/expenses?view=day&date=2026-10-05")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    row = re.search(r"Chỉ đến hạn, phân bổ.*?</tr>", body, re.S)
    assert row is not None
    assert "80.000" in row.group(0)
    assert 'data-bs-target="#editRecord' in row.group(0)
    assert "Ngoài tổng: 70.000" in body
    assert "0 task phân bổ trong ngày · 1 task chỉ đến hạn" in body


def test_year_view_avoids_record_modal_list_but_day_view_keeps_edit(client, app):
    task = _seed_canonical_task(
        USER,
        date(2026, 10, 5),
        amount=50000,
        title="Hằng ngày",
        schedule_tag="DAILY",
    )
    services.checkin_task(
        USER,
        task.id,
        action="actual",
        amount_raw="60000",
        expense_date_raw="2026-10-05",
    )

    year_body = client.get("/expenses?view=year&year=2026").data.decode("utf-8")
    assert 'id="editRecord' not in year_body
    assert "Năm 2026 có" in year_body

    day_body = client.get("/expenses?view=day&date=2026-10-05").data.decode("utf-8")
    assert 'id="editRecord' in day_body


def test_expense_views_render_navigation_and_filter(client):
    default = client.get("/expenses")
    assert default.status_code == 200
    default_body = default.data.decode("utf-8")
    assert "Lịch tháng" in default_body
    assert "Các tháng trong năm" not in default_body

    day = client.get("/expenses?view=day&date=2026-10-05")
    assert day.status_code == 200
    body = day.data.decode("utf-8")
    assert 'id="mobile-view"' in body
    assert "bc-mode-tabs" in body
    assert "Chế độ xem" in body
    assert "Lịch tháng 10 năm 2026" in body

    month = client.get("/expenses?view=month&date=2026-10-15")
    assert month.status_code == 200
    month_body = month.data.decode("utf-8")
    assert "Nghĩa vụ trong tháng" in month_body
    assert 'name="month"' in month_body

    month_picker = client.get("/expenses?view=month&month=2026-02")
    assert month_picker.status_code == 200
    assert 'value="2026-02"' in month_picker.data.decode("utf-8")

    year = client.get("/expenses?view=year&date=2026-10-15&tag=DATE")
    assert year.status_code == 200
    year_body = year.data.decode("utf-8")
    assert "Các tháng trong năm 2026" in year_body
    assert "Lọc lịch: Một ngày cụ thể" in year_body
    assert 'name="tag"' in year_body
    assert 'name="year"' in year_body

    year_picker = client.get("/expenses?view=year&year=2027")
    assert year_picker.status_code == 200
    assert "Các tháng trong năm 2027" in year_picker.data.decode("utf-8")
