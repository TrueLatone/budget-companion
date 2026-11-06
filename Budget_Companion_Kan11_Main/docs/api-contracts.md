# API contracts

The health, KAN-15, KAN-21, KAN-23, KAN-25 and KAN-27 routes below are implemented.
Budget, Expense and Recommendation services share the
canonical database, authenticated session and global CSRF protection.

## Build 1 status and boundaries

Budget setup/three-plan confirmation, explicit Expense scheduling/check-ins,
and the monthly Dashboard are implemented core flows. Recommendation analysis
is implemented with the original F18 gate; financial adjustment is disabled.
An insufficient-data response includes reasons and separately labeled baseline
guidance, not synthetic transactions or a reduced completeness threshold.
See [Build 1 verification](build1-verification.md) for reproducible acceptance
coverage and remaining deployment limitations.

Load Example and Food's 30/40/30 meal guidance are illustrative presentation
features, not demo persistence or additional transactions. No live endpoint uses
`ui_demo.py` or browser localStorage as financial storage. Funds addition,
cross-month reports, automatic adjustments and LLM advice have no implemented
write contract. Some legacy Expense/Recommendation text still needs translation.

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
| POST | `/budget/<uuid:month_id>/expenses/suggested` | Atomically add selected suggested expenses before confirmation; existing names are skipped |
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

Successful confirmation now redirects to the owned month's Expense calendar,
where the user explicitly POSTs **Create spending schedule**. Confirmation
itself still creates no tasks. Scheduling errors preserve the confirmed plan
and allow retry; no GET creates financial records.

Suggested setup fields: repeated `suggestion` keys from `rent`, `electricity`,
`water`, `internet`, `food`, `transportation`, plus optional
`<key>_estimated_amount`, `<key>_minimum_amount` (P1 only),
`<key>_allocation_frequency` and `<key>_due_day` (monthly only). Names, default
priorities and categories come from the server's suggestion list, not submitted
identity fields. Omitted frequencies use monthly bills / daily Food / weekly
Transportation. Blank estimates stay NULL; example amounts require explicit
user input or the unsaved **Load Example** action. Existing case-insensitive
names are always preserved on retries, even if submitted values differ. The
entire batch uses the existing Budget write path and rolls back on failure.
No GET seeds financial records. See [Budget core parity](budget-core-parity.md)
for examples, read-only plan comparison and presentation-only meal guidance.

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

## Implemented by KAN-25 — Workspace and Dashboard

KAN-25 adds authenticated GET `/dashboard`, selecting an owned
`budget_month_id=<uuid>` or `month=YYYY-MM`, otherwise the active session month
or latest owned month. It renders confirmed allocations, savings, observed
spending and nullable remaining allocation using canonical services. It adds no
financial write endpoint. The shared Workspace carries that owned month across
Budget, Expense and Recommendation pages. See the
[KAN-25 contract](kan25-workspace-dashboard.md) for formulas and UI behavior.

## Implemented by KAN-27 — Spending analysis

KAN-27's implemented HTML and JSON endpoints use `/recommendations`, not the
proposed `/api/recommendations` path below. GET `/recommendations` is an
authenticated page. GET `/recommendations/analysis`, `/completeness` and
`/monthly-review` take `month=YYYY-MM` and optional `as_of=YYYY-MM-DD`.
POST `/recommendations/generate` takes the same fields as a JSON object.
GET `/recommendations/<uuid>` reads an owned saved snapshot;
POST `/recommendations/<uuid>/decision` takes `decision` (REJECT is repeat-safe;
ACCEPT always returns 409 because financial adjustments are disabled).
POST `/recommendations/monthly-review/feedback` upserts owned feedback.
All POSTs retain global CSRF; JSON callers use `X-CSRFToken`. See the
[KAN-27 contract](kan27-spending-analysis.md) for exact statuses, baseline guidance,
replay behavior, F18 thresholds and HTML actions. Other `/api/...` entries below
remain proposals.

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

## Established conventions and future API work

- Implemented financial routes require the Flask authenticated session; no
  submitted `user_id` grants access. Global Flask-WTF protects all POSTs,
  including login/register/logout. HTML forms carry `csrf_token`; JSON clients
  supply `X-CSRFToken` obtained from their session's rendered page.
- Internal IDs/FKs are UUIDs; dates use ISO format, months use `YYYY-MM`, and
  money is integer VND. Blank estimates remain NULL and explicit zero remains zero.
- Budget/Expense HTML writes redirect on success, with 400 invalid input, 404
  inaccessible resources and 409 state/replay conflicts. Recommendation JSON
  response bodies/statuses are defined in the KAN-27 contract; a universal JSON
  error envelope for the proposed `/api/...` endpoints is not implemented.
- Suggestions preserve existing names; schedule/confirmation retries preserve
  IDs and check-ins. Purchase tokens are scoped to an owned month and reject
  changed payloads. Recommendation generation reuses snapshots of unchanged data.
  These guarantees do not make every form (such as account registration) an
  arbitrary idempotency-token endpoint.
- GETs may update the selected month/language in the session but create no
  financial records. Confirmation redirects to an explicit CSRF-protected
  schedule POST; refreshing the calendar alone never creates tasks.
