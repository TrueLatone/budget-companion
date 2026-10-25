# KAN-08 — Expense Planning & Smart Check-in — Work Report

**Module:** Expense Planning & Smart Check-in
**Branch:** `feature/KAN-08-expense-planning-checkin`
**Report date:** 25/10/2026
**Status:** P1 and P2 implemented and verified. P3 and P4 were not implemented. Outstanding integration blockers remain.

---

## 1. Overview

This report covers the recovery and integration of the Expense Planning & Smart Check-in module, the correction of the test fixture, consolidation of the Alembic migration graph (P1), and addition of CSRF protection to Expense Planning POST forms (P2).

The work was performed on branch `feature/KAN-08-expense-planning-checkin`. The objective was to preserve existing application behavior while restoring the module and validating its integration without expanding the approved implementation scope.

The report distinguishes:

- **Recovery and integration work** — restoring the recovered module and reconciling it with the current application.
- **P1** — creating the empty Alembic merge revision.
- **P2** — adding CSRF hidden fields to Expense Planning POST forms.

P3 (authentication and ownership integration) and P4 (general README/documentation updates) were not performed.

---

## 2. Recovery & Integration

### 2.1. Stash context

The Expense Planning work was recovered from the existing Git stash:

```text
stash@{0}: On feature/expense-planning-checkin: WIP before adding expense model Markdown
```

The stash was based on an older commit (`116c8e0`, “Initial Repo Initialization”) than the current `main` and branch HEAD (`9297bcc`, “Add F18 and F19 demo implementation”). This difference explains the conflicts encountered when the stash was applied.

The stash remains preserved as a recovery point. It was not reapplied, popped, dropped, or cleared during P1/P2 or during preparation of this report.

### 2.2. Conflict resolution and integration

The following files required manual reconciliation with the current application:

| File | Recovery/integration change |
|---|---|
| `README.md` | Reconciled with the current project state and Expense Planning integration. |
| `app/models/__init__.py` | Integrated the Expense Planning model imports so Flask-Migrate can see the models. |
| `app/static/css/app.css` | Integrated the Expense Planning UI styles with the current stylesheet. |
| `app/templates/base.html` | Reconciled the shared base template with the current application layout. |
| `tests/conftest.py` | Corrected the test fixture so the Flask application context remains active for the duration of each test. |

These changes are part of the recovery/integration phase. They are separate from the later P1 and P2 tasks.

No conflict markers, `.orig` files, `.rej` files, or unmerged index entries remained after reconciliation. The recovered module includes its Expense Planning models, routes, services, validation and scheduling helpers, templates, tests, and migration files.

### 2.3. Test-fixture correction

`tests/conftest.py` was corrected so the application context remains active while tests use the application and database. The fixture now creates/drops the in-memory test database inside the application context and keeps that context active for the test body.

This addressed failures caused by the fixture yielding outside the application context.

### 2.4. Scope boundary

Recovery and integration restored existing work and reconciled it with the current codebase. P1 and P2 were then implemented as narrowly scoped follow-up tasks:

- P1 did not alter any existing migration file.
- P2 did not change routes, services, validators, models, business rules, or test configuration.
- Neither task changed the approved database designs.

---

## 3. P1 — Migration Merge

### 3.1. Added revision

A single new, empty Alembic merge revision was added:

```text
migrations/versions/a8c32b643be1_merge_expense_planning_and_budget_.py
```

### 3.2. Revision metadata

```python
revision = 'a8c32b643be1'
down_revision = ('de12e989405f', 'dfa92b9022a2')
```

The two parent revisions are:

- `de12e989405f` — creates `users` and `budget_months`.
- `dfa92b9022a2` — adds the unexpected-expense idempotency key and index.

### 3.3. Schema operations

Both migration functions are empty:

```python
def upgrade():
    pass


def downgrade():
    pass
```

The revision performs no table, column, constraint, index, foreign-key, or data operations. No existing migration file was edited, renamed, or deleted.

### 3.4. Alembic head

`flask db heads` reports exactly one head:

```text
a8c32b643be1 (head)
```

`flask db history` confirms the merge point:

```text
de12e989405f, dfa92b9022a2 -> a8c32b643be1 (head) (mergepoint)
```

