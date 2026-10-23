# Adaptive AI Budget Assistant (Rule-Based) — F18 and F19

**Project:** Budget Companion  
**Module scope:** F18 Data Completeness Check and F19 Monthly Budget Review only  
**Implementation status:** Initial deterministic prototype using CSV and Python  
**Currency:** VND  
**Budget period:** Calendar month (`YYYY-MM`)  
**Input dataset:** `f18_input_with_planned_amount.csv`

This README documents the two features implemented in the current prototype. F18 checks whether expense records contain enough usable information for analysis and identifies records or tasks that require attention. F19 reviews one selected calendar month by summarizing task statuses, recorded spending, planned amounts available from task-level data, category-level results, and optional user feedback.

The current prototype uses deterministic rules, not a trained machine-learning model. It reads and analyzes data but does not modify the confirmed budget plan, change source transactions, make payments, or automatically reallocate spending limits.

---

# I. Model and Algorithm

## 1. Purpose and Feature Scope

| Feature | Name | Priority | Responsibility in the current prototype |
|---|---|---|---|
| F18 | Data Completeness Check | MUST | Detect incomplete recorded transactions and unrecorded tasks, calculate a completeness summary, and select personalized or general baseline guidance using configurable prototype thresholds. |
| F19 | Monthly Budget Review | MUST (basic) | Summarize a selected month, compare task-level planned amounts with observed actual transactions where the data supports comparison, show category and task-status results, and collect an optional satisfaction rating and comment. |

Features F14–F17 and F20 are outside the implementation scope documented here. F18's readiness result may inform later recommendation features, but this prototype only produces the F18 and F19 outputs described below.

## 2. Overall Workflow

```text
f18_input_with_planned_amount.csv
             |
             v
       Load and validate CSV
             |
             v
      Normalize numbers, dates,
      and category names
             |
       +-----+----------------+
       |                      |
       v                      v
F18: Data Completeness    F19: Monthly Budget Review
Check                    for selected YYYY-MM month
       |                      |
       v                      v
f18_completeness_        f19_monthly_review_summary.csv
summary.csv              f19_category_review.csv
f18_data_issues.csv      f19_task_status_counts.csv
                          f19_unexpected_transactions.csv
```

The script is run for one dataset and one selected month, for example:

```bash
python f18_f19_demo.py --month 2026-09
```

The script writes its output files into the same directory as the input CSV. F18 analyzes the historical records available in the dataset. F19 filters assigned tasks by `assigned_date` and actual transactions by `expense_date`, which are different dates and must not be treated as interchangeable.

## 3. Input Data and Field Selection

The current input is a compact, denormalized CSV that combines assigned tasks and transaction records. It contains the following fields:

| Field | Meaning | Used by |
|---|---|---|
| `user_id` | Owner of the task or transaction. | F18, F19 |
| `row_kind` | Indicates a task-linked transaction, task with no record, or unexpected transaction. | F18, F19 |
| `task_id` | Identifier of a scheduled expense task; blank for unexpected transactions. | F18, F19 |
| `assigned_date` | Date on which the task is assigned/scheduled. | F18 output, F19 task-month selection |
| `planned_amount` | Planned amount for one task occurrence. It is not necessarily the full monthly category allocation. | F19 |
| `task_status` | `PENDING`, `UNRECORDED`, `NO_EXPENSE`, `WITHIN_BUDGET`, or `OVER_BUDGET`. | F18, F19 |
| `record_id` | Identifier of an actual transaction record. | F18, F19 |
| `record_type` | `PLANNED` for a transaction linked to a planned task; `UNEXPECTED` for a transaction without a task. | F18, F19 |
| `title` | Human-readable task or transaction name. | F18 issue report, F19 review |
| `category` | Expense category used to group spending. | F18, F19 |
| `amount` | Actual recorded transaction amount in VND. | F18, F19 |
| `expense_date` | Date on which an actual expense occurred. | F18, F19 actual-spending calculations |

