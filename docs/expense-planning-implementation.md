# Expense Planning & Smart Check-in — Implementation Notes

**Module:** F07–F13 (Expense Planning & Smart Check-in)
**Repository:** `budget-companion/`
**Branch used during implementation:** `feature/expense-planning-checkin`
**Date:** 21/10/2026
**Status:** Core F07–F13 flows implemented; advanced budget adjustment is deliberately not implemented.

> This document describes the code that actually exists. Business requirements remain in
> [`doc.md`](../../doc.md); technical direction remains in [`doc-technical.md`](../../doc-technical.md).
> Do not treat this file as a second specification. Some “current repository” statements in
> `doc-technical.md` (for example “no migrations yet”) are snapshots from before this
> implementation; this file records the post-implementation state.

---

## 1. What was implemented

| Capability | Status | Where |
|---|---|---|
| Daily / weekly / monthly plan view (F07) | Day/month UI implemented; week remains a service-only period (no separate UI tab) | `app/modules/expenses/services.py`, `app/templates/pages/expenses.html` |
| Hierarchical Ngày → Tháng → Năm navigation | Implemented | `routes.index`, navigation/calendar helpers in `services.py`, `app/templates/pages/expenses.html`, `app/static/css/app.css` |
| Schedule generation for all five tags (F08) | Implemented | `services.generate_tasks`, `services.occurrence_dates` |
| Payment due date separate from assigned date (F08/F12) | Implemented per task | `services.set_payment_due_date`, POST `/expenses/tasks/<task_id>/due-date` |
| Three check-in actions (F09) | Implemented | `services.checkin_task`, POST `/expenses/tasks/<task_id>/checkin` |
| Actual / unexpected expense records (F10) | Implemented | `services.create_unexpected_record`, `services.update_record`, `services.delete_record` |
| Planned expense editing and unexpected expenses (F11) | Implemented | `services.update_plan_item`, `services.create_unexpected_record` |
| Spending history and difference (F13) | Implemented | GET `/expenses/history`, `app/templates/pages/expense_history.html` |
| Demo input area | Implemented and labelled | `DemoExpenseSource`, `POST /expenses/sources` |
| Real Budget/M1 source | Not implemented; adapter placeholder only | `M1BudgetSource` raises `NotImplementedError` |
| Advanced BudgetAdjustment / allocation | Not implemented (optional in `doc.md`) | — |
| Authentication / authorization | Not implemented (pre-existing repository state) | `resolve_current_user_id()` returns `"demo-user"` |
| CSRF protection | Not implemented (pre-existing repository state) | No form token |
| Background overdue job | Not implemented; refresh happens on page access | `services.refresh_unrecorded` |

The existing stack is used unchanged: Flask application factory, Jinja2, Bootstrap 5.3.3 CDN, vanilla JavaScript, Flask-SQLAlchemy, Flask-Migrate, SQLite/PostgreSQL, pytest.

---

## 2. Files added or changed

### Added

| File | Purpose |
|---|---|
| `app/models/expense_planning.py` | SQLAlchemy models for plan items, tasks, actual records |
| `app/modules/expenses/idgen.py` | `ddmmyyyy-uniqueid` generator and validation |
| `app/modules/expenses/sources.py` | Demo source adapter and M1 placeholder |
| `app/modules/expenses/validators.py` | Server-side amount/date/schedule validation |
| `app/templates/pages/expenses.html` | Main module page (plan, check-in, demo data, unexpected expenses, history) |
| `app/templates/pages/expense_history.html` | Filterable history page with plan/actual/difference summary |
| `migrations/` | Flask-Migrate initialised for this repository |
| `migrations/versions/b5187cd44b85_create_expense_planning_tables.py` | First module schema migration |
| `migrations/versions/dfa92b9022a2_add_unexpected_idempotency_key.py` | Adds `expense_records.idempotency_key` and its partial unique index |
| `tests/test_expense_scheduling.py` | Schedule, ID and plan-edit tests |
| `tests/test_expense_checkin.py` | Check-in, deadline, record-update, plan-history preservation tests |
| `tests/test_expense_summary.py` | Day/week/month summary and demo-isolation tests |
| `tests/test_expense_navigation.py` | Year/month/day/week navigation, calendar, due-task totals and year-filter tests |
| `tests/test_expense_unexpected.py` | UNEXPECTED create idempotency and same-amount/date distinct-record tests |
| `tests/test_expense_routes.py` | HTTP flow, validation, clear-demo tests |

### Changed

| File | Change |
|---|---|
| `app/models/__init__.py` | Imports the three new models so Flask-Migrate sees them |
| `app/modules/expenses/routes.py` | Replaced the placeholder with the module routes |
| `app/modules/expenses/services.py` | Implemented scheduling, check-in, records, summaries, and navigation/calendar helpers |
| `app/static/css/app.css` | Added compact month calendar, day-cell, mode-tab and responsive task-card styles |
| `app/templates/pages/expenses.html` | Refactored to hierarchical Ngày/Tháng/Năm navigation and responsive day cards |
| `app/templates/base.html` | Added Bootstrap flash alerts and a `scripts` block |
| `tests/conftest.py` | Creates/drops tables inside the in-memory test database |
| `README.md` | Documents migration, secret-key setup, and the implemented `/expenses` route |

