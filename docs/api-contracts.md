# API contracts (DRAFT)

All endpoints below are **proposals** except `/api/health` and `/api/health/database`. Implement only after ticket review.

## Implemented on day 1

| Method | Endpoint | Behavior |
|---|---|---|
| GET | `/api/health` | `200 {"status":"ok","service":"budget-companion"}` |
| GET | `/api/health/database` | `200` DB connected, `503` DB unavailable |

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
