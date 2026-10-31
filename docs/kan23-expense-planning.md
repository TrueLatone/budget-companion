# KAN-23 — Expense Planning and Smart Check-in

Integrated selectively from feature/KAN-8-expense-checkin at
c382f6caaf31255bfc9dd7793a6d368f638fa8a1 on integration/pa2-20261031.
The KAN-21 Budget implementation and all 13 canonical models/migrations are
unchanged. No duplicate models, alternate database or dependencies were added.

## Reused and replaced code

- Retained KAN-8's day/month/year navigation, calendar/task adapters, responsive
  calendar CSS, expense/history templates, HTTP form flow and validation helpers.
  Presentation helpers live in presentation.py, isolated from persistence.
- Reused compatible navigation tests and adapted check-in, summary, ownership,
  history and retry scenarios to create plans with the real Budget services.
  Expense workflow fixtures confirm plans through Budget services, not raw plan
  inserts or legacy string IDs; malformed rows appear only in negative tests.
- Replaced KAN-8's demo identity/user creation, date-prefixed ID generator,
  unused all-month source, first-transaction overwrite and unsafe bulk cleanup.
  expense_planning.py and idgen.py are not copied or imported. Its changes to
  models/__init__.py, tests/conftest.py and existing shared CSS are not applied.
- Added only template style/script blocks to the common shell; Expense flashes
  are local to Expense templates, preserving existing auth/Budget flash handling.

## Scheduling and Budget contract

1. Sign in, select an owned BudgetMonth, create/choose/confirm a KAN-21 plan,
   then open Expenses from the budget page.
2. POST the CSRF-protected Create / verify spending schedule action. GETs are
   read-only. ensure_tasks_for_month(user_id, month_id) locks the authorized
   month and consumes budgets.get_confirmed_allocations; drafts never supply
   tasks. List/get/due queries also restrict ownership and confirmed status.
3. The entire monthly allocation covers tracking_start_date through month end.
   DAILY creates one task per eligible day. WEEKLY creates Monday–Sunday
   periods clipped to tracking/month edges; MONTHLY creates one tracked period.
   is_recurring is Budget's future-month reuse flag, not permission to ignore
   allocation_frequency or repeat the monthly amount on every occurrence.
4. Split integer VND by eligible days per period using integer largest-remainder
   arithmetic, tied chronologically. This reuses KAN-21's exact split helper.
   Example: 100,003 VND over three eligible days is 33,335 + 33,334 + 33,334.
   A zero-limit task remains PENDING; a zero limit does not mean no spending.
5. New task UUIDs reference allocation_id. original_limit is the computed share,
   current_limit starts equal to it, and task_status starts PENDING. A monthly
   due_day is clamped to month end; payment status begins UNPAID. Due dates
   before tracking stay unchanged and outstanding, never silently paid/deleted.
   Non-bill tasks have NULL payment fields.
6. Each allocation's original limits sum exactly to allocated_amount, including
   leap months/partial weeks. Original task limits plus savings equal the
   confirmed plan total even after available_vnd changes. Savings, reservations
   and meal subdivisions are not scheduled a second time.
7. Retrying uses (allocation_id, assigned_date), compares saved periods, original
   limits and due dates, and inserts only missing matching tasks. Existing UUIDs,
   current limits, transactions and check-in/payment statuses are preserved.
   Incompatible schedules return 409. The transaction and existing unique
   constraint prevent partial/duplicate schedules; a concurrent conflict can be
   retried after reloading. No Budget allocation or confirmed setup is rewritten.

## Spending/check-in rules

- All routes use login_required and global Flask-WTF CSRF. Identity comes from
  g.current_user; explicit service user_id is a trusted server-side argument.
  Malformed/foreign month/task/record/category references are rejected. No
  anonymous demo fallback or production bulk-cleanup route exists.
- Actual check-ins append positive integer VND transactions. Multiple purchases
  per task are supported and summed for display/derived status. A distinct token
  means a new purchase; the same month-scoped token with identical type, task,
  category, date, amount, title, priority, scope and note replays without a write.
  Different data under an existing token returns 409, including a token reused
  between planned and unexpected transactions.