No other module, template, configuration, manifest, or dependency file was changed.

---

## 3. Data model

### 3.1 Tables

All money is integer VND (`BigInteger`). All module-owned IDs are `String(21)` and use the
ID convention in section 8.

#### `expense_plan_items`

| Column | Type | Notes |
|---|---|---|
| `plan_item_id` | String(21), PK | Generated once by `new_id()` |
| `source_expense_id` | String(128), nullable | External M1/Budget ID stored verbatim |
| `user_id` | String(64), indexed | Owner filter |
| `title` | String(200) | Expense name |
| `amount_source` | String(20) | `BUDGET_DEFAULT` or `USER_ENTERED` |
| `planned_amount` | BigInteger | Must be > 0 |
| `priority` | String(2) | `P0`, `P1`, `P2` |
| `schedule_tag` | String(20) | `DAILY`, `WEEKLY`, `MONTHLY`, `DAY_OF_MONTH`, `DATE` |
| `day_of_week` | SmallInteger, nullable | ISO 1–7, only for `WEEKLY` |
| `day_of_month` | SmallInteger, nullable | 1–31, only for `DAY_OF_MONTH` |
| `specific_date` | Date, nullable | Only for `DATE` |
| `is_active` | Boolean | Inactive items are not scheduled |
| `is_demo` | Boolean | Demo isolation flag |
| `created_at`, `updated_at` | DateTime | UTC, naive |

Partial unique index: `(user_id, source_expense_id)` where `source_expense_id IS NOT NULL`.

#### `assigned_expense_tasks`

| Column | Type | Notes |
|---|---|---|
| `task_id` | String(21), PK | Generated once |
| `plan_item_id` | String(21), FK | References `expense_plan_items.plan_item_id` |
| `user_id` | String(64) | Owner filter |
| `assigned_date` | Date | Plan grouping date |
| `planned_amount` | BigInteger | Snapshot of plan amount |
| `priority` | String(2) | Snapshot |
| `checkin_deadline_at` | DateTime | 23:59:59 Vietnam time converted to UTC |
| `payment_due_date` | Date, nullable | Independent from assigned date |
| `task_status` | String(20) | Five statuses below |
| `checked_at` | DateTime, nullable | Last confirmation time |
| `is_demo` | Boolean | Inherited from plan item |
| `created_at`, `updated_at` | DateTime | UTC, naive |

Unique constraint: `(plan_item_id, assigned_date)` (prevents duplicate tasks).
Index: `(user_id, assigned_date)`.

#### `expense_records`

| Column | Type | Notes |
|---|---|---|
| `record_id` | String(21), PK | Generated once |
| `user_id` | String(64) | Owner filter |
| `task_id` | String(21), FK, nullable | `NULL` for unexpected expenses |
| `record_type` | String(20) | `PLANNED` or `UNEXPECTED` |
| `amount` | BigInteger | Actual amount, > 0 |
| `expense_date` | Date | Actual date, independent from `created_at` |
| `actual_amount_source` | String(20), nullable | `PLANNED` or `USER_ENTERED` |
| `title` | String(200), nullable | Required for unexpected expenses |
| `category` | String(80), nullable | Temporary free-text category |
| `note` | Text, nullable | Optional |
| `idempotency_key` | String(64), nullable | Client form token for UNEXPECTED create; null for other records |
| `is_demo` | Boolean | Inherited or true for demo UI |
| `created_at`, `updated_at` | DateTime | UTC, naive |

Index: `(user_id, expense_date)`.
Partial unique index: `task_id` where
`task_id IS NOT NULL AND record_type = 'PLANNED'` — at most one planned record per task.
Partial unique index: `(user_id, idempotency_key)` where `idempotency_key IS NOT NULL` — a
client request token is accepted once per user. The token is not derived from amount or date, so
two legitimate same-day expenses with equal amounts remain distinct records.

### 3.2 Status mapping

The module stores five statuses required by `doc.md`:

`PENDING`, `UNRECORDED`, `NO_EXPENSE`, `WITHIN_BUDGET`, `OVER_BUDGET`.

Mapping to the older DRAFT statuses in `docs/database-design.md`:

| DRAFT | Implemented meaning |
|---|---|
| `UNKNOWN` | `PENDING` before deadline, `UNRECORDED` after deadline |
| `NO_EXPENSE` | `NO_EXPENSE` |
| `RECORDED` | `WITHIN_BUDGET` or `OVER_BUDGET` (record exists) |

No DRAFT table is modified or created by this module.

### 3.3 Migrations

Two migrations make up the current head:

1. `migrations/versions/b5187cd44b85_create_expense_planning_tables.py` creates the three tables,
   foreign keys, unique constraint, indexes, and the planned-record partial unique index.
2. `migrations/versions/dfa92b9022a2_add_unexpected_idempotency_key.py` adds
   `expense_records.idempotency_key` and the `(user_id, idempotency_key)` partial unique index.
   Its `down_revision` is `b5187cd44b85`, so the current Alembic head is `dfa92b9022a2`.

Both revisions were tested on a throwaway SQLite database with `flask --app app db upgrade`,
`db downgrade`, and `db upgrade` again. The generated partial indexes were verified in
`sqlite_master`, including:

```sql
CREATE UNIQUE INDEX uq_expense_records_idempotency
ON expense_records (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL
```

PostgreSQL/Supabase was **not** available in this environment, so the migrations have not been
applied to the shared PostgreSQL database. Run `flask --app app db upgrade` against the configured
database before using the updated code.

`docs/database-design.md` is still a DRAFT and no table existed before the first migration. The
`expense_records` name is reused for the module’s actual source-of-truth table with extra fields;
it is not a second parallel table. No DRAFT document was edited.

No `db.create_all()` is used for the real database. It is used only by the test fixture.

---

## 4. Schedule generation (F08/F12)

### Entry points

- `POST /expenses/plan/generate` → `routes.generate_plan` → `services.generate_tasks`
- `services.occurrence_dates` contains the pure date rules.

### `services.occurrence_dates(schedule_tag, start, end, ...)`

Returns every occurrence date in the inclusive range.

| Tag | Implementation |
|---|---|
| `DAILY` | One date per day from `start` to `end` |
| `WEEKLY` | `date.isoweekday() == day_of_week`; ISO 1 = Monday |
| `MONTHLY` | Last day of every month intersecting the range |
| `DAY_OF_MONTH` | Requested day, clamped to the last day when needed |
| `DATE` | `specific_date` only if it is inside the range |

`WEEKLY` uses ISO `isoweekday()`, not `weekday()`. Tests cover Monday dates in January 2026,
February 2026 (28 days), February 2028 (29 days), day 31 clamping, and a single `DATE`.

### `services.generate_tasks(user_id, period_start, period_end)`

1. Rejects `period_end < period_start`.
2. Gets plan items from `get_expense_source()`.
3. For the demo adapter, reads active `is_demo=True` items.
4. Materialises a module row for non-demo adapter items when an external ID is present.
5. Builds the set of existing `(plan_item_id, assigned_date)` pairs in the period.
6. Inserts only missing `AssignedExpenseTask` rows.
7. Commits once; `IntegrityError` is rolled back and converted to a user-facing validation error.

The database unique constraint is the final duplicate guard. Re-running the action returns
created count `0` and does not delete or recreate existing tasks, so check-ins and records survive.

### Plan-item edits and task snapshots

`services.update_plan_item(user_id, item_id, form)` updates the template first, then refreshes only
tasks that are still editable:

- `task_status == PENDING`;
- `checked_at IS NULL` and the task has no linked record;
- `assigned_date >= today_vn()` (today before its deadline, or a future date);
- `checkin_deadline_at >= now_utc()`.

All other tasks keep their generated `planned_amount` and `priority` snapshots. This includes
confirmed tasks (`NO_EXPENSE`, `WITHIN_BUDGET`, `OVER_BUDGET`), checked tasks, overdue
`UNRECORDED` tasks, and pending tasks whose deadline has already passed but which have not yet
been refreshed to `UNRECORDED`. Historical check-in results and records are therefore not rewritten
by editing a plan item. Deactivation only flips `is_active`; it leaves existing task snapshots and
history untouched.

The task snapshot is still distinct from the plan item: after a task leaves the editable window,
the plan item may show the new template amount while the task and its history keep the old one.

### Payment due date

`payment_due_date` is **not** copied from `assigned_date`. A task starts with no due date and shows
“Chưa thiết lập”. Each task can be updated independently through:

- `POST /expenses/tasks/<task_id>/due-date` → `services.set_payment_due_date`
- Empty input clears the date.

The period page also lists tasks whose `payment_due_date` falls in the selected period.

---

## 5. Check-in (F09)

### Entry point

`POST /expenses/tasks/<task_id>/checkin` → `routes.checkin` → `services.checkin_task`.

### Actions

| `action` value | Behaviour |
|---|---|
| `planned` | Uses `task.planned_amount`; creates/updates one `PLANNED` record |
| `actual` | Parses a positive integer VND amount; creates/updates the same record |
| `no_expense` | Sets `NO_EXPENSE`; creates no record and no zero amount |

### `services.checkin_task(...)`

