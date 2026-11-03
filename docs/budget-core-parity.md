# Budget core parity audit

Audit base: `integration/pa2-20261031` at
`b4bdb9a781b313b9d87b9599d9256727cbac8d57`.
Reference: `origin/feature/KAN-11-initial-monthly-budget-setup` at
`29df414811c2f49fbdbb96c8a9f779e85c3ac046`.
The working tree was clean; baseline: **294 passed, 122 warnings**.

Reviewed the prototype's budget_rules.py, ai_service.py, app.py,
templates/index.html, static/app.js and all three associated test files against
the integrated Budget services/routes/rules/templates and Expense scheduler.

| Capability | Before restoration | After restoration |
|---|---|---|
| Rent/Electricity/Water P0 and optional Internet validation | Implemented | Preserved |
| Suggested setup rows; optional Internet/Food/Transportation selection | Missing | Implemented |
| Explicit prototype example amounts | Missing | Implemented |
| User-defined P0/P1/P2, optional positive P1 minima, frequency and due day | Implemented | Preserved |
| Saving/Balanced/Lifestyle, exact VND, minima before discretionary spending | Implemented | Preserved |
| Side-by-side P0/P1/P2/savings comparison | Partially implemented (savings links only) | Implemented |
| Setup → compare → confirm → schedule journey | Partially implemented | Implemented |
| Enter multiple expenses without visiting separate add screens | Missing | Implemented |
| Confirmed, owned UUID allocations; one confirmed plan per month | Implemented | Preserved |
| Daily/weekly/monthly calendar periods and exact allocation conservation | Implemented by KAN-23 | Preserved |
| Optional daily Food meal guidance (30/40/30) | Missing | Implemented |
| Gemini priority/weight hints and generated prose | Intentionally excluded | Deferred; deterministic rules retained |
| Manual allocation editor | Intentionally excluded by current prototype HTTP/UI | Remains excluded; confirmation is read-only |
| Standalone Flask app, anonymous APIs, TXT history/persistence | Intentionally excluded | Remains excluded; canonical SQLAlchemy only |
| Prototype-specific calendar screens/design | Partially implemented by Expense calendar | Reuse Expense calendar rather than duplicate it |

The prototype defines an unused manual-adjustment helper and tests it, but its
actual confirmation route rejects submitted allocations/savings. It is not a
missing core confirmation feature. The prototype automatically loads examples
on page startup; the integrated application must instead require explicit user
action and must not change real month funds to the prototype's 5,000,000 VND.


## Restored workflow

1. Open an owned month at `/budget`. GET only displays suggestions; it creates
   no expense, category, plan, task or spending records.
2. Choose suggested rows (Internet is off by default; Food and Transportation
   can also be omitted). Enter real estimates/minima and choose frequencies.
   **Load Example amounts** explicitly fills selected, unsaved fields with
   KAN-11 examples: Rent 1,500,000, Electricity 200,000, Water 100,000 and
   optional Internet 100,000 VND, with due days 5/12/12/1. It neither changes
   available funds nor saves financial data. Example values remain editable.
3. **Apply selected expenses** posts to
   `/budget/<uuid:month_id>/expenses/suggested` with CSRF. Blank estimates remain
   NULL, explicit zero remains zero; neither is invented spending. Unknown P0
   amounts can be retained during setup but block generation until positive.
4. Add custom expenses inline on the workspace using the existing creation
   route; successful saves reopen the add section for the next expense. Existing
   edit routes remain available. This is regular HTML with a page reload on
   save, rather than a second financial state in JavaScript.
5. Generate and compare all three saved plans, including P0/P1/P2/Savings and
   their exact total. Review and confirm a saved plan without editing its
   allocations. Open **Continue to Spending Schedule**, explicitly create/verify
   the KAN-23 schedule, and select a date for check-in.
6. Daily Food tasks offer a collapsed **Optional meal guidance** section on
   desktop and mobile. Breakfast/Lunch/Dinner use illustrative 30/40/30 weights
   and integer largest-remainder splitting. Parts sum exactly to that task's
   current limit, including zero and BIGINT values. Weekly/monthly Food has no
   meal split. These are allowances, not transactions, extra allocations, extra
   tasks, or evidence of NO_EXPENSE.

## Write, idempotency and database contract

