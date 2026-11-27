# Expense Calendar integration repair

Base: `integration/pa2-20261031` at
`7326e2cfa5e225dc182bb866c0fab85d02d25758`. Working tree was clean.
Baseline: **344 passed, 150 warnings in 30.12s**.

## Reproduced root cause

Diagnostics used an explicit `sqlite://` in-memory database with synthetic,
owned Budget data created through the canonical services. No configured or
production database was accessed, reset, migrated or modified. Diagnostic
queries were read-only; scheduling was then explicitly exercised in that
disposable database to compare results.

| Stage (October 2026, tracking October 15) | Expenses | Confirmed allocations | Tasks | Calendar assignments |
|---|---:|---:|---:|---:|
| After Budget confirmation | 5 | 5 | 0 | 0 |
| After explicit schedule POST | 5 | 5 | 23 | 23 |

Confirmation saved the immutable Budget snapshot but created no tasks. The
calendar reads AssignedExpenseTasks, rather than Budget allocations directly.
Confirmation returned to the saved plan, making the separate schedule step easy
to miss. Once scheduled, the old monthly list omitted daily Food; calendar cells
showed only assignment-start dots, and continuing periods were absent from day
detail unless they started or were due that day.

| Possibility checked | Finding and repaired presentation |
|---|---|
| No BudgetExpenses | Distinct setup guidance; never invent expenses |
| No BudgetPlan | Distinct generation guidance |
| Draft plans only | Distinct confirmation guidance; drafts never schedule |
| No confirmed allocations | Explicit invalid-handoff message and plan review link |
| Missing tasks | Reproduced primary defect; explicit schedule action |
| Wrong month | Explicit owned month ID now wins over stale date/month/year fields |
| Tracking start | Intentionally excludes earlier assignments; valid bill due dates remain visible |
| Ownership filters | Confirmed-plan, owner, same-month and category checks retained |
| DAILY omitted from month list | Daily tasks, including Food, now appear once each |
| Weekly/monthly periods | Inclusive ranges and active-period indicators now explain coverage |
| Calendar rendering | Names, bill due dates, recorded actuals and check-in states are visible |

## Guided workflow and failure handling

Login → create/select owned Budget Month → add expenses → generate/compare
plans → confirm → redirect to that month's Expense page → **Create spending
schedule** (POST + CSRF) → populated calendar → select date for check-in.
The saved Budget plan remains available through a review link.

Confirmation and scheduling remain separate writes. The Budget confirmation
service still commits only its immutable plan. The HTTP route now redirects to
Expense instead of back to Budget detail. Scheduling calls the unchanged,
authorized `ensure_tasks_for_month`. Failures roll back all task inserts while
the already-confirmed plan remains valid and retryable. No GET creates tasks.

The read-only `expenses.services.get_schedule_state(user_id, month_id)` reports
NO_EXPENSES, NO_PLAN, UNCONFIRMED, NO_ALLOCATIONS, NOT_SCHEDULED, INCOMPLETE,
CONFLICT or READY. Missing owned months have a create/select link. Incomplete
schedules offer verification to fill missing rows. Conflicting original limits
or periods are explained and never overwritten. The state check inspects only
tasks under authorized confirmed allocation UUIDs, including malformed periods
that ordinary display queries must exclude.

An explicit `budget_month_id` wins over stale navigation fields. A selected date
inside that month is retained. Date-only navigation can still leave the active
session month. Scheduling redirects include the owned month ID.

## Financial and display contracts

- DAILY tasks show names on their dates. Month view lists every assigned task
  once, including Food; each links to day detail.
- Weekly/monthly starts show name and inclusive period; later dates show active
  period indicators. Day detail includes continuing tasks with their full period
  limits. Bills also show due-date markers, including valid dates before tracking.
- Calendar `task_count` and `plan_total` count assignments only on their start
  dates. Summing them across the month counts each task/current limit once.
  Continuing periods and due-only items do not enter the day assigned total.
  Status indicators describe tasks covering a date; they can repeat visually
  across dates and must not be summed as new assignments or allocations.
- Actual amounts follow ExpenseRecord.expense_date and include only PLANNED
  and UNEXPECTED records. FUNDS_ADDED is excluded. Actual records, PENDING,
  explicit NO_EXPENSE and overdue UNRECORDED are distinguished. A calendar day
  without records does not display an observed zero as a confirmed check-in.
- Continuing-period purchases default to the selected date when it lies inside
  that task's period. Full-task spending totals remain labeled as such. Backend
  amount/date/ownership/token checks and CSRF remain in force.
- Canonical models, UUID FKs, integer VND, scheduler and confirmation service
  are unchanged. Original task limits sum exactly to monthly allocations.
  Retrying preserves UUIDs, original/current limits, payment state and spending.
  Meal guidance remains presentation-only; no extra tasks or money are created.

## Verification and limits

Added 19 regression cases in `tests/test_expenses.py` cover before/after
scheduling, login/CSRF, confirmation redirect, empty states, month precedence,
daily Food throughout tracking, weekly/monthly coverage, early bill due dates,
conservation, actuals/unknown/NO_EXPENSE, funds exclusion, retries preserving
spending and current limits, missing/corrupt schedules, ownership and HTTP
failure followed by retry. The targeted Expense suite passes **72 tests**.

Final command: `.venv\Scripts\python.exe -m pytest -q`.
Result: **363 passed, 0 failed, 150 warnings in 35.70s**. Warnings remain the
existing WTForms choice, Flask-Migrate engine and SQLite date-adapter deprecation
categories. `git diff --check` passed.

Tests use disposable SQLite plus the existing migration-backed suite and Flask
test client. Live PostgreSQL concurrency and real-browser layout/interaction
remain deployment checks. No production-data repair or backfill was attempted.

Changed implementation files: Budget `routes.py` (confirmation handoff only),
Expense `routes.py`, `services.py` (new read-only state inspection),
`presentation.py`, `static/css/expenses.css`, `templates/pages/expenses.html`,
`templates/expenses/_setup.html` and `tests/test_expenses.py`. Documentation:
this report, root README, docs index, API contracts and KAN-23 contract addendum.
