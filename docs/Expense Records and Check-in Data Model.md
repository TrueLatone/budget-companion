# Expense Planning & Smart Check-in — Design Specification

## I. Expense Model and Algorithms

### 1. Overall Workflow

The intended workflow is:

Confirmed monthly plan from BUDGET MODULE  → Expense source adapter → Local plan-item representation → Scheduled task occurrences → Day/Month/Year navigation → Check-in and actual records → Spending summaries and history.

### 2. Schedule Generation Algorithm

The scheduling function receives a recurrence tag, an inclusive start date, an inclusive end date, and any tag-specific fields. It returns only dates that both satisfy the recurrence rule and fall inside the requested range.

| schedule_tag | Occurrence rule | Required scheduling data |
| --- | --- | --- |
| DAILY | Every date from start through end, inclusive. | No additional field. |
| WEEKLY | Every matching ISO weekday in the range. ISO Monday = 1 and Sunday = 7. | day_of_week (1–7). |
| MONTHLY | The last calendar day of each month, only if that day is within the requested range. | No additional field. |
| DAY_OF_MONTH | The chosen day in each month; if the day does not exist, use that month's final day. Include it only if it falls within the range. | day_of_month (1–31). |
| DATE | Exactly the configured date, if it falls within the requested range. | specific_date. |

#### Idempotency and duplicate task prevention

For every plan-item/date pair, at most one task may exist. The service may check existing pairs before inserting, but a database unique constraint on (plan_item_id, assigned_date) is the final guard. Re-running task generation must preserve existing tasks, records, and check-in results.

#### Payment due date is independent

The assigned date and payment due date represent different concepts. A task's payment_due_date starts unset. A user may configure or clear the due date for that individual task. A monthly occurrence is scheduled for the last day of the month, but this does not automatically set its payment due date.

Under the selected design, moving a payment obligation from October into November means changing its payment_due_date. Its original assigned_date and original assigned-plan total remain unchanged. In November, it appears as a due-only task; its planned amount is not added again to November's assigned-plan total. This rule prevents the same planned allocation from being counted twice. If the group intends a full transfer of the task's assigned budget period instead, that is a different business rule and must be approved explicitly.

### 3. Hierarchical Navigation: Year → Month → Day

The top-level UI has exactly three modes: Day, Month, and Year.

#### 3.1 Day view

- Display a monthly calendar with the selected day highlighted.

- Show tasks assigned to the selected day and tasks due that day.

- Calculate the daily plan total using assigned tasks only. Show due-only tasks separately without adding them to the total again.

- Display each task’s title, priority, planned amount, actual amount, status, and payment due date.

- Open a modal when the user clicks Check-in.

#### 3.2 Month view

- Display a monthly calendar with drill-down to each day.

- List non-daily tasks (WEEKLY, MONTHLY, DAY_OF_MONTH, DATE) and tasks due in the selected month.

- Show tasks due this month but assigned in another month separately from the monthly plan total.

- Display DATE expenses in the month containing their specific_date, if it falls within the generated plan period.

#### 3.3 Year view and filters

- Display the yearly summary and 12 monthly cards, with links to drill down.

- Default to all five recurrence tags (DAILY, WEEKLY, MONTHLY, DAY_OF_MONTH, DATE) and allow multiple tags to be selected or deselected.

- Update task lists and related summaries according to the selected tags. Keep unexpected expenses under a separate filter.

- Clearly distinguish filtered totals from overall actual spending.

### 4. Check-in Workflow

Clicking Check-in opens a modal. The modal provides three user actions:

1.  Confirm as planned: records the task's exact planned_amount as actual spending.

2.  Enter actual amount: records an actual amount entered by the user.

3.  No expense: confirms that no spending occurred for the task.

For the actual-amount action, the amount input is prefilled with the task's planned amount for convenience but the user may change it. The UI also supports recording additional individual transactions for a task.

#### Multi-transaction rules

- Each individual purchase is a separate ExpenseRecord linked to the same task.

- Task actual amount = sum of all linked actual records for that task.

- Task status compares that sum with planned_amount: WITHIN_BUDGET when total actual amount is less than or equal to plan, and OVER_BUDGET when it is greater.

- NO_EXPENSE is valid only when no linked actual records exist.

- The Confirm as planned shortcut is available only while the task has no actual records. It creates one record equal to the planned amount.

