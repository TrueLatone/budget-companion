# KAN-35 — Test Report

**Ticket:** KAN-35 — *Verify Expense History, Edit/Delete Operations and Integration Tests*
**Jira description:** *Complete verification of expense history and transaction management using the shared database, ensuring that changes to actual expenses are reflected consistently across the application.*
**Branch:** `feature/KAN-34-AND-KAN-35`
**Date:** 2026-11-05
**Companion documents:** [KAN-34-smart-checkin-statuses.md](KAN-34-smart-checkin-statuses.md) (implementation, section 17.11 = KAN-35 verification), [KAN-34-test-report.md](KAN-34-test-report.md) (KAN-34 test report)

This report covers only the **testing** portion of KAN-35. The repository has no separate KAN-35 acceptance-criteria file, so verification follows the ticket title and description. No model, migration or live database row was changed.

---

## 1. Environment and commands

| Item | Value |
|---|---|
| OS / shell | Windows 10 (10.0.19045), PowerShell + Git Bash |
| Runtime | `.venv\Scripts\python.exe` (bare `python` has no pytest) |
| Full-suite command | `.venv\Scripts\python.exe -m pytest -q` |
| Expense module command | `.venv\Scripts\python.exe -m pytest -q tests/test_expenses.py` |
| Integration module command | `.venv\Scripts\python.exe -m pytest -q tests/test_build1_integration.py tests/test_dashboard.py` |
| Database | Real canonical schema (SQLAlchemy models / Alembic head) on SQLite test databases |

---

## 2. Headline result

| Suite | Tests | Result |
|---|---|---|
| **Full repository suite** | **486** | **486 passed, 0 failed** (108.59 s) |
| `tests/test_expenses.py` | 100 | 100 passed |
| `tests/test_build1_integration.py` | 3 | 3 passed |
| `tests/test_dashboard.py` | 23 | 23 passed |
| `tests/test_schema_constraints.py` | 96 | 96 passed |
| `tests/test_migrations.py` | 4 | 4 passed |
| `tests/test_recommendations.py` | 63 | 63 passed |

0 failed, 0 errors, 0 skipped. Warnings (214) are pre-existing third-party deprecations and were not suppressed.

---

## 3. Requirement → test evidence

| KAN-35 requirement | Test evidence | Result |
|---|---|---|
| History lists real `ExpenseRecord` rows only (PLANNED/UNEXPECTED, owned month, no `FUNDS_ADDED`) | `test_cross_user_and_malformed_resource_access_is_rejected`, `test_summary_pending_is_unknown_and_funds_additions_are_not_spending` | PASS |
| History totals agree with the expense views and the dashboard | `test_kan35_edit_and_delete_actuals_stay_consistent_across_pages_and_budget` — the same edited amount and `Total:` appear in `/expenses/history`, the day view and `build_dashboard()` | PASS |
| The history range follows `ExpenseDate`, not `AssignedDate` | `test_kan35_history_range_follows_expense_date_while_assigned_date_stays` | PASS |
| Edit a `PLANNED` record without changing task dates or Budget data | `test_editing_planned_record_changes_expense_date_not_assigned_date`, `test_kan35_…budget` (Budget snapshot identical before/after) | PASS |
| Edit an `UNEXPECTED` record (priority, scope, still `TaskID = NULL`) | `test_editing_unexpected_record_updates_priority_scope_and_keeps_task_null` | PASS |
| Delete removes exactly one row; sibling records survive | `test_delete_from_history_removes_record_and_returns_to_history_range`, `test_kan35_…budget` | PASS |
| Delete reverts task state | `test_deleting_final_planned_record_resets_to_pending_and_derives_unrecorded`, `test_delete_from_history_removes_record_and_returns_to_history_range` | PASS |
| Edit/delete never touch Budget | `_budget_snapshot()` compares `BudgetMonth.AvailableFunds`, `BudgetPlan`, `BudgetAllocation`, `BudgetExpense`, and each task's `OriginalLimit`/`CurrentLimit`/`AssignedDate`/`PeriodEnd`/`PaymentDueDate`/`PaymentStatus` at every step | PASS |
| Changes propagate to the Dashboard | `spent` sequence 250.123 → 400.123 → 123 → 0; `records`/`breakdown` shrink; `/dashboard` returns 200 | PASS |
| Changes propagate to Recommendations | `test_actual_overspending_changes_evidence_and_snapshot_without_adjustment`, `test_saved_guidance_is_withheld_when_current_evidence_becomes_insufficient` | PASS |
| Ownership and CSRF on every mutation | `test_cross_user_and_malformed_resource_access_is_rejected`, `test_http_cross_user_posts_do_not_trust_submitted_identity`, `test_expense_mutations_require_csrf[6 cases]`, `test_no_anonymous_demo_identity_or_cleanup` | PASS |
| Shared database and migrations | `test_integrated_workflow_on_migrated_schema`, `test_canonical_schema_has_no_single_planned_record_per_task_constraint`, `tests/test_migrations.py` | PASS |
| History UI offers Edit and Delete, and returns to the same range | `test_history_page_offers_edit_and_delete_for_every_transaction`, `test_edit_from_history_returns_to_history_range`, `test_delete_from_history_removes_record_and_returns_to_history_range`, `test_day_view_edit_modal_also_offers_delete` | PASS |

---

## 4. Tests added for KAN-35

### 4.1 `test_kan35_edit_and_delete_actuals_stay_consistent_across_pages_and_budget`

Scenario:

