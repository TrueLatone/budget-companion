# KAN-27: rule-based spending analysis integration

Target: `integration/pa2-20261031`, base
`5cb0b0a9dc61e398cb31e7476b24ddcd5ebb0ca0` (clean working tree).
Fetched source: `feature/recommendations-f16-f19` at
`3e6c3bc229c7f25a64f006389480e2ca011a41ba`.
Reviewed its complete four-file diff: module initialization, rules, services and
routes. Integrated compatible logic selectively rather than merge older shared
application code. The application factory already registers this blueprint;
the source package's extra blueprint import is unnecessary.

## Demonstrable workflow

1. Log in, create/select a Budget Month and use the existing Budget setup,
   generation and confirmation flow. Create its Expense schedule with the existing
   authenticated POST and record actual purchases or explicit NO_EXPENSE check-ins.
2. Open **Spending analysis** in signed-in navigation (`/recommendations`), select
   an owned month and inspect observed facts, completeness and explainable guidance.
3. **Analyze and save guidance** explicitly persists eligible read-only observations
   as canonical Recommendation rows. GET analysis never creates financial records,
   schedules, recommendations, users or months.
4. Dismiss saved guidance with an authenticated CSRF-protected POST. Dismissal
   changes only Recommendation.status. Unchanged generation requests reuse saved
   UUIDs and retain dismissed status rather than creating repeated proposals.

All IDs/FKs remain UUID; financial amounts remain integer VND. No canonical
models, Budget/Expense services, scheduler, authentication, dependencies or
migrations were changed. Navbar integration and the Recommendation placeholder
smoke expectation are the only changes outside the Recommendation implementation,
its tests and documentation.

## Source logic retained and corrected

- F18 thresholds remain **10 complete actual transactions, 3 actual categories,
  30 inclusive calendar days from earliest to latest actual transaction, and 80%
  completeness**. The source's no-unresolved/no-incomplete safeguards remain.
- Complete items are valid actual transactions plus consistent explicit NO_EXPENSE
  tasks. The denominator also includes invalid transactions, overdue unresolved
  tasks and inconsistent check-ins. NO_EXPENSE does not invent a transaction,
  category or date span; a contradictory NO_EXPENSE-with-purchases task receives
  no zero-spending credit.
- Missing check-ins are evaluated after **period_end**, not assigned_date. On
  today's Vietnam date, ongoing periods are not overdue. Historical cutoff dates
  are closed days; future tasks/transactions are excluded from historical metrics.
- Ownership is resolved through authenticated BudgetMonth, the confirmed-only
  Budget accessor, Expense task reads and validated Expense transaction reads.
  Draft tasks are never a fallback data source. Tracking start is respected.
- Complete schedule validation uses the existing Expense schedule-state service;
  missing or conflicting periods prevent personalization even if transaction
  thresholds alone pass. An unscheduled category budget stays unknown, not zero.
- FUNDS_ADDED is excluded from totals, record counts, categories and coverage.
  Each real transaction is counted once; monthly task limits are not multiplied
  by days, and meal guidance is not an allocation or transaction.
- Source category thresholds of **at least 110% / at most 80%** are retained as
  review signals, using integer cross-products. Comparisons use completed task
  periods and their associated spending, plus observed unexpected spending.
  Open monthly/weekly limits are not compared with partial spending. Groups are
  separated by category **and priority**, avoiding P0/P1 overwrite within a category.
  P0 bills never receive a discretionary reduction/increase signal.
- Insufficient data returns `SKIPPED_INSUFFICIENT_DATA`, failed-check explanations,
  static baseline guidance and empty findings/recommendations. Observed amounts
  remain visible as facts without claiming missing spending is zero. Fully ready
  data with no threshold crossing returns `NO_ACTION_REQUIRED` on generation.

F19 review keeps observed spending separate from a reliable remaining-versus-plan
balance. That balance and category variances are NULL until the tracked month is
closed, schedules match and all tasks have consistent recorded/NO_EXPENSE states.
A resolved month with fewer than 10 purchases can have a known F19 balance while
still failing F18 personalized readiness. Variance is planned minus observed.

## Financial adjustments deliberately disabled

The source ACCEPT path changed future current_limit values by 10% without
verifying available funding, conservation, P0 protections or P1 minima. Its
floating-point rounding also did not preserve integer precision at BIGINT limits.
That path and calculate_new_limit were not activated. Confirmed BudgetAllocation
rows are immutable, and this ticket establishes no safe transfer/funding policy
for BudgetAdjustment/Detail. Those tables alone do not authorize a financial edit.

Every ACCEPT returns **409**, even for a legacy proposal or repeated request.
It changes no status, allocation, task, original/current limit, funds, transaction,
adjustment or adjustment detail. All payload-supplied task IDs, limits and user IDs
are ineffective. Unsafe legacy JSON proposals are withheld from detail responses.
REJECT is an idempotent metadata-only dismissal; the HTML offers no accept control.

## Routes and requests