1. Loads the task and verifies `task.user_id`.
2. Finds an existing `PLANNED` record for the task.
3. For `no_expense`, refuses if a record already exists (prevents silently deleting actual data).
4. For `planned`/`actual`, reuses the existing record instead of inserting a second one.
5. Defaults `expense_date` to `assigned_date` if the user leaves it blank.
6. Validates category length (80 characters).
7. Calculates `WITHIN_BUDGET` when `amount <= planned_amount`, otherwise `OVER_BUDGET`.
8. Sets `checked_at` and commits transactionally.

Repeated check-in requests update the same row. The partial unique index is a second guard.

### Deadline and `UNRECORDED`

`services.deadline_for(date)` builds 23:59:59 Asia/Ho_Chi_Minh (UTC+7) and converts it to naive
UTC for storage.

`services.refresh_unrecorded(user_id)` runs when the plan page or history page is loaded. It moves
only `PENDING` tasks whose deadline is in the past to `UNRECORDED`. It is idempotent and does not
turn them into `NO_EXPENSE` or zero spending. There is no background scheduler.

### Task-level vs day-level

Task status is stored and displayed per task. Summary totals are calculated separately from
`planned_amount` and record `amount`; one task can be `OVER_BUDGET` while the day total is within
plan. Pending tasks contribute no actual amount.

---

## 6. Actual and unexpected records (F10/F11/F13)

### `services.create_unexpected_record(user_id, form)`

- Validates title, amount, expense date, category, note.
- Reads the optional `idempotency_key` hidden field (maximum 64 characters).
- If the same user already has an `UNEXPECTED` record with that token, returns the existing record
  instead of inserting another one. This makes a retried POST safe even when the browser sends the
  same payload twice.
- The token is supplied by the server on each render of the unexpected-expense form; the form’s
  hidden input is `idempotency_key`. It is opaque and independent of amount/date.
- The partial unique index `(user_id, idempotency_key)` is the final concurrency guard. If two
  requests race, the loser catches `IntegrityError`, rolls back, and returns the winning row.
- Two legitimate expenses with the same title, amount and `expense_date` but different form tokens
  are both kept. There is no amount/date uniqueness rule.
- Creates `ExpenseRecord` with `record_type=UNEXPECTED`, `task_id=None`, `is_demo=True`.
- The title is stored on the record because no task exists.
- If `idempotency_key` is absent (for backward-compatible service callers), the record is created
  normally without retry protection; the UI always supplies the token.

### `services.update_record(user_id, record_id, form)`

- Updates amount, expense date, category, note.
- Updates title only for unexpected records.
- If linked to a task, recalculates task status against the current task planned amount.
- Updates `checked_at` and relies on SQLAlchemy `onupdate` for `updated_at`.

### `services.delete_record(user_id, record_id)`

- Deletes the record.
- If linked to a task, restores `PENDING` or `UNRECORDED` based on the deadline and clears
  `checked_at`.
- It does not delete a task or plan item.

### History

- `GET /expenses/history` → `routes.history`
- Date range is filtered by `expense_date`.
- Shows actual records, task check-in status, plan total, actual total and difference.
- The task section also lists no-expense and pending tasks, so status is visible even when a task
  has no transaction.
- Editing/deleting a record is available in day/month mode on `/expenses`, where the record
  table has edit modals and delete confirmation. Year mode links to that history instead of
  rendering a year-long record table and modal set.

---

## 7. Period summary (F07/F13)

### `services.resolve_period(view, date)`

- `day`: selected date.
- `week`: Monday–Sunday using `anchor - timedelta(days=anchor.weekday())`; retained for the
  existing service/tests, not exposed as a top-level UI mode after the navigation refactor.
  `build_navigation` moves a week anchor by exactly ±7 days, so the previous/next period is the
  adjacent Monday–Sunday week.
- `month`: first to last calendar day.
- `year`: 1 January–31 December of the anchor year.
- Invalid view falls back to month; invalid date raises `ValidationError`. The HTTP index defaults
  to `day` when no `view` is supplied.

### `services.build_summary(user_id, period, *, schedule_tag=None)`

| Output | Rule |
|---|---|
| `tasks` | Tasks with `assigned_date` in period |
| `records` | Records with `expense_date` in period |
| `plan_total` | Sum of task `planned_amount` |
| `actual_total` | Sum of record `amount` (planned + unexpected) |
| `difference` | `plan_total - actual_total` |
| `counts` | pending, unrecorded, no_expense, within, over |
| `confirmed` | no_expense + within + over |
| `unconfirmed` | pending + unrecorded |
| `planned_by_task` | Linked planned records for tasks in the period |
| `unexpected_records` | Unexpected records in the period |
| `due_tasks` | Tasks with `payment_due_date` in the period |

`created_at` is never used as the spending date. A pending task is never counted as zero actual
spending. The same record is not counted again through its task because plan and actual are
separate sums.

The optional `schedule_tag` filter is implemented in `list_tasks`, `list_due_tasks`,
`list_records`, and therefore in `build_summary`. Tasks are filtered by joining
`expense_plan_items.schedule_tag`; records are filtered through their linked task. Unexpected
records have no linked task and are excluded when a specific tag is selected. Plan and actual are
still summed separately, so adding a due-date list never duplicates an actual record.

