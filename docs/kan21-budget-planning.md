# KAN-21: Budget Planning integration

The existing application factory registers the Budget blueprint. It now uses
User → BudgetMonth → BudgetExpense → BudgetPlan → BudgetAllocation through the
existing SQLAlchemy extension. No schema changes, migrations, alternate Flask
application, TXT storage, external AI calls or additional dependencies are needed.

## User flow

1. Sign in, create/select a budget month, then open **Plan budget** or `/budget`.
2. Add/edit/remove expenses, choosing an owned/built-in category or naming a new
   owned category. Names are unique within the month, ignoring case.
3. Supply Rent, Electricity and Water as P0. Internet is optional but P0 when
   included. Each P0 requires a positive estimate at generation/confirmation.
   An incomplete draft may retain an unknown or explicit-zero P0 estimate.
4. Optionally supply positive P1 minimums. Blank estimated amounts are NULL,
   never zero. Explicit zero estimates remain zero. Included P1/P2 expenses
   receive positive allocations; estimates are informational, not hard caps.
5. Generate three plans, read their stored allocations, then confirm one.
   Confirmation rechecks the current funds, expense set, category authorization,
   exact P0 amounts, P1 minimums and conservation. Submitted allocation overrides
   and client user IDs are not used.

Saving/Balanced/Lifestyle use KAN-11's implemented P1/P2/savings targets of
70/5/25, 65/15/20 and 60/30/10 after reserving P0. The older rules document also
contains a competing extra-P1 ratio table. KAN-21 selects the runnable KAN-11
policy and the matching second table; it does not combine the two policies.
P1 minimums and a positive allocation for every included expense take priority:
discretionary surplus is transferred before savings. Unselected group shares go
to savings. Per-expense fallback weights reuse Food/Transportation/other weights
3/1.5/1 scaled to integer weights 6/3/2. Largest-remainder splitting uses integer
products and remainders, including at signed BIGINT limits.

## Persistence and safety

- All model keys are UUIDs; all monetary values are integer VND.
- Ownership is checked in services as well as authenticated routes. A category
  must be owned by the user or built-in. Every allocation must match an expense
  of the same authorized month, once and only once.
- Expense changes/regeneration atomically replace generated candidates. Invalid
  operations roll back, retaining previous candidates. Drafts with scheduled
  tasks cannot be replaced. Categories are retained when an expense is removed.
- Confirmation and setup changes lock the month's row on PostgreSQL. The
  existing partial unique index additionally enforces one confirmed plan per
  month on PostgreSQL/SQLite. Confirming the same plan again is harmless;
  selecting a different one returns a conflict. No replacement workflow exists.
- Confirmed allocations, savings and expense metadata are immutable through
  Budget services. Later funds edits do not rewrite the original plan. Its
  original funding total is derived from allocations plus planned savings,
  rather than displayed using the mutable month funds.
- Routes retain the existing sessions and Flask-WTF protection. No CSRF exemption
  or alternative authentication path is introduced. Unknown and explicit zero
  estimates display separately; neither is an expense check-in.

## Expense Planning handoff and remaining scope

KAN-21 does **not** create AssignedExpenseTask rows. Expense Planning must read
only CONFIRMED BudgetPlan allocations owned through BudgetMonth.user_id. Each
BudgetAllocation.allocated_amount is a monthly total, not a per-occurrence amount.
Use its UUID as allocation_id; obtain category, priority, frequency, recurring
flag and optional due day from BudgetExpense. Do not convert UUIDs into legacy
date-prefixed IDs or introduce duplicate task/expense models.

### Implemented read interface

`app.modules.budgets.services.get_confirmed_allocations(user_id, month_id)`
returns canonical BudgetAllocation objects for that owner's confirmed plan in
exactly that month. It returns an empty list if the owned month has no confirmed
plan, including when generated alternatives exist. Invalid/non-owned month IDs
raise BudgetNotFound. Cross-month expense references and unauthorized categories
raise BudgetError. The function is read-only, creates no tasks, and does not
return generated alternatives. Callers must obtain user_id from g.current_user;
this service parameter is not permission to trust a submitted client user ID.

Each returned allocation exposes UUID id, plan_id and budget_expense_id, plus
integer allocated_amount. Its BudgetExpense supplies category_id, priority,
allocation_frequency, due_day and is_recurring. The plan supplies the owned
BudgetMonth, month_start and tracking_start_date. Savings are not expense task
allocations. Do not use list_plans or all BudgetAllocation rows as the handoff:
generated plans intentionally coexist with the confirmed plan.