- Repeated form submission must not create duplicate rows. Each create-record request uses an idempotency token; the same token returns the existing record, while a new token permits another legitimate transaction.

#### Task status values

| Status | Meaning | Amount treatment |
| --- | --- | --- |
| PENDING | No check-in result has been submitted and the deadline has not passed. | Unknown; never treated as zero actual spending. |
| UNRECORDED | The deadline has passed without a check-in result. | Unknown; never treated as zero actual spending. |
| NO_EXPENSE | The user explicitly confirmed no expense and no linked actual records remain. | No transaction is created. |
| WITHIN_BUDGET | The sum of linked actual records is not greater than the task's planned amount. | Actual spending is the sum of records. |
| OVER_BUDGET | The sum of linked actual records is greater than the task's planned amount. | Actual spending is the sum of records. |

The first two values describe the check-in state. WITHIN_BUDGET, NO_EXPENSE and OVER_BUDGET describe the result of comparing confirmed spending with the task plan. The module retains these five values for compatibility with the current design, while day/month/year summaries must keep task statuses separate from aggregate totals.

#### Overdue handling

The check-in deadline is 23:59:59 in Asia/Ho_Chi_Minh on the assigned date and is stored as a naive UTC timestamp in the current implementation. When the module page is accessed, overdue PENDING tasks become UNRECORDED. Additionally, a task must never become NO_EXPENSE merely because time has passed.

### 5. Actual Spending, Editing, and Deletion

#### Planned-task transactions

- A task may have multiple linked ExpenseRecord rows of type PLANNED.

- Creating a new individual transaction adds one row; it does not overwrite other transaction rows.

- Editing a record updates that row's amount, actual date, category, or note and then recalculates the linked task's aggregate amount and status.

- Deleting one record does not delete the task or other records.

- After a deletion, recalculate from remaining records. If none remain, the task returns to PENDING or UNRECORDED depending on its deadline, unless an explicit NO_EXPENSE action is then confirmed.

- Planned amount, priority, and the assigned date are not editable by the end user in this module.

#### Unexpected expenses

- An unexpected expense has record_type = UNEXPECTED, task_id = NULL, a title, positive amount, actual expense date, category, optional note, and budget_impact_scope.

- The user can edit and delete an unexpected transaction.

- Each transaction keeps its real expense_date, regardless of which budget limit it affects.

- The category is free text for the MVP. The module does not create a separate category-management subsystem.

### 6. Unexpected Expense Budget-Impact Scope

An unexpected expense has two independent date/period concepts:

- expense_date: when the money was actually spent; this drives historical placement in day, month, and year records.

- budget_impact_scope: which spending-limit comparison the unexpected expense should affect.

The only accepted values are English uppercase tags:

| budget_impact_scope | Meaning |
| --- | --- |
| DAILY | Include the unexpected amount in the daily budget-limit comparison for its actual date. |
| MONTHLY | Include the unexpected amount in monthly budget-limit comparison, but exclude it from the daily allocated-limit comparison. |

All unexpected records remain visible in real spending history and date-based actual cash-outflow reports, regardless of their impact scope. Therefore, the UI may need to distinguish:

1.  Total actual spending recorded on a date (all records by expense_date).

2.  The amount counted against that day's limit (excluding unexpected records tagged MONTHLY).

3.  The total counted against the month limit.

This is a scope selector for unexpected expenses only. It does not replace schedule_tag on an expense plan item and does not make an unexpected expense recurring.

### 7. Budget Reallocation Boundary

This module does not automatically reallocate future daily or weekly limits. When a task exceeds its planned amount, it reports OVER_BUDGET, updates actual totals, and exposes the difference. It does not move money between later days, rewrite the confirmed monthly plan, or consume another expense's allocation.

## II. Business Rules

#### BR-01. Module Ownership

Budget module manages income, expense priorities, budget allocation, and plan confirmation.

Expense Planning manages scheduled tasks, check-ins, actual transactions, and spending history.

This module must not modify the confirmed plan or reallocate budgets automatically.

#### BR-02. IDs and Demo Data

Module-owned IDs follow ddmmyyyy-uniqueid; external IDs from BUDGET MODULE  remain unchanged.

Demo data must be marked is_demo = true, kept separate from official data, and safely removable without affecting official records.

#### BR-03. Money and Dates

Monetary values use integer VND; planned and actual transaction amounts must be positive.