### Navigation and calendar helpers

The year view and day/month drill-down use service-level date logic; the template and JavaScript
do not calculate a second calendar.

| Helper | Behaviour |
|---|---|
| `shift_month(anchor, delta)` | Moves by calendar month and clamps the day to the target month's last day (31 Jan → 28/29 Feb). |
| `shift_year(anchor, delta)` | Moves by year, clamping 29 Feb where needed. |
| `build_navigation(period)` | Returns `prev`, `next`, `prev_month`, `next_month`, `prev_year`, `next_year` anchors for the active view. Day moves ±1 day, week moves ±7 days, month uses `shift_month`, and year uses `shift_year`. |
| `build_month_calendar(tasks, records, year, month)` | Returns seven-column weeks containing real days only (28/29/30/31), with task, plan, actual, pending, unrecorded, and confirmed indicators per day. |
| `build_day_items(summary, selected_date)` | Returns tasks assigned on the selected day plus tasks due that day, de-duplicated by `task_id`. `TaskEntry.assigned_in_period` and `due_in_period` distinguish the two cases. |
| `summarize_day_items(items)` | Returns `DayTotals`: assigned/due-only task counts and separate planned totals. The assigned total equals `summary["plan_total"]`; the due-only total is shown as “Ngoài tổng” and is never added to the assigned total. |
| `build_month_items(summary)` | Lists non-`DAILY` obligations in the month (including `MONTHLY`, `WEEKLY`, `DAY_OF_MONTH`, and `DATE`) plus due-only tasks. `DAILY` occurrences are viewed by selecting a day instead of being dumped into the month list. |
| `build_year_months(summary, year, *, schedule_tag=None)` | Groups the filtered year summary into 12 `MonthCard` values with plan/actual/difference, task counts, daily counts, confirmation counts, and highlight tasks. `DAILY` filter results are represented by counts and a month link to avoid hundreds of rows. |
| `planned_records_for_tasks(task_ids)` | Loads linked planned records for visible tasks, including due-only tasks assigned outside the current period. |

Day and month pages build the month calendar from a separate month summary so the calendar can show
all days while the day table stays limited to the selected day.

### Assigned date versus payment due date

A task appears in a day list for either reason, but the two reasons are not interchangeable:

- **Assigned in the day**: `assigned_date` is the selected day; the task contributes to
  `summary["plan_total"]` and the “Tổng kế hoạch được phân bổ” card.
- **Due in the day**: `payment_due_date` is the selected day but `assigned_date` may be another
  date. It is shown so the user can act on the deadline, but its planned amount is **not** added to
  the assigned total because it already belongs to another period.
- If both are true, the task appears once (deduplicated by `task_id`) and is marked with both
  “Phân bổ trong ngày” and “Đến hạn trong ngày”.
- A due-only task is marked “Chỉ đến hạn, phân bổ dd/mm/yyyy”. Its plan amount is shown on its row
  and summarised separately as “Ngoài tổng: … task chỉ đến hạn”; it is not added to the KPI.
- Actual records are always counted by `expense_date`; a due-only task’s linked actual record is
  counted once even when its assigned date is outside the selected day. No task/record pair is
  double-counted.

Month mode follows the same rule: due-only tasks from another month can appear in the obligation
list but are not added to the month’s assigned plan total.

### Weekly view / F07 note

The HTTP UI intentionally exposes only `Ngày`, `Tháng`, `Năm`; `view=week` is not a UI mode and
unknown/legacy values fall back to `day`. No fourth tab was added. F07’s weekly planning intent is
covered by:

- `WEEKLY` plan items generating tasks on their ISO weekday, visible on the day calendar and in
  month summaries;
- the service-level `resolve_period("week")` and `build_summary` week aggregation, with correct
  ±7-day navigation, available to tests/future callers;
- day selection inside the real-month calendar, which lets a user inspect any seven consecutive
  days.

A dedicated weekly totals page is **not** implemented; if F07 is later interpreted as requiring a
separate week summary in the UI, that is an explicit enhancement rather than an accidental nav
item.

### Demo isolation

- `list_tasks`, `list_records`, `list_due_tasks`, `refresh_unrecorded` default to `demo_only=True`.
- Plan-item edit/deactivate/delete services also reject non-demo rows in the demo flow.
- Dashboard summaries therefore show only demo rows while the real source is unavailable.
- `clear_demo_data` deletes only records/tasks/items with `is_demo=True`.
- Official rows (`is_demo=False`) are not displayed, edited, or deleted by the current demo UI.
- `list_tasks(..., demo_only=False)` remains available for future integration/tests.

---

## 8. ID convention

`app/modules/expenses/idgen.py` implements:

```python
f"{now:%d%m%Y}-{secrets.token_hex(6)}"
```

