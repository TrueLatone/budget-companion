# KAN-34: Stabilize Smart Check-in Statuses and Prevent Duplicate Expense Records

## 17.1 Task information

| Field | Value |
|---|---|
| Task ID | KAN-34 |
| Title | Stabilize Smart Check-in Statuses and Prevent Duplicate Expense Records |
| Module | Expense Smart Check-in (`/expenses`) |
| Scope | `AssignedExpenseTask` and `ExpenseRecord` application logic + UI integration |
| Database design | Existing shared schema — **unchanged** |
| Status model (persisted) | `PENDING`, `RECORDED`, `NO_EXPENSE` |
| Status model (derived) | `UNRECORDED`, `WITHIN_BUDGET`, `OVER_BUDGET` |

## 17.2 Problem statement

Problems actually found in the pre-KAN-34 implementation:

1. **Invalid calendar spreading.** Day and month views placed a task on every date it covered up to `PeriodEnd` ("continuing periods"), so the same weekly/monthly task was counted and displayed on many days. This inflated `plan_total` per day and produced a "Continuing period; excluded" workaround UX instead of data that was correct by construction.
2. **Schedule-tag contamination.** Route, services, validators, templates and tests still consumed `AllocationFrequency`-derived tags (`DAILY/WEEKLY/MONTHLY/DAY_OF_MONTH`) as a UI filter and as year-view grouping. Expense must not consume recurrence tags.
3. **Stale persisted status.** A task persisted as `NO_EXPENSE` stayed `NO_EXPENSE` even after a later PLANNED record was created. Persisted status must yield to the actual linked records.
4. **Zero-limit "planned" check-in.** `checkin_task(action="planned")` happily wrote a `0` VND `PLANNED` record when `CurrentLimit = 0`.
5. **Check-in duplicate protection.** Duplicate submission prevention relied on the postponed `idempotency_key` token (`_token`/`_replay`); the submit buttons were never locked. The token column itself exists in the locked canonical model, but KAN-34 forbids using it.
6. **Page reload/scroll jump.** Every POST redirected to `url_for("expenses.index")` without query params, resetting Day/Month/Year, selected date and scroll position to the top.
7. **Due-date mixing.** `PaymentDueDate` was folded into the same task list as assigned tasks, so a bill due on 2026-11-01 looked and counted like a task assigned on 2026-11-01.
8. **UNEXPECTED edit gap.** `update_record` only edited amount/date/note/category for UNEXPECTED records; `Priority` and `BudgetImpactScope` could never be changed after creation.
9. **Category boundary violation.** The UNEXPECTED form and `_category()` helper created a new `ExpenseCategory` whenever the typed name did not exist. Expense must not create or manage Budget-owned categories.
10. **Read-path recurrence reconstruction.** `get_schedule_state()` and `_complete_period()` still rebuilt allocation periods with `build_task_schedule()`/`AllocationFrequency` to diagnose the handoff. Expense reads must not reconstruct schedules from recurrence metadata.
11. **Fragile scroll key and client-only duplicate lock.** The scroll key included the full query string, so every PRG redirect (`budget_month_id` added) or date/view change lost the position; the only duplicate protection was disabling the submit button in the browser.

## 17.3 Database integration

Canonical read-only lookup path (implemented in `presentation.py`/`services.py`):

```text
AssignedExpenseTask
        │ AllocationID (FK)
        ▼
BudgetAllocation
        │ BudgetExpenseID (FK)
        ▼
BudgetExpense      → ExpenseName (task display name), Priority (task priority)
```

- Expense reads `ExpenseName` and `Priority` exclusively through the canonical relationships; no denormalization, no new fields.
- `AssignedExpenseTask.AssignedDate` is the **only** calendar placement date.
- `AssignedExpenseTask.CurrentLimit` is the comparison limit for actual spending (never `OriginalLimit`).
- `ExpenseRecord` is the sole source of truth for actual spending; totals are `SUM(Amount)` over linked PLANNED records.
- Operational (writable) entities for Expense: `AssignedExpenseTask.TaskStatus`, `AssignedExpenseTask.PaymentStatus` (within existing permission boundary), and `ExpenseRecord` CRUD. `ExpenseCategory` is now **read-only** for Expense: `services.list_categories()` and `_category()` only resolve an existing owned or built-in row. A missing name is rejected with `ValidationError`; Expense never creates, renames or deletes a category.
- Task name, priority and the default PLANNED category come from `AssignedExpenseTask → BudgetAllocation → BudgetExpense` (`ExpenseName`, `Priority`, `CategoryID`). The check-in form offers those existing rows as a select; no free-text category creates data.
- Everything else (`User`, `BudgetMonth`, `BudgetPlan`, `BudgetAllocation`, `BudgetExpense`, `BudgetAdjustment*`, `Recommendation`, `MonthlyReview`) is consumed via read-only JOINs only.

## 17.4 Smart Check-in business rules

Persisted transitions (all within one locked-month DB transaction):

| Trigger | Persisted `TaskStatus` |
|---|---|
| Positive PLANNED record created | `RECORDED` |
| "Confirm as planned" | `RECORDED` (one record, `Amount = CurrentLimit`, refused if records exist or `CurrentLimit = 0`) |
| "Enter actual amount" | `RECORDED` (each new record is appended; prior rows untouched) |
| "No expense" explicit confirmation | `NO_EXPENSE` (refused while positive PLANNED records exist) |
| One of several PLANNED records deleted | `RECORDED` recalculated via `_recalculate_task_status` |
| Final PLANNED record deleted | `PENDING` (never `NO_EXPENSE` automatically) |

Derived display states (`presentation.get_task_status`, evaluated fresh on every read and never persisted):

