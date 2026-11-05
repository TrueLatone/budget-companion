# KAN-34 — Test Report

**Ticket:** KAN-34 — *Stabilize Smart Check-in Statuses and Prevent Duplicate Expense Records*
**Jira description:** *Refine Smart Check-in behavior to ensure that expense task statuses and recorded spending remain consistent with the shared database and use-case specifications.*
**Branch:** `feature/KAN-34-AND-KAN-35`
**Date:** 2026-11-05
**Companion documents:** [KAN-34-smart-checkin-statuses.md](KAN-34-smart-checkin-statuses.md) (implementation + rationale), [KAN-35-test-report.md](KAN-35-test-report.md) (history/edit/delete verification)

This report covers only the **testing** portion of KAN-34. It records what was executed, what passed, what the tests actually assert, and which risks remain untested. The shared database was not modified: no model file, migration, index, constraint or live database row was touched.

---

## 1. Environment and commands

| Item | Value |
|---|---|
| OS / shell | Windows 10 (10.0.19045), PowerShell + Git Bash |
| Runtime | `.venv\Scripts\python.exe` (project virtualenv; the bare `python` on PATH has no pytest) |
| Framework | pytest, Flask test client, real SQLite test databases |
| Full-suite command | `.venv\Scripts\python.exe -m pytest -q` |
| Single-module command | `.venv\Scripts\python.exe -m pytest -q tests/test_expenses.py` |
| Browser command | Flask dev server on a disposable port against a throwaway SQLite file, driven by the in-app browser |

The default test configuration is `TESTING=True` with `sqlite://` (in-memory) and `WTF_CSRF_ENABLED=False`; a dedicated CSRF test re-enables it. `tests/test_migrations.py` runs real Alembic `upgrade()` against a file database.

---

## 2. Headline result

| Suite | Tests | Result |
|---|---|---|
| **Full repository suite** | **486** | **486 passed, 0 failed** (108.59 s) |
| `tests/test_expenses.py` | 100 | 100 passed |
| `tests/test_schema_constraints.py` | 96 | 96 passed |
| `tests/test_expense_presentation.py` | 10 | 10 passed |
| `tests/test_migrations.py` | 4 | 4 passed |
| `tests/test_dashboard.py` | 23 | 23 passed |
| `tests/test_recommendations.py` | 63 | 63 passed |
| `tests/test_budget_setup_parity.py` | 50 | 50 passed |
| `tests/test_budgets.py` | 45 | 45 passed |
| `tests/test_build1_integration.py` | 3 | 3 passed |

0 failed, 0 errors, 0 skipped, 0 xfailed. The 214 warnings are pre-existing deprecations from WTForms, Flask-SQLAlchemy `get_engine`, and the Python 3.12 SQLite date adapter; none originate from Expense code.

---

## 3. What KAN-34 changed, and the tests that guard each change

### 3.1 Task status consistency (`PLANNED` records, `RECORDED`, `NO_EXPENSE`, `UNRECORDED`)

