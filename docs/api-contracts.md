# API contracts

The health, KAN-15, KAN-21 and KAN-23 HTML routes below are implemented. JSON
feature API endpoints remain proposals. Budget and Expense services share the
canonical database, authenticated session and global CSRF protection.

## Implemented on day 1

| Method | Endpoint | Behavior |
|---|---|---|
| GET | `/api/health` | `200 {"status":"ok","service":"budget-companion"}` |
| GET | `/api/health/database` | `200` DB connected, `503` DB unavailable |

## Implemented by KAN-15 — HTML form routes

| Method | Endpoint | Behavior |
|---|---|---|
| GET, POST | `/register` | Create an account with normalized email and hashed password |
| GET, POST | `/login` | Authenticate and establish a Flask session |
| POST | `/logout` | Clear the authenticated session; CSRF protected |
| GET | `/account` | Show the authenticated account page |
| GET | `/budget-periods` | List the authenticated user's calendar months |
| GET, POST | `/budget-periods/new` | Create one user-owned calendar month |
| GET, POST | `/budget-periods/<uuid>/edit` | Update available funds for an owned month |
| POST | `/budget-periods/<uuid>/select` | Select an owned month in the session |

Mutating routes use CSRF-protected HTML forms. The backend always derives the
account identity from the session and returns `404` for another user's budget
period identifier.

KAN-19 creation accepts optional `tracking_start_date` in `YYYY-MM-DD` format.
It must fall inside the selected calendar month; omission defaults to its first
day. Funds editing does not change it. The period list displays it.
All internal model IDs/FKs use UUID; money remains integer VND. See the
[entity dictionary](entity-dictionary.md).

Future feature contracts must use canonical month/allocation/category links,
allow multiple PLANNED records per task, and distinguish stored states
PENDING/RECORDED/NO_EXPENSE from derived display outcomes. UNEXPECTED requires
priority; FUNDS_ADDED is not spending. Retryable writes must use a token scoped
to the budget month, validate replay payloads, and update funds exactly once
in the same transaction. These service/API workflows are not implemented merely
by adding model constraints.

## Implemented by KAN-21 — Budget Planning HTML routes

All routes require the existing authenticated session. Every month, expense,
category and plan is checked against that user; client-provided `user_id` fields
never authorize access. Every POST uses global Flask-WTF CSRF protection.

| Method | Endpoint | Behavior |
|---|---|---|
| GET | `/budget?budget_month_id=<uuid>` | Select an owned month; otherwise use the selected session month or latest owned month |
| GET | `/budget/<uuid:month_id>` | List the month's expenses and saved plans |
| GET, POST | `/budget/<uuid:month_id>/expenses/new` | Add an expense using an owned/built-in category or create an owned category |
| GET, POST | `/budget/<uuid:month_id>/expenses/<uuid:expense_id>/edit` | Edit expense setup before confirmation |
| POST | `/budget/<uuid:month_id>/expenses/<uuid:expense_id>/delete` | Remove an expense before confirmation |
| POST | `/budget/<uuid:month_id>/plans/generate` | Persist Saving, Balanced and Lifestyle alternatives |
| GET | `/budget/<uuid:month_id>/plans/<uuid:plan_id>` | Read a saved plan and allocations from SQLAlchemy |
| POST | `/budget/<uuid:month_id>/plans/<uuid:plan_id>/confirm` | Revalidate and confirm the stored plan; repeated confirmation is harmless |

Expense fields: `expense_name`, `category_id` OR `category_name`, `priority`,
`estimated_amount`, `minimum_amount`, `allocation_frequency`, `is_recurring`,
`due_day`. Blank estimates persist as NULL; explicit `0` persists as zero.
Amounts must be integer VND, bounded by signed BIGINT. Frequencies are DAILY,
WEEKLY or MONTHLY. Minimums are optional positive P1 amounts. Due day is optional
1–31 for monthly expenses. Category names are reused within the owner namespace.

Successful POSTs redirect. Invalid form/rule input returns 400, inaccessible
resources return 404, and locked or conflicting state returns 409. Category
choices submitted through WTForms must be in the visible owned/built-in list.
Expense changes and regeneration atomically replace unconfirmed drafts only;
drafts with tasks cannot be replaced. Confirmation accepts no allocation edits:
only saved allocations, savings, current funds and current expense rules count.
See [KAN-21 integration contract](kan21-budget-planning.md) for the Expense handoff.