- `UNRECORDED` — no linked positive PLANNED record, not explicitly NO_EXPENSE, deadline passed.
- `WITHIN_BUDGET` — one or more positive PLANNED records exist and `SUM(Amount) <= CurrentLimit`.
- `OVER_BUDGET` — `SUM(Amount) > CurrentLimit`.
- A fresh PLANNED record overrides a stale persisted `NO_EXPENSE`; `NO_EXPENSE` is displayed only when the task currently has no linked positive PLANNED records.
- A persisted `RECORDED` status with no linked PLANNED records is treated as inconsistent: it stays `PENDING` until the approved deadline and only then derives `UNRECORDED`; no derived value is written back.

`ActualTaskAmount = SUM(Amount of all linked PLANNED ExpenseRecords)`, compared against `CurrentLimit`. UNEXPECTED and FUNDS_ADDED are never counted into task totals.

Check-in expense date validation: transaction date must belong to the task's month tracking interval and lie inside `AssignedDate ≤ ExpenseDate ≤ PeriodEnd` (pre-existing `_valid_date` rule; the Budget-side PLANNED-period restriction is unchanged). Editing `ExpenseDate` changes history placement only — `AssignedDate` never moves.

**Deadline rule (documented ambiguity).** Implementation and docs currently express UNRECORDED overdue by `PeriodEnd` end-of-day in Asia/Ho_Chi_Minh (`deadline_for(task.period_end)`). The KAN-34 prompt text describes the deadline as `AssignedDate` 23:59:59 Asia/Ho_Chi_Minh. The existing implementation rule was **preserved** and the discrepancy **reported** rather than silently changed, because section 5.4/8.5 forbids replacing the approved rule without an approved change.

## 17.5 Duplicate prevention

### Legacy one-PLANNED-record-per-task index inspection — Case 1: no conflicting constraint

Inspected (read-only):

- Canonical model `app/models/expense_record.py` `__table_args__`.
- Canonical migration `migrations/versions/19a01e000002_kan19_finalize_core_schema.py` (the revision that finalizes the 13-entity core).
- Runtime SQLite introspection of `instance/budget_companion_dev.db` and of a freshly migrated in-test DB: `PRAGMA index_list`/`index_info` on `expense_records`.

Result:

- Index `ix_expense_records_task_id` is a **non-unique** single-column index on `task_id`.
- The only unique constraint on `expense_records` besides the primary key is `UNIQUE(budget_month_id, idempotency_key)`. KAN-34 stops using `idempotency_key`, so new rows keep it `NULL`; SQLite treats multiple NULLs as distinct, so the constraint never fires for KAN-34 writes.
- No partial unique index with predicate `record_type = 'PLANNED'` and no unique constraint on `task_id` exists.

`tests/test_expenses.py::test_canonical_schema_has_no_single_planned_record_per_task_constraint` asserts both the introspection result **and** that two positive PLANNED records referencing the same `TaskID` persist successfully. No DB-level workaround exists or is needed.

### Application-level safeguards (implemented)

- `data-no-double-submit` on every Expense form (check-in, unexpected create, edit, delete, payment status; auth-free GET pickers excluded): the submit handler disables the button and swaps its label to "Processing…" until navigation completes. The handler also finds submit buttons linked to a form through the HTML `form="…"` attribute.
- **Server-side in-flight guard.** `services._single_flight(key)` wraps check-in, UNEXPECTED create, record update and delete. A concurrent request with the same user + action + payload is refused with `ExpenseConflict` while the first request is still running; the key is released in `finally`, so a later legitimate repeat is accepted. The guard is process-local (threading lock + key set) and complements, not replaces, the database transaction.
- **Submission-token anti-replay (no schema change).** See 17.5.1.
- `confirm as planned` is server-side refused with `ExpenseConflict` when the task already owns positive PLANNED records (`services.checkin_task`), with a UI hint directing users to "Enter actual amount".
- `no_expense` is refused when positive PLANNED records exist — no contradictory state is possible.
- `enter actual amount` accepts intentionally repeated identical amounts/dates (two 100 VND purchases are two separate records; verified by test). No `TaskID + Amount + ExpenseDate` uniqueness is enforced.
- `app/static/js/expenses.js` uses a **path-stable** scroll key (`expense-scroll:/expenses`, not the query string) with a 30-minute freshness stamp and `history.scrollRestoration = 'manual'`. It saves before internal links, form submits, `pagehide`, `beforeunload` and tab hiding, then restores after load or focuses the last `data-focus-target` row. `<details>` open state is also restored.

### 17.5.1 Replay of a submitted creation form → recorded details + explicit choice

Requested behaviour: when the same creation submission reaches the server twice (weak network, repeated click, back-and-resubmit), accept only the first write, show the saved transaction's details, and ask whether an identical copy should be added.

**Mechanism (chosen over DB field matching).** No column, index, constraint or migration was added, and no rule compares `TaskID + Amount + ExpenseDate`:

1. `app/modules/expenses/duplicates.py` (session-only, no DB access) issues an opaque random `submission_token` that every rendered creation form embeds as a hidden field. `routes.py` exposes it to templates as `new_submission_token()`.
2. The token is stored (SHA-256 digest + record id + flow + target id + user id + timestamp) **only after the write commits**. `checkin_task` and `create_unexpected_record` accept an optional `on_created(record_id)` callback that `_write_month` runs after its commit; a validation error or rollback never consumes the token.
3. On a POST carrying a remembered token for the same user, flow and task/month, the route writes nothing. It stores the submitted service arguments, the recorded id and the navigation fields in a session *pending* entry and redirects to `GET /expenses/duplicates/<pending_id>`.
4. That page reads the saved row through the ownership-checked `services.get_record()` and renders its title, type, amount, expense date, task, category and note, plus two explicit actions:
   - **Save another identical transaction** → `POST /expenses/duplicates/<pending_id>/confirm`. The pending entry is removed first (single use, so a double-clicked confirmation cannot create a third row), then the same validated service is re-invoked with a fresh token. This is offered only for repeatable writes (check-in *actual* and UNEXPECTED); a *planned* check-in can only exist once per task, so that page shows only "Keep only the first".
   - **Keep only the first** → `POST /expenses/duplicates/<pending_id>/dismiss`, no write, informative flash.