Calendar dates follow Vietnam time (Asia/Ho_Chi_Minh); timestamps use naive UTC.

assigned_date, expense_date (actual spending), and payment_due_date represent different concepts and must remain separate.

created_at and updated_at are audit timestamps, not expense dates.

#### BR-04. Scheduling

Supported tags: DAILY, WEEKLY, MONTHLY, DAY_OF_MONTH, and DATE.

MONTHLY occurs at month-end; DATE occurs only when its specific date falls within the generation period.

Each (plan_item_id, assigned_date) pair may have only one task. Regenerating tasks must preserve existing tasks, transactions, and check-in results.

#### BR-05. Payment Due Dates

Payment due dates are optional and configurable per task.

Changing a due date does not change the original assigned date or planned amount.

A task due in another month appears as a due-only obligation and is not counted again in that month's assigned-plan total.

#### BR-06. Check-in and Actual Transactions

Task states are PENDING, UNRECORDED, NO_EXPENSE, WITHIN_BUDGET, and OVER_BUDGET.

Unconfirmed spending is not treated as zero. Overdue unconfirmed tasks become UNRECORDED when the module is accessed.

A task may have multiple actual transactions; its total actual spending is their sum.

WITHIN_BUDGET or OVER_BUDGET is determined by comparing aggregate actual spending with the task's planned amount.

“Confirm as planned” creates one transaction equal to the planned amount only when no actual transaction exists.

NO_EXPENSE requires explicit confirmation and no linked actual transactions.

#### BR-07. Unexpected Expenses

Unexpected expenses have no assigned task and require a budget_impact_scope of DAILY (counted against the daily budget limit for the transaction date) or WEEKLY (counted against the weekly budget limit for the transaction date) or MONTHLY (counted against the monthly budget limit for the month of the transaction date).

The scope determines which budget limit is affected; the actual expense date determines historical reporting.

Unexpected expenses must remain included in actual spending history and have a separate filter.

#### BR-08. Editing and Duplicate Prevention

Users may edit or delete actual transactions. Changes must recalculate task totals and statuses.

Deleting the final transaction resets the task to PENDING or UNRECORDED, depending on its deadline.

Repeated requests must not create duplicate transactions. Different idempotency keys must permit legitimate transactions with identical amounts and dates.

End users cannot modify planned amounts, priorities, or assigned dates in this module.

#### BR-09. Navigation and Summaries

The interface provides Day, Month, and Year views.

Day and month summaries distinguish assigned tasks from due-only tasks and avoid double-counting planned amounts.

Year view groups results by month and supports multi-select filters for all five recurrence tags, selected by default. Unexpected expenses have a separate filter.

Filtered totals must be clearly labelled; actual spending is grouped by expense_date, while assigned-plan totals are grouped by assigned_date.

#### BR-10. Security and Integration

All reads and writes must be scoped to the resolved user. Demo and official data must remain isolated.

When importing confirmed expense plans from another module, preserve the original IDs assigned by the source module.

Authentication, authorization, and CSRF protection must be implemented before shared deployment.

Automatic budget reallocation remains outside this module's scope and requires explicit ownership elsewhere in the system.

## III. Initial Database Model

### 1. Entity Relationships

- expense_plan_items 1 → many assigned_expense_tasks.

- assigned_expense_tasks 1 → many expense_records with record_type = PLANNED.

- expense_records with record_type = UNEXPECTED has task_id = NULL.

### 2. Table: expense_plan_items

| Field | Suggested type | Constraint / purpose |
| --- | --- | --- |
| plan_item_id | String(21) | Primary key generated by module ID rule. |
| source_expense_id | String(128), nullable | References the source Expense.Expense ID provided by Budget Planning. Required for budget-sourced items; nullable for manually created items without a source Expense. Preserve the source ID exactly. |
| user_id | String(64) | Identifies the record owner using the user ID provided by the Accounts module. Must use the same ID format and data type as the Accounts module; indexed for user-scoped queries. |
| title | String(200) | Expense.Name |
| amount_source | String(20) | BUDGET_DEFAULT or USER_ENTERED. |
| planned_amount | BigInteger | Copied from Budget Allocation.Allocated Amount for the source Expense under the selected and confirmed Budget Plan. Read-only when amount_source = BUDGET_DEFAULT. The allocation amount must be defined as per-occurrence or period-level; period-level amounts must not be treated as per-occurrence amounts without an agreed allocation rule. |
| priority | String(2) | P0, P1, or P2; from Expense.Priority |
| schedule_tag | String(20) | Recurrence type from the agreed source data contract. Supported values: DAILY, WEEKLY, MONTHLY, DAY_OF_MONTH, DATE. The recurrence type and its date details must be consistent with the source schedule. |
| day_of_week | SmallInteger, nullable | ISO 1–7 only for WEEKLY. |
| day_of_month | SmallInteger, nullable | 1–31 only for DAY_OF_MONTH. |
| specific_date | Date, nullable | Required only for DATE. |
| is_active | Boolean | Whether the source item should generate future tasks. |
| is_demo | Boolean | Separates developer/test data from official data. |
| created_at, updated_at | DateTime | Naive UTC audit timestamps. |

