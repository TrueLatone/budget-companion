# API contracts

The health, KAN-15 and KAN-21 HTML routes below are implemented. JSON feature API
endpoints remain proposals. KAN-21 integrates budget setup and plan persistence;
expense/check-in/report/recommendation feature endpoints remain unimplemented.

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
