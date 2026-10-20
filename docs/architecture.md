# Architecture — Initial design (DRAFT)

**Date:** 20/10/2026.
**Note:** Propose base structure

## 1. Context

Budget Companion is a responsive web application. The app release should track personal budgeting manually by user.

```text
Browser (Bootstrap + Jinja2 + vanilla JS)
                 |
          HTTP/JSON requests
                 |
       Flask Application Factory
          /       |        \
     Routes    Services   Shared Models
                 |        /
          SQLAlchemy ORM
                 |
        Supabase PostgreSQL
```

- `routes.py`: accept HTTP input, render Jinja templates or JSON; delegate business logic.
- `services.py`: validation and domain operations, separated from templates.
- `models/`: data storage entities agreed by the team.
- `templates/components/` and `static/`: shared frontend maintained by UI/Dashboard owner.
- `rules.py`: deterministic recommendations; do not introduce ML dependency at day 1.

## 2. Modules / ownership

| Module | Primary owner | Vision scope |
|---|---|---|
| `accounts` + application core | Thịnh | F35-F37 plus recurring schedules & reminder integration |
| `budgets` | Nhân | F01-F06, budget allocation |
| `expenses` | Tuấn Anh | F07-F13 check-ins, records and payment confirmations |
| `dashboard` | Thiện | F28-F34 statistics, comparisons, reports and shared layout |
| `recommendations` | Khiêm | F14-F20, with basic rule-based recommendation first |

## 3. Domain

1. Budget periods are **calendar months**, currency **VND**.
2. Reserve **P0** before allocating money to P1/P2
3. If money cannot cover P0 + P1 minima, report shortfall. Don't save an unrealistic plan as valid.
4. Check-in statuses distinguish `UNKNOWN`, `NO_EXPENSE`, `RECORDED`, missing values are not counted as zero.
6. Recommendations should explain input and request acceptance only, don't auto-change budget.
7. Month-over-month reports must flag missing records, not claim false zero spending.
8. Track a single expense exactly once, even when created through check-in or recurring payment.

## 4. Initial build limitations

- No real account system or feature endpoints yet.
- Local SQLite is for testing. We will use Supabase for database integration..