Recommended constraints:

- planned_amount > 0.

- Check constraints for the accepted priority and schedule_tag values.

- Check constraints for day_of_week and day_of_month ranges.

- A schedule-field constraint enforcing that only fields relevant to the selected tag are populated.

- Partial unique index on (user_id, source_expense_id) where source_expense_id IS NOT NULL, if this matches the BUDGET MODULE  source identity contract.

### 3. Table: assigned_expense_tasks

| Field | Suggested type | Constraint / purpose |
| --- | --- | --- |
| task_id | String(21) | Primary key. |
| plan_item_id | String(21) | Foreign key to expense_plan_items.plan_item_id. |
| user_id | String(64) | Validate consistency with parent item. |
| assigned_date | Date | Date assigned by schedule generation. |
| planned_amount | BigInteger | Positive immutable snapshot used for comparison. |
| priority | String(2) | Snapshot of source priority. |
| checkin_deadline_at | DateTime | Vietnam end-of-day converted to naive UTC. |
| payment_due_date | Date, nullable | Separately configured due date; initially unset. |
| task_status | String(20) | One of PENDING, UNRECORDED, NO_EXPENSE, WITHIN_BUDGET, OVER_BUDGET. |
| checked_at | DateTime, nullable | Time of latest explicit check-in. |
| is_demo | Boolean | Must match the source/demo path. |
| created_at, updated_at | DateTime | Naive UTC audit timestamps. |

Recommended constraints and indexes:

- Unique constraint on (plan_item_id, assigned_date).

- Positive planned_amount check.

- Check constraint for permitted task status values.

- Index on (user_id, assigned_date) and on payment_due_date where appropriate.

- Service-level ownership checks ensuring user_id and demo flag agree with the referenced plan item.

### 4. Table: expense_records

| Field | Suggested type | Constraint / purpose |
| --- | --- | --- |
| record_id | String(21) | Primary key. |
| user_id | String(64) | Owner scope. |
| task_id | String(21), nullable | FK to task; required for PLANNED, null for UNEXPECTED. |
| record_type | String(20) | PLANNED or UNEXPECTED. Here PLANNED means an actual transaction attached to a planned task. |
| amount | BigInteger | Positive actual amount in VND. |
| expense_date | Date | Actual date the expense occurred. |
| actual_amount_source | String(20) | Current implementation values are PLANNED (confirm planned amount) or USER_ENTERED; standardize consistently. |
| title | String(200), nullable | Required for unexpected expenses; for task-linked records may be displayed from the plan item. |
| category | String(80), nullable | Free-text category for MVP. |
| note | Text, nullable | Optional user note. |
| budget_impact_scope | String(20), nullable | Required for UNEXPECTED: DAILY or MONTHLY; null for task-linked records. |
| idempotency_key | String(64), nullable | Request token to prevent duplicate create submissions. Apply to record-creation flows that can be retried. |
| is_demo | Boolean | Demo/official data isolation. |
| created_at, updated_at | DateTime | Naive UTC audit timestamps. |

Recommended constraints and indexes:

- Check amount > 0.

- Check record_type is PLANNED or UNEXPECTED.

- Check task_id IS NOT NULL for PLANNED and task_id IS NULL for UNEXPECTED.

- For UNEXPECTED, require a non-empty title and budget_impact_scope IN ('DAILY', ‘WEEKLY’, 'MONTHLY').

- For task-linked records, budget_impact_scope should be null; recurrence/assigned-period semantics come from the linked task and plan item.

- Unique partial index on (user_id, idempotency_key) where the key is not null.

- Index on (user_id, expense_date).