`planned_amount` was added by matching the detailed source dataset on `task_id`. Tasks may have multiple linked transaction rows; F19 counts a task's `planned_amount` once per task and sums all valid linked actual records. Unexpected transactions have no `task_id` and therefore have no task-level `planned_amount` in this input.

### Current input limitation

The compact dataset does not include a confirmed monthly `Budget Allocation`, available funds, the selected `Budget Plan` ID/status, priority (`P0`/`P1`/`P2`), user-defined P1 minimums, or a separate `is_demo` column. Therefore, the current F19 planned total is the sum of task-level planned amounts for unique tasks assigned in the selected month. It is **not a substitute for the authoritative full-month allocation** held by the Budget module. The current prototype cannot independently validate P0/P1 budget constraints or prove that a budget plan is confirmed.

## 4. Feature Algorithms

### 4.1 F18 — Data Completeness Check

**Goal:** Identify missing essential expense information and avoid treating incomplete evidence as a fully reliable basis for personalized guidance.

**Processing steps:**

1. Load the dataset and parse `amount`, `planned_amount`, `assigned_date`, and `expense_date` into usable numeric/date values.
2. Select rows whose task status is `WITHIN_BUDGET`, `OVER_BUDGET`, `UNRECORDED`, or `NO_EXPENSE`, and include all `UNEXPECTED_TRANSACTION` rows in the quality check. Future/pending tasks are not treated as historical missing check-ins in this prototype.
3. For transaction records, check whether `record_id` exists, `amount` is a positive number, `category` is present, and `expense_date` is valid.
4. Mark `UNRECORDED` task rows as requiring attention. This does not prove that the user definitely spent money; it means the task has not been explicitly resolved in the available records.
5. Create `f18_data_issues.csv` with each unrecorded task or incomplete transaction and its `missing_fields` list.
6. Create one summary row per user and calculate the completeness measures below.

**Completeness calculations:**

- `complete_records`: transaction rows that have a record ID, positive actual amount, category, and valid expense date.
- `incomplete_records`: unrecorded tasks plus transaction rows missing one or more required fields.
- `completeness_rate_pct`:

  `complete_records / (complete_records + incomplete_records) * 100`

- `distinct_categories`: number of distinct normalized categories among complete transaction records.
- `coverage_days`: inclusive calendar-day span between the earliest and latest complete transaction dates.

**Prototype sufficiency gate:** The data is marked sufficient only when all the following conditions are met:

- At least 10 complete transaction records.
- At least 3 distinct categories.
- At least 30 calendar days of coverage.
- Completeness rate of at least 80%.

If all conditions pass, `guidance_type` becomes `PERSONALIZED_GUIDANCE`; otherwise it becomes `GENERAL_BASELINE_GUIDANCE`.

These four numeric thresholds are prototype settings introduced to make the demonstration testable, not thresholds dictated by the Budget Model. They should be reviewed and made configurable before production use. The current F18 result assesses the supplied record set; it does not verify all Budget-module prerequisites or a two-month confirmed-history rule.

**F18 outputs:**

- `f18_completeness_summary.csv`: one row per user with counts, coverage, completeness rate, sufficiency result, and guidance type.
- `f18_data_issues.csv`: individual records/tasks requiring attention, including the missing fields and completeness flags.

### 4.2 F19 — Monthly Budget Review

**Goal:** Produce an understandable review of a selected month without pretending unknown spending is zero.

**Processing steps:**

