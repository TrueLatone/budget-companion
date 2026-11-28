# Budget Planning test execution

| Run detail | Value |
| --- | --- |
| Component | Budget Planning |
| Testing scope | 60 cases, BP-01 through BP-60. Includes period selection and cross-owner checks. |
| Build version | Build 3, main |
| Tested commit SHA | `440b3f75a9e233b08bed74e6053e36ce089df307` |
| Tester | Budget Planning verification |
| Execution date and timezone | 28 November 2026, Asia/Ho_Chi_Minh |
| Operating system | Debian GNU/Linux 13, x86-64 |
| Browser and version | Chromium 158.0.8127.0, desktop, 1440 × 980, English and Vietnamese |
| Database and environment | Isolated SQLite fixtures for pytest. Separate migrated SQLite file for browser sessions. Python 3.12.14, Flask 3.1.3 and pytest 9.2.0. |
| Tested use case IDs | UC05, UC06, UC08–UC12 and UC27, plus two cross-owner checks. UC28 and UC29 have designs for later execution. |

## Automated execution commands

Run at the tested commit from the folder containing `requirements.txt`, with project dependencies installed. The two runs produced 43 and 622 passing nodes respectively. The full suite includes the focused set.

```sh
python -m pytest -v --tb=short -p no:cacheprovider --junitxml=budget-planning.xml tests/test_sprint4_budget_planning.py tests/test_pa4_integration.py::test_visible_custom_expense_without_category_controls tests/test_budget_customization.py::test_t2_budget_schedule_displays_original_not_adjusted_limits
python -m pytest -q --tb=short -p no:cacheprovider --junitxml=full-regression.xml tests
```

Use the [case designs](test-cases.csv) and [case results](test-results.csv) for each procedure and expected result. The browser run used real forms and disposable users. A separate HTTP check changed one saved current limit in a fixture to test an adjustment. The browser run used January for period switching and customization, and December for the language checks.

## Result counts

| Outcome | Count |
| --- | ---: |
| Total test cases | 60 |
| PASS | 43 |
| FAIL | 2 |
| BLOCKED | 0 |
| SKIPPED | 0 |
| NOT RUN | 15 |

45 distinct case IDs were executed. Among the 40 BP-prefixed pytest nodes, BP-39 passed its implementation assertion and failed its use-case expectation. Browser checks supplied the outcomes for BP-04, BP-14, BP-28, BP-59 and BP-60. Browser and HTTP checks also supported other rows without adding extra cases.

## Identified defects

- **BP-D02 / BP-39.** The confirmation request created 34 tasks before the student selected Create / Verify. A second request preserved the same task IDs.
- **BP-D03 / BP-59.** In Vietnamese, the original schedule displayed the standard Rent entry as “Rent”. The custom Cinema entry retained its name. The English case passed.

See [defect details and retest steps](defects.md).

## Testing limitations

BP-44–53 cover previous-month copying. BP-54–58 cover the optional savings target. Both functions are absent from this commit. Keep all 15 designs and record them as NOT RUN. Source reports from other branches are separate executions.

BP-20/21 test confirmation at the service level. BP-25 tests explicit generation on a confirmed fixture. BP-39 checks the actual HTTP handoff, including its timing. UC10 and UC11 of the v1.2 specification require a separate user action. UC29 describes automatic generation in its proposed flow. The team still needs to agree on that conflict. BP-59/60 check the language requirement in the submitted Budget Planning case designs. Budget figures and screenshots are synthetic. Browser checks used desktop Chromium and local SQLite.

## Evidence links

| Session | Evidence |
| --- | --- |
| Switch December and January, then save the January Custom plan | [Selected periods](evidence/BP-04-periods.png) and [saved allocations](evidence/BP-14-custom-plan.png) |
| Open the confirmed original schedule | [Day view](evidence/BP-28-original-schedule.png) and [limit comparison before and after check-in](automated/schedule-check.log) |
| Read the December schedule in Vietnamese and English | [Vietnamese label](evidence/BP-59-vietnamese-label.png) and [browser session output](automated/browser-session.log) |
| Focused tests | [Console log](automated/pytest-budget-planning.log) and [JUnit XML](automated/pytest-budget-planning.xml) |
| Full regression | [Console log](automated/pytest-full-regression.log) and [JUnit XML](automated/pytest-full-regression.xml) |
