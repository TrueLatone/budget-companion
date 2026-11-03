# KAN-25: live Workspace and Dashboard integration

Target: `integration/pa2-20261031`, initially clean at
`e0e6813b17513d0720d48cd13dd67d0bc2f4d570`.
Fetched UI source: `feature/UI` at
`762ae29ccf768bde63eae2abceb526d4d3d7c5aa`.

Reviewed the source Budget/Dashboard routes, base/workspace/Budget/Dashboard
templates, both JavaScript files, ui_demo.py, icons, translations, CSS and UI
documentation against the verified KAN-21/KAN-23/KAN-27 integration.

## Design retained, data paths replaced

Thien's sidebar, top bar, typography, purple palette, rounded cards, Budget
editor/summary columns, Dashboard metrics, four-color donut, P0/P1/P2 progress,
recent-transaction feed, history dialog, responsive CSS and EN/VI labels are
reused. The mobile sidebar retains focus management, overlay and Escape handling.

The source routes rendered anonymous ui_demo snapshots, and its JavaScript wrote
financial plans, transactions and day check-ins to localStorage. Those routes
and financial scripts were not activated. The live implementation has no
ui_demo.py, defaultPlan JSON or browser financial persistence. Old browser preview
keys are ignored and left untouched; they are not imported, cleared or treated
as authoritative user records. No demo preview is shipped in this integration.

| Page | Live connection |
|---|---|
| `/dashboard` | Authenticated owned month, confirmed plan/allocations, actual records, completeness and task states |
| `/budget`, month/setup/plan/expense pages | Original canonical forms and services inside the Workspace layout; editable setup, read-only saved plan totals |
| `/expenses`, `/expenses/history` | Existing scheduled tasks, calendar, check-ins and history inside the same layout |
| `/recommendations` | Existing KAN-27 real-data analysis and save/dismiss actions inside the same layout |

Budget uses pages/budget.html as a layout around the verified expense-entry and
plan-comparison blocks. The summary shows the confirmed plan, or clearly labels
the Balanced generated candidate as an unconfirmed draft. Available funds are
edited through the existing authorized Budget Month form. Generated allocations
cannot be edited in the browser or at confirmation. Suggestions/examples, P0/P1
validation, unknown estimates, three plans and confirmation/scheduling remain.

Dashboard Add expense and check-in actions link to the canonical Expense page,
where records and task-specific NO_EXPENSE are submitted with the existing CSRF
and idempotency protections. Dashboard does not fake a whole-day NO_EXPENSE or
implement competing transaction writes. The history dialog is a read-only
enhancement of a real Expense history link and works with server-rendered records.

## Dashboard monetary contract

All money is integer VND and all model IDs/FKs remain UUID. Dashboard is read-only.

| Display | Calculation / meaning |
|---|---|
| Monthly budget | Sum of the owned CONFIRMED BudgetAllocations once; unknown without confirmed allocations |
| Planned savings | The confirmed BudgetPlan.planned_savings target; separate from spending and unallocated funds |
| Saved plan total | Confirmed expense allocations + planned savings; independent of later funding edits |
| Recorded spending | Actual PLANNED + UNEXPECTED records in the tracked month; FUNDS_ADDED excluded |
| Remaining in plan | Confirmed expense allocations minus observed spending, only when the canonical Expense completeness check passes and schedule state is READY; otherwise NULL/Unknown |
| P0/P1/P2 progress | Each group's confirmed allocations versus actual transactions with that priority; PLANNED priority falls back only to its real BudgetExpense |
| Available funds | BudgetMonth.available_vnd, the saved funding input; it is not a live bank balance or remaining allocation |
| Funds outside saved plan | max(available funds - saved plan total, 0); savings are already reserved and never counted again here |
| Funding shortfall | max(saved plan total - available funds, 0), not overspending |

Without a confirmed plan, current month funds are unallocated, and plan/savings/
remaining values stay unknown. If a legacy confirmed row has no authoritative
allocations, saved total and unallocated funds stay unknown rather than double
counting its savings. Incomplete check-ins do not establish zero spending.
Explicit NO_EXPENSE creates no expense transaction. Meals remain presentation
subdivisions of existing Food tasks and never enter totals a second time.

Scheduled task limits distribute the allocation, so they are never added to the
allocation total. The Dashboard uses original confirmed allocations for its
plan; a future adjustment consumer's current task limits are a separate contract.
Changing available funds never rewrites that plan. An observed zero transaction
sum is labeled separately from a known spending balance.

