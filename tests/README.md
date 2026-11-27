# Automated tests

Run commands from the repository root with the Python 3.11+ virtual environment from [Getting started](../README.md#getting-started) activated. Install the project dependencies with `python -m pip install -r requirements.txt`. Pytest uses standard `test_*.py` and `test_*` discovery here. There is no custom pytest configuration in the repository.

The shared `app` fixture creates and tears down an in-memory SQLite schema, enables Flask testing mode and disables CSRF for ordinary request tests. The `client` fixture uses that app's Flask test client. Migration and persistence checks use temporary SQLite files as needed. The automated suite can run with disposable databases and does not require a team PostgreSQL connection. Use synthetic accounts and financial data.

| Test type | Existing examples |
| --- | --- |
| Unit tests of rules or transformations | `test_budget_rules.py`, `test_expense_presentation.py` |
| Integration tests of routes, services and persistence | `test_accounts.py`, `test_budgets.py`, `test_expenses.py`, `test_migrations.py`, `test_build1_integration.py`, `test_pa4_integration.py` |
| Functional system tests of user workflows | Use the [PA4 evidence workflow](../docs/testing/README.md) for browser execution and [system/](system/) for future automated system tests. Some root integration tests cover end-to-end application flows through Flask's test client. |

All existing tests and `conftest.py` are directly under `tests/`. `test_sprint4_budget_planning.py` keeps existing `BP-*` case mappings. `f18_f19_demo.py` and `f18_f19_.csv` are standalone demo materials outside default test collection.

## Run and export

```bash
python -m pytest tests -q
python -m pytest tests --collect-only -q
python -m pytest -q tests/test_accounts.py tests/test_budget_periods.py
python -m pytest -q tests/test_budgets.py tests/test_budget_customization.py tests/test_sprint4_budget_planning.py
python -m pytest -q tests/test_expenses.py tests/test_expense_presentation.py
python -m pytest -q tests/test_dashboard.py
python -m pytest -q tests/test_recommendations.py
python -m pytest -q tests/test_pa4_integration.py tests/test_migrations.py
```

Use the collected node ID, such as `tests/test_smoke.py::test_home_loads`, to rerun a single test. To export JUnit XML and a console log to an ignored local directory:

```bash
python -c "from pathlib import Path; Path('instance/test-output').mkdir(parents=True, exist_ok=True)"
python -m pytest tests -q --junitxml=instance/test-output/pytest-full.xml > instance/test-output/pytest-full.log 2>&1
```

Check the pytest exit code. Review and copy approved files into the appropriate component's `automated/` directory following the [evidence naming guide](../docs/testing/README.md#evidence-and-defects).

## Add a test

Add a descriptive `test_*` function in the closest existing test file or a new `test_*.py` for a distinct responsibility. Reuse `app` and `client` from [conftest.py](conftest.py) and keep test data local to the case or its fixture. Use `tmp_path` when a case needs its own file database. Exercise CSRF where the behavior under test requires it.

When a test verifies a functional case, record the pytest node ID and the existing Test Case ID in the component results or execution report. Trace the case to the official Use-Case Specification in restricted project storage using its UC ID (for example, `UC09` for section 2.9). `TC-UC09-01` shows the naming format for new cases. Keep existing case IDs stable and use the [PA4 component testing scope](../docs/pa4-test-coverage-matrix.md) to find component mappings.