- The explicit planned action records current_limit once. Zero allowances cannot
  be inserted as transactions. After spending exists, use a new actual purchase
  or edit an individual record, rather than adding the full plan again.
- NO_EXPENSE creates no transaction and is repeat-safe. It is rejected while
  linked spending exists. A later explicit purchase changes it to RECORDED.
  Deleting the last purchase restores PENDING, not NO_EXPENSE. OVER_BUDGET,
  WITHIN_BUDGET and UNRECORDED are derived, never stored in task_status.
- Actual dates cannot be future, pre-tracking, outside the month, or outside the
  task's period. Editing cannot move a transaction to another month or unlink
  it from its task. Late cross-month bill reporting needs a separate policy.
- Unexpected spending requires an existing owned month, category name and
  explicit P0/P1/P2 priority. It never creates a zero-funded month or assumes
  a missing amount/category/priority. Amounts are positive signed-BIGINT VND,
  titles at most 120 characters, categories at most 100 and notes at most 2000.
- All writes lock the owned month and roll back together on validation or DB
  failure. Category creation is also rolled back on failure. Editing/deleting
  spending never changes available_vnd or the original Budget plan.
- FUNDS_ADDED is excluded from spending totals and cannot be edited/deleted by
  Expense routes. Funds additions and automatic budget adjustment are separate
  unimplemented workflows. Self-reported PAID/UNPAID does not move money or
  automatically create an actual transaction.

## Unknown values and reports

The observed transaction sum is labeled separately from a complete spending
comparison. No check-in means Unknown, not zero. Explicit NO_EXPENSE is the
only zero-spending confirmation. Incomplete schedules, pending/missing check-ins
or mismatched period/date coverage keep difference NULL, displayed as a dash
with an Unknown explanation. Missing schedule rows cannot establish a balance.
Year cards compute completeness per month. Views use assigned period starts for
plan totals and actual dates for transactions; due-only items are displayed
without adding the same allocation to the assigned total again.

Dates/times use Vietnam calendar days, with overdue status after the assigned
period ends. Day/month/year navigation, calendar drill-down, individual record
edit/delete and history come from the KAN-8 UI. Actual input fields are blank
for a new purchase; aggregate task totals are not submitted as another purchase.
Edit-latest links are labeled explicitly and all purchases remain individually
editable in the transaction list. Existing language preference/navigation is
preserved; Expense copy currently mixes Vietnamese and English.

## Remaining limits

- Live PostgreSQL concurrent scheduling/write tests and browser interaction
  remain deployment checks; automated verification uses SQLite, migrations and
  Flask's HTTP test client. Unique constraints are the final duplicate guard.
- Retry tokens remain reserved while the corresponding transaction exists.
  Deleting a transaction deletes its token reservation under the unchanged
  schema; forms must be refreshed after deletion. Durable cancellation/tombstone
  semantics would require a separately reviewed persistence design.
- There is no cross-month payment transfer, funds-addition workflow, scheduled
  future-month copying, automatic reallocation or Dashboard/Recommendations
  binding. Budget setup/confirmation behavior is preserved.

## Validation

Final command: `.\.venv\Scripts\python.exe -m pytest -q`.
Result: **294 passed, 122 warnings in 36.27s**, with no failures. Warnings are
WTForms SelectField tuple choices, Flask-Migrate get_engine and SQLite date
adapter deprecations; no new dependencies are involved.

Coverage includes an actual login → Budget confirmation → schedule → repeated
actual purchase → NO_EXPENSE → unexpected transaction → history HTTP flow with
CSRF enabled, all six unprotected Expense POSTs rejected, cross-user/forged-user
access, exact BIGINT database round trips, leap years/clipped weeks, future and
zero-limit tasks, schedule retries/missing periods/atomic rollback, multiple
purchases, token-payload conflicts, edits/deletes and migration-created schema.
The canonical 13-table metadata is unchanged. Budget module code/rules/forms and
Budget tests have no diff against the verified pre-KAN-23 integration HEAD.