The chart uses real categories, with three leading categories plus an Other
aggregate when more than four are present. Integer largest-remainder shares sum
to exactly 100.0%; client JavaScript does no financial arithmetic. Recent records
are ordered by expense date, then UUID for deterministic same-date ties (the
canonical record has no creation timestamp). The dialog shows up to 20 records;
the history link exposes the full owned month.

## Selection, navigation and safety

Workspace navigation links Dashboard → Budget → Expenses → Recommendations using
the same owned budget_month_id. The month selector uses real owned months; source
month=YYYY-MM links remain supported by Dashboard and Budget. Explicit query
selection takes precedence over the session default. Existing explicit Budget
Month selection still uses its existing POST; viewing a page does not rewrite
financial data or silently create a month. Date-based Expense navigation stays
available. Expense history takes its workspace month from the owned end date.

All financial module pages require the original login/session. A client user_id
never authorizes anything. Foreign/invalid Dashboard months return 404; invalid
saved references return 409 without leaking private category names. The default
month fallback is also scoped to g.current_user. Existing POST routes, CSRF,
UUID ownership, task uniqueness, replay checks and confirmed-plan locking remain.

The base template gains only a navigation override block. Home/auth pages retain
their layout and language cookie behavior. All four financial modules use the
Workspace shell. Dashboard and Budget setup labels/rules are EN/VI; legacy
Expense/Recommendation content and validation prose still contain mixed English
and Vietnamese. User expense/category names and contractual English P0 names
are not renamed by translation. Server forms work without JavaScript; mobile
navigation has a noscript fallback. Help is visibly disabled as a future item;
Account and Budget Month management link to existing authenticated pages.

## Verification

Baseline: **427 passed, 152 warnings in 48.84s**.
Final command: `.venv\Scripts\python.exe -m pytest -q`.
Result: **450 passed, 0 failed, 170 warnings in 53.75s**, including 23 new
Dashboard/Workspace cases and all existing Budget/Expense/Recommendation and
migration tests. Dashboard's placeholder smoke expectation is now authenticated
access. Warnings remain the existing WTForms, Flask-Migrate engine and SQLite
date-adapter deprecation categories. `git diff --check` and the three JavaScript
syntax checks passed.
Added Dashboard/Workspace regressions cover live projections, confirmation and
scheduling, check-in refresh, NO_EXPENSE versus unknown, funds additions exclusion,
funding/savings distinction, missing tasks, invalid imported state, cross-user
isolation, escaped transaction titles, selected-month navigation, EN/VI, exact
BIGINT totals, CSRF and absence of browser financial persistence.

Browser checks used an isolated headless Chrome profile and an explicit disposable
SQLite database, never production data or a personal browser profile:

- All four modules at 1440px and 390px, both EN/VI: 16 page/viewport/language
  combinations with no document overflow and correct selected-month links.
- Mobile sidebar open/Escape close and transaction-history dialog.
- Poisoned prototype localStorage values did not change the real 1,580,000 VND
  recorded-spending total in the test database.
- Real CSRF-backed expense creation → three-plan generation → confirmation →
  schedule creation in the browser. The newly scheduled month retained zero
  observed transactions and unknown remaining spending until check-in.
- Desktop and mobile screenshots inspected; JavaScript syntax checks passed for
  workspace.js, dashboard.js and budget-setup.js. Test server/browser stopped.

No canonical models, schema, migrations, Budget financial services/rules,
Expense financial services/scheduler or Recommendation services were changed.
Live PostgreSQL verification remains a deployment check. Automatic adjustments,
fund additions, bank balances, cross-month reports and durable live-refresh/event
subscriptions are not implemented; reload after a write to retrieve current facts.

## Files and module boundaries

- Layout: `app/templates/base.html`, `workspace_base.html`,
  `components/workspace_nav.html`, `components/navbar.html`, `components/icons.html`.
- Design assets: `app/static/css/workspace.css`, `dashboard.css`,
  `app/static/js/workspace.js`, `dashboard.js`; the Budget example notice is
  localized in the existing `budget-setup.js`.
- Dashboard: `app/modules/dashboard/routes.py`, `services.py`,
  `app/templates/pages/dashboard.html`, `app/templates/dashboard/error.html`.
- Workspace helpers: `app/workspace.py` and its context-processor registration in
  `app/__init__.py`; no authentication hook or extension initialization changed.
- Budget presentation: `app/templates/pages/budget.html`, existing Budget
  index/expense/plan/error/suggestion templates, translated form labels and owned
  month selection/summary context in `app/modules/budgets/routes.py`.
- Expense and Recommendation templates inherit the shared shell and retain their
  scripts/forms; Expense history receives its selected-month presentation context.
- `app/translations.py`, `tests/test_dashboard.py`, the Dashboard smoke expectation,
  README, docs index, API contracts and this report.