| Behaviour | Guarding test(s) |
|---|---|
| Several `PLANNED` records for one task aggregate against the current limit instead of overwriting each other | `test_multiple_planned_records_aggregate_against_current_limit`, `test_actuals_are_multiple_independent_transactions_and_aggregate`, `test_actual_record_edits_and_deletes_recalculate_from_all_purchases` |
| Editing a `PLANNED` record moves `ExpenseDate` only; `AssignedDate`, `PeriodEnd` and Budget money stay put | `test_editing_planned_record_changes_expense_date_not_assigned_date`, `test_kan35_history_range_follows_expense_date_while_assigned_date_stays` |
| Deleting the final `PLANNED` record resets the persisted status to `PENDING` and the display becomes `UNRECORDED` after the deadline (never auto `NO_EXPENSE`) | `test_deleting_final_planned_record_resets_to_pending_and_derives_unrecorded` |
| `NO_EXPENSE` is explicit, repeat-safe and cannot hide an existing actual | `test_no_expense_is_explicit_repeat_safe_and_cannot_hide_actuals`, `test_future_tasks_cannot_be_converted_to_no_expense` |
| `confirm as planned` is refused once a record exists | `test_confirm_as_planned_is_rejected_after_a_transaction_exists` |
| A zero allowance stays unknown until an explicit check-in | `test_zero_task_allowance_stays_unknown_until_explicit_checkin` |
| `PaymentStatus` is independent of check-in, edit and delete | `test_payment_status_is_independent_of_checkin_edit_and_delete` |
| A `PaymentDueDate` marker never creates a task occurrence | `test_payment_due_date_marker_does_not_create_a_task_occurrence` |
| Calendar cells place tasks on `AssignedDate` only; due moves are shown separately | `test_tasks_appear_only_on_assigned_date_and_due_dates_are_separate`, `test_calendar_distinguishes_actual_pending_no_expense_and_unrecorded` |
| Calendar status covers empty, unplanned, draft, confirmed-but-unscheduled and partial schedules | `test_calendar_empty_states_are_actionable_and_read_only[4 cases]`, `test_calendar_partial_schedule_is_explicit_and_repaired_without_overwriting`, `test_conflicting_calendar_schedule_is_explained_and_not_overwritten`, `test_confirmed_plan_without_allocations_explains_corrupt_handoff` |
| A confirmed plan receives its tasks in the same request (Budget→Expense handoff) | `test_confirm_schedule_and_calendar_connect_to_dashboard`, `test_confirmation_guides_to_owned_month_and_safe_csrf_post`, `test_build1_registration_to_recommendation_survives_replay_and_restart`, `test_schedule_post_failure_preserves_confirmation_and_allows_retry` |
| Reads never generate or rewrite tasks | `test_drafts_never_schedule_and_reads_do_not_write`, `test_schedule_retry_preserves_transactions_adjustments_and_original_snapshot`, plus the `_budget_snapshot()` comparisons in the KAN-35 tests |

### 3.2 Category and priority rules

| Behaviour | Guarding test(s) |
|---|---|
| A `PLANNED` record uses the Budget category and stores `priority = NULL` | `test_planned_record_uses_budget_category_and_leaves_priority_null` |
| An unknown UNEXPECTED category is rejected and no category is created | `test_unexpected_unknown_category_is_rejected_without_creating_a_category` |
| Expense only offers existing categories (no free-text category input) | `test_expense_page_only_offers_existing_categories`, `test_task_record_adapter_does_not_expose_a_foreign_category` |
| UNEXPECTED edits change priority/scope while `TaskID` stays `NULL` | `test_editing_unexpected_record_updates_priority_scope_and_keeps_task_null` |
| Invalid UNEXPECTED input never creates funds, months or categories | `test_invalid_unexpected_expense_never_creates_funds_or_months[8 cases]` |

### 3.3 In-flight duplicate guard

`test_identical_write_already_in_flight_is_rejected_and_released` proves that a second identical write during the first one's transaction is rejected with the English conflict message, and that the guard is released afterwards (a later write succeeds). This is a process-local guard; see section 6.

### 3.4 Submission-token anti-replay (Prevent Duplicate Expense Records)

Nine tests in `tests/test_expenses.py`:

1. `test_creation_forms_render_one_fresh_opaque_token_per_form` — each rendered creation form carries a distinct token of at least 20 characters.
2. `test_replayed_checkin_token_prompts_with_saved_details_and_writes_nothing` — the replayed POST redirects to `/expenses/duplicates/<id>`, the page shows the saved title/amount/date, and the record count stays 1.
3. `test_confirming_the_duplicate_adds_exactly_one_copy_and_is_single_use` — confirming writes exactly one more record; re-posting the confirmation flashes "already used" and still leaves 2.
4. `test_identical_values_with_a_new_token_are_not_treated_as_duplicates` — two fresh tokens with identical values write two records and never prompt.
5. `test_failed_validation_does_not_consume_the_submission_token` — a rejected UNEXPECTED POST (400) leaves the token usable; the valid retry writes once, and a later replay prompts.
6. `test_deleting_the_first_transaction_lets_the_same_token_submit_normally` — after deletion the replay writes instead of prompting (no prompt about a row that no longer exists).
7. `test_planned_checkin_replay_is_kept_to_one_transaction` — a planned replay prompts with only "Keep only the first"; dismissal leaves one row.
8. `test_unexpected_replay_prompt_shows_the_saved_transaction_and_dismiss_keeps_one` — the prompt shows title, amount and date; dismissal leaves one row.
9. `test_duplicate_confirmation_is_scoped_to_its_owner` — another session cannot open the pending confirmation and is redirected with a warning.

Design constraints asserted by these tests:

- The token registry is populated only **after** the write commits, so a crash or rollback leaves the token usable.
- A token is never consumed by a validation failure or a 404/403.
- Confirmation pending entries are single-use.
- Missing/unknown/expired tokens fail open: token-less clients and service-level callers are never blocked.
- No request-field matching, no `idempotency_key`, no schema change.
- Out of scope by user decision (not implemented, not claimed): refresh-then-retype and two tabs submitting the same values.

### 3.5 Canonical schema and English UI

| Behaviour | Guarding test(s) |
|---|---|
| No unique "one PLANNED record per task" constraint exists in the canonical schema | `test_canonical_schema_has_no_single_planned_record_per_task_constraint` (plus all 96 schema tests) |
| The expense page has no recurrence-tag filter and no idempotency input | `test_expense_page_has_no_recurrence_filter_or_idempotency_input` |
| Day/month/year/history render English labels only (no Vietnamese probes) | `test_expense_pages_use_english_labels_only` |
| Scroll restoration uses a path-stable key and manual restoration | `test_scroll_script_uses_a_stable_path_key_and_manual_restoration` |

### 3.6 Integration and ownership

| Behaviour | Guarding test(s) |
|---|---|
| Real HTTP budget→check-in→dashboard workflow with CSRF | `test_complete_budget_to_expense_http_workflow_with_csrf`, `test_complete_summary_requires_every_scheduled_period_and_matching_dates` |
| Every Expense mutation requires CSRF | `test_expense_mutations_require_csrf[6 cases]` |
| Cross-user and malformed resource access is rejected | `test_cross_user_and_malformed_resource_access_is_rejected`, `test_http_cross_user_posts_do_not_trust_submitted_identity`, `test_calendar_readiness_and_display_never_include_other_users_data` |
| Registration→recommendation survives replay, restart and re-upgrade | `test_build1_registration_to_recommendation_survives_replay_and_restart` |
| Alembic head upgrade preserves data | `tests/test_migrations.py` (4 tests) |

---

## 4. Tests updated rather than duplicated

Pre-existing tests already covered several scenarios and were adapted, not duplicated: multi-actual aggregation, identical-transaction acceptance, `confirm as planned` refusal, `no_expense` refusal when records exist, zero-limit behaviour, Funds-Added exclusion, empty calendar diagnosis, the ownership/CSRF matrix and 404 isolation.

Four tests were changed for the new Budget→Expense handoff and re-verified in the final run:

- `tests/test_dashboard.py::test_confirm_schedule_and_calendar_connect_to_dashboard` — expects `READY` and 24 tasks straight after the HTTP confirm.
- `tests/test_build1_integration.py::test_build1_registration_to_recommendation_survives_replay_and_restart` — expects 40 tasks after confirm, no legacy schedule POST.
- `tests/test_expenses.py::test_confirmation_guides_to_owned_month_and_safe_csrf_post` — expects `READY` and a non-zero task count, still checks CSRF rejection and the idempotent repair endpoint.
- `tests/test_expenses.py::test_schedule_post_failure_preserves_confirmation_and_allows_retry` — injects the insert failure before confirm, asserts the warning flash, the preserved `CONFIRMED` plan, `NOT_SCHEDULED`, the 409 on repair, and a successful retry.