5. Fail-open rules: a missing, unknown or expired token is written normally (ordinary clients, service-level tests and token-less forms are never rejected). Used tokens expire after 60 minutes and only the newest 6 are kept; at most 2 pending confirmations are kept. `login`/`logout` clear the whole session.
6. If the first transaction was deleted before the replay arrives, `get_record` raises `NotFoundError`; the route forgets the token and performs the write normally instead of prompting about a row that no longer exists.
7. Existing CSRF, login requirements and month/task ownership checks are unchanged; the confirmation page and both POST targets re-check that the session user owns the referenced row.

**Why not compare business fields in the database.** Amount, date, title and category are legitimately repeated (two 100.000 VND meals on the same day are two real purchases). A field match would either block valid spending or need a heuristic threshold, and it would require the schema change the task forbids. The token answers exactly one question — "has *this rendered submission* already been written?" — and leaves distinct submissions untouched. Knowing the stored row id also lets the page show the real saved record rather than an echo of the request.

**Explicitly out of scope (approved).** The user chose "Không xử lý" for both cases, so they are neither implemented nor claimed:

- Page refresh, then retyping identical values: a refresh renders a *new* token, so the retyped submission is accepted as a new record.
- Two tabs opening the same form: each tab that fetched its own page has its own token, so both submissions are accepted. (Two submits that share one rendered form's token would still prompt, but that is not a promised scope.)

**Tests** (`tests/test_expenses.py`, nine cases): fresh token per rendered form; replay prompts and shows the saved details while writing nothing; confirm adds exactly one copy and the confirmation cannot be replayed; identical values with a fresh token are accepted; a validation failure does not consume the token; deleting the first row makes the replay save normally; planned replay offers only "keep the first"; UNEXPECTED replay prompt/dismiss; a different user cannot open another session's pending confirmation.

### Not implemented (documented limitation)

- `idempotency_key` was **not** implemented in forms, API requests, services or tests. The column remains in the locked model but is always NULL for KAN-34 writes.
- No new unique constraint, no migration, no model change was added.
- Accepted limitation: the submission-token registry and pending confirmations live in the signed session cookie. A client that discards its cookie (or a request retried on a different session) loses the replay detection and is treated as a fresh submission. Durable retry-safe idempotency remains deferred; the process-local in-flight guard is not shared across multiple gunicorn/uWSGI workers.

## 17.6 ExpenseRecord handling

| RecordType | Written by Expense? | TaskID | Priority | BudgetImpactScope | Counted into task/spending totals? |
|---|---|---|---|---|---|
| `PLANNED` | Yes (check-in + manual edits) | linked task | `NULL`; display reads `BudgetExpense.Priority` through the relation | always NULL | Task actual: yes. Spending summary: yes |
| `UNEXPECTED` | Yes (create/edit/delete) | always NULL | user-required `P0/P1/P2` | optional `DAILY`/`WEEKLY`/`MONTHLY`, never defaulted | Task actual: no. Spending summary: yes |
| `FUNDS_ADDED` | **No** — Expense never creates/edits/deletes this type and the record query filters it out | NULL | NULL | NULL | Never |

- `ExpenseRecord.Priority` for PLANNED records is written as `NULL`; the UI and recommendation code fall back to the Budget-owned `BudgetExpense.Priority` through `ExpenseRecord → AssignedExpenseTask → BudgetAllocation → BudgetExpense`. This avoids denormalizing a value that Budget can change, and PLANNED priority remains non-editable by the user. PLANNED category defaults to the Budget expense category but may be replaced by another **existing** owned/built-in category; a missing name is rejected.
- UNEXPECTED editing supports `Amount`, `ExpenseDate`, `Title`, `Priority`, `Note`, `BudgetImpactScope`, `CategoryID`; `RecordID`, `RecordType` and `TaskID = NULL` are immutable.
- PLANNED editing supports `Amount`, `ExpenseDate`, `Title`, `Note`, `CategoryID`; `TaskID`, `RecordType`, `BudgetMonthID` and Budget-owned priority are immutable. Changing `ExpenseDate` keeps the task's `AssignedDate` untouched.
- Deleting one record of a multi-record task deletes exactly that row and recalculates the task; sibling records survive. Deleting the final PLANNED record resets persisted status to `PENDING` and displays `UNRECORDED` after the deadline (never auto `NO_EXPENSE`).
- `PaymentStatus` is updated only through the pre-existing `set_payment_status` boundary and is never modified by record create/edit/delete (covered by `test_payment_status_is_independent_of_checkin_edit_and_delete`).

## 17.7 UI changes

- **English UI.** Every Expense screen (`/expenses` day, month and year views, all modals, the setup banner, the error page and `/expenses/history`) renders English labels and messages. Backend `VIEW_LABELS`, `WEEKDAY_LABELS`, `STATUS_LABELS`, `PRIORITY_LABELS`, validator messages, service conflict messages and the `Processing…` submit label were translated; no i18n framework was introduced. `tests/test_expenses.py::test_expense_pages_use_english_labels_only` guards the four expense URLs against Vietnamese strings reappearing. These templates are not wired to `app/i18n.py`, so the EN/VI selector does not translate the Expense pages (see Known limitations).
- **History actions.** `/expenses/history` now has an Actions column with **Edit** (opens the shared record modal) and **Delete** for each `ExpenseRecord`, plus an edit modal per record. Delete carries `page=history`, `start` and `end`, so `_back_url()` returns to the same history range after the PRG redirect.
- **Delete in the edit modal.** `app/templates/expenses/_edit_record_modal.html` is a shared macro used by both `/expenses` and `/expenses/history`. Its footer holds the Delete form (with `data-confirm` and a focus target) next to Cancel/Save; Save uses `form="editRecordForm<id>"` because it lives outside the `<form>`. Delete is a single-row `ExpenseRecord` delete through `services.delete_record`, which recalculates the surviving task status; sibling records and Budget data are untouched.
- **Day view** — tasks where `AssignedDate = selected date`, plus a separate due-only section ("Due today only"); due-only rows are excluded from assigned plan totals and marked as out-of-plan. Check-in button opens the three-action modal for both assigned and due-only tasks.
- **Month view** — one list entry per task at its `AssignedDate`; due-only tasks in the month appear in a separate section. Calendar cells show a task dot for `AssignedDate`, distinct overdue/pending/confirmed dots, a separate due badge, and the actual total for `ExpenseDate`.
- **Year view** — 12 monthly cards grouped by `AssignedDate` (plan) vs `ExpenseDate` (actual), no recurrence-tag filter; the year view is summary-only and points to `/expenses/history` for editing or deleting a transaction.
- **URL sync.** Nav tabs, prev/next/"Today"/"Go" jumpers and every modal row include correct `view`/`date`/`month`/`year` params. `_back_url()` (PRG) preserves `view`, `date` and `budget_month_id`, and returns to `/expenses/history?start=…&end=…` when the hidden `page=history` marker is present.
- **Scroll/state restoration.** `app/static/js/expenses.js` keys scroll by pathname only (PRG query changes no longer reset it), sets `history.scrollRestoration = 'manual'`, stores a timestamp, saves on internal link clicks, submits and page hiding, and restores after load. The last touched row (`data-focus-target`) wins with a focus pulse; `<details>` state is preserved. No frontend framework was added.
- **Existing categories only.** The check-in modal, UNEXPECTED create form and record edit modal render `<select>` lists of existing owned/built-in categories. The UNEXPECTED submit button is disabled when no category exists; there is no free-text category input.
- **Task detail.** Rows and cards show `CurrentLimit` as the plan, display `OriginalLimit` when it differs, and expose the independent payment-status toggle for tasks with a `PaymentDueDate`. Due-only rows also show both limits and the payment badge.
- **Modal sync.** The checklist modal's radio defaults align with live server state (`planned` only selectable when no linked records and `CurrentLimit > 0`); amount input is prefilled with `CurrentLimit` when positive; the "No expense" confirm flow and zero-limit hint are shown inline.
- **Empty state.** When no real `AssignedExpenseTask` rows exist, day/month panels display an explicit accurate empty state; the setup banner states that Expense only displays existing tasks and that Budget must create them.

## 17.8 Code changes

| File | Responsibility of the change |
|---|---|
| `app/modules/expenses/presentation.py` | `AssignedDate`-only calendar cells; separate `build_due_items`; year view without recurrence grouping; status override so real PLANNED records beat stale `NO_EXPENSE`; persisted `RECORDED` without records follows the approved deadline; exposed `budget_category_id`/`budget_category_name` for the check-in select; removed `_PlanItemShim` and the adapter `idempotency_key` exposure |
| `app/modules/expenses/services.py` | Removed `schedule_tag` filters, `_token`/`_replay` and `idempotency_key` from check-in; added `_recalculate_task_status`; added `_single_flight()` in-flight guard for check-in/create/update/delete; `list_categories()`/`_category()` are read-only and reject unknown names; PLANNED records store `priority=NULL`; `get_schedule_state()` and `_complete_period()` diagnose stored tasks by allocation totals instead of rebuilding recurrence; `checkin_task` refuses planned-when records-exist and limit-0 planned; UNEXPECTED create/update require valid P0/P1/P2 and optional DAILY/WEEKLY/MONTHLY scope; `delete_record` recalculates surviving-task status; `checkin_task`/`create_unexpected_record` accept an optional `on_created(record_id)` callback that runs only after the write commits (used by the submission-token registry); all conflict/message text is English (`Choose an existing category.`, in-flight warning) |
| `app/modules/expenses/duplicates.py` | **New, session-only** anti-replay helper: opaque token generation, SHA-256 token registry filled after commit (60-minute TTL, newest 6), single-use pending confirmations (newest 2), no database access and no schema change |
| `app/modules/expenses/routes.py` | Removed tag parsing/filter and uuid tokens; day/month/year contexts rebuilt with due items and due-only panel; PRG `_back_url` preserves `view`/`date`/`budget_month_id` and returns to `history` when `page=history` (also replayable from a stored navigation snapshot); history route passes `categories`, `priority_labels` and the current month; all user-facing labels, flashes, picker errors and date/amount field names are English; removed the unused `schedule_label` filter (it referenced an undefined `SCHEDULE_LABELS`); check-in/UNEXPECTED POSTs check the submission token and divert replays to `GET /expenses/duplicates/<id>`; added `duplicate_submission`, `confirm_duplicate` and `dismiss_duplicate` routes and the `new_submission_token()` template global |
| `app/modules/budgets/routes.py` | `confirm()` now invokes `expenses.services.ensure_tasks_for_month()` after `confirm_plan()` commits, so a confirmed plan receives its `AssignedExpenseTask` rows in the same request; a generation failure is caught as an Expense validation conflict, flashes a warning and leaves the confirmed plan intact |
| `app/modules/expenses/validators.py` | Removed `SCHEDULE_TAGS` constant; all validation messages and default field names (`Amount`, `Date`, `Actual amount`, `Expense date`) are English |
| `app/templates/pages/expenses.html` | Rewritten calendar/day/month/year markup in English; separate due sections; three-action check-in modals with an existing-category select and a hidden `submission_token`; UNEXPECTED create form requires an existing category, carries a hidden `submission_token` and is disabled when no category exists; `OriginalLimit` shown when different; independent payment-status toggle on desktop, mobile and due-only rows; no tag filter and no schedule button; edit modals now come from the shared macro (with Delete) |
| `app/templates/pages/duplicate_submission.html` | **New** confirmation page: reads the already-saved record and shows transaction, type, amount, expense date, task, category and note; offers "Save another identical transaction" (when the write is repeatable) and "Keep only the first"; both POSTs carry the CSRF token |
| `app/templates/expenses/_edit_record_modal.html` | **New shared macro**: one edit form + `form=`-linked Save button, plus the Delete action in the footer, reused by `/expenses` and `/expenses/history` |
| `app/templates/expenses/_setup.html` | Removed `can_schedule` action button; copy explains Expense reads existing tasks only |
| `app/templates/pages/expense_history.html` | Rewritten in English; new Actions column with Edit modal trigger and per-row Delete form (`page=history`, `start`, `end`); edit modals rendered through the shared macro; `data-expense-root` + `expenses.js` for scroll/focus restore |
| `app/static/js/expenses.js` | Path-stable timestamped scroll save/restore with `history.scrollRestoration='manual'`; saves on internal links, submits, page hide and tab hiding; details/`focus-target` restore; double-submit lock (`Processing…`) that also disables a `form=`-linked submit button; check-in radio/amount affordance sync |
| `app/static/css/expenses.css` | Added `.bc-focus-pulse` animation for restored row focus |
| `tests/test_expenses.py` | Rewrote idempotency-token tests into multi-record/identical-transaction tests; fixed AssignedDate-only calendar assertions; existing-category fixtures; added KAN-34 regressions including the in-flight guard, read-only category rejection, PLANNED priority/category, stable scroll script, history edit/delete flow, English-only UI and nine submission-token replay tests |
| `tests/test_expense_presentation.py` | Year label expectation updated to `Year 2026` |
| `tests/test_dashboard.py` | Removed `idempotency_key` from helpers/posts; seeded an owned category for the cross-user record; unexpected records use an existing Budget category |
| `tests/test_recommendations.py` | Removed `idempotency_key` from check-in helpers; seeded `Health`/`Repairs` categories for read-only references |
| `tests/test_budget_setup_parity.py` | Removed `idempotency_key` from check-in helpers |
| `tests/test_budgets.py` | Unchanged semantics |
| `tests/test_build1_integration.py` | Duplicate check-in asserted as two distinct 302 records; restart snapshot no longer performs a second same-form mutation |

Not modified: anything under `app/models/`, `migrations/`, `.env`, config, or the canonical database files.

### Schedule handoff on Budget confirmation

`budgets.routes.confirm()` calls `expenses.services.ensure_tasks_for_month()` immediately after `services.confirm_plan()` commits, so confirming a plan now produces its `AssignedExpenseTask` rows in the same request. This closes the reported production gap: a `CONFIRMED` plan whose allocation rows existed could still leave `/expenses` empty because nothing ever ran the generator.

- The generator itself stays Expense-owned (`expenses.scheduling.build_task_schedule`) and is repeat-safe: confirming an already-confirmed plan, re-posting the confirm form, or re-running the repair endpoint never duplicates, rewrites or deletes existing tasks.
- Generation runs in its own transaction. If it fails, the confirmed plan and its allocations remain committed, the response flashes `Budget plan confirmed, but its spending schedule could not be created: ...`, redirects to `/expenses`, and `POST /expenses/months/<id>/schedule` can complete the handoff later.
- No Expense read path calls the generator. `get_schedule_state()` still only inspects stored tasks, so Expense never fabricates tasks while rendering.
- Architectural caveat: Budget→Expense is a pragmatic cross-module call. Upstream Budget still has no `AssignedExpenseTask` generator of its own; moving it there is a follow-up refactor, out of scope while the shared database is frozen.

For months confirmed **before** this fix, tasks are still absent; the plan cannot be re-confirmed from the UI (the confirm button is only rendered for `GENERATED` plans). The idempotent repair is one call to `ensure_tasks_for_month(user_id, month_id)` (or `POST /expenses/months/<id>/schedule` with a CSRF token). No such write was performed on the live development database during this review.

## 17.9 Testing and verification

Per-ticket test evidence is also kept separately in [KAN-34-test-report.md](KAN-34-test-report.md) and [KAN-35-test-report.md](KAN-35-test-report.md).

Executed locally on Windows via `.venv\Scripts\python.exe -m pytest -q`:

| Suite | Result |
|---|---|
| Full repository suite (486 tests) | **486 passed, 0 failed** |
| `tests/test_expenses.py` (100 tests, Expense module) | 100 passed |
| `tests/test_expense_presentation.py` (10 tests) | 10 passed |
| `tests/test_schema_constraints.py` (96 tests, canonical schema integrity) | 96 passed |
| `tests/test_migrations.py` (4 tests) | 4 passed |

KAN-34 regressions added to `tests/test_expenses.py`:

1. `test_multiple_planned_records_aggregate_against_current_limit`
2. `test_editing_planned_record_changes_expense_date_not_assigned_date`
3. `test_editing_unexpected_record_updates_priority_scope_and_keeps_task_null`
4. `test_deleting_final_planned_record_resets_to_pending_and_derives_unrecorded`
5. `test_payment_status_is_independent_of_checkin_edit_and_delete`
6. `test_payment_due_date_marker_does_not_create_a_task_occurrence`
7. `test_canonical_schema_has_no_single_planned_record_per_task_constraint`
8. `test_expense_page_has_no_recurrence_filter_or_idempotency_input`
9. `test_identical_write_already_in_flight_is_rejected_and_released`
10. `test_unexpected_unknown_category_is_rejected_without_creating_a_category`
11. `test_planned_record_uses_budget_category_and_leaves_priority_null`
12. `test_expense_page_only_offers_existing_categories`
13. `test_scroll_script_uses_a_stable_path_key_and_manual_restoration`
14. `test_history_page_offers_edit_and_delete_for_every_transaction` — Edit trigger, edit modal, `form=`-linked Save and the in-modal Delete form exist for both a PLANNED and an UNEXPECTED record, with `page=history` hidden fields.
15. `test_edit_from_history_returns_to_history_range` — POST redirects to `/expenses/history?start=…&end=…` and persists amount/note/date.
16. `test_delete_from_history_removes_record_and_returns_to_history_range` — the row is deleted, the task returns to `PENDING`, and the history URL is preserved.
17. `test_day_view_edit_modal_also_offers_delete` — the same shared modal on `/expenses` carries the Delete form.
18. `test_expense_pages_use_english_labels_only` — day/month/year/history render no Vietnamese probes and show the English labels.
19. `test_kan35_edit_and_delete_actuals_stay_consistent_across_pages_and_budget` — see section 17.11.
20. `test_kan35_history_range_follows_expense_date_while_assigned_date_stays` — see section 17.11.
21. `test_creation_forms_render_one_fresh_opaque_token_per_form` — every rendered creation form carries a distinct token of at least 20 characters.
22. `test_replayed_checkin_token_prompts_with_saved_details_and_writes_nothing` — the second POST redirects to `/expenses/duplicates/<id>`, the page shows the saved title/amount/date, and the row count stays 1.
23. `test_confirming_the_duplicate_adds_exactly_one_copy_and_is_single_use` — confirm writes exactly one more row; reposting the same confirmation redirects with an "already used" flash and still leaves 2.
24. `test_identical_values_with_a_new_token_are_not_treated_as_duplicates` — two fresh tokens with identical values write two records and never prompt.
25. `test_failed_validation_does_not_consume_the_submission_token` — a rejected UNEXPECTED POST (400) leaves the token usable; the valid retry writes once and a later replay prompts.
26. `test_deleting_the_first_transaction_lets_the_same_token_submit_normally` — after deleting the first row, the replayed token writes instead of prompting.
27. `test_planned_checkin_replay_is_kept_to_one_transaction` — a planned replay prompts with only "Keep only the first"; dismissal leaves one row.
28. `test_unexpected_replay_prompt_shows_the_saved_transaction_and_dismiss_keeps_one` — UNEXPECTED prompt shows title, amount and date; dismissal leaves one row.
29. `test_duplicate_confirmation_is_scoped_to_its_owner` — another session cannot open the pending confirmation and is redirected with a warning.

Pre-existing tests covering the same scenarios were adapted rather than duplicated: multiple-actual aggregation, identical-transaction acceptance, `confirm as planned` refusal after a record exists, `no_expense` refusal when records exist, zero-limit behavior, Funds-Added exclusion, empty calendar diagnosis, ownership/CSRF matrix and 404 isolation.

Four tests were updated for the new Budget→Expense handoff and re-verified (final full-suite run: **486 passed, 0 failed**):

- `tests/test_dashboard.py::test_confirm_schedule_and_calendar_connect_to_dashboard` now expects `READY` and 24 tasks straight after HTTP confirm.
- `tests/test_build1_integration.py::test_build1_registration_to_recommendation_survives_replay_and_restart` now expects 40 tasks after confirm and no longer needs the legacy schedule POST.
- `tests/test_expenses.py::test_confirmation_guides_to_owned_month_and_safe_csrf_post` now expects `READY` and a non-zero task count, while still checking CSRF rejection and the idempotent repair endpoint.
- `tests/test_expenses.py::test_schedule_post_failure_preserves_confirmation_and_allows_retry` now injects the insert failure **before** confirm, asserts the warning flash, the preserved `CONFIRMED` plan, `NOT_SCHEDULED`, the 409 on the repair endpoint, and a successful retry once the failure is removed.

### Runtime verification

**Live development database (read-only inspection).** `instance/budget_companion_dev.db`, SQLite, opened with `mode=ro`: 3 `User`, 3 `BudgetMonth` (all 2026-11, tracking start 2026-11-01), 15 `BudgetExpense`, 9 `BudgetPlan` (3 `CONFIRMED`, 6 `GENERATED`), 45 `BudgetAllocation`, 39 `AssignedExpenseTask` (all `PENDING`), 1 `ExpenseRecord` (UNEXPECTED, 300.000 VND, 2026-11-05, `TaskID NULL`) and 13 `ExpenseCategory`. All 39 tasks belong to `nguyenvana@gmail.com`'s month (`268b4b38-...`): 5 allocations, all exactly conserved. The other two users (`nguyenvanb`, month `5aba2fe8-...`, and `nguyenvanc`, month `f1942856-...`) also have a `CONFIRMED` BALANCED plan with 5 allocations each but **zero** tasks — the exact symptom of the missing handoff. `PRAGMA index_list('expense_records')` shows only non-unique `task_id`, `budget_month_id`, `category_id`, `(budget_month_id, expense_date)` indexes, the primary key and `UNIQUE(budget_month_id, idempotency_key)`. No write was made to this database.

**Reported empty-month diagnosis (read-only).** For month `f1942856-28a1-4144-a949-4d72032b4eb8` (BALANCED `CONFIRMED`, 780.000/910.000/1.040.000 plans, 5 allocations: Electricity 250.000, Food 1.126.666, Rent 500.000, Transportation 563.334, Water 150.000), a read-only query returned `assigned_expense_tasks = 0`. The plan and allocations were correct; the confirm route simply never ran the generator, and the Expense UI has no button that would. That route is fixed as described above. The live row set was not modified during diagnosis.

**Browser verification (isolated temporary database).** A disposable SQLite database outside the repository was seeded with one user, a confirmed BALANCED plan, 39 tasks and one UNEXPECTED record. A local dev server on port 5017 was driven through the in-app browser:

- Login succeeded; `/expenses?view=day&date=2026-11-05&budget_month_id=...` rendered with the correct month banner (`READY`), the calendar placed tasks only on `AssignedDate`, and the day panel showed one Food task, 46.223 ₫ plan, 30.000 ₫ from its PLANNED record and a separate 50.000 ₫ UNEXPECTED transaction (80.000 ₫ actual).
- The check-in modal offered the three actions (then labelled `Theo kế hoạch`, `Nhập số tiền thực tế` and `Không phát sinh`; now `As planned`, `Enter the actual amount` and `No expense`); "As planned" was disabled because the task already had a record. The category control was a `<select>` listing the existing Budget categories, with the Budget category as the default.
- Submitting an actual amount of 12.345 VND redirected back to the **same** `view/date/budget_month_id` URL, preserved the page, recalculated the task to 42.345 ₫ across two transactions, restored `window.scrollY ≈ 332.67`, reported `history.scrollRestoration === 'manual'`, and stored the position under `expense-scroll:/expenses` (no query string). No console messages were emitted.
- `view=year` (2026) rendered successfully with no error page; the month view was exercised in the same navigation sequence.

**Browser verification, history edit/delete and English UI (isolated temporary database).** A second disposable SQLite database (Alembic `upgrade()` + one user, confirmed BALANCED plan, 40 tasks, one PLANNED check-in of 250.000 ₫ and one UNEXPECTED "Repair" record) was served on port 5021 and driven through the in-app browser:

- `/expenses/history?start=2026-11-01&end=2026-11-30` rendered the new **Actions** column with an `Edit` button and a `Delete` form for both rows, and the page was fully English.
- Clicking `Edit` opened the shared `Edit transaction` modal with the Delete/Cancel/Save footer; both forms carried `csrf_token`, `page=history`, `start` and `end` hidden fields.
- Saving with amount 260.000 ₫ and note `verified edit` redirected to the same `/expenses/history?start=2026-11-01&end=2026-11-30`, flashed `Transaction updated.`, and the row showed `260.000 ₫` / `verified edit`.
- Clicking `Delete transaction` raised the browser confirm `Delete this transaction? Other transactions for the same task are kept.`; cancelling kept the row and the modal. Accepting redirected back to the same history range, flashed `Transaction deleted.`, and removed only that row (the PLANNED row survived).
- `view=day` (2026-11-05), `view=month` (`Month 11/2026`) and `view=year` (2026) rendered with no error page and no Vietnamese characters in the visible text; the day view exposed the Delete form inside its edit modal. No console messages were emitted.

**Browser verification, duplicate-submission prompt (isolated temporary database).** A third disposable SQLite database (Alembic `upgrade()` + one user, confirmed BALANCED plan, 39 tasks) was served on port 5025 and driven through the in-app browser to exercise section 17.5.1:

- A first check-in of 50.000 ₫ on the Food task redirected back to `/expenses?view=day&date=2026-11-05&budget_month_id=...` and flashed `Transaction saved.`; the task recalculated to 50.000 ₫ actual from one record.
- The hidden `submission_token` of the rendered form was then reused (the browser's `fetch` of a replayed POST is blocked by the debug evaluator, so the hidden input value was swapped for the already-used token and the same form was submitted through the UI, which is the same server-side path a repeated click or weak-network retry takes). The server answered with `302 → /expenses/duplicates/<pending_id>` instead of writing a second row.
- The confirmation page rendered the saved transaction as `Food`, `Planned`, `50.000 ₫`, `05/11/2026`, category `Living`, with the note row empty. The database still held exactly one `ExpenseRecord` at that point.
- Choosing `Keep only the first` redirected to `/expenses`, flashed `Only the first transaction was kept. Nothing else was saved.`, and the count stayed at 1.
- Replaying again and choosing `Save another identical transaction` after ticking the confirmation checkbox redirected to `/expenses`, flashed `A second identical transaction was saved.`, and the database held 2 `ExpenseRecord` rows totalling 100.000 ₫.
- A third replay of the same token went back to the prompt: the pending entry is single-use and the token stays registered for the session's 60-minute TTL.
- No console messages were emitted in any step.

The disposable databases and the local servers were removed after verification; the repository's `instance/budget_companion_dev.db` was never opened for writing.

### Known limitations (honest reporting)

1. Task generation still lives in `expenses.services.ensure_tasks_for_month()` / `build_task_schedule()`, not in Budget. Budget `confirm` invokes it after the plan commits, and `POST /expenses/months/<id>/schedule` remains as an idempotent repair endpoint (not linked from the Expense UI). No Expense read path generates tasks. A plan confirmed before this handoff stays `NOT_SCHEDULED` until the repair call runs.
2. Read paths no longer reconstruct recurrence schedules: `get_schedule_state()` and `_complete_period()` inspect stored tasks and compare per-allocation `SUM(OriginalLimit)` with `AllocatedAmount`. `AllocationFrequency` remains visible only in the Food meal-guidance display (`presentation.py`), never as a schedule filter.
3. The deadline rule (PeriodEnd end-of-day Asia/Ho_Chi_Minh in code, AssignedDate 23:59:59 in the KAN-34 prompt text) is documented but not changed; an approved rule change is required before touching it.
4. Durable retry-safe idempotency remains out of scope, as required by section 9. The in-flight guard is process-local, and the submission-token registry lives in the signed session: losing the session cookie (or a second worker process without the same client cookie jar) makes a replay look like a fresh submission, and the replay is accepted. Expired tokens (60 minutes) are treated the same way. Both are the approved "fail open" trade-off — no database column was added for this.
5. Expense templates are hardcoded English and do not call the `app/i18n.py` helpers, so the header's EN/VI selector leaves Expense pages in English. Adding Vietnamese would mean adding message keys, which was not requested; the previous hardcoded Vietnamese copy is gone.

## 17.10 Database integrity confirmation

The shared database design was left **completely unchanged**:

- No migration was created, edited or deleted (Alembic `upgrade()`, run by `tests/test_migrations.py`, produces only the pre-existing revision graph: `de12e989405f → 19a01e000001 → 19a01e000002`).
- No SQLAlchemy model file under `app/models/` was modified. The repository still has no commits/HEAD, so `git status --short` lists every project file as untracked; the branch is `feature/KAN-34-smart-checkin-expense`.
- No index, unique constraint, check constraint, FK or column was added, altered or removed.
- No fallback to raw SQL, no test-only model duplication of `expense_records`, and no temporary alternate table was introduced.
- The browser verification used a disposable database in the OS temp directory, not the repository or the live `instance/budget_companion_dev.db`; that temporary database contained only test-seeded records.
- The only canonical field formerly used by Expense but now unused is `idempotency_key`, which stays NULL for every KAN-34 write path; the existing `UNIQUE(budget_month_id, idempotency_key)` constraint remains intact and never fires for NULL values.

## 17.11 KAN-35 verification — Expense history, edit/delete and integration

KAN-35 (*"Verify Expense History, Edit/Delete Operations and Integration Tests: Complete verification of expense history and transaction management using the shared database, ensuring that changes to actual expenses are reflected consistently across the application."*) has no separate specification file in this repository, so it was verified against its title and description. The work below was completed on the KAN-34 branch against the same canonical schema; no model or migration was touched.

### Requirement → evidence

| KAN-35 requirement | Evidence | Result |
|---|---|---|
| History lists real `ExpenseRecord` rows only | `list_records()` joins `ExpenseRecord → BudgetMonth` and filters `user_id` + `PLANNED/UNEXPECTED`; `test_cross_user_and_malformed_resource_access_is_rejected`, `test_summary_pending_is_unknown_and_funds_additions_are_not_spending`, `test_kan35_history_range_follows_expense_date_while_assigned_date_stays` | PASS |
| History totals match the expense views | `test_kan35_edit_and_delete_actuals_stay_consistent_across_pages_and_budget` asserts the same edited amount and `Total:` in `/expenses/history`, the day view and the dashboard | PASS |
| History range is driven by `ExpenseDate` | `test_kan35_history_range_follows_expense_date_while_assigned_date_stays` moves a Rent transaction from 2026-10-15 to 2026-10-20: the old day/range is empty, the new one shows it, and `AssignedDate` is unchanged | PASS |
| Edit a PLANNED record | `test_editing_planned_record_changes_expense_date_not_assigned_date`, `test_actual_record_edits_and_deletes_recalculate_from_all_purchases`, `test_kan35_…budget` | PASS |
| Edit an UNEXPECTED record | `test_editing_unexpected_record_updates_priority_scope_and_keeps_task_null` (priority/scope/summary update, `TaskID` stays `NULL`) | PASS |
| Delete a record (single row) | `test_deleting_final_planned_record_resets_to_pending_and_derives_unrecorded`, `test_delete_from_history_removes_record_and_returns_to_history_range`, `test_kan35_…budget` (sibling UNEXPECTED row survives) | PASS |
| Delete reverts task state | Delete recalculates the task to `PENDING`; after the deadline the display becomes `UNRECORDED`, never auto `NO_EXPENSE` | PASS |
| Edit/delete never touches Budget | `_budget_snapshot()` compares `BudgetMonth.AvailableFunds`, `BudgetPlan`, `BudgetAllocation`, `BudgetExpense` and each task's `OriginalLimit`/`CurrentLimit`/`AssignedDate`/`PeriodEnd`/`PaymentDueDate`/`PaymentStatus` before editing, after editing and after both deletes: identical | PASS |
| Changes propagate to Dashboard | `build_dashboard()` reads `expenses.build_summary()` on every request (no cache); the new test asserts `spent` 250.123 → 400.123 → 123 → 0 and `records`/`breakdown` shrink with each delete; `/dashboard` renders 200 | PASS |
| Changes propagate to Recommendations | `analysis_key` hashes the record set, so edited/deleted evidence yields a new key; `test_actual_overspending_changes_evidence_and_snapshot_without_adjustment` and `test_saved_guidance_is_withheld_when_current_evidence_becomes_insufficient` | PASS |
| Ownership and CSRF on every mutation | `test_cross_user_and_malformed_resource_access_is_rejected`, `test_http_cross_user_posts_do_not_trust_submitted_identity`, `test_expense_mutations_require_csrf`, `test_no_anonymous_demo_identity_or_cleanup` | PASS |
| Shared database / migrations | `test_canonical_schema_has_no_single_planned_record_per_task_constraint`, `test_integrated_workflow_on_migrated_schema` (Alembic head, real workflow), `tests/test_migrations.py` | PASS |
| UI access to history edit/delete | Added with this branch: Actions column, shared edit modal with Delete, `page=history` PRG return; verified in the browser (section 17.9) and by tests 14–17 | PASS |

### What KAN-34 already covered vs. what KAN-35 added

Already covered by KAN-34 (re-used, not duplicated): history listing, multi-record aggregation, edit semantics, delete recalculation, payment-status independence, ownership/CSRF matrix, schema constraints, recommendation invalidation.

Added for KAN-35:

1. `tests/test_expenses.py::test_kan35_edit_and_delete_actuals_stay_consistent_across_pages_and_budget` — one HTTP scenario that edits a checked-in transaction, asserts History/Day/Dashboard agree, deletes it, asserts the task reverts to `PENDING`, deletes the UNEXPECTED row, asserts `spent == 0`, and compares a Budget snapshot at every step.
2. `tests/test_expenses.py::test_kan35_history_range_follows_expense_date_while_assigned_date_stays` — proves the history filter follows `ExpenseDate` while `AssignedDate` stays put, including the day view on both dates.
3. `_budget_snapshot()` helper in the same module, encoding the "Expense never rewrites Budget money or dates" rule as a testable invariant.

Full suite after all additions: **486 passed, 0 failed** (`tests/test_expenses.py` = 100).

### Residual gaps (honest)

- The comparison uses a single confirmed BALANCED month. Recommendations **generation** after an edit is covered (`generate()` is called again and the recommendation ID set is compared); after a **delete** only the read/analysis path is asserted (`test_saved_guidance_is_withheld_when_current_evidence_becomes_insufficient`), so a delete→regenerate scenario is not separately tested.
- History pagination does not exist; the page renders every record in the chosen range, so very long ranges are limited by rendering, not by a cap. This matches the current product scope.
- KAN-35 is documentation-verified against its title/description, since the repository contains no separate KAN-35 acceptance-criteria file.
