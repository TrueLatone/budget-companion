# Initial database design

Only template for designing Database

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
