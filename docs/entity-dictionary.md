# Budget Companion — implemented entity dictionary

KAN-19 implements these 13 entities in `app/models/`. All `id` columns are
application-generated UUID primary keys; all FKs use UUID. Money is integer VND
BIGINT. All columns are required unless marked NULL; defaults permit omission
on insertion where stated. Relationships listed below are ORM attributes, not
extra columns. See [database design](database-design.md) for source decisions,
deletion policy, migrations, and service responsibilities.

## 1. User — `users`

Identifies and authenticates the owner of private budgeting data. Existing
operational and audit attributes are preserved.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Stable account identifier; conceptual UserID. |
| `email` | VARCHAR(320), unique | Trimmed lowercase email. |
| `password_hash` | VARCHAR(255) | Secure password hash. |
| `is_active` | BOOLEAN, default true | Whether authentication is permitted. |
| `created_at` | TIMESTAMP with timezone, default now | Account creation in UTC. |
| `updated_at` | TIMESTAMP with timezone, default now | ORM updates refresh this audit timestamp. |

Relationships: many budget months/categories; zero or one preference.

## 2. UserPreference — `user_preferences`

Stores optional budgeting strategy and in-app notification choices.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Preference identifier. |
| `user_id` | UUID, unique FK → users.id | Account owning these choices. |
| `preferred_plan_type` | VARCHAR(20), NULL | SAVING, BALANCED, LIFESTYLE or MANUAL. |
| `budget_alerts_enabled` | BOOLEAN, default true | Enables reported-spending warnings. |
| `payment_reminders_enabled` | BOOLEAN, default true | Enables derived upcoming-payment reminders. |

## 3. BudgetMonth — `budget_months`

Defines an owner's calendar month, tracking interval and current available funds.
Funds are neither spending nor a calculated remaining balance.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Period identifier; conceptual BudgetMonthID. |
| `user_id` | UUID, FK → users.id | Period owner. |
| `month_start` | DATE, day = 1 | Calendar month; unique together with owner. |
| `tracking_start_date` | DATE, within month | First tracking date; omitted ORM/service input defaults to month_start. |
| `available_vnd` | BIGINT ≥ 0 | Current total funds available for this month. |
| `created_at` | TIMESTAMP with timezone, default now | Period creation in UTC. |
| `updated_at` | TIMESTAMP with timezone, default now | ORM updates refresh this audit timestamp. |

Relationships: many planned expenses, plans, records and recommendations;
zero or one review. Tasks are reached through plans and allocations.

## 4. ExpenseCategory — `expense_categories`

Provides stable category identities for planned and actual spending.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Category identifier. |
| `user_id` | UUID, NULL, FK → users.id | Custom-category owner; NULL denotes built-in. |
| `category_name` | VARCHAR(100), nonblank | Unique after SQL trim/lower within owner or built-in namespace. |

Relationships: many planned expenses/records. Priority belongs to expenses,
not categories. Built-in and custom categories may share names.

## 5. BudgetExpense — `budget_expenses`

Describes an expense that should be funded during a particular month.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Planned expense identifier. |
| `budget_month_id` | UUID, FK → budget_months.id | Month being planned. |
| `category_id` | UUID, FK → expense_categories.id | Expense classification. |
| `expense_name` | VARCHAR(120) | Name such as Rent or Food. |
| `priority` | VARCHAR(2) | P0 mandatory, P1 essential, P2 flexible. |
| `estimated_amount` | BIGINT ≥ 0, NULL | Estimated/required amount; P0 positivity is a service rule. |
| `minimum_amount` | BIGINT > 0, NULL | Optional protected minimum. |
| `allocation_frequency` | VARCHAR(10) | DAILY, WEEKLY or MONTHLY. |
| `is_recurring` | BOOLEAN, default false | Offer/copy this expense when setting up another month. |
| `due_day` | SMALLINT 1–31, NULL | Usual bill deadline day. |

Relationship: many allocations across candidate plans.

## 6. BudgetPlan — `budget_plans`

Stores a candidate strategy or the month's confirmed allocation snapshot.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Plan identifier. |
| `budget_month_id` | UUID, FK → budget_months.id | Month being planned. |
| `plan_type` | VARCHAR(20) | SAVING, BALANCED, LIFESTYLE or MANUAL. |
| `status` | VARCHAR(20), default GENERATED | GENERATED or CONFIRMED; at most one confirmed per month. |
| `planned_savings` | BIGINT ≥ 0, default 0 | Money reserved for savings. |

Relationship: many allocations. Confirmation/funding/immutability require services.

## 7. BudgetAllocation — `budget_allocations`

Associates a plan with an expense and its assigned monthly amount.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Allocation identifier. |
| `plan_id` | UUID, FK → budget_plans.id | Containing plan. |
| `budget_expense_id` | UUID, FK → budget_expenses.id | Expense; unique together with plan. |
| `allocated_amount` | BIGINT > 0 | Monthly allocation, not an amount to repeat per task. |

