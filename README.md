# Budget Companion — Group 10

**Project:** Responsive web application for student renters to plan and monitor living expenses.  
**Source:** Vision v1.0 and Software Development Plan v1.0, 18 October 2026.  
**Status:** Sprint 2 scaffolding (20 October 2026). **Not a functional MVP yet.**

## Technical stack

- Backend: Python 3.11+, Flask, Flask Blueprints / Application Factory.
- Frontend: Jinja2 + Bootstrap 5 + vanilla JavaScript.
- ORM: Flask-SQLAlchemy; migrations: Flask-Migrate.
- Database: PostgreSQL managed by Supabase (`DATABASE_URL`).
- Local bootstrap: optional SQLite fallback; final integration needs PostgreSQL testing.
- Testing: pytest + GitHub Actions CI.

## Getting started

### 1. Prerequisites

Install Python 3.11+, Git and an editor. Clone the repository:

```bash
git clone https://github.com/TrueLatone/budget-companion.git
cd budget-companion
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate on Linux/macOS:

```bash
source .venv/bin/activate
```

### 2. Install dependencies and configuration

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`; Linux: `cp .env.example .env`).

For first boot, the example uses **local SQLite only**. To switch to the team's Supabase PostgreSQL, follow [Supabase setup](docs/supabase-setup.md). `.env` must never be committed.

### 3. Run application

```bash
flask --app app run --debug
```

Visit `http://127.0.0.1:5000`.

### 4. Basic verification

```bash
python -m pytest -q
```

Available on day 1:
- `GET /` — landing page.
- `GET /api/health` — application process health.
- `GET /api/health/database` — database connectivity.
- `/account`, `/budget`, `/expenses`, `/dashboard`, `/recommendations` — nonfunctional placeholders.

**Not implemented:** login, budgets, expenses, check-ins, alerts, dashboard statistics, AI recommendations, recurring bills, user authorization, actual database tables. Do not represent these as completed.

## Project documentation

- [Architecture](docs/architecture.md)
- [Database design — DRAFT](docs/database-design.md)
- [API contracts — DRAFT](docs/api-contracts.md)
- [Architecture Decision](docs/decisions/tech-stack.md)
- [Team contribution rules](CONTRIBUTING.md)

## Functional scope

Monthly income/budget setup; P0 mandatory bills, P1 essentials, P2 flexible Manual expense/check-in; Unknown is not zero; plan vs actual; month-over-month comparison with missing-data flags; basic rule-based recommendations; account management. Shared-living expenses are LATER.

## Team ownership

See `CONTRIBUTING.md`. Integrate via Jira tickets and code-reviewed Pull Requests.

## Key dates

- 18/10/2026: Vision & Project Plan v1.0.
- 20/10/2026: KAN-14 repository setup.
- 01/11/2026: Early demo / Build 1 (planned).
- 15/11/2026: Alpha (planned).
- 29/11/2026: Beta (planned).
- 13/12/2026: Final product (planned).