`budgets.services.apply_suggested_expenses(user_id, month_id, selected_keys,
values=None)` authorizes and locks the month using the existing Budget service
transaction. It reuses the same `_save_expense` validation/write implementation
as `save_expense`, with one commit for the entire selected batch. A bad row or
insert failure rolls back the batch, category creation and any draft replacement.

Idempotency uses the existing expense's case-insensitive name within this month,
not a client user ID. Repeated or changed initialization payloads always skip an
existing name, preserving its UUID, category, estimate (including NULL/0), minimum,
frequency, due day and recurrence flag. Adding only already-existing names does
not discard drafts. Selecting any genuinely new row invalidates unconfirmed
plans as ordinary expense creation does. Duplicate/unknown selection keys and
empty selections return 400. Confirmed months return 409, including retries;
they cannot be initialized, regenerated, edited or deleted through Budget.
The existing confirmation retry remains harmless.

No shared models, schemas, migrations, dependencies or scheduling algorithms
changed. All canonical IDs/FKs remain UUID, money remains integer VND, and the
existing single-confirmed-plan constraint is retained. Meal display reads
AssignedExpenseTask.current_limit; original limits and confirmed allocations
are never rewritten. The confirmed-only Expense handoff is unchanged.

## Deferred scope and integration limits

- Optional Gemini priority suggestions, AI weights and generated prose remain
  deferred. Deterministic Food/Transportation/other weights are preserved; no
  private financial data is sent to another service.
- Manual allocation editing, prototype TXT/JSON event storage, anonymous APIs,
  localStorage persistence and automatic example insertion remain excluded.
- Use the existing Expense calendar and check-ins rather than reproduce the
  prototype's separate schedule screens. Meal guidance appears in day view.
- New Budget labels remain English, and mandatory bill/Food detection retains
  the canonical case-insensitive English names. Localization beyond the shared
  page shell is deferred.
- Tests use SQLite, including the existing migration-backed flows. PostgreSQL
  row-lock concurrency remains a deployment check. SQLite does not enforce
  SELECT FOR UPDATE; parallel setup writers can conflict and sequential retry
  coverage is not a claim of full SQLite concurrency verification.
- This change restores Budget core functionality only. KAN-27/KAN-25 remain
  outside this commit; Recommendation and Dashboard are still placeholders.

## Validation

Baseline: `python -m pytest -q`: **294 passed, 122 warnings in 28.93s**.
Added `tests/test_budget_setup_parity.py`: **50 passed**. Coverage includes
explicit selection, GET-without-writes, repeat initialization, existing values,
transaction rollback, three plan totals, confirmation immutability with actual
spending already recorded, CSRF, ownership, complete Budget-to-Expense navigation,
meal rendering, zero-versus-unknown behavior, partial months, leap February,
current-versus-original limits and conservation through signed BIGINT limits.
JavaScript syntax verified with `node --check app/static/js/budget-setup.js`.
Final complete suite: **344 passed, 0 failed, 150 warnings in 29.58s**.
Warnings are the existing WTForms choice, Flask-Migrate engine access and SQLite
date-adapter deprecation categories; rendering inline forms increases their
occurrence count. HTML workflow and rendering were verified with Flask's test
client; the example-fill interaction has syntax validation, not an automated
real-browser run.

## Changed files

- `app/modules/budgets/suggestions.py`: explicit server-side suggestion metadata.
- `app/modules/budgets/services.py`: atomic idempotent setup and saved-plan totals;
  existing expense writes share the same validation implementation.
- `app/modules/budgets/routes.py`: authenticated, CSRF-protected setup POST and
  workspace/comparison context; existing URLs remain valid.
- `app/modules/budgets/rules.py`: exact presentation-only meal subdivision.
- `app/modules/expenses/presentation.py`: daily Food guidance from current limit.
- `app/templates/budgets/_suggestions.html`, `index.html`, `plan.html`: suggested
  and inline setup, comparison and confirmed schedule handoff.
- `app/templates/pages/expenses.html`: optional meal details on both day layouts.
- `app/static/js/budget-setup.js`: explicit unsaved example fill and add-section
  reopening; no financial persistence or arithmetic.
- `tests/test_budget_setup_parity.py`: 50 regression cases.
- `README.md`, `docs/README.md`, `docs/api-contracts.md`,
  `docs/kan21-budget-planning.md`, `docs/budget-core-parity.md`: parity audit,
  workflow, route contract and verification record.