Relationship: many tasks. Services ensure plan/expense share the authorized month.

## 8. AssignedExpenseTask — `assigned_expense_tasks`

Represents one scheduled spending period from a confirmed allocation.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Task identifier. |
| `allocation_id` | UUID, FK → budget_allocations.id | Source allocation. |
| `assigned_date` | DATE | Period start; unique together with allocation. |
| `period_end` | DATE ≥ assigned_date | Inclusive period end. |
| `original_limit` | BIGINT ≥ 0 | Original allowance, preserved by services. |
| `current_limit` | BIGINT ≥ 0 | Currently applicable allowance. |
| `task_status` | VARCHAR(20), default PENDING | PENDING, RECORDED or NO_EXPENSE. |
| `payment_due_date` | DATE, NULL | Individual bill deadline. |
| `payment_status` | VARCHAR(20), NULL | Self-reported PAID or UNPAID. |

Relationships: many transactions/adjustment details. UNRECORDED, WITHIN_BUDGET
and OVER_BUDGET are derived display states, not stored values.

## 9. ExpenseRecord — `expense_records`

Stores one actual purchase or funds addition. A task may own multiple purchases.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Transaction identifier. |
| `budget_month_id` | UUID, FK → budget_months.id | Reporting month and ownership path. |
| `task_id` | UUID, NULL, FK → assigned_expense_tasks.id | Required for PLANNED; NULL otherwise. |
| `category_id` | UUID, NULL, FK → expense_categories.id | Required for spending; NULL for FUNDS_ADDED. |
| `amount` | BIGINT > 0 | Positive VND amount; type determines treatment. |
| `expense_date` | DATE | Date spent or funds became available. |
| `record_type` | VARCHAR(20) | PLANNED, UNEXPECTED or FUNDS_ADDED. |
| `priority` | VARCHAR(2), NULL | Required P0/P1/P2 for UNEXPECTED; NULL for FUNDS_ADDED; PLANNED derives from BudgetExpense. Included from revised DOCX despite image omission. |
| `title` | VARCHAR(120), NULL | Short description. |
| `note` | TEXT, NULL | Optional context. |
| `budget_impact_scope` | VARCHAR(10), NULL | Optional DAILY/WEEKLY/MONTHLY scope for UNEXPECTED only. |
| `idempotency_key` | VARCHAR(64), NULL | Technical retry token; unique with month when non-NULL. |

FUNDS_ADDED is excluded from spending. Atomic fund updates, replay validation,
ownership and check-in consistency require services.

## 10. Recommendation — `recommendations`

Stores an explainable proposed change awaiting a user's decision.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Recommendation identifier. |
| `budget_month_id` | UUID, FK → budget_months.id | Month analyzed. |
| `reason` | TEXT | Why it was proposed. |
| `expected_impact` | TEXT | Expected effect if accepted. |
| `proposed_changes` | JSON / PostgreSQL JSONB | Structured task/limit proposals; references are not SQL FKs. |
| `status` | VARCHAR(20), default PENDING | PENDING, ACCEPTED or REJECTED. |

Relationship: zero or one adjustment. Services validate JSON and acceptance.

## 11. BudgetAdjustment — `budget_adjustments`

Records an applied manual or recommendation-driven change.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Adjustment identifier. |
| `recommendation_id` | UUID, NULL, unique FK → recommendations.id | Originating recommendation; NULL for manual changes. |
| `effective_date` | DATE | When the change takes effect. |
| `reason` | TEXT | Why limits changed. |
| `adjustment_type` | VARCHAR(24), nonblank | Trigger such as MANUAL or RECOMMENDATION; no closed enum. |

Relationship: many details. Services require at least one and derive manual
adjustment ownership/month through its tasks.

## 12. BudgetAdjustmentDetail — `budget_adjustment_details`

Preserves the previous and applied limits for one affected task.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Detail identifier. |
| `adjustment_id` | UUID, FK → budget_adjustments.id | Parent adjustment. |
| `task_id` | UUID, FK → assigned_expense_tasks.id | Task; unique together with adjustment. |
| `previous_limit` | BIGINT ≥ 0 | Limit before this change. |
| `new_limit` | BIGINT ≥ 0 | Limit applied by this change. |

Services atomically write details/current limits and preserve original limits.

## 13. MonthlyReview — `monthly_reviews`

Stores optional monthly user feedback. Financial summaries remain derived.

| Attribute | Type / constraint | Description |
|---|---|---|
| `id` | UUID, PK | Feedback identifier. |
| `budget_month_id` | UUID, unique FK → budget_months.id | Month reviewed. |
| `rating` | SMALLINT 1–5, NULL | Optional satisfaction score. |
| `comment` | TEXT, NULL | Optional written feedback. |
