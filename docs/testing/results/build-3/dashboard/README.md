# Dashboard testing

Use this workspace to record Build 3 functional execution and supporting regression tests for dashboard.

Exercise monthly financial overview (UC22) against known planned and actual amounts for the selected period. Check totals, progress and empty states from the user's Dashboard. Include UC30 same-period comparison and insufficient-data behavior in the design inventory. Record unavailable features as NOT RUN. See the [requirements and traceability](../../../../requirements/README.md), [PA4 component testing scope](../../../../pa4-test-coverage-matrix.md) and [Build 3 verification](../../../../build3-verification.md).

1. Record the run's commit, tester, environment, case IDs and commands in the [execution report](test-execution.md). Enter each observed outcome and evidence reference in [test results](test-results.csv).
2. Capture the selected period and the figures the test compares. Record the source test data so totals can be reproduced. Save reviewed screenshots in [evidence/](evidence/) and approved pytest XML and logs in [automated/](automated/). Use the [shared naming and relative path conventions](../../../README.md#evidence-and-defects).
3. Write reproducible failures in the [defect log](defects.md) and include an approved public issue reference once available. Reference its key in the results row.
4. When requirements change, record the applicable revision, update the case design in the official test case document, and append a result for the retest. Keep prior outcomes and evidence tied to their original revision and commit.
