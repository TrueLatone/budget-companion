# Budget integration verification — 31 October 2026

## Branch and history

- Work branch: integration/pa2-20261031, already present locally; no corresponding
  remote branch was found after fetching all remotes and querying GitHub.
- Verified origin/main: e0399901abb4f8bc91398cc51c04365973c00737.
- Local main remains at 9297bcc5df20bf8254d6a86bcb164ccd0eaa40f5; it was not changed.
- Starting integration HEAD: cf74b1c504f591c72420bdb3fb38bde73dec9648.
- Nhan's fetched feature HEAD: 5b31a1dfbf838927b99f5224d3b4fae0f692123a.
  Its parent is cf74b1c; the Budget implementation was therefore already in the
  integration branch. A fast-forward merge preserved both commits with no
  conflicts, rewriting, cherry-picking or replacement implementation.
- The only initially uncommitted change was deletion of
  docs/kan21-budget-planning.md. A binary Git patch was saved in the session's
  temporary directory before merging. No reset, clean or force operation ran.
- No push or merge into main was performed. The follow-up integration commit
  contains documentation recovery, a small read-only handoff and verification
  tests; the existing Budget algorithm/routes/forms/templates are retained.

## Documentation deletion investigation

Commit 5b31a1d deletes only the 79-line integration document and leaves its links
in README, API contracts, database design and budget rules unchanged. Its message
does not explain the deletion; intent cannot be established from Git history.
The prior contents still describe the implementation accurately. They were
restored from cf74b1c (blob 0eadeb5c9ec656cc9308fd4639c97db4fe5ae72f), then
extended with the confirmed-allocation interface and proposed Expense schedule
contract. All four existing references now resolve to an existing file.

## Verification results

Command: `.\.venv\Scripts\python.exe -m pytest -q`.

| Run | Exact result |
|---|---|
| Nhan's merged implementation, before integration follow-up | 222 passed, 120 warnings in 18.26s |
| Focused Budget rules/services/routes after handoff additions | 73 passed, 10 warnings in 1.78s |
| Final full suite | 230 passed, 120 warnings in 17.57s |

No tests failed. Warnings concern legacy WTForms SelectField tuple choices,
Flask-Migrate's deprecated get_engine call and the SQLite date adapter. Tests
use SQLite, including an upgrade-created database; the existing PostgreSQL test
compiles migration SQL offline. Live PostgreSQL locking/concurrency and browser
interaction were not verified in this pass.

Verified behavior:

- Authenticated month selection through the existing session, explicit owned
  month routes and ownership-scoped queries; inaccessible month/plan/item IDs
  are rejected and client-submitted user IDs never authorize access.
- Expense creation, editing and removal; owned/built-in categories; priority,
  optional estimates/minimums, frequency, recurring flag and monthly due day.
- Required positive Rent/Electricity/Water P0 values; optional Internet as P0;
  optional positive P1 minimums; positive included P1/P2 allocations and shortfall
  rejection; Saving/Balanced/Lifestyle generation using the existing ratios.
- BudgetPlan/BudgetAllocation saving and loading in another SQLAlchemy session,
  exact conservation, stale-funds and invalid-allocation rejection, rollback,
  repeat-safe confirmation and one confirmed plan per month. Confirmed setup
  stays locked while later funds edits preserve the original plan total.
- Cross-user month/item/plan/category isolation, including corrupt foreign
  references; CSRF rejection on all five mutation types and acceptance of a valid
  form token in the existing flow; UUID links and integer arithmetic through
  BIGINT-limit rule tests; NULL estimates distinct from explicit zero.
- get_confirmed_allocations(user_id, month_id) returns only the owned month's
  confirmed allocations, excludes drafts and creates no tasks. It rejects
  unauthorized months/categories. No full Expense module was implemented.

The canonical models, application factory, extensions, authentication files,
migrations and requirements have no diff against origin/main.

## Changed files

The inherited KAN-21 implementation changes these 17 files relative to main:

- app/modules/budgets/forms.py, routes.py, rules.py and services.py.
- app/templates/budgets/error.html, expense_form.html, index.html and plan.html.
- app/templates/budget_periods/index.html.
- tests/test_budget_rules.py, test_budgets.py, test_i18n.py and test_smoke.py.
- README.md, docs/Budget-Model-and-Rules.md, docs/api-contracts.md and
  docs/database-design.md.

This verification adds/changes five files relative to Nhan's HEAD:

- app/modules/budgets/services.py: confirmed-only, month-scoped read accessor.
- tests/test_budgets.py: eight additional confirmed-handoff/CSRF cases.
- docs/kan21-budget-planning.md: restored contract, extended scheduling guidance.
- docs/api-contracts.md: internal read interface documented; existing links fixed
  by restoring their target.
- docs/integration-pa2-budget-verification.md: this evidence and findings.

## Expense dependencies and recommended next action

The integration branch's Expense module remains a placeholder. Its future
adapter must call get_confirmed_allocations using the authenticated user and
owned month, then create canonical AssignedExpenseTask rows with allocation UUID
FKs. The [handoff contract](kan21-budget-planning.md) specifies proposed scheduler
interfaces, inclusive daily/weekly/monthly periods, exact integer splitting,
initial task/payment fields, sum invariants and repeat-safe insertion. A monthly
allocation must be divided among periods, never repeated for every occurrence.

Before merging KAN-8, fix its source's ignored date window and task queries'
missing confirmed-plan filter, remove anonymous demo identity and unsafe demo
cleanup, and avoid importing its incompatible legacy models. Its existing
weekly occurrence helper requires a weekday that the canonical model does not
store; spending-period scheduling must use the agreed period policy instead.

Agree whether allocations cover the full month or only the tracking interval,
and how bills due before tracking start are handled. Test zero-limit tasks
without treating them as confirmed NO_EXPENSE or inserting zero transactions.
Then implement/review the narrow scheduler in KAN-8, with conservation,
idempotency and cross-user tests, and verify PostgreSQL behavior before demo
deployment. No Expense code should modify original Budget allocations.

Budget limitations remain: English new labels and mandatory names, no manual
allocation editor, no original-plan replacement workflow, and no live
PostgreSQL concurrency evidence. These are follow-ups, not failing tests in this
verification. Review this integration branch and the period/bill policy before
starting Expense integration; publishing and merging main remain separate steps.