KAN-23 now consumes this interface for actual Expense scheduling. The integration
selectively reuses KAN-8 presentation code, replacing its unsafe data source,
anonymous fallback and write paths; it does not activate the legacy models.
All task reads require confirmed plans and owned, matching month/category links.
See the [KAN-23 contract](kan23-expense-planning.md) for current behavior.

### Scheduler interfaces (implemented by KAN-23)

| Interface | Responsibility |
|---|---|
| Budget: get_confirmed_allocations(user_id, month_id) | Implemented authorized, confirmed-only source |
| Expense: build_task_schedule(allocation, tracking_start_date) | Pure calculation of period dates and integer limits |
| Expense: ensure_tasks_for_month(user_id, month_id) | Authorized, atomic, repeat-safe task creation |
| Expense: list_tasks(user_id, start, end) / list_due_tasks(user_id, start, end) | Confirmed-plan filtering and authorized assigned/due date scoping |

The adapter should consume the confirmed-only source per overlapping owned
month, preserve explicit allocation_id and budget_month_id, and treat amount as
the monthly allocation. Budget frequency describes spending periods, not the
legacy occurrence_dates API's weekly weekday rule. The canonical schema has
no day_of_week or arbitrary specific_date, and is_recurring describes offering
the expense in another month; do not invent those missing recurrence fields.

### Task construction and conservation contract

The following handoff is now implemented by KAN-23; KAN-21 itself still creates
no tasks and retains its verified Budget behavior:

1. Resolve and authorize the owned month, then obtain only its confirmed
   allocations. Lock the month while inserting a complete schedule transaction.
   Never schedule generated alternatives.
2. Build eligible periods within tracking_start_date through calendar month end.
   DAILY uses one day per period. WEEKLY uses Monday–Sunday periods clipped to
   the eligible interval. MONTHLY uses one period over the eligible interval.
   KAN-23 treats the complete confirmed allocation as funds for that eligible
   interval, without changing the original monthly Budget plan or amounts.
3. For monthly total A and chronological period weights w_i, use integer bases
   `A * w_i // sum(weights)`. Distribute the remaining VND one at a time by
   descending `A * w_i % sum(weights)`, breaking ties by period start date.
   Daily weights are 1; weekly weights are eligible days in each clipped week;
   a single monthly period receives A. Example: 100,003 VND over three eligible
   days becomes 33,335 + 33,334 + 33,334 VND, never 100,003 on each day.
4. Create each AssignedExpenseTask with a new UUID, allocation_id equal to the
   canonical allocation UUID, assigned_date/period_end equal to the period's
   inclusive dates, original_limit equal to its computed share, current_limit
   initially equal to original_limit, and task_status PENDING. Limits may be
   zero when the monthly total is smaller than the number of periods. A zero
   task allowance is not evidence of NO_EXPENSE, and cannot be recorded as a
   zero-amount ExpenseRecord (transactions must be positive).
5. For a monthly bill due_day, clamp to the month's last calendar day and use
   payment_due_date; initialize payment_status UNPAID when a due date exists,
   otherwise NULL. Keep payment_due_date/payment_status NULL for non-bill tasks.
   KAN-23 retains a bill due before tracking start as outstanding UNPAID, with
   the original due date; it is not assumed to have been paid. The UI states
   this policy. A month whose full schedule is invalid is not partially committed.
6. Enforce one task per (allocation_id, assigned_date) using the existing unique
   constraint. A retry must compare the expected dates and original limits with
   existing rows, insert only missing matching rows, and return existing UUIDs.
   Mismatched schedules are conflicts, not permission to overwrite recorded
   tasks, original limits, adjusted current limits, or payment/check-in states.
7. Before committing, require sum(task.original_limit) == allocated_amount for
   each allocation. Across the plan, task original limits plus planned_savings
   must equal the confirmed plan's original total (allocations plus savings),
   not the subsequently mutable BudgetMonth.available_vnd. Do not include P0
   reservation or meal subdivisions a second time as additional task amounts.

Scheduling must be idempotent per (allocation_id, assigned_date), respect
tracking_start_date, preserve the sum of task original_limit values, initialize
current_limit from original_limit and store PENDING rather than derived display
states. Do not repeat a monthly allocation on each daily/weekly task. Actual
spending and explicit check-ins are implemented by KAN-23. FUNDS_ADDED,
adjustments, automatic reallocation, carry-forward, history-based suggestions
and Dashboard data binding remain outside these two tickets.

The new budget UI uses the existing page shell and language preference; its new
form labels and explanatory copy are currently English. Mandatory P0 detection
uses the prototype's English expense names (case-insensitive), not category names.
JSON APIs and manual allocation editing are not added; generated plans cover
the minimum functional flow. Live PostgreSQL concurrency testing remains a
deployment integration check; SQLite tests verify constraints and rollback.