1. Seed a confirmed month; check in 250.000 ₫ on Food and add a 123 ₫ UNEXPECTED record. Dashboard `spent == 250.123`.
2. Capture `_budget_snapshot()` (Budget months, plans, allocations, expenses and every task money/date/payment field).
3. HTTP-edit the planned transaction to 400.000 ₫ with note `raise`.
4. Assert `/expenses/history` shows `400.000 ₫` and `Total: 400.000 ₫`; dashboard `spent == 400.123`; the stored record is 400.000 ₫; the Budget snapshot is unchanged.
5. HTTP-delete the planned transaction. History shows "No transactions in the selected range.", the day view shows "No actual transactions", `/dashboard` still returns 200, dashboard `spent == 123` and only the UNEXPECTED record remains, the task is back to `PENDING`, and the Budget snapshot is unchanged.
6. HTTP-delete the UNEXPECTED record. Dashboard `spent == 0`, `records == []`, `breakdown == []`, zero `ExpenseRecord` rows, Budget snapshot still unchanged.

This is the end-to-end proof that an actual-expense edit or delete is reflected consistently in history, the day view, the dashboard and the database, while Budget-owned data is never rewritten.

### 4.2 `test_kan35_history_range_follows_expense_date_while_assigned_date_stays`

Scenario: check in a Rent task on its `AssignedDate` (2026-10-15, `PeriodEnd` 2026-10-31), then edit the transaction's `ExpenseDate` to 2026-10-20.

Assertions:

- `AssignedExpenseTask.AssignedDate` is still 2026-10-15 and the Budget snapshot is unchanged.
- `/expenses/history?start=2026-10-15&end=2026-10-15` is empty.
- `/expenses/history?start=2026-10-20&end=2026-10-20` shows `150.000 ₫` and `Total: 150.000 ₫`.
- The day view on 2026-10-20 shows the amount; the day view on 2026-10-15 shows "No actual transactions".

### 4.3 Shared helper

`_budget_snapshot()` encodes "Expense never rewrites Budget money or dates" as a reusable invariant: `BudgetMonth.AvailableFunds`, `BudgetPlan.Status`/`PlannedSavings`, `BudgetAllocation.AllocatedAmount`, `BudgetExpense` fields, and per-task `OriginalLimit`/`CurrentLimit`/`AssignedDate`/`PeriodEnd`/`PaymentDueDate`/`PaymentStatus`. It is compared before the first mutation, after the edit and after each delete.

---

## 5. Reused KAN-34 coverage (not duplicated)

KAN-34 already established the history listing, multi-record aggregation, edit semantics, delete recalculation, payment-status independence, the ownership/CSRF matrix, schema constraints and recommendation invalidation. KAN-35 re-runs those tests in the same suite instead of restating them.

---

## 6. Browser verification (history edit/delete, real UI)

A disposable SQLite database (Alembic `upgrade()` + one user, confirmed BALANCED plan, 40 tasks, one PLANNED check-in of 250.000 ₫ and one UNEXPECTED "Repair" record) was served on a temporary port and driven by the in-app browser. The live development database was not opened for writing; the temporary database and server were removed afterwards.

| Step | Observed |
|---|---|
| `/expenses/history?start=2026-11-01&end=2026-11-30` | New **Actions** column with `Edit` and `Delete` for both rows; page fully English |
| Click `Edit` | Shared "Edit transaction" modal with Delete/Cancel/Save footer; both forms carry `csrf_token`, `page=history`, `start`, `end` |
| Save 260.000 ₫ + note `verified edit` | 302 to the same history range, flash "Transaction updated.", row shows `260.000 ₫` / `verified edit` |
| Click `Delete transaction` | Browser confirm "Delete this transaction? Other transactions for the same task are kept."; cancelling keeps row and modal |
| Accept delete | 302 to the same range, flash "Transaction deleted.", only that row removed (the PLANNED row survived) |
| Day/month/year views | `view=day` (2026-11-05), `view=month` (Month 11/2026), `view=year` (2026) render with no error page and no Vietnamese visible text; the day view exposes the Delete form in its edit modal |
| Console | No messages emitted |

---

## 7. Residual gaps and honest limitations

1. **Single-month test data.** The consistency scenario uses one confirmed BALANCED month. Cross-month history ranges are not separately tested.
2. **Delete → regenerate Recommendations is not tested directly.** Edit → regenerate is covered; after delete only the read/analysis path is asserted (`test_saved_guidance_is_withheld_when_current_evidence_becomes_insufficient`).
3. **No history pagination.** The page renders every record in the chosen range; there is no cap and therefore no pagination test. This matches current product scope.
4. **KAN-35 is verified against its title/description**, not a repository acceptance-criteria file, because none exists.
5. **Browser evidence is manual** and not part of `pytest`; the automated tests cover the same server-side contract.
6. **SQLite only.** No test runs against Postgres/Supabase; the migrated-schema integration test uses SQLite with the real Alembic revision graph.
7. **No live-data backfill verification.** Months confirmed before the KAN-34 handoff fix still lack tasks; the repair endpoint exists and is tested idempotently, but no live production row set was modified or re-checked after a repair.

---

## 8. Verdict

- Expense history, edit and delete are verified end-to-end (HTTP + database + dashboard + history + day view): **PASS**.
- Budget-owned data remains untouched across edit and delete: **PASS** (snapshot equality at every step).
- Integration suite, schema constraints and migrations all green: **PASS**.
- Remaining gaps are scope/coverage disclosures, not failures.
