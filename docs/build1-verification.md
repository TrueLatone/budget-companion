# Build 1 integration verification — 3 November 2026

## Scope and repository state

Target: `integration/pa2-20261031` in `TrueLatone/budget-companion`.
The working tree was clean at inspection; no existing work was discarded.
The audited integration HEAD was
`f5c08dd439c83227d898a45620ad960d48262c87`.
Fetched `origin/main` was
`e0399901abb4f8bc91398cc51c04365973c00737`, an ancestor of the integration
branch with eight additional integration commits. Main contained the shared
schema, not the completed Budget/Expense/Recommendation/Workspace integration.
No checkout, reset, force-push, schema replacement or main merge was used.

Integrated history includes Nhan's KAN-21 commit `5b31a1d`, Budget contract repair
`3c1b55d`, KAN-23 `b4bdb9a`, restored Budget core `7326e2c`, Calendar handoff
`5cb0b0a`, KAN-27 `e0e6813` and KAN-25 `f5c08dd`. The verification commit adds
acceptance coverage, documentation and the narrow edit-form correction below.

## Verification environment and commands

Windows, Python 3.12.2, Flask 3.1.3, SQLAlchemy 2.1.6, Flask-Migrate 4.1.0,
WTForms 3.3.1 and pytest 9.2.0 using the repository's `.venv`.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q tests/test_build1_integration.py tests/test_budgets.py
node --check app/static/js/workspace.js
node --check app/static/js/dashboard.js
node --check app/static/js/budget-setup.js
git diff --check
```

Baseline full suite: **450 passed, 0 failed, 170 warnings in 57.27s**.
Focused verification after the fix: **48 passed, 0 failed, 62 warnings in 6.14s**.
Final full suite: **458 passed, 0 failed, 214 warnings in 57.63s**.
Eight new cases (three acceptance checks and five edit-form cases) passed.
Warnings are deprecations for WTForms tuple choices, Flask-Migrate's engine
accessor and Python 3.12's SQLite date adapter; none are test failures.
JavaScript syntax checks and `git diff --check` also passed.

All database verification used explicitly configured disposable SQLite files or
the existing isolated pytest fixtures. No production database was read, seeded,
reset or migrated for debugging. The new acceptance fixture uses actual Alembic
`upgrade()`, not `db.create_all()`.

## Startup, routes and schema

- Actual HTTP startup on a loopback ephemeral port passed both health endpoints,
  landing/auth pages and Workspace/Dashboard assets. Anonymous financial page
  requests redirect to login. Startup created no sample users/months/transactions.
- All seven blueprints register: core, accounts, budget_periods, budgets,
  expenses, dashboard and recommendations. Flask's route listing succeeds;
  all 40 rules (including static) resolve to registered views without duplicate
  path/method registrations. Authenticated GETs cover all financial modules,
  saved-plan/detail pages, expense edit/history/calendar views and analysis JSON.
- Exactly 13 canonical SQLAlchemy mappers/tables, one mapper per table and one
  SQLAlchemy extension instance. No legacy duplicate Expense models activated.
  All mapped primary keys and foreign keys use UUID types.
- Single Alembic head: `19a01e000002`. The chain is
  `de12e989405f → 19a01e000001 → 19a01e000002`.
  Empty-database upgrade succeeds, foreign keys are enabled and metadata/schema
  comparison reports no differences. Existing migration regressions also cover
  legacy row preservation and offline PostgreSQL SQL compilation.
- A fresh factory instance reopens the same migrated file, upgrades again at
  head, reauthenticates and replays the original purchase without changing any
  saved financial record. No new migration or canonical model change was needed.

## Authenticated acceptance scenario

`tests/test_build1_integration.py` executes the following through Flask requests
with CSRF enabled, real registration/password login and a frozen 3 November
2026 clock. All amounts below are explicitly submitted synthetic test inputs
in the disposable account, not application defaults or seeded live activity.

1. Register → login → create October 2026 Budget Month with 5,000,000 VND.
   Empty Dashboard/Budget/Expense/Recommendation GETs create no financial rows.
2. Explicitly apply Rent/Electricity/Water/Food/Transportation suggestions twice;
   five expenses exist once. Add one custom P2 expense. Missing Food estimate
   remains NULL, not zero. Separate regression tests cover saved zero values.
3. Generate and compare Saving/Balanced/Lifestyle: three persisted plans and 18
   allocations. Each plan's allocations plus planned savings equal 5,000,000 VND.
4. Confirm Balanced from stored allocations; submitted allocation edits are
   ignored. Plan confirmation alone creates no tasks. The Expense page explains
   the missing schedule and offers its explicit POST action.
5. Create the confirmed plan's schedule: **40 UUID-linked tasks**, including
   31 daily Food tasks, five Transportation periods and four monthly tasks.
   Every allocation equals the sum of its original task limits exactly.
   Daily Food is discoverable on all 31 Calendar dates. Existing scheduler and
   presentation tests cover weekly/monthly coverage, due dates and tracking starts.
6. Record a 123,456 VND Food purchase twice with the same token: one transaction.
   Changed amount with the same token returns 409. Explicit NO_EXPENSE on another
   task creates no zero-valued transaction. Dashboard shows observed spending
   of 123,456 VND and unknown remaining allocation while check-ins are missing.
7. Request analysis: **SKIPPED_INSUFFICIENT_DATA**, no saved personalized
   recommendations, explicit reasons and separate baseline guidance. F18 is
   unchanged; the application invents no transactions to make this eligible.
8. Explicitly submit enough test purchases/check-ins for F18: ten complete
   transactions, three categories and 31 days of coverage, with no unresolved
   due tasks. Generation returns **SUFFICIENT**, explainable saved read-only
   suggestions and stable IDs on repeated requests. ACCEPT returns 409 and does
   not change allocations/tasks/transactions.
9. Dashboard now shows **4,360,000 VND planned spending**, **640,000 VND planned
   savings**, **1,730,456 VND observed spending** and **2,629,544 VND remaining
   allocation** with complete check-ins. No allocation or task is counted twice.
10. Refresh all financial pages, re-confirm, re-schedule and repeat analysis:
    IDs, task limits, confirmed allocations and all ten transactions survive.
    Regenerating a confirmed month is rejected with 409.
11. Try every registered POST without CSRF: 400 and no financial change.
    A separately registered user's requests for the owner's month, schedule or
    recommendation return 404 even when submitting the owner's user_id.
12. Restart the factory/session against the same migrated database, login again,
    replay the first transaction and open each financial page in EN/VI:
    all records and totals remain unchanged.

The existing suite additionally verifies FUNDS_ADDED exclusion, unexpected
spending, expense corrections/deletion, unknown versus NO_EXPENSE, mandatory P0
and P1 minimums, one-confirmed-plan constraints, cross-user writes, meal rounding,
exact BIGINT/VND arithmetic and recommendation decisions.

## Browser and translations

Fresh headless Chrome used an isolated temporary profile and a migrated
disposable database populated by the acceptance requests above. Dashboard,
Budget, Expenses and Recommendations passed **16 combinations**: EN/VI at
1440px desktop and 390px mobile. No horizontal document overflow; every Workspace
link retained the selected month. Mobile sidebar open/Escape and Dashboard
history dialog worked. Vietnamese Dashboard/Expense mobile screenshots were
visually inspected. Injecting financial prototype localStorage values did not
change the real 1,730,456 VND spending total. Test server/browser were stopped.

This confirms language switching and layout, not complete translation coverage:
Expense/Recommendation content and some validation/flash messages still contain
English. Financial state comes only from canonical database records.

## Defect fixed and files changed in this verification

Opening an existing Budget expense edit form crashed when WTForms applied
`value.strip()` to an integer estimate or P1 minimum. Amount filters now strip
only strings, preserving saved integers, NULL and explicit zero. Five HTTP
round-trip cases cover P0 amounts, P1 unknown/minimum and P2 zero; confirmed-plan
locking and all financial services remain unchanged.

- `app/modules/budgets/forms.py`: integer-safe edit form filters.
- `tests/test_budgets.py`: five saved-value edit/round-trip regressions.
- `tests/test_build1_integration.py`: migrated schema/route/startup gate and
  full authenticated workflow, security, retries and persisted-record checks.
- `README.md`, `docs/api-contracts.md`, `docs/README.md`, this report: accurate
  implemented/partial/illustrative scope, required startup migrations and limits.

## Remaining limitations and release conditions

| Area | Current boundary |
|---|---|
| Recommendation decisions | Saving/dismissing guidance works; financial ACCEPT/automatic adjustments are disabled (409). Confirmed allocations remain immutable. |
| F18 | Fixed 10 complete transactions / 3 categories / 30 inclusive days / 80% completeness, plus valid schedule/check-ins. Short tracking periods and February cannot meet 30 days in this month-scoped implementation; baseline guidance is returned honestly. |
| Financial meaning | Dashboard savings are planned, funds are user-entered, and missing spending is unknown. There is no bank balance or verified saved-money workflow. |
| Scheduling | Explicit POST after confirmation; no financial writes on Calendar GET. Original limits conserve allocations and retries preserve existing check-ins/current limits. |
| Illustrative features | Optional unsaved Load Example and 30/40/30 Food meal guidance only; meals create no additional allocations/tasks/transactions. Live ui_demo/localStorage financial persistence is absent. |
| Later functionality | Funds additions, alerts, cross-month reports/recurring copying, shared living, LLM advice and Help are not implemented. Reload retrieves fresh data; no live event subscription. |
| Localization | Shared Workspace/Dashboard/Budget support EN/VI; remaining mixed Expense/Recommendation and validation prose needs completion. |
| Deployment validation | Live Supabase/PostgreSQL migrations, concurrent-client behavior and deployment credentials/HTTPS settings still need validation in an authorized staging environment. Offline PostgreSQL SQL checks are not a live PostgreSQL test. |
| CI | No repository GitHub Actions workflow is configured; these are local verification results, not claimed remote CI success. |

No blocking SQLite Build 1 workflow failure remains after the edit-form fix.
Push only the verified integration branch, prepare a PR targeting main, and keep
the final main merge subject to explicit approval after review of the results
and complete diff. Do not enable automatic merging or bypass branch protection.
