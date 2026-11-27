# Budget Companion — Group 10

**Project:** Responsive web application for student renters to plan and monitor living expenses.  
**Status (27 November 2026):** Build 3 candidate merged to main through PR #15
at `d61475d`. The prior verification of runtime source `bdb4825` recorded
**564 passing automated tests**. The Beta release and PA4 designed-case coverage
remain pending.

| Build | Verified source/history | Status |
|---|---|---|
| Build 1 | `3d742a9`, merged through PR #7 on 3 November | Earlier integrated baseline; [original evidence](docs/build1-verification.md) |
| Build 2 Core Alpha | Main `871aee6`, 7 November; planned milestone 15 November | [Retrospective](docs/build2-retrospective.md), no published Release |
| Build 3 Beta candidate | `bdb4825`, 26 November; PA4 due 29 November | [Verification and limitations](docs/build3-verification.md); not a published Beta |

KAN-21/23/25/27 plus KAN-71/63 and KAN-59 share authenticated ownership and
the canonical database. See the [changelog](CHANGELOG.md) and
[PA4 component testing scope](docs/pa4-test-coverage-matrix.md).

## Technical stack

- Backend: Python 3.11+, Flask, Flask Blueprints / Application Factory; current verification uses Python 3.13.14.
- Frontend: Jinja2 + Bootstrap 5 + vanilla JavaScript.
- ORM: Flask-SQLAlchemy; migrations: Flask-Migrate.
- Database: PostgreSQL managed by Supabase (`DATABASE_URL`).
- Local verification: SQLite; live PostgreSQL/Supabase testing remains a deployment gate.
- Testing: pytest. No GitHub Actions workflow is configured in this repository yet.

## Getting started

### 1. Prerequisites

Install Python 3.11+, Git and an editor. If an existing virtual environment points
to a removed interpreter, create a new environment. Clone the repository:

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
python -m flask --app app db heads
python -m flask --app app db upgrade
python -m flask --app app run --debug
```

Visit `http://127.0.0.1:5000`. Run migrations against the intended database before
startup; application startup does not create tables or seed financial records.
The candidate has one migration head, `19a01e000003`. It assigns legacy months
`planning_unit=1` and defaults new periods to `1000`, preserving saved funds,
plans, tasks and transactions. Verify migrations on disposable SQLite or an
authorized PostgreSQL staging database before deployment. Never use the live
team database for test resets/seeds. `run-local.cmd` also invokes a bulk schedule
completion command; the explicit commands above provide the reviewed setup path.

### 4. Basic verification

```bash
python -m pytest -q
python -m pytest -q tests/test_pa4_integration.py tests/test_migrations.py tests/test_build1_integration.py
```

The suite uses disposable databases. The Build 1 acceptance test also migrates a
fresh file, exercises authenticated forms with CSRF enabled, restarts the factory
against that file and verifies record preservation. It never resets live data.

## Current implementation status

| Area | Status | Available behavior / boundary |
|---|---|---|
| Accounts and months | Core available | Register/login/logout, owned UUID periods, new-period 1,000-VND planning increments, funds locked after generating plans |
| Budget (KAN-21/KAN-71) | Core verified | Suggested/custom entries, three plans, separate MANUAL draft, immutable confirmation with atomic automatic scheduling; actual purchases remain integer VND |
| Expenses (KAN-23) | Core verified; UI limitations | Calendar, actual/unexpected purchases, NO_EXPENSE, corrections and replay protection; payment/scope controls and history ordering need owner work |
| Recommendations (KAN-27/KAN-59) | Partial product scope | F18 10/3/30/80% gates; incomplete records reported/excluded; sufficient valid evidence can personalize; ACCEPT changes status only |
| Workspace and Dashboard (KAN-25) | Completed core | Shared owned-month navigation, confirmed plan/savings, observed spending and completeness-aware remaining allocation |
| EN/VI | Partial | Shared navigation, Dashboard and Budget translated; some Expense/Recommendation/validation prose remains mixed |
| Prototype examples | Illustrative only | Suggested expense estimates start blank; optional meals subdivide Food without extra records; no live financial localStorage/ui_demo |
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
[KAN-21 integration contract](docs/architecture/components/kan21-budget-planning.md) for rules and the
Expense Planning handoff.

Select suggested expenses, enter amounts, and optionally add a custom expense.
**Generate three plans** saves the entries and opens the plan comparison.
See the [earlier Budget parity audit](docs/architecture/components/budget-core-parity.md) for background.

Confirmation creates the initial spending schedule and opens Expense Planning
for the selected month. Record purchases or explicitly confirm **NO_EXPENSE**.
Repeat confirmation preserves task IDs and recorded activity; a scheduling
failure rolls back confirmation. The explicit schedule POST remains available
for verification/completion of legacy confirmed months. See the
[current API contract](docs/architecture/api-contracts.md) for the approved Build 3 behavior.

Confirming a plan now opens its Expense month with explicit schedule-state
guidance. Daily expenses appear in the calendar/month list; weekly/monthly
periods and bill due dates remain visible without duplicating allocations.
See the [Expense Calendar diagnosis and repair](docs/architecture/components/expense-calendar-integration.md).

Open **Spending analysis** after recording real expenses. KAN-27 preserves F18's
10-transaction / 3-category / 30-day / 80% thresholds and explains insufficient
data with baseline guidance. Eligible comparisons use completed scheduled periods.
Guidance can be saved or dismissed; financial ACCEPT adjustments are disabled.
Invalid transactions still appear in completeness issues and its denominator;
other readiness gates must pass. F19 reliable month-end totals have stricter
completion rules than personalized readiness. See the
[current API contract](docs/architecture/api-contracts.md); older integration reports retain
their historical context.

The [KAN-25 Workspace integration](docs/architecture/components/kan25-workspace-dashboard.md) preserves
the responsive design across Dashboard → Budget → Expenses → Recommendations.
Each link carries the selected owned Budget Month. Dashboard reads the shared
database; savings, unallocated funds and unknown remaining spending are separate.
No financial localStorage prototype or ui_demo data is used by live pages.

## Project documentation

Start with the [documentation index](docs/README.md) for the PA1–PA3 baseline,
architecture and revision history. The [testing guide](docs/testing/README.md)
links the PA4 templates and Build 3 component workspaces for execution, results,
defects and reviewed evidence. Official academic artifacts are maintained
separately in restricted project storage. See the [pytest guide](tests/README.md) for the automated suite.

- [Architecture](docs/architecture/architecture.md)
- [Database design](docs/architecture/database-design.md)
- [Entity dictionary — 13 shared entities](docs/architecture/entity-dictionary.md)
- [API contracts — implemented routes and separate proposals](docs/architecture/api-contracts.md)
- [Build 1 verification and limitations](docs/build1-verification.md)
- [Build 2 retrospective](docs/build2-retrospective.md)
- [Build 3 verification and limitations](docs/build3-verification.md)
- [PA4 component testing scope](docs/pa4-test-coverage-matrix.md)
- [Changelog](CHANGELOG.md)
- [Architecture Decision](docs/decisions/tech_stack.md)
- [Team contribution rules](CONTRIBUTING.md)

## Functional scope

The integrated candidate supports monthly budget setup, P0 mandatory bills, P1 essentials, P2
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
- 03/11/2026: Build 1 integrated through PR #7.
- 15/11/2026: Core Alpha planned milestone, documented retrospectively.
- 26/11/2026: Build 3 candidate verified; review/Release pending.
- 29/11/2026: PA4 due; Beta planned.
- 13/12/2026: Final product (planned).