`tests/test_build1_integration.py` also gained `pending_id="missing-pending-id"` in its CSRF sweep so the new duplicate-confirmation routes are covered by the global CSRF assertion.

---

## 5. Browser verification (not a unit test)

A disposable SQLite database was created outside the repository and served on a temporary port; the in-app browser drove the real UI. The live `instance/budget_companion_dev.db` was never opened for writing.

| Step | Observed |
|---|---|
| First check-in of 50.000 ₫ on the Food task | 302 back to the same `view/date/budget_month_id` URL, flash "Transaction saved.", task actual 50.000 ₫ |
| Replay the same rendered form's token (hidden input swapped in the UI) | 302 to `/expenses/duplicates/<id>`, **no** second row written |
| Confirmation page | Shows `Food`, `Planned`, `50.000 ₫`, `05/11/2026`, category `Living`, empty note |
| "Keep only the first" | Redirect to `/expenses`, flash "Only the first transaction was kept. Nothing else was saved.", count stays 1 |
| Replay again → "Save another identical transaction" (checkbox required) | Redirect to `/expenses`, flash "A second identical transaction was saved.", count 2, total 100.000 ₫ |
| Third replay of the same token | Prompt again (pending entries are single-use; the token remains registered for its TTL) |
| Console | No messages emitted at any step |

Direct `fetch()` of a replayed POST is blocked by the browser debug evaluator (`Possible side-effect in debug-evaluate`), so the replay was performed by setting the form's hidden token to the already-used value and submitting through the UI. That reaches the same route and the same server-side check as a repeated click or weak-network retry.

Earlier browser runs on the same branch also verified: AssignedDate-only calendar placement, due-only section, the three check-in actions, the category `<select>`, scroll/focus restoration (`history.scrollRestoration === 'manual'`, `window.scrollY ≈ 332.67`), and `view=year`/`view=month` rendering.

---

## 6. Residual gaps and honest limitations

1. **No durable idempotency.** The submission-token registry and pending confirmations live in the signed session. A client that loses its cookie, or a second worker without the same client cookie jar, is treated as a fresh submission; expired tokens (60 minutes) behave the same. The in-flight guard is process-local. Both are deliberate fail-open choices so no database column had to be added.
2. **Approved out-of-scope cases are untested and unsupported:** page refresh followed by retyping identical values, and two tabs submitting the same values. The tests do not assert protection for them.
3. **Live development database not exercised for writes.** Verification used disposable databases only; three of the live months still show the historical missing-handoff symptom (plan confirmed before the fix), which the repair endpoint can correct but which was not corrected in place.
4. **Browser verification is manual.** It is recorded here as evidence but is not part of `pytest` and would not catch a regression automatically; the token tests cover the server-side contract instead.
5. **Warnings are pre-existing.** 214 deprecation warnings (WTForms tuple choices, Flask-SQLAlchemy `get_engine`, Python 3.12 SQLite date adapter) are unrelated to this ticket and were not suppressed.
6. **Test database is not Postgres.** All automated tests run on SQLite, including the migrated-schema integration test; Supabase/Postgres behaviour is covered only by the URL normalisation in `app/config.py`, not by an executed test.

---

## 7. Verdict

- Functional requirements of KAN-34 covered by automated tests: **PASS**.
- Duplicate-record prevention (token scope) covered by automated tests and a real browser run: **PASS**.
- Canonical schema untouched, all 96 schema-constraint tests and 4 migration tests green: **PASS**.
- Known untested areas are the ones explicitly approved as out of scope plus the documented session-bound limitations: **accepted, disclosed**.