- Uses Vietnam time (`UTC+7`) for the date portion.
- Produces 8 date digits + `-` + 12 lowercase hex characters = 21 characters.
- `ID_RE = ^[0-9]{8}-[a-z0-9]{12}$`
- `ID_REFERENCE_RE = ^[0-9]{8}-[a-z0-9]{8,}$` (reference pattern from `doc.md`).

Rules enforced by the code:

- IDs are generated once when an entity is inserted.
- Editing a plan item or record never regenerates its ID.
- Foreign keys store the referenced module ID verbatim.
- `source_expense_id` is never generated, reformatted, lowercased, or truncated; it is copied
  from the external source as-is.
- Demo rows use the same ID convention.

There is no retry loop for the astronomically unlikely 48-bit hex collision; the primary key and
database constraints would reject a collision. A future hardening step can add a retry helper.

---

## 9. Routes

| Endpoint | Method | Path | Handler | Purpose |
|---|---|---|---|---|
| `expenses.index` | GET | `/expenses` | `routes.index` | Ngày/Tháng/Năm navigation, calendar, summary, task check-in, demo data, records |
| `expenses.history` | GET | `/expenses/history` | `routes.history` | Filtered history and difference |
| `expenses.create_source` | POST | `/expenses/sources` | `routes.create_source` | Add demo plan item |
| `expenses.edit_source` | POST | `/expenses/sources/<item_id>/edit` | `routes.edit_source` | Edit plan item |
| `expenses.set_source_active` | POST | `/expenses/sources/<item_id>/active` | `routes.set_source_active` | Activate/deactivate |
| `expenses.delete_source` | POST | `/expenses/sources/<item_id>/delete` | `routes.delete_source` | Delete only when no check-in/record history |
| `expenses.generate_plan` | POST | `/expenses/plan/generate` | `routes.generate_plan` | Generate tasks for a date range |
| `expenses.checkin` | POST | `/expenses/tasks/<task_id>/checkin` | `routes.checkin` | Three check-in actions |
| `expenses.set_due_date` | POST | `/expenses/tasks/<task_id>/due-date` | `routes.set_due_date` | Set/clear payment due date |
| `expenses.create_record` | POST | `/expenses/records` | `routes.create_record` | Add unexpected expense; form carries `idempotency_key` |
| `expenses.edit_record` | POST | `/expenses/records/<record_id>/edit` | `routes.edit_record` | Edit actual record |
| `expenses.delete_record` | POST | `/expenses/records/<record_id>/delete` | `routes.delete_record` | Delete actual record |
| `expenses.clear_demo` | POST | `/expenses/demo/clear` | `routes.clear_demo` | Delete demo rows only |

All POST routes use POST-Redirect-GET and Flask `flash()` for success/error messages. All queries
use the user returned by `resolve_current_user_id()`; no `user_id` is accepted from the client.

`GET /expenses` generates a fresh `idempotency_key` for the unexpected-expense form on each render.
The POST handler passes the submitted form to `create_unexpected_record`; a replay with the same
key returns the original row, while a later new form has a new key. A first send flashes
“Đã thêm khoản chi bất ngờ”; a detected replay flashes “Giao dịch này đã được ghi nhận trước đó;
không tạo bản ghi trùng.”

### `/expenses` query contract

| Query parameter | Values | Behaviour |
|---|---|---|
| `view` | `day`, `month`, `year` | Missing/unknown values fall back to `day`; legacy `week` is not exposed as a top-level mode. |
| `date` | `YYYY-MM-DD` | Anchor date. Switching mode preserves it, so 15/10/2026 means day 15, month 10, and year 2026. |
| `month` | `YYYY-MM` | Month-view picker; keeps the current day when possible, clamps to the target month's last day, then passes the resulting date to `resolve_period`. |
| `year` | `YYYY` | Year-view picker; keeps the current month/day when possible, clamps leap-day changes, then passes the resulting date to `resolve_period`. |
| `tag` | `DAILY`, `WEEKLY`, `MONTHLY`, `DAY_OF_MONTH`, `DATE`, empty | Year-view only. Invalid values are ignored; it is passed to `build_summary` and `build_year_months`. |

`routes.index` builds a day/month summary and a month-wide summary for the calendar. The year view
uses one filtered year summary and groups it into month cards without summing per-month totals again.
`services.planned_records_for_tasks` extends `planned_by_task` for visible due-only tasks whose
assigned date is outside the period, so their actual amount and edit button stay available in the
day/month list. For day/month views, `modal_records` contains the period records plus records
linked to visible tasks so edit modals are present even when a record's `expense_date` differs
from the task's `assigned_date`; year view intentionally skips this list and links to history.

---

## 10. UI

### `app/templates/pages/expenses.html`

- Desktop mode navigation: three Bootstrap tabs `Ngày`, `Tháng`, `Năm` (`.bc-mode-tabs`).
- Mobile mode navigation: the tabs collapse into one `Chế độ xem` select (`#mobile-view`) that
  submits the same `view/date/tag` query and changes the title from Ngày to Tháng to Năm.