1. Select task rows with a non-empty `task_id` and `assigned_date` in the requested month (`YYYY-MM`). Deduplicate by `user_id` and `task_id` so a task with multiple transaction rows is counted once for task counts and planned amounts.
2. Count unique tasks by `task_status`, including `WITHIN_BUDGET`, `OVER_BUDGET`, `NO_EXPENSE`, `UNRECORDED`, and `PENDING` when present.
3. Select valid task-linked actual transactions whose status is `WITHIN_BUDGET` or `OVER_BUDGET`, with a non-empty `record_id`, positive `amount`, and `expense_date` in the selected month.
4. Select valid `UNEXPECTED_TRANSACTION` records by `expense_date` for the same month. These count as actual spending even though they do not have a linked task or planned amount.
5. Combine actual records and deduplicate by `user_id` and `record_id`. Sum recorded actuals and unexpected spending separately.
6. Aggregate task-level planned amounts and observed actual transactions by normalized category. Category names are normalized to improve matching, for example `Books Supplies` to `books_supplies`.
7. Assign category statuses. If a category contains an `UNRECORDED`, `PENDING`, unknown, or blank task status, it is marked `INCOMPLETE_DATA`. If data is available and comparable, the status may be `OVER_BUDGET`, `UNDER_BUDGET`, or `ON_BUDGET`. Categories with unexpected spending and no matching task are reported separately.
8. Mark the month review incomplete when a task does not have a confirmed status or a recorded transaction lacks a category. When the required data is incomplete, `remaining_vs_plan` is left blank rather than presented as a reliable balance.
9. Optionally record a satisfaction rating from 1 to 5 and a comment of up to 2,000 characters.

**Variance convention:**

`variance_actual_minus_planned = observed actual amount - task-level planned amount`

A positive value means the observed actual amount is above the planned amount; a negative value means it is below the planned amount. Because the current input uses task-level plans and not the Budget module's confirmed monthly allocations, this comparison is task-derived and should not be represented as a definitive full-month Budget-module comparison.

**F19 outputs:**

- `f19_monthly_review_summary.csv`: one row per user and selected month, with plan/actual totals, task status counts, unexpected spending, data completeness, feedback, and review status.
- `f19_category_review.csv`: one row per user/category with planned amount, observed actual, variance where reliable, task counts, and category status.
- `f19_task_status_counts.csv`: count of unique tasks by status for the month.
- `f19_unexpected_transactions.csv`: unexpected transaction rows dated in the selected month.

## 5. Demonstration Result and Interpretation

With the supplied demo dataset and `--month 2026-09`, the current saved outputs show:

| Result | Demonstration value |
|---|---:|
| F18 complete records | 85 |
| F18 incomplete records | 7 |
| F18 completeness rate | 92.39% |
| F18 guidance type | `PERSONALIZED_GUIDANCE` |
| F19 task-derived planned total | 8,310,000 VND |
| F19 recorded spending observed | 7,034,770 VND |
| F19 unexpected spending observed | 180,000 VND |
| F19 unrecorded tasks in September | 2 |
| F19 missing-category transactions | 1 |
| F19 review status | `PARTIAL_REVIEW_DATA_INCOMPLETE` |

The F18 and F19 outcomes are not contradictory: F18 checks the overall record set across the available period, while F19 checks whether the selected month's review is complete. The user can pass an overall demo completeness threshold while a particular month still contains unresolved tasks or a missing category.

The numbers above are synthetic/test-data outputs and illustrate the calculations. They are not claims about a real user's financial situation.

## 6. Running the Prototype

Requirements: Python 3.10+ and the `pandas` and `numpy` packages.

```bash
pip install pandas numpy
python f18_f19_demo.py --month 2026-09
```

To skip the interactive feedback prompt:

```bash
python f18_f19_demo.py --month 2026-09 --skip-feedback-prompt
```

To provide a rating and comment through command-line arguments:

```bash
python f18_f19_demo.py --month 2026-09 --rating 4 --comment "The monthly review was helpful."
```

The input file can be selected explicitly:

```bash
python f18_f19_demo.py --input f18_input_with_planned_amount.csv --month 2026-09
```

The script writes the six F18/F19 CSV outputs beside the input file. If a file with the same output name already exists, it is replaced by the latest run.

---

# II. Business Rules

### BR-01. Module Ownership and Scope

- The Budget module is the authoritative source for available funds, expense definitions, priorities, confirmed monthly plans, and monthly allocations.
- The Expense module is the authoritative source for scheduled tasks, check-in status, and actual transaction records.
- F18 and F19 read and report information; they must not modify source records or silently edit the confirmed budget plan.
- The compact demo CSV is a normalized combined input for testing. It does not replace the source modules' database schema.