### 3.5. Database upgrade status

No database upgrade was performed in this task. The merge revision was created and the Alembic graph was inspected, but `flask db upgrade` was not run against any database.

---

## 4. P2 — CSRF Protection for Expense Planning POST Forms

### 4.1. Changed template

The only template changed by P2 was:

```text
app/templates/pages/expenses.html
```

### 4.2. Change made

A hidden CSRF field was added to each Expense Planning POST form:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

The template contains 11 unique POST form definitions, and all 11 now include this field:

1. Task check-in form.
2. Payment due-date form.
3. Clear-demo form.
4. Create demo expense source form.
5. Activate/deactivate expense source form.
6. Delete expense source form.
7. Generate task schedule form.
8. Create unexpected expense record form.
9. Delete expense record form.
10. Edit expense source form.
11. Edit expense record form.

### 4.3. Preserved behavior

The change added hidden security fields only. The following were not changed:

- Form `action` URLs.
- Form methods.
- Input names and values.
- Server-side validation.
- Routes and services.
- Business logic.
- Layout and user-facing text.
- JavaScript behavior.

The history page (`app/templates/pages/expense_history.html`) was not changed because its form uses `GET`, not `POST`.

Global CSRF protection was not disabled or weakened. The test configuration was not changed to hide CSRF failures.

---

## 5. Form-Count Discrepancy — Verified

An earlier report noted a difference between the static template count and the runtime rendered count. The difference was investigated and is fully explained.

### 5.1. Static template count

`app/templates/pages/expenses.html` contains:

| Item | Count |
|---|---:|
| Total `<form>` tags | 14 |
| POST form definitions | 11 |
| GET form definitions | 3 |
| CSRF hidden fields | 11 |

All 11 POST form definitions contain a CSRF token.

### 5.2. Runtime count — seeded day view

A runtime check was performed with `WTF_CSRF_ENABLED=True` and a disposable in-memory SQLite database. One plan item, one generated task, and one unexpected record were seeded.

Rendered page result:

| Item | Count |
|---|---:|
| Total rendered forms | 14 |
| Rendered GET forms | 2 |
| Rendered POST form instances | 12 |
| Rendered POST instances with CSRF token | 12 |
| Rendered POST instances without CSRF token | 0 |

### 5.3. Explanation

The difference is not a missing token. The template intentionally renders the due-date form in both responsive layouts:

- Desktop table: `render_due_form(...)` is called at `expenses.html:330`.
- Mobile card layout: the same macro is called at `expenses.html:376`.

One layout is hidden by responsive CSS at any viewport, so the same form appears twice in the HTML.

In addition, the year-view GET form at `expenses.html:447` is not rendered in the tested day view. Therefore:

```text
11 unique POST form definitions
+ 1 repeated due-date form instance from desktop/mobile rendering
= 12 rendered POST form instances
```

All 12 rendered POST instances contained a valid CSRF token.

### 5.4. CSRF behavior check

The runtime check also verified:

| Request | Result |
|---|---|
| POST `/expenses/sources` without CSRF token | HTTP 400 |
| POST `/expenses/sources` with valid CSRF token | HTTP 200 |

The temporary verification script was created outside the repository and removed afterward. No CSRF test was added to the repository during this task.

---

## 6. Tests and Verification

### 6.1. Results actually obtained

| Check | Result |
|---|---|
| Full test suite (`python -m pytest -q -p no:cacheprovider`) | **89 passed in 9.04s** |
| Alembic heads (`flask --app app db heads`) | **One head: `a8c32b643be1`** |
| Alembic history | Merge point confirmed: `de12e989405f, dfa92b9022a2 -> a8c32b643be1` |
| CSRF runtime check | 12/12 rendered POST forms had tokens; no-token POST returned 400; valid-token POST returned 200 |

### 6.2. Important limitation of the suite

The test fixture configures `WTF_CSRF_ENABLED=False`. Therefore, the 89 passing tests validate the application flows but do not themselves prove that the templates contain valid CSRF fields. The CSRF behavior was verified separately with the runtime check described above.

### 6.3. Commands not run

The following were not run as part of this work:

- `flask db upgrade` against any database.
- `flask db downgrade` against any database.
- Any shared, production, or Supabase database migration.
- Any commit, push, branch switch, reset, clean, or stash modification (apply/pop/drop/clear).

The reported test and Alembic results above are actual results from the verification performed in this conversation. No additional test result is claimed.

---

## 7. Out of Scope

The following items were explicitly not implemented:

### P3 — Authentication and user ownership

- `DEMO_USER_ID = "demo-user"` was not replaced.
- No login decorators were added.
- Authentication, authorization, session ownership, and user-ID formats were not changed.
- Demo-data behavior was not changed.

### P4 — General README and documentation updates

- `README.md` and general documentation were not updated as part of P1/P2.
- `README.md` had been touched during the earlier recovery conflict resolution; that is separate from P4.
- This report file is the requested artifact and is not a general documentation update.

### Database design protection

- No database tables, columns, constraints, indexes, foreign keys, or data were added, removed, renamed, or retyped.
- The only migration change is the empty merge revision `a8c32b643be1`.
- No mapping table, `source_allocation_id`, or other workaround field was added.

### Unrelated modules

No unrelated module, shared template, route, service, model, or test configuration was changed by P1/P2.

---

## 8. Outstanding Blockers

The following issues remain unresolved and are not claimed as complete.

### 8.1. Authentication and ownership integration

- Expense Planning still uses `DEMO_USER_ID = "demo-user"`.
- Expense routes are not protected by login enforcement.
- There is an ownership type mismatch:
  - Expense Planning `user_id` fields are `String(64)`.
  - `users.id` is UUID (`Uuid(as_uuid=True)`).
- A coordinated decision with the Accounts owner and Project Lead is required before changing this.

### 8.2. Budget Plan/Allocation integration

- No implemented Budget Expense, Budget Plan, Budget Allocation, or Spending Schedule physical table/API is available to link against.
- `expense_plan_items.source_expense_id` is only a nullable external identifier; it does not establish a Budget Plan/Allocation relationship.
- There is no plan/allocation identifier suitable for a verified relationship.
- The Budget and Expense designs conflict on who owns automatic reallocation.
- The Budget design documents conflict on the shape of Budget Allocation.
- Integration must wait for an agreed physical schema or API contract from the Budget Planning owner.

### 8.3. Schema and documentation gaps

- `expense_records.budget_impact_scope` appears in the approved Expense design but is absent from the physical schema. Adding it would require separate schema approval.
- `docs/expense-planning-implementation.md` still contains older statements, including that CSRF was not implemented. That statement is now stale after P2.
- The local development database was not upgraded and therefore does not reflect the new merge head.
- The local development database was previously observed at `dfa92b9022a2` with only the Expense tables; the `users` and `budget_months` tables were not present. This must be addressed by a separate, approved database upgrade plan.

### 8.4. Database upgrade plan

No decision has been made about upgrading the local, shared, or production database to `a8c32b643be1`. That work is intentionally deferred and must not be treated as completed.

---

## 9. Git Status and Handoff

- **Branch:** `feature/KAN-08-expense-planning-checkin`
- **HEAD at verification:** `9297bcc` (same as `main` at that time)
- **Commit/push:** none performed.
- **Stash:** `stash@{0}` remains present and preserved.
- **Branch switch/reset/clean:** none performed.
- **Database upgrade:** none performed.
- **P1 file:** `migrations/versions/a8c32b643be1_merge_expense_planning_and_budget_.py` (new, untracked).
- **P2 file:** `app/templates/pages/expenses.html` (updated).
- **Report file:** `docs/KAN-08-expense-planning-work-report.md` (this file).

The recovery/staged changes from the earlier integration phase remain in the working tree. They were not committed or discarded.

---

## 10. Conclusion

P1 and P2 are implemented and verified:

- The migration graph now has a single head through the empty merge revision `a8c32b643be1`.
- Expense Planning POST forms now include CSRF tokens.
- The apparent 11-versus-12 form-count discrepancy is explained by responsive duplicate rendering of the due-date form, not by a missing token.
- The latest full test suite result is **89 passed in 9.04s**.

Authentication/ownership integration, Budget Plan/Allocation linkage, `budget_impact_scope`, documentation synchronization, and the database upgrade plan remain outstanding and require separate approval.