- Period navigation: previous/next anchors come from `services.build_navigation`; the current
  label and `Hôm nay` link preserve the selected mode. Day/month views also link back to the
  parent month/year. A direct picker uses `date` in day mode, `month` in month mode and `year` in
  year mode; the route converts the latter two back to an anchor date while keeping the current
  day/month when possible and clamping to the target month's last day.
- Day mode: macro-rendered real month calendar with selected-day highlight and indicator dots;
  detail area lists only the selected day's assigned tasks plus tasks due that day. The header
  reports assigned and due-only counts separately, with the assigned plan total and a separate
  “Ngoài tổng” due-only amount. Rows use distinct badges “Phân bổ trong ngày” and “Đến hạn trong
  ngày”; a task that is both appears once. Desktop uses a compact three-column table:
  task/status/payment-due control, plan/actual, and actions; below `lg` the same tasks become cards.
  Due-only tasks assigned on another date show their linked actual amount and edit action.
  Check-in opens a Bootstrap modal with the three existing actions; `actual` enables and requires
  the amount field with vanilla JavaScript.
- Month mode: the same real-day calendar drills down to day mode; the side panel lists non-daily
  monthly obligations (especially `MONTHLY` and `DATE`) and due-only tasks, not every `DAILY`
  occurrence.
- Year mode: 12 month cards with plan/actual/difference and task counts, links to month/day, and
  a `schedule_tag` filter. Non-daily highlights make date-specific tasks findable in other months;
  the `DAILY` filter shows counts plus a month link instead of hundreds of rows.
- Summary cards: assigned plan, actual, difference, unconfirmed; status badges and an unconfirmed
  warning. The plan card is labelled “Tổng kế hoạch được phân bổ” and states that due-only tasks are
  not included.
- DEMO/TẠM THỜI area is a collapsed `<details>` panel: create/edit/deactivate/delete plan items,
  generate schedule, clear demo data.
- Unexpected expense form and current-period transaction table are also in a collapsed
  `<details>` panel. The form includes a hidden `idempotency_key` so double-submit/retry does not
  create a second row. In year mode the panel shows a compact transaction count/total and a link to
  history instead of rendering hundreds of transaction rows and edit modals; edit/delete actions
  remain in day/month mode, while the history page stays read-only.
- Empty states for day, month, year, and no-data cases; responsive Bootstrap grid.

The month calendar and selected-day task list are server-rendered. JavaScript is limited to the
existing schedule-field toggling, check-in amount enable/disable, Bootstrap modal behavior, and the
mobile mode form submit; no second calendar or rule engine exists in the browser.

### `app/templates/pages/expense_history.html`

- Date range filter.
- Plan/actual/difference/confirmed cards.
- Record list with type, amount, category, note and linked task status.

### `app/templates/base.html`

- Flash messages rendered as Bootstrap alerts.
- Added a `scripts` block for the schedule-field JavaScript.

The schedule form uses vanilla JavaScript to show only fields relevant to the selected tag and to
disable/require them accordingly. Server validation remains authoritative.

---

## 11. Validation

`app/modules/expenses/validators.py`:

- `parse_amount` accepts positive integer VND only; rejects zero, negative, text, float notation.
- `parse_date` accepts `YYYY-MM-DD`.
- `parse_choice` restricts priority, amount source and schedule tags.
- `parse_schedule_fields` nulls irrelevant fields and requires the relevant one.
- `validate_plan_item_form` validates title, amount, source, priority and schedule.
- `validate_record_form` validates amount, expense date, title (unexpected only), category, note.

HTML forms also use `required`, `min`, `max`, `type=number` and `maxlength`. Server-side errors are
shown as Bootstrap flash alerts. Field-local `is-invalid`/`invalid-feedback` is not implemented;
this is a known UI gap, not a silent validation bypass.

---

## 12. Tests and verification

### Commands actually run

```text
python -m pytest -q
→ 48 passed

flask --app app routes
→ list includes 13 expenses routes; no import/runtime error

python -m compileall -q app tests
→ passed (no output)

flask --app app db upgrade / db downgrade / db upgrade
→ passed on a throwaway SQLite database; column and partial unique index verified
```

No lint, type-check, or build command was run because the repository does not provide one and no
tool was installed. No package was added or removed. No `git add`, `git commit`, `git push`,
merge, or pull request was performed.

### Test map

