# Initial database design

## KAN-15 foundation

KAN-15 establishes two shared tables:

- `users`: native UUID primary key, normalized unique email, password hash,
  active flag, and timezone-aware UTC audit timestamps.
- `budget_months`: native UUID primary key, UUID owner foreign key,
  first-day `month_start`, non-negative integer `available_vnd`, and
  timezone-aware UTC audit timestamps.

Each user may have at most one period for a calendar month through
`UNIQUE(user_id, month_start)`. Deleting a user cascades to that user's budget
months at the database level, although KAN-15 exposes no account-deletion UI.
All application reads and writes derive ownership from the authenticated
session.

Internal shared IDs use native UUIDs. Modules must use the same UUID type for
foreign keys. IDs imported from another module or external source remain in a
separate string source-ID column; they are not converted into internal primary
keys.

`budget_months` deliberately has no status column. Future draft/confirmed
states belong to the Budget Planning contract. A future confirmed plan must
snapshot its original funds and allocations instead of treating mutable
`budget_months.available_vnd` as historical truth.

## Suggested entities

| Entity | Suggested main fields | Owner / notes |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `created_at` | Thịnh; use password hashing, not plaintext |
| `budget_months` | `id`, `user_id`, `month_start`, `available_vnd`, `status` | Thịnh/ Nhân; one per user/calendar month |
| `categories` | `id`, `user_id`, `name`, `priority` | Nhân; priority P0/P1/P2 |
| `budget_allocations` | `id`, `budget_month_id`, `category_id`, `planned_vnd`, `min_vnd` | Nhân |
| `recurring_bills` | `id`, `user_id`, `category_id`, `schedule`, `due_date` | Thịnh; design recurring occurrence separately |
| `expense_records` | `id`, `user_id`, `category_id`, `spent_vnd`, `spent_on`, `source` | Tuấn Anh; actual spending source of truth |
| `expense_checkins` | `id`, `user_id`, `occurrence_id`, `status`, `expense_record_id` | Tuấn Anh; prevent repeat check-in |
| `recommendations` | `id`, `user_id`, `budget_month_id`, `reason`, `status` | Khiêm; user accepted/rejected |
| `monthly_reviews` | `id`, `budget_month_id`, `rating`, `comment` | Khiêm |

Do not create tables until the team agrees PK/FK conventions, ownership boundaries, required columns and migrations.

## Important database constraints

- `UNIQUE(user_id, month_start)` for one monthly plan per user.
- One check-in per *logical occurrence*, with uniqueness on `user_id + occurrence_id` (exact occurrence model pending).
- When check-in generates an expense, reference **one** `expense_record_id`; do not count both check-in and expense as two costs.
- Use integer VND (`BIGINT` for amounts if needed), no floating-point currency math.
- `UNKNOWN` = not confirmed; `NO_EXPENSE` = explicitly confirmed zero; `RECORDED` = actual amount supplied.
- Define timezone and day/week boundaries consistently (Vietnam local date for user-facing periods).
- Monthly comparison must mark incomplete check-in data and should not silently fill missing expense amounts with zero.
- Add foreign keys, indexes for `(user_id, month_start)` and relevant record date columns.

## Security decisions to make

- Authentication: Flask-managed session or Supabase Auth? **Proposed: Flask-managed server sessions; not implemented.**
- Flask backend must always verify ownership for user data. Do not accept arbitrary user IDs on queries.
- Supabase database credentials must stay server-side and out of the repo. Supabase Data API exposure and RLS roles require separate review (do not assume that having Supabase automatically enforces per-user authorization for a server-side SQLAlchemy connection).

## Migration workflow (after first model is approved)

```bash
flask --app app db init    # only once in the repository; commit generated folder
flask --app app db migrate -m "create initial models"
# Read/edit the generated migration BEFORE applying
flask --app app db upgrade
```

Never apply unreviewed migration to a shared project DB. Don't use `db.create_all()` as a substitute for later schema changes.
