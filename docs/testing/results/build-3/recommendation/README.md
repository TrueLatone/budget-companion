# Recommendation testing

Use this workspace to record Build 3 functional execution and supporting regression tests for recommendation.

Exercise adaptive guidance (UC23), explanation and response (UC24), data completeness (UC25), and monthly review (UC26). Compare early guidance with data-ready scenarios and check the effect of responding to a recommendation. Use the approved completeness contract recorded in the verification report. See the [requirements and traceability](../../../../requirements/README.md), [PA4 component testing scope](../../../../pa4-test-coverage-matrix.md) and [Build 3 verification](../../../../build3-verification.md).

1. Record the run's commit, tester, environment, case IDs and commands in the [execution report](test-execution.md). Enter each observed outcome and evidence reference in [test results](test-results.csv).
2. Capture the relevant readiness state, explanation or decision and the resulting review or financial state. Save reviewed screenshots in [evidence/](evidence/) and approved pytest XML and logs in [automated/](automated/). Use the [shared naming and relative path conventions](../../../README.md#evidence-and-defects).
3. Write reproducible failures in the [defect log](defects.md) and include an approved public issue reference once available. Reference its key in the results row.
4. When requirements change, record the applicable revision, update the case design in the official test case document, and append a result for the retest. Keep prior outcomes and evidence tied to their original revision and commit.

## Recorded execution

28 November 2026 · Build 3 · main `440b3f75a9e233b08bed74e6053e36ce089df307` · tester TTKhiem.

- [Designed cases](test-cases.csv): 27 UC23–UC26 cases (6/6/7/8), plus one supporting integration journey.
- [Results](test-results.csv): **28 PASS, 0 FAIL, 0 BLOCKED, 0 SKIPPED, 0 NOT RUN** for this selection.
- [Execution report](test-execution.md): 53 passing functional variants; 127 passing Recommendation regression nodes; one successful real Chrome journey. These counts overlap and must not be added.
- [Defects and limitations](defects.md); [reviewed evidence](evidence/); [automated reports](automated/).

Application code matches the recorded main commit. F19-08 is a new appended test included with these results. The first Chrome fixture setup was blocked before Recommendation was reached; its corrected rerun passed, with the attempt history preserved.