### BR-02. User and Period Scoping

- Every task, transaction, completeness finding, and monthly review must be scoped to `user_id`.
- The reporting period is a calendar month represented as `YYYY-MM`.
- F19 selects task rows using `assigned_date` and actual transactions using `expense_date`.
- A payment due date is not an actual spending date and must not be used as a substitute for `expense_date`.

### BR-03. Required Transaction Fields

- A transaction is complete for this prototype only when it has a non-empty `record_id`, a positive numeric `amount`, a non-empty `category`, and a valid `expense_date`.
- F18 reports missing values; it does not invent an amount, date, record ID, or category.
- Category normalization may standardize a known spelling/format, but it must not silently infer a missing category from an untrusted title.

### BR-04. Task Status Semantics

- `PENDING` means the task has not yet been checked in; its spending is unknown.
- `UNRECORDED` means the task has not been resolved with a transaction or explicit no-expense confirmation. It is not proof that spending occurred.
- `NO_EXPENSE` means the user explicitly confirmed that no expense occurred for that task.
- `WITHIN_BUDGET` and `OVER_BUDGET` are task-level check-in outcomes and must be preserved as provided by the Expense module.
- `PENDING` and `UNRECORDED` must never be automatically changed into `NO_EXPENSE` merely because no transaction row exists.

### BR-05. F18 Completeness Gate

- F18 reports incomplete transaction records and unrecorded tasks separately through its issue rows and summary metrics.
- `complete_records` counts transaction rows with all required fields and a positive amount.
- `incomplete_records` includes unrecorded tasks and transaction rows that fail the required-field checks.
- The completeness rate is calculated as `complete_records / (complete_records + incomplete_records) * 100`; explicitly confirmed `NO_EXPENSE` tasks are not counted as incomplete transactions.
- The prototype sufficiency thresholds are at least 10 complete records, at least 3 categories, at least 30 coverage days, and at least 80% completeness. These are configurable demo thresholds, not immutable financial rules.
- A `PERSONALIZED_GUIDANCE` result indicates only that these prototype checks passed. It does not prove that the Budget module's confirmed plan, P0 items, P1 minimums, or all monthly allocations have been validated.

### BR-06. F19 Actual-Spending Calculation

- F19 counts a task once by `user_id` and `task_id`, even if multiple transaction records link to that task.
- Planned task amounts are counted once per unique task. Actual spending is the sum of valid transaction records, not the sum of task amounts.
- Only positive, identified transaction records dated in the selected month are included in the actual-spending total.
- Unexpected transaction records are included in actual spending even when they do not map to a planned category.
- Duplicate transaction IDs within the same user are counted once in the monthly actual total.

### BR-07. F19 Unknown Spending and Category Status

- No transaction row is not equivalent to zero spending.
- `NO_EXPENSE` can be treated as zero for that task only when there is no conflicting linked transaction.
- Categories containing `PENDING`, `UNRECORDED`, blank, or unknown task statuses are marked `INCOMPLETE_DATA` rather than automatically `UNDER_BUDGET`.
- Missing-category unexpected transactions are retained in a separate `uncategorized_unexpected` group and flagged for review.
- If monthly task data is incomplete, F19 leaves `remaining_vs_plan` blank rather than presenting it as a confirmed remaining balance.
- In this prototype, category variance uses task-level planned amounts. For production, the authoritative full-month comparison should use confirmed Budget-module allocations.

### BR-08. Feedback and Monthly Review

- F19 accepts an optional integer satisfaction rating from 1 to 5 and an optional comment up to 2,000 characters.
- Feedback describes the user's review of the month; it does not change a confirmed budget plan or override transaction records.
- If task/status/category data is incomplete, the review remains partial even if the monetary totals can be calculated.
- A review should clearly distinguish observed spending from unknown or unrecorded activity.

