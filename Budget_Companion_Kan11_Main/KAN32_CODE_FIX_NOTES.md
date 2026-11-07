# KAN-32 Budget Planning — code-only compatibility fix

This folder is the full Budget Companion project from the reviewed KAN-32
implementation. It includes the existing 19-case Jira Task 1/2 test file.
**No test files were edited to make failing tests pass.**

## Application fixes

1. `app/modules/budgets/services.py`: honor submitted `category_id` and
   `category_name` when saving/editing expenses; preserve existing category
   when editing with no new category; use the expense name only for new entries
   without category input. Suggested expenses generated from the inline Budget
   form now retain their suggested category. These changes address the
   Budget and Recommendations category regressions without changing the
   financial model or daily/weekly/monthly scheduler.
2. `app/modules/budgets/routes.py`: distinguish locked confirmed-plan
   conflicts (HTTP 409) from malformed submissions (HTTP 400), including the
   generated-plan and legacy expense-edit routes. No confirmed plan is modified.

## Intentionally unchanged

- All tests are preserved exactly from the user's uploaded test folder, except
  that `test_budget_jira_tasks.py` uses the user's latest 19-case Task 2 update.
- Expense Scheduling / Smart Check-in, Dashboard, Accounts, Recommendations,
  Budget Periods, migrations, shared database models, and frontend layouts.
- Confirmation still redirects to the confirmed Budget plan details; the
  existing Expense POST creates the schedule explicitly.
- Default UI language, date validation, and the team's existing tests remain
  unchanged. Legacy test assertions expecting old English labels or old
  navigation may continue to fail; do not reinterpret these as schedule faults.
- Available-funds edits after confirmation are a cross-team contract decision;
  existing Expense and Dashboard tests intentionally exercise that behavior.

## Local verification (PowerShell, from project root)

```powershell
uv venv
uv pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -v tests/test_budget_jira_tasks.py
.\.venv\Scripts\python.exe -m pytest -v tests/test_budgets.py tests/test_budget_setup_parity.py tests/test_recommendations.py
.\.venv\Scripts\python.exe -m pytest -q
```

The code was syntax-checked while preparing this ZIP. Runtime pytest was
not executed in the packaging environment because Flask-related dependencies
could not be installed without network access. The previous user run, before
these edits, reported 19/19 focused Jira tests passing and 50 failures in the
full suite. No claim of newly passing tests is made here.