| Test file | Covers |
|---|---|
| `tests/test_expense_scheduling.py` | DAILY/WEEKLY/MONTHLY/DAY_OF_MONTH/DATE, leap year, clamping, idempotency, invalid range, ID format, ID/external-ID immutability, nulling irrelevant fields, schedule-change rejection after tasks exist |
| `tests/test_expense_checkin.py` | planned check-in, actual update, within/over status, repeated check-in, no-expense rejection after record, no zero record, positive amount validation, UNRECORDED refresh, unconfirmed-task plan update, confirmed-history preservation, UNRECORDED-history preservation, and pending-but-past-deadline preservation after plan change |
| `tests/test_expense_summary.py` | month totals, day/week boundaries, pending not zero, records outside period, edit/delete status recalculation, demo isolation |
| `tests/test_expense_navigation.py` | year period boundaries, month shift/clamping, week ±7-day navigation, real 28/29/30/31-day calendar, selected-day task filtering, assigned+due de-duplication, separate assigned/due-only day totals, MONTHLY only on month-end but in month overview, month obligations excluding assigned DAILY, year grouping and all five schedule filters, linked actual visible for due-only tasks assigned elsewhere, year view omitting record modals while day view keeps edit, route rendering of desktop/mobile mode controls, and month/year pickers preserving the day/month with clamping |
| `tests/test_expense_unexpected.py` | same idempotency key returns one row even with changed payload, same amount/date with different keys creates two rows, form renders a token, and replaying the form POST does not duplicate |
| `tests/test_expense_routes.py` | page rendering, full create/generate/checkin/due-date/unexpected/history HTTP flow, validation error, clear-demo isolation, 404 |

Additional manual render check with seeded daily/monthly/date plan items requested
`/expenses?view=day|month|year` and `tag=DATE|DAILY`; all returned HTTP 200 and the rendered HTML
had no duplicate element IDs.

---

## 13. Intentional deviations and known gaps

| Item | Decision / gap | Reason |
|---|---|---|
| Category storage | `ExpenseRecord.category` is free text (String 80), not `category_id` | Repository has no categories table yet; `doc.md` allows minimal category information |
| Unexpected expense demo flag | The current form writes `is_demo=True` | The module is still running on the demo data path; official source integration is not implemented |
| Demo filtering | Summary/list queries default to `is_demo=True` | Prevents demo data from mixing with future official data |
| Plan amount edit | Updates `planned_amount`/`priority` only on still-pending, unchecked tasks assigned today (before deadline) or in the future; confirmed, checked, overdue, and UNRECORDED tasks keep their generated snapshots | Preserves past check-in history and report values while allowing current-cycle plan edits |
| Schedule edit | Rejected when the item already has generated tasks; create a new item if the schedule must change | Keeps existing tasks/check-ins consistent and avoids silently creating a second schedule |
| Payment due date | Per task only; no inheritance from plan item | Matches “do not assume due date equals assigned date” |
| Week view | `resolve_period("week")` and its tests remain with correct ±7-day navigation, but the refactored UI exposes only Ngày/Tháng/Năm | The requested navigation is three-level; weekly planning is represented by WEEKLY tasks/calendar day selection, while a dedicated weekly totals page is not implemented |
| Unexpected create idempotency | UI sends a per-render token; repeated token returns the existing record. Service callers without a token retain legacy create behaviour | Prevents double-submit/replay without forbidding two real same-day, same-amount expenses |
| `BudgetAdjustment` | Not implemented | Explicitly optional in `doc.md`; core F07–F13 does not require it |
| M1 integration | `M1BudgetSource` raises `NotImplementedError` | `docs/api-contracts.md` is still a proposal; no fake network calls |
| Auth | `resolve_current_user_id()` always returns `demo-user` | Accounts/auth not implemented in repository |
| CSRF | No token | Pre-existing repository state; documented as unsafe for shared deployment |
| Inline validation | Flash alerts; no field-local `is-invalid` | Known UI gap |
| History editing | Edit/delete on `/expenses`; `/expenses/history` is read-only with filters | Avoids duplicating the record edit UI; both use the same records |
| Pagination | Not implemented | Period filters bound the dataset for MVP |
| Background jobs | Not implemented | Overdue refresh is idempotent on page load, allowed by `doc.md` |
| ID collision retry | Not implemented | 48-bit random suffix; DB PK/unique constraints are the final guard |

---

## 14. Not changed

- No Budget, Dashboard, Recommendations, Accounts, or Core route was modified.
- No existing table, data, or DRAFT document was deleted or rewritten.
- No `source_expense_id` is modified by module code.
- No new Python dependency, frontend framework, Node build tool, or UI kit was added.
- `.env`, secrets, database URL, and local `.db` files are not part of the changes.
- The app repo remains on `feature/expense-planning-checkin`; all changes are unstaged.

---

## 15. Next integration steps (not done)

1. Replace `resolve_current_user_id()` with the Accounts module’s session user.
2. Implement `M1BudgetSource.list_expenses` when the Budget/M1 API is published, keeping
   `source_expense_id` unchanged.
3. Add CSRF protection and real authorization before shared deployment.
4. Add field-local validation feedback and pagination if the record volume grows.
5. Decide whether editing a schedule should regenerate future PENDING tasks; current behaviour
   rejects a schedule change after tasks exist, so the user must create a new item instead.
6. Implement `BudgetAdjustment`/`BudgetAdjustmentAllocation` only if the team explicitly adds the
   advanced adjustment scope.