### BR-09. Demo Data and Monetary Values

- Amounts in the supplied prototype dataset are VND and must be processed as numeric values, not formatted currency strings.
- Synthetic test data must remain clearly identified as demo data in the integration environment and must not be mixed with official financial records.
- Missing values remain missing unless the source module supplies a verified value or the user explicitly confirms the relevant fact.

---

# III. Initial Database Model

The database model below separates the logical entities represented by the compact CSV. It is an initial design for F18/F19 integration, not a claim that all these tables already exist in the application database. If the Budget and Expense modules already own equivalent tables, the Assistant should read those tables or their normalized exports instead of duplicating them as new sources of truth.

## 1. Entity Relationships

```text
User 1 -------------------- N AssignedExpenseTask
User 1 -------------------- N ExpenseRecord
AssignedExpenseTask 1 ----- N ExpenseRecord (record_type = PLANNED)
User 1 -------------------- N DataCompletenessSummary
DataCompletenessSummary 1 - N DataQualityIssue
User 1 -------------------- N MonthlyBudgetReview
MonthlyBudgetReview 1 ----- N MonthlyCategoryReview
MonthlyBudgetReview 1 ----- N MonthlyTaskStatusCount
MonthlyBudgetReview 1 ----- N UnexpectedTransactionReview
```

`ExpenseRecord.task_id` is nullable for `UNEXPECTED` records. A task can have multiple actual transaction rows, so planned task counts and actual transaction totals must be calculated separately.

## 2. Source Tables / Adapter Entities

### 2.1 `users` — Accounts reference

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `user_id` | String(64) | Primary key or source user ID. Used to scope all data and queries. |

### 2.2 `assigned_expense_tasks` — Expense module adapter

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `task_id` | String(21) | Primary key for a scheduled expense occurrence. |
| `user_id` | String(64) | Owner; references `users.user_id`. |
| `assigned_date` | Date | Date on which the task is assigned/scheduled. |
| `task_status` | String(20) | One of `PENDING`, `UNRECORDED`, `NO_EXPENSE`, `WITHIN_BUDGET`, or `OVER_BUDGET`. |
| `title` | String(200) | Human-readable expense/task label. |
| `category` | String(80), nullable | Category from the linked expense plan item; may be missing and require review. |
| `planned_amount` | BigInteger | Planned amount for this task occurrence in integer VND; positive when a planned task is created. |
| `row_kind` | String(30) | Adapter field indicating transaction task versus task without a record; can be derived from normalized source tables. |
| `is_demo` | Boolean | Recommended integration field to separate synthetic rows from official data; not present in the compact 12-column demo file. |

Recommended constraints: unique `task_id`; non-negative/positive `planned_amount` according to task creation rules; valid task status; and ownership validation against the linked plan item.

### 2.3 `expense_records` — Expense module adapter

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `record_id` | String(21) | Primary key for an actual transaction. |
| `user_id` | String(64) | Record owner. |
| `task_id` | String(21), nullable | Required for a planned-task transaction; null for an unexpected transaction. |
| `record_type` | String(20) | `PLANNED` or `UNEXPECTED`. `PLANNED` denotes an actual transaction linked to a task. |
| `title` | String(200), nullable | Transaction title; required for an unexpected transaction. |
| `category` | String(80), nullable | Actual transaction category; missing values are surfaced by F18 rather than guessed. |
| `amount` | BigInteger | Positive actual transaction amount in integer VND. |
| `expense_date` | Date | Actual date of spending. Used to group spending into a calendar month. |
| `is_demo` | Boolean | Recommended integration field for demo isolation; not present in the compact 12-column demo file. |

Recommended constraints: unique `record_id`; `amount > 0`; valid `record_type`; actual date required for valid transaction records; and `task_id` required for `PLANNED` records but null for `UNEXPECTED` records.

## 3. Assistant-Owned Tables

