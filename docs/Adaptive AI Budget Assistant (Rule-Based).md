# Adaptive AI Budget Assistant (Rule-Based) — F18 and F19

> The CSV prototype remains independent of the shared database. KAN-19's
> [entity dictionary](entity-dictionary.md) is the canonical persistence contract;
> summary/cache tables proposed here are not part of its 13 entities. Runtime
> integration must derive display task states and exclude FUNDS_ADDED from
> spending. No prototype CSV is imported automatically.

**Project:** Budget Companion  
**Scope:** F18 Data Completeness Check and F19 Monthly Budget Review  
**Implementation:** Python and CSV, deterministic rule-based prototype  
**Currency:** VND  
**Input:** `f18_f19_.csv`

This document describes the algorithms, business rules, and initial database design for F18 and F19. The prototype analyzes expense data and produces review reports. It does not modify transactions, change confirmed budget plans, or automatically reallocate spending.
**Prototype Status:** This is an initial demo version intended for testing and validation. Some features, algorithms, business rules, and database designs may change as development progresses. The remaining features will be implemented and documented in future updates.
# I. Model and Algorithm

## 1. Feature Overview

| Feature | Name | Responsibility | Priority |
|---|---|---|---|
| F18 | Data Completeness Check | Detect incomplete transactions and unresolved tasks, calculate data completeness, and determine whether the dataset meets the prototype's requirements for personalized guidance. | MUST |
| F19 | Monthly Budget Review | Summarize monthly task statuses, planned amounts, observed spending, category results, unexpected transactions, and optional user feedback. | MUST (basic) |

F14–F17 and F20 are outside the current implementation scope.

## 2. Input Data and Workflow

The input CSV combines assigned expense tasks and transaction records.

| Field | Purpose | Feature |
|---|---|---|
| `user_id` | Identifies the data owner. | F18, F19 |
| `row_kind` | Identifies task and transaction row types. | F18, F19 |
| `task_id` | Identifies a scheduled expense task. | F18, F19 |
| `assigned_date` | Determines the task's reporting month. | F19 |
| `planned_amount` | Planned amount per task occurrence. | F19 |
| `task_status` | Indicates task check-in status. | F18, F19 |
| `record_id`, `record_type` | Identify actual and unexpected transactions. | F18, F19 |
| `title`, `category` | Describe and classify expenses. | F18, F19 |
| `amount` | Actual recorded transaction amount. | F18, F19 |
| `expense_date` | Determines the actual spending month. | F18, F19 |

The prototype follows this workflow:

1. Load and validate the CSV.
2. Normalize numeric values, dates, categories, and task statuses.
3. Execute F18 data-quality checks and F19 monthly review calculations.
4. Export summary, issue, category, and task-status reports.

Run the prototype for a selected month:

```bash
pip install pandas numpy
python f18_f19_demo.py --month 2026-09
```

`assigned_date` determines which tasks belong to the selected month, while `expense_date` determines when actual spending is counted.

### Input Limitation

The CSV contains task-level planned amounts but does not provide the authoritative confirmed monthly Budget Allocation. Therefore, F19 cannot independently validate the full monthly budget or enforce P0/P1 constraints. Its planned totals are estimates derived from unique tasks, not confirmed monthly allocations.

## 3. F18 — Data Completeness Check

**Goal:** Identify missing expense information and determine whether the available data is sufficiently complete for personalized guidance.

### Algorithm

1. Validate transaction IDs, positive numeric amounts, categories, and expense dates.
2. Identify incomplete transactions and tasks marked `UNRECORDED`.
3. Exclude future or pending tasks from historical missing-check-in findings.
4. Calculate completeness metrics for each user.
5. Generate issue-level and summary CSV files.

The main metrics are:

- `complete_records`: transaction rows with all required fields.
- `incomplete_records`: unrecorded tasks plus transactions missing required information.
- `completeness_rate_pct`:

  `complete_records / (complete_records + incomplete_records) * 100`

- `distinct_categories`: distinct categories among complete transactions.
- `coverage_days`: inclusive calendar-day span between the earliest and latest complete transaction dates.

### Readiness Criteria

The prototype considers the data sufficient when **all four conditions** are met:

- At least 10 complete transaction records.
- At least 3 distinct categories.
- At least 30 days of data coverage.
- At least 80% completeness.

If all criteria pass, the result is `PERSONALIZED_GUIDANCE`; otherwise, it is `GENERAL_BASELINE_GUIDANCE`.

These are configurable prototype thresholds, not mandatory thresholds defined by the Budget Model.

### F18 Outputs

- `f18_completeness_summary.csv`: completeness metrics and guidance readiness per user.
- `f18_data_issues.csv`: incomplete transactions and unresolved tasks requiring attention.

## 4. F19 — Monthly Budget Review

**Goal:** Summarize a selected month's financial activity while distinguishing confirmed spending from unknown or incomplete information.

### Algorithm

1. Select tasks by `assigned_date` and deduplicate them by `user_id` and `task_id`.
2. Count unique tasks by status: `PENDING`, `UNRECORDED`, `NO_EXPENSE`, `WITHIN_BUDGET`, and `OVER_BUDGET`.
3. Select valid task-linked transactions and unexpected transactions by `expense_date`.
4. Deduplicate actual transactions by `user_id` and `record_id`.
5. Aggregate planned amounts and observed actual spending by normalized category.
6. Classify categories as `OVER_BUDGET`, `UNDER_BUDGET`, `ON_BUDGET`, or `INCOMPLETE_DATA` where applicable.
7. Mark the review as partial when required status or category information is missing.
8. Optionally collect a satisfaction rating from 1 to 5 and a comment of up to 2,000 characters.

