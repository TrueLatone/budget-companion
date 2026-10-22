# Budget model/rules

## I. Budget model and algorithm

**Overall Workflow:** Available Funds → P0 Reservation → P1 Baseline (based on reference/past months) → Three Budget Plans → User Confirmation.

Users can create a monthly budget manually or select a suggested budget plan.

### a) Plan generation

**Plan generation partitioning:** Dividing to 3 options:

- **Saving:** Prioritizes savings and limits flexible spending.
- **Balanced:** Distributes the remaining funds across essential spending, flexible spending, and savings.
- **Lifestyle:** Allows more flexible spending while maintaining mandatory and minimum essential allocations.

AI may suggest whether custom expenses belong to P1 or P2 when the user has not specified their priority. Each suggestion includes a brief explanation, and users can confirm or modify the classification before generating their monthly budget plans.

**Remaining Budget = Available Funds − Total P0 − Total P1 Minimum**

If the remaining budget is negative, the system reports a budget shortfall instead of generating an unrealistic plan. If sufficient funds are available, the remaining budget can be distributed among Extra P1, P2, and Savings according to the selected plan.

The allocation percentages are applied only to the remaining budget after P0 and P1 minimums have been reserved, not to the user's total available funds.

Users can review and customize the suggested allocations before confirming a monthly plan.

| Plan | Extra P1 | P2 | Savings |
|---|---:|---:|---:|
| Saving | 15% | 15% | 70% |
| Balanced | 25% | 35% | 40% |
| Lifestyle | 30% | 55% | 15% |

| Plan | P1 – Essential | P2 – Flexible | Savings |
|---|---:|---:|---:|
| Saving | 70% | 5% | 25% |
| Balanced | 65% | 15% | 20% |
| Lifestyle | 60% | 30% | 10% |

### b) Expense partitioning

**Partitioning by day/week/month:**

| Frequency | Partitioning Method | Example |
|---|---|---|
| Daily | Divide monthly allocation by the number of applicable days in the month. | Food: 1,500,000đ ÷ 30 days = 50,000đ/day |
| Weekly | Divide monthly allocation among the applicable weeks of the month. | Transportation: 400,000đ ÷ 4 weeks = 100,000đ/week |
| Monthly | Keep the full monthly allocation, associated with its scheduled due date if applicable. | Rent: 1,500,000đ/month |

The system distributes confirmed monthly allocations into daily, weekly, or monthly spending limits depending on the expense frequency.

- **Daily Allocation:** Distribute the monthly allocation across the applicable days of the selected calendar month.
- **Weekly Allocation:** Distribute the monthly allocation across the applicable weekly periods.
- **Monthly Allocation:** Keep the full monthly allocation associated with the expense and its scheduled period.

**Food-specific allocation (Example for distribution only, future development):** After determining the monthly Food allocation, the system divides it into daily budgets and further partitions each day's amount into breakfast, lunch, and dinner. An initial distribution is provided , while future suggestions may adapt based on confirmed spending history. The total food allocation must remain within the confirmed monthly budget.

**Automatic reallocation:** When confirmed spending exceeds a daily or weekly limit, the system automatically redistributes the remaining amount across future days or weeks within the same expense’s monthly allocation. The original confirmed monthly plan remains unchanged, and the user is informed of the updated spending limits

## II. Business rules

### 1. Available Fund

- Previous months' remaining funds are not automatically carried over. Users manually enter their current available funds.
- Users may update their available funds if their financial situation changes during the month.(as extra funds during the day). Changes to available funds do not automatically overwrite an existing confirmed budget plan.
- When available funds change, the system may suggest a revised allocation. Users must review and confirm the adjustment before it becomes active.

### 2. Expense Categories

- Expenses are classified into three priority levels:
  - P0 – Mandatory: Rent, electricity, water, Internet.
  - P1 – Essential: Food, transportation.
  - P2 – Flexible: Entertainment, shopping, and other optional expenses.
- The system provides default P0 and P1 expenses. P2 has no default expenses.
- Users may create custom expense categories and individual expenses. New categories without P1,P2 will be decided by AI
- Expense priorities and categories may be modified before confirming a monthly plan. After confirmation, they are locked.
- Expenses may have daily, weekly, or monthly cycles, independently of their priority.

### 3. P0 – Mandatory Expenses

- Users must enter rent, electricity, and water amounts. Electricity and water may be estimated.
- Internet is optional. If included, it is classified as P0.
- P0 amounts are carried forward to the next month unless users update or remove them.
- Every included P0 expense must have a positive amount. An expense that no longer applies may be removed or manually reclassified during a future month's setup.
- P0 expenses must be reserved before allocating funds to P1 and P2. Future bills only reduce actual remaining cash when payment is recorded.

### 4. P1 – Essential Expenses

- Users can specify a minimum amount for each P1 expense. Minimum amounts are optional but must be positive when provided.
- The system generates suggested P1 allocations. If a user-defined minimum exists, the allocation must not fall below it.
- First-month suggestions use reference spending data. Later suggestions use the user's confirmed spending history when sufficient information is available.
- P1 has higher priority and less allocation flexibility than P2.

### 5. P2 – Flexible Expenses

- Users may add their own P2 expenses without specifying individual preferred allocations.
- The system determines P2 allocations based on the budget plan type and available funds.
- Every expense included in a confirmed plan must have a positive planned amount. Expenses with no planned spending should not be included.

### 6. Budget Generation and Confirmation

- The system proposes alternative monthly plans based on available funds, P0 expenses, P1 minimums, and financial preferences.
- A monthly plan must have sufficient funds to cover all included P0, P1, and P2 allocations, along with any planned savings.
- If available funds cannot cover P0 and user-defined P1 minimums, the system reports a budget shortfall.
- Users may review and customize proposed plans before choosing and confirming one.
- Users may request changes to an active plan when their financial circumstances or spending needs change.
- The original confirmed monthly plan is preserved for historical comparison. Overspending triggers automatic recalculation of future daily/weekly spending limits within the same monthly allocation; changes to available funds do not automatically rewrite the original plan

## III. Initial database model

| Data Object | Description | Main Attributes |
|---|---|---|
| User | Student who owns the budget. | User ID |
| Monthly Budget | Represents the user's budget for a calendar month. | Budget ID, Month/Year, Available Funds |
| Expense | Represents a planned expense belonging to P0, P1, or P2. | Expense ID, Name, Priority, Estimated Amount, Minimum Amount (optional), Frequency |
| Budget Plan | Represents one generated budget strategy. | Plan ID, Plan Type, Status, Planned Savings |
| Budget Allocation | Stores how much a plan assigns to each expense. | Allocation ID, Expense ID, Plan ID, Allocated Amount |
| Spending Schedule | Represents the daily/weekly/monthly spending limits derived from the confirmed plan. | Schedule ID, Allocation ID, Date/Period, Planned Limit, Adjusted Limit |

| Relationship | Cardinality |
|---|---|
| User → Monthly Budget | 1:N |
| Monthly Budget → Expense | 1:N |
| Monthly Budget → Budget Plan | 1:N |
| Budget Plan → Budget Allocation | 1:N |
| Expense → Budget Allocation | 1:N |
| Budget Allocation → Spending Schedule | 1:N |