HTML: GET `/recommendations` uses `month=YYYY-MM`, optionally an owned
`budget_month_id`, otherwise the active session month or latest owned month.
It remains a real page/navigation destination. POST `/recommendations/analyze`
accepts `month`, optional `as_of` and CSRF, then redirects to the page.
POST `/recommendations/<uuid>/dismiss` dismisses only owned guidance.

JSON routes (authenticated session, all under `/recommendations`):

| Method | Path | Request / response |
|---|---|---|
| GET | `/analysis` | `month`, optional `as_of`; current facts, F18 checks, preview and matching saved guidance |
| GET | `/completeness` | Same query; F18 metrics, issues, thresholds, failed checks |
| POST | `/generate` | JSON `month`, optional `as_of`; 201 GENERATED, otherwise 200 |
| GET | `/<uuid>` | Owned saved guidance snapshot, read-only status and staleness notice |
| POST | `/<uuid>/decision` | JSON `decision: REJECT` or `ACCEPT`; 200 dismissal or 409 adjustments disabled |
| GET | `/monthly-review` | `month`, optional `as_of`; observed totals and nullable reliable comparison |
| POST | `/monthly-review/feedback` | JSON `month`, optional integer rating 1–5 and text comment ≤2000; metadata upsert, 200 |

POST JSON must be an object. Supply the normal `X-CSRFToken` header obtained
from the signed-in page, or the HTML hidden form token. No CSRF exemption or new
identity architecture is introduced. Anonymous HTML redirects to login; anonymous
JSON returns 401 (global CSRF can reject tokenless POSTs first). Invalid inputs
return 400, inaccessible owned resources 404 and conflicting/unsafe saved state
409. Errors use `{"error": "message"}` for JSON.

Explicit `as_of` must be a real ISO date inside the month, no later than today's
Vietnam date. Default cutoff is today's date or the earlier month end; future
months return not-started baseline guidance. Historical cutoffs filter records,
but task statuses are current saved state: the canonical schema has no historical
check-in event log, so these results are not historical audit replays.

## Persistence, replay and transaction safety

Generation locks the owned BudgetMonth through the existing Budget service,
reloads authoritative data and atomically saves only Recommendation metadata.
An evidence/algorithm/cutoff fingerprint plus per-category/priority signal key
reuses unchanged guidance, including rejected guidance. Feedback and decisions
also lock the month and recheck ownership. Insert failures roll back all metadata;
financial-state snapshots are asserted unchanged by regression tests.

Changing evidence creates a new snapshot. The page shows saved guidance only
for the current eligible snapshot; it does not resurrect old recommendations
when data becomes insufficient. Individual saved-detail URLs remain accessible
to their owner and explicitly warn that current evidence may differ.

Replay tests cover sequential requests. PostgreSQL row locks serialize competing
module writes, but live concurrency has not been tested. No new unique index
was added to Recommendation JSON; parallel SQLite writers could conflict or
duplicate informational notes. This limitation cannot move money because financial
adjustments are disabled.

## Verification and remaining scope

Baseline: **363 passed, 150 warnings in 37.78s**.
Final command: `.venv\Scripts\python.exe -m pytest -q`.
Result: **427 passed, 0 failed, 152 warnings in 49.93s**: all baseline tests,
63 new Recommendation regression cases and one new authenticated-page smoke
case. Existing placeholder assertions now apply only to Dashboard. Warnings
remain the existing WTForms, Flask-Migrate engine and SQLite date-adapter
deprecation categories; the added migration-backed test accounts for two more.
`git diff --check` passed.
New Recommendation tests exercise real Budget services and Expense check-ins,
including sufficient/insufficient data, exact thresholds and integer signals,
NO_EXPENSE versus missing check-ins, funds exclusion, real overspending,
category/priority isolation, drafts, missing schedules, unknown amounts, stale
snapshots, repeat requests, authorization, CSRF, decisions, feedback and rollback.
An existing-migrations database test verifies UUID-linked Recommendation JSON
persistence and reload without schema changes.

Limits: financially read-only; no automatic or acceptance-based adjustments,
cross-month/rolling-history analysis, LLM calls or imported sample transactions.
Month-scoped F18 cannot reach 30 days in February or from a short tracking interval;
thresholds were not reduced. Standalone CSV prototypes remain independent.
New labels are English within the existing language-aware shell. Live PostgreSQL
and browser interaction remain deployment checks; HTTP behavior is tested with
Flask's test client. Dashboard/KAN-25 remains outside this task.

Changed files:

- `app/modules/recommendations/rules.py`, `services.py`, `routes.py`.
- `app/templates/recommendations/index.html`, `error.html`.
- `app/templates/components/navbar.html` (signed-in navigation link only).
- `tests/test_recommendations.py`, `tests/test_smoke.py`.
- `README.md`, `docs/README.md`, `docs/api-contracts.md`,
  `docs/database-design.md`, `docs/Adaptive AI Budget Assistant (Rule-Based).md`,
  `docs/kan27-spending-analysis.md`.