The internal read-only `budgets.services.get_confirmed_allocations(user_id,
month_id)` interface returns only the authorized month's confirmed allocations;
it excludes generated alternatives and creates no tasks. The Expense module
must consume it before scheduling. This is a Python service, not a new HTTP API.

## Implemented by KAN-23 — Expense Planning and Smart Check-in

| Method | Endpoint | Behavior |
|---|---|---|
| GET | `/expenses?budget_month_id=<uuid>` | Open an owned month; otherwise use the active session month or date navigation |
| GET | `/expenses?view=day\|month\|year&date=YYYY-MM-DD` | Calendar, assigned periods, due bills and recorded spending |
| GET | `/expenses/history?start=YYYY-MM-DD&end=YYYY-MM-DD` | Owned spending history; FUNDS_ADDED is excluded |
| POST | `/expenses/months/<uuid:month_id>/schedule` | Idempotently schedule only confirmed allocations, conserving each monthly total |
| POST | `/expenses/tasks/<uuid:task_id>/checkin` | Add a positive actual transaction or explicitly confirm NO_EXPENSE |
| POST | `/expenses/tasks/<uuid:task_id>/payment-status` | Set self-reported PAID/UNPAID on a bill task; no money is moved |
| POST | `/expenses/records` | Add an unexpected transaction to an existing owned month |
| POST | `/expenses/records/<uuid:record_id>/edit` | Correct a spending transaction within its original month/task period |
| POST | `/expenses/records/<uuid:record_id>/delete` | Delete one owned spending transaction and recalculate task status |

Every route requires login; every POST uses the existing CSRF architecture.
No client user_id authorizes access. Unknown/malformed/foreign resources return
404, invalid inputs 400, conflicting schedules/retry payloads 409, and successful
POSTs redirect. GET requests create no schedules, users, months or transactions.
No demo identity, bulk cleanup or legacy duplicate model is exposed.

Check-in fields: action (`actual`, `planned`, `no_expense`), amount (required
positive integer VND for actual), expense_date (optional, defaults to assigned
date), category (optional override name), note and idempotency_key. Actual and
planned submissions require a nonempty retry token of at most 64 characters.
The token is unique within the budget month across both transaction types;
identical replay returns the existing result and changed payload returns 409.
Each new token may create a separate actual purchase; a task may have many.
`planned` explicitly records current_limit once and is rejected if it is zero or
other purchases already exist. NO_EXPENSE creates no zero-amount record, is
repeat-safe, and conflicts while transactions exist. Future tasks cannot be
checked in. Transaction dates must lie inside the tracked month and the linked
task's inclusive period, and cannot be future dates.

Unexpected fields: budget_month_id, title (1–120 characters), category (required
name up to 100), priority (explicit P0/P1/P2), positive integer amount,
expense_date, note (up to 2000), optional budget_impact_scope
(DAILY/WEEKLY/MONTHLY) and idempotency_key. A month is never auto-created with
zero funds. Unknown input is rejected, not replaced with a category/priority or
zero amount. Updates do not move transactions across months or modify funds.

Read totals label the observed transaction sum separately. Missing/unconfirmed
check-ins and incomplete schedules keep the plan comparison Unknown (NULL),
not zero. The [KAN-23 contract](kan23-expense-planning.md) defines period
distribution, original/current limits, payment due dates and retry boundaries.

## Planned endpoints — NOT IMPLEMENTED

| Owner | Method | Endpoint | Description |
|---|---|---|---|
| Nhân | GET | `/api/budgets?month=YYYY-MM` | Read a user's monthly plan |
| Nhân | POST | `/api/budgets` | Create plan / validate P0+P1 minimum |
| Tuấn Anh | POST | `/api/expenses` | Add actual expense |
| Tuấn Anh | POST | `/api/check-ins` | Confirm `RECORDED` or `NO_EXPENSE` |
| Thiện | GET | `/api/reports/month-over-month?month=YYYY-MM` | Monthly comparisons incl. missing-record flag |
| Khiêm | GET | `/api/recommendations?month=YYYY-MM` | Explainable suggestions |
| Thịnh | GET | `/api/recurring-bills` | Scheduled/recurring costs |

## Contract conventions to decide

- Login/session transport and CSRF protection for mutating requests.
- Authentication and user authorization (backend derives account identity from the session).
- ISO dates; calendar month string `YYYY-MM`; integer VND values.
- Error envelope, e.g. `{ "error": { "code": "...", "message": "..." } }`.
- Create/submit endpoints must be repeat-safe or provide idempotency/unique key to prevent duplicate expenses.
- Agree whether page POST actions submit HTML forms, JSON fetch or both; don't duplicate business logic.
