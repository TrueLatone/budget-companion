# KAN-21: Budget Planning integration

The existing application factory registers the Budget blueprint. It now uses
User → BudgetMonth → BudgetExpense → BudgetPlan → BudgetAllocation through the
existing SQLAlchemy extension. No schema changes, migrations, alternate Flask
application, TXT storage, external AI calls or additional dependencies are needed.

## User flow

1. Sign in, create/select a budget month, then open **Plan budget** or `/budget`.
2. Add/edit/remove expenses, choosing an owned/built-in category or naming a new
   owned category. Names are unique within the month, ignoring case.
3. Supply Rent, Electricity and Water as P0. Internet is optional but P0 when
   included. Each P0 requires a positive estimate at generation/confirmation.
   An incomplete draft may retain an unknown or explicit-zero P0 estimate.
4. Optionally supply positive P1 minimums. Blank estimated amounts are NULL,
   never zero. Explicit zero estimates remain zero. Included P1/P2 expenses
   receive positive allocations; estimates are informational, not hard caps.
5. Generate three plans, read their stored allocations, then confirm one.
   Confirmation rechecks the current funds, expense set, category authorization,
   exact P0 amounts, P1 minimums and conservation. Submitted allocation overrides
   and client user IDs are not used.

Saving/Balanced/Lifestyle use KAN-11's implemented P1/P2/savings targets of
70/5/25, 65/15/20 and 60/30/10 after reserving P0. The older rules document also
contains a competing extra-P1 ratio table. KAN-21 selects the runnable KAN-11
policy and the matching second table; it does not combine the two policies.
P1 minimums and a positive allocation for every included expense take priority:
discretionary surplus is transferred before savings. Unselected group shares go
to savings. Per-expense fallback weights reuse Food/Transportation/other weights
3/1.5/1 scaled to integer weights 6/3/2. Largest-remainder splitting uses integer
products and remainders, including at signed BIGINT limits.

## Persistence and safety

- All model keys are UUIDs; all monetary values are integer VND.
- Ownership is checked in services as well as authenticated routes. A category
  must be owned by the user or built-in. Every allocation must match an expense
  of the same authorized month, once and only once.
- Expense changes/regeneration atomically replace generated candidates. Invalid
  operations roll back, retaining previous candidates. Drafts with scheduled
  tasks cannot be replaced. Categories are retained when an expense is removed.
- Confirmation and setup changes lock the month's row on PostgreSQL. The
  existing partial unique index additionally enforces one confirmed plan per
  month on PostgreSQL/SQLite. Confirming the same plan again is harmless;
  selecting a different one returns a conflict. No replacement workflow exists.
- Confirmed allocations, savings and expense metadata are immutable through
  Budget services. Later funds edits do not rewrite the original plan. Its
  original funding total is derived from allocations plus planned savings,
  rather than displayed using the mutable month funds.
- Routes retain the existing sessions and Flask-WTF protection. No CSRF exemption
  or alternative authentication path is introduced. Unknown and explicit zero
  estimates display separately; neither is an expense check-in.

## Expense Planning handoff and remaining scope

KAN-21 does **not** create AssignedExpenseTask rows. Expense Planning must read
only CONFIRMED BudgetPlan allocations owned through BudgetMonth.user_id. Each
BudgetAllocation.allocated_amount is a monthly total, not a per-occurrence amount.
Use its UUID as allocation_id; obtain category, priority, frequency, recurring
flag and optional due day from BudgetExpense. Do not convert UUIDs into legacy
date-prefixed IDs or introduce duplicate task/expense models.

Scheduling must be idempotent per (allocation_id, assigned_date), respect
tracking_start_date, preserve the sum of task original_limit values, initialize
current_limit from original_limit and store PENDING rather than derived display
states. Weekly boundaries, partial-month distribution and bills before tracking
start still require an agreed Expense policy. Do not silently repeat a monthly
allocation on each daily/weekly task. Actual spending, FUNDS_ADDED, adjustments,
automatic reallocation, carry-forward, history-based suggestions and Dashboard
data binding are outside this ticket. Expense routes' demo identity and cleanup
behavior must be resolved separately before integrating that feature branch.

The new budget UI uses the existing page shell and language preference; its new
form labels and explanatory copy are currently English. Mandatory P0 detection
uses the prototype's English expense names (case-insensitive), not category names.
JSON APIs and manual allocation editing are not added; generated plans cover
the minimum functional flow. Live PostgreSQL concurrency testing remains a
deployment integration check; SQLite tests verify constraints and rollback.