### 3.1 `data_completeness_summary` — F18 output

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `check_id` | String(36) | Primary key for one completeness run. |
| `user_id` | String(64) | User being checked. |
| `total_transaction_records` | Integer | Number of transaction rows included in the F18 review. |
| `complete_records` | Integer | Count of transactions with required fields. |
| `unrecorded_tasks` | Integer | Count of tasks marked `UNRECORDED`. |
| `confirmed_no_expense_tasks` | Integer | Count of tasks explicitly marked `NO_EXPENSE`. |
| `incomplete_records` | Integer | Count of unrecorded tasks plus incomplete transaction rows. |
| `completeness_rate_pct` | Decimal(5,2) | Completeness rate calculated by the prototype. |
| `distinct_categories` | Integer | Number of normalized categories among complete transactions. |
| `coverage_days` | Integer | Inclusive date span from earliest to latest complete transaction. |
| `data_sufficient` | Boolean | Whether all F18 prototype thresholds passed. |
| `guidance_type` | String(40) | `PERSONALIZED_GUIDANCE` or `GENERAL_BASELINE_GUIDANCE`. |
| `created_at` | DateTime | Time at which the check was executed. |

### 3.2 `data_quality_issues` — F18 findings

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `issue_id` | String(36) | Primary key for the finding. |
| `user_id` | String(64) | User affected by the issue. |
| `task_id` | String(21), nullable | Related task, if present. |
| `record_id` | String(21), nullable | Related transaction, if present. |
| `row_kind` | String(30) | Source row classification. |
| `task_status` | String(20), nullable | Status associated with the issue. |
| `missing_fields` | Text | Comma-separated or normalized list of required fields that are absent/invalid. |
| `is_unrecorded` | Boolean | Whether the row is an unrecorded task. |
| `is_transaction` | Boolean | Whether the row represents a transaction. |
| `is_complete` | Boolean | Whether the transaction passes all required-field checks. |
| `is_incomplete` | Boolean | Whether the row requires attention. |
| `created_at` | DateTime | Time the finding was generated. |

### 3.3 `monthly_budget_reviews` — F19 monthly summary

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `review_id` | String(36) | Primary key for the review run. |
| `user_id` | String(64) | Review owner. |
| `month` | String(7) | Calendar month in `YYYY-MM` format. |
| `total_planned` | BigInteger, nullable | Sum of task-level planned amounts for unique tasks assigned in the selected month in this prototype; not the authoritative Budget-module monthly allocation. |
| `total_confirmed_spending_observed` | BigInteger | Sum of valid recorded transactions with `expense_date` in the selected month. |
| `remaining_vs_plan` | BigInteger, nullable | Task-derived planned total minus observed actual spending; null when review data is incomplete. |
| `categories_over_budget` | Integer | Number of categories marked over budget by the prototype. |
| `categories_unplanned` | Integer | Count of categories represented in unexpected transactions. |
| `unrecorded_tasks` | Integer | Count of unique selected-month tasks marked `UNRECORDED`. |
| `pending_tasks` | Integer | Count of unique selected-month tasks marked `PENDING`. |
| `confirmed_no_expense_tasks` | Integer | Count of unique tasks marked `NO_EXPENSE`. |
| `within_budget_tasks` | Integer | Count of unique tasks marked `WITHIN_BUDGET`. |
| `over_budget_tasks` | Integer | Count of unique tasks marked `OVER_BUDGET`. |
| `unexpected_spending_total` | BigInteger | Sum of valid unexpected transactions in the selected month. |
| `missing_category_transactions` | Integer | Count of actual transactions without a category. |
| `planned_amount_available` | Boolean | Whether every selected task has `planned_amount`. |
| `monthly_task_data_complete` | Boolean | Whether selected task statuses and transaction categories pass the prototype completeness check. |
| `satisfaction_rating` | SmallInteger, nullable | Optional integer rating from 1 through 5. |
| `review_comment` | Text, nullable | Optional user comment, limited to 2,000 characters in the prototype. |
| `review_status` | String(50) | `REVIEW_READY` or a partial-review status. |
| `created_at` | DateTime | Time the review was generated or saved. |

