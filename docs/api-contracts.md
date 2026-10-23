# API contracts (DRAFT)

All endpoints below are **proposals** except `/api/health` and `/api/health/database`. Implement only after ticket review.

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
