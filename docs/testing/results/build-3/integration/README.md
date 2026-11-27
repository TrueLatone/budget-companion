# Integration testing

Use this workspace to record Build 3 functional execution and supporting regression tests for integration.

Exercise flows that cross component boundaries, such as creating a period (UC05), confirming a budget and generating a schedule (UC10–UC11), recording an expense (UC16 or UC18), and observing the dashboard (UC22). List the actual UCS IDs for each flow and link any component results that cover the same case. See the [requirements and traceability](../../../../requirements/README.md), [PA4 component testing scope](../../../../pa4-test-coverage-matrix.md) and [Build 3 verification](../../../../build3-verification.md).

1. Record the run's commit, tester, environment, case IDs and commands in the [execution report](test-execution.md). Enter each observed outcome and evidence reference in [test results](test-results.csv).
2. Capture the relevant handoff outcomes and final state. Keep shared evidence references so the consolidated report can count overlapping cases once. Save reviewed screenshots in [evidence/](evidence/) and approved pytest XML and logs in [automated/](automated/). Use the [shared naming and relative path conventions](../../../README.md#evidence-and-defects).
3. Write reproducible failures in the [defect log](defects.md) and include an approved public issue reference once available. Reference its key in the results row.
4. When requirements change, record the applicable revision, update the case design in the official test case document, and append a result for the retest. Keep prior outcomes and evidence tied to their original revision and commit.