The variance is calculated as:

`variance_actual_minus_planned = observed actual amount - task-level planned amount`

Positive variance means spending exceeds the task-derived plan; negative variance means spending is below it.

No transaction does not automatically mean zero spending. When the required data is incomplete, the remaining balance is left blank rather than reported as reliable.

### F19 Outputs

- `f19_monthly_review_summary.csv`: monthly totals, task counts, feedback, and review status.
- `f19_category_review.csv`: category-level planned amounts, actual spending, variance, and status.
- `f19_task_status_counts.csv`: unique task counts by status.
- `f19_unexpected_transactions.csv`: unexpected transactions recorded in the selected month.



# II. Business Rules

### BR-01. Data Ownership and Scope

- The Budget module owns available funds, priorities, confirmed plans, and monthly allocations.
- The Expense module owns expense tasks, check-in statuses, and actual transactions.
- F18 and F19 only analyze and report data. They must not modify source records or confirmed budget plans.
- All queries and outputs must be scoped by `user_id`.

### BR-02. Transaction Completeness

A complete transaction must have a valid `record_id`, a positive numeric `amount`, a non-empty `category`, and a valid `expense_date`.

Missing values must be reported, not invented. Category normalization may standardize known naming variations but must not guess missing categories.

### BR-03. Task Status Semantics

- `PENDING`: The task has not been checked in; spending is unknown.
- `UNRECORDED`: The task has not been resolved with a transaction or explicit no-expense confirmation.
- `NO_EXPENSE`: The user has explicitly confirmed no expense occurred.
- `WITHIN_BUDGET`: The task was confirmed within its planned limit.
- `OVER_BUDGET`: The task was confirmed above its planned limit.

`PENDING` and `UNRECORDED` must never be automatically converted to `NO_EXPENSE`.

### BR-04. F18 Readiness Rules

- Calculate completeness using the defined complete and incomplete record counts.
- Apply the prototype thresholds of 10 complete records, 3 categories, 30 coverage days, and 80% completeness.
- Personalized guidance is permitted by this prototype gate only when every threshold passes.
- Passing the gate does not verify confirmed monthly allocations or P0/P1 budget constraints.

### BR-05. F19 Spending and Budget Comparison

- Count each unique task once for planned amounts and task-status counts.
- Sum valid actual transactions separately, counting each transaction ID at most once per user.
- Include valid unexpected transactions in observed spending even when no task is linked.
- Use `assigned_date` for tasks and `expense_date` for transactions.
- Compare task-level planned amounts with actual spending only where the data supports the comparison.
- Missing or unresolved data must not be interpreted as zero spending or a confirmed remaining balance.

### BR-06. Feedback and Demo Data

- Satisfaction ratings must be integers from 1 to 5; comments are optional and limited to 2,000 characters.
- Feedback must not modify budget plans or transaction records.
- All prototype amounts are in VND and must be processed numerically.
- Synthetic demo data must remain separate from official financial records.

# III. Initial Database Model






## 1. Source Entities

| Entity | Main fields | Responsibility |
|---|---|---|
| `users` | `user_id` | Identifies the user whose data is analyzed. |
| `assigned_expense_tasks` | `task_id`, `user_id`, `assigned_date`, `task_status`, `title`, `category`, `planned_amount` | Provides scheduled tasks and task-level planned amounts from the Expense integration. |
| `expense_records` | `record_id`, `user_id`, `task_id`, `record_type`, `title`, `category`, `amount`, `expense_date` | Provides actual transactions, including planned and unexpected spending. |

Recommended constraints include unique task and transaction identifiers, valid task statuses and record types, positive amounts for valid actual transactions, and ownership validation for linked records.

## 2. Assistant-Owned Entities

| Entity | Main fields | Responsibility |
|---|---|---|
| `data_completeness_summary` | `check_id`, `user_id`, `complete_records`, `incomplete_records`, `completeness_rate_pct`, `distinct_categories`, `coverage_days`, `data_sufficient`, `guidance_type`, `created_at` | Stores F18 completeness results. |
| `data_quality_issues` | `issue_id`, `user_id`, `task_id`, `record_id`, `missing_fields`, `is_unrecorded`, `created_at` | Stores individual data-quality findings. |
| `monthly_budget_reviews` | `review_id`, `user_id`, `month`, `total_planned`, `total_confirmed_spending_observed`, `remaining_vs_plan`, task-status counts, `unexpected_spending_total`, `review_status`, feedback fields | Stores F19 monthly summaries. |
| `monthly_category_reviews` | `category_review_id`, `review_id`, `category`, `planned_amount`, `confirmed_actual_amount_observed`, `variance_actual_minus_planned`, `status` | Stores category-level review results. |
| `monthly_task_status_counts` | `status_count_id`, `review_id`, `task_status`, `task_count` | Stores monthly task counts by status. |

Fields should retain source identifiers and `user_id` for traceability. Monetary fields should use integer VND, and unknown values should remain nullable rather than being replaced with zero.