### 3.4 `monthly_category_reviews` — F19 category detail

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `category_review_id` | String(36) | Primary key. |
| `review_id` | String(36) | References `monthly_budget_reviews.review_id`. |
| `user_id` | String(64) | User owner for convenient scoping. |
| `month` | String(7) | Reviewed calendar month. |
| `category` | String(80) | Normalized category label; a placeholder category may represent missing classification. |
| `planned_amount` | BigInteger, nullable | Sum of task-level planned amounts for unique tasks in the category. |
| `confirmed_actual_amount_observed` | BigInteger, nullable | Actual transaction amount observed in the category; null when unknown, not automatically zero. |
| `variance_actual_minus_planned` | BigInteger, nullable | Actual minus planned where comparison is sufficiently reliable. |
| `task_count` | Integer | Number of unique tasks in the category. |
| `incomplete_task_count` | Integer | Number of tasks in an unresolved status. |
| `status` | String(40) | For example `OVER_BUDGET`, `UNDER_BUDGET`, `ON_BUDGET`, `INCOMPLETE_DATA`, or `UNPLANNED_OR_UNEXPECTED_SPENDING`. |

### 3.5 `monthly_task_status_counts` — F19 task-status detail

| Field | Suggested type | Constraint / purpose |
|---|---|---|
| `status_count_id` | String(36) | Primary key. |
| `review_id` | String(36) | References the monthly review. |
| `user_id` | String(64) | Review owner. |
| `month` | String(7) | Reviewed month. |
| `task_status` | String(20) | Status label. |
| `task_count` | Integer | Number of unique tasks with that status. |

The `f19_unexpected_transactions.csv` output is a filtered view of source expense records, so a separate assistant-owned table is optional. If persisted separately, preserve `record_id` and link it to the source transaction rather than creating a second authoritative transaction record.

## 4. Database and Integration Constraints

- Budget and Expense modules remain the systems of record for their respective source information. The Assistant's tables store derived checks/reviews and should not duplicate source transactions as authoritative data.
- Preserve `user_id`, source identifiers, task-to-record links, and demo/official data separation.
- Enforce unique IDs for tasks and transaction records; validate ownership for all linked records.
- Monetary values use integer VND. Reject non-positive amounts for valid actual transaction rows unless a separately defined source rule permits them.
- Keep `PENDING` and `UNRECORDED` distinct from confirmed `NO_EXPENSE`.
- Count the planned amount once per unique task, while summing each valid actual transaction once. Never add a task-level aggregate to the transaction-level actual total.
- Use `expense_date` for actual spending periods and `assigned_date` for task-period reporting.
- A partial or incomplete review must preserve unknown values as null/blank instead of reporting a misleading zero balance.
- The current prototype's `planned_amount` is task-level. Production F19 should use the confirmed monthly `Budget Allocation` for authoritative monthly Plan-vs-Actual analysis.
- Store a satisfaction rating only when it is an integer from 1 to 5. The comment is optional and must be length-limited.
- The Assistant must not overwrite a confirmed budget plan or apply plan/schedule changes. The source-owning module may apply a change only after the user reviews and confirms it.

---

## Implementation Status Summary

| Area | Status |
|---|---|
| F18 — Data Completeness Check | Implemented as a CSV/Python prototype with required transaction-field checks, unrecorded-task findings, completeness metrics, and a configurable-by-code readiness threshold. It does not yet validate the full Budget-module P0/P1/confirmed-plan contract. |
| F19 — Monthly Budget Review | Implemented as a CSV/Python prototype with monthly task counts, recorded actual totals, task-level planned totals, category review, unexpected transaction output, and optional satisfaction feedback. |
| Confirmed monthly plan integration | Not present in the compact demo CSV. Integrate confirmed Budget-module allocation rows before treating F19 `total_planned` as the authoritative monthly budget. |
| Automatic budget or spending-limit changes | Not implemented in F18/F19. These features report and review data only. |

