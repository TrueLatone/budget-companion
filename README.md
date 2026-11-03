# Budget Companion — Group 10

**Project:** Responsive web application for student renters to plan and monitor living expenses.  
**Source:** Vision v1.0 and Software Development Plan v1.0, 18 October 2026.  
**Status:** Build 1 integration on `integration/pa2-20261031`, verified 3 November 2026.
KAN-21, KAN-23, KAN-27 and KAN-25 share the authenticated application and database.
See the [final verification and limitations](docs/build1-verification.md) before deployment.

## Technical stack

- Backend: Python 3.11+, Flask, Flask Blueprints / Application Factory.
- Frontend: Jinja2 + Bootstrap 5 + vanilla JavaScript.
- ORM: Flask-SQLAlchemy; migrations: Flask-Migrate.
- Database: PostgreSQL managed by Supabase (`DATABASE_URL`).
- Local verification: SQLite; live PostgreSQL/Supabase testing remains a deployment gate.
- Testing: pytest. No GitHub Actions workflow is configured in this repository yet.

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

Copy `.env.example` to `.env` only if `.env` does not already exist
(PowerShell: `Copy-Item .env.example .env`; Linux: `cp -n .env.example .env`).
Replace the example `FLASK_SECRET_KEY` with a generated secret, for example from
`python -c "import secrets; print(secrets.token_hex(32))"`.

For first boot, the example uses **local SQLite only**. For PostgreSQL, set
`DATABASE_URL` to the team's authorized database connection string; generic
`postgres://` and `postgresql://` URLs are normalized to the psycopg 3 driver.
`.env` must never be committed. For HTTPS deployment, disable debug mode and set
`SESSION_COOKIE_SECURE=true`.

### 3. Migrate and run application

```bash
flask --app app db upgrade
flask --app app run --debug
```

Visit `http://127.0.0.1:5000`. Run migrations against the intended database before
startup; application startup does not create tables or seed financial records.

### 4. Basic verification

```bash
python -m pytest -q
```

The suite uses disposable databases. The Build 1 acceptance test also migrates a
fresh file, exercises authenticated forms with CSRF enabled, restarts the factory
against that file and verifies record preservation. It never resets live data.

## Build 1 implementation status

| Area | Status | Available behavior / boundary |
|---|---|---|
| Accounts and months | Completed core | Register, login, owned UUID month selection, integer VND funding input |
| Budget (KAN-21) | Completed core | Explicit suggested/custom expenses, optional examples, three plans, immutable confirmation |
| Expenses (KAN-23) | Completed core | Explicit schedule creation, calendar, actual/unexpected purchases, NO_EXPENSE, corrections and replay protection |
| Recommendations (KAN-27) | Partial product scope | Real-data F18 analysis and explainable read-only guidance; ACCEPT financial adjustments disabled |
| Workspace and Dashboard (KAN-25) | Completed core | Shared owned-month navigation, confirmed plan/savings, observed spending and completeness-aware remaining allocation |
| EN/VI | Partial | Shared navigation, Dashboard and Budget translated; some Expense/Recommendation/validation prose remains mixed |
| Prototype examples | Illustrative only | Load Example fills unsaved inputs; optional meals subdivide Food without extra records; no live financial localStorage/ui_demo |
| Later functions | Not implemented | Funds additions, automatic reallocation, alerts, cross-month reports/copying, LLM advice, bank integration and Help |

Available:
- `GET /` — landing page.
- `GET /api/health` — application process health.
- `GET /api/health/database` — database connectivity.
- `/register`, `/login`, `/logout`, `/account` — basic session authentication.
- `/budget-periods` — calendar-month setup and selection.
- `/budget` — authenticated monthly expense setup, generated plans and confirmation (KAN-21).
- `/expenses`, `/expenses/history` — authenticated scheduling, spending, check-ins and history (KAN-23).
- `/recommendations` — authenticated spending analysis, F18 completeness and read-only guidance (KAN-27).
- `/dashboard` — authenticated monthly overview, real spending, savings, check-in completeness and owned recent transactions (KAN-25).

**Not implemented:** automatic reallocation, funds additions, alerts,
cross-month dashboard reports, LLM recommendations, and cross-month recurring bill copying. Do not
represent these as completed.

Budget Planning persists UUID-linked plans and integer VND allocations in the
shared database. Open **Plan budget** from a budget month to begin. See the
[KAN-21 integration contract](docs/kan21-budget-planning.md) for rules and the
Expense Planning handoff.

Budget setup now offers explicit suggested expenses and optional **Load Example**
amounts, inline custom expense entry, and P0/P1/P2/Savings plan comparison.
Examples are never saved automatically. Confirmed daily Food tasks offer optional
30/40/30 meal guidance without adding transactions or duplicating limits. See
the [before/after Budget parity audit](docs/budget-core-parity.md).

After confirming a Budget plan, open **Expenses & check-in for this month** and
choose **Create / verify spending schedule**. Monthly totals are distributed
across eligible dates without duplication. Record positive purchases or explicitly
confirm **NO_EXPENSE**; missing check-ins remain Unknown. See the
[KAN-23 contract](docs/kan23-expense-planning.md) for scheduling and retry rules.

Confirming a plan now opens its Expense month with explicit schedule-state
guidance. Daily expenses appear in the calendar/month list; weekly/monthly
periods and bill due dates remain visible without duplicating allocations.
See the [Expense Calendar diagnosis and repair](docs/expense-calendar-integration.md).

Open **Spending analysis** after recording real expenses. KAN-27 preserves F18's
10-transaction / 3-category / 30-day / 80% thresholds and explains insufficient
data with baseline guidance. Eligible comparisons use completed scheduled periods.
Guidance can be saved or dismissed; financial ACCEPT adjustments are disabled.
See the [KAN-27 contract](docs/kan27-spending-analysis.md) for JSON routes and limits.

The [KAN-25 Workspace integration](docs/kan25-workspace-dashboard.md) preserves
Thien's responsive design across Dashboard → Budget → Expenses → Recommendations.
Each link carries the selected owned Budget Month. Dashboard reads the shared
database; savings, unallocated funds and unknown remaining spending are separate.
No financial localStorage prototype or ui_demo data is used by live pages.

## Project documentation

- [Architecture](docs/architecture.md)
- [Database design](docs/database-design.md)
- [Entity dictionary — 13 shared entities](docs/entity-dictionary.md)
- [API contracts — implemented routes and separate proposals](docs/api-contracts.md)
- [Build 1 verification and limitations](docs/build1-verification.md)
- [Architecture Decision](docs/decisions/tech_stack.md)
- [Team contribution rules](CONTRIBUTING.md)

## Functional scope

Build 1 supports monthly budget setup, P0 mandatory bills, P1 essentials, P2
flexible spending, manual expense/check-in, plan versus observed actual and
rule-based guidance. Unknown is not zero. Planned savings are not verified bank
savings, and available funds are user-entered funding rather than a bank balance.
Month-over-month reports and shared-living expenses remain later work.

## Team ownership

See `CONTRIBUTING.md`. Integrate via Jira tickets and code-reviewed Pull Requests.

## Key dates

- 18/10/2026: Vision & Project Plan v1.0.
- 20/10/2026: KAN-14 repository setup.
- 31/10/2026: Integration deadline.
- 03/11/2026: Build 1 integration verification; merge remains subject to review.
- 15/11/2026: Alpha (planned).
- 29/11/2026: Beta (planned).
- 13/12/2026: Final product (planned).
