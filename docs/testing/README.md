# Testing documentation

Use the [Build 3 workspaces](results/build-3/) to record planned and executed component cases. The [pytest guide](../../tests/README.md) covers automated regression tests. The [PA4 component testing scope](../pa4-test-coverage-matrix.md) maps use cases to workspaces. [Build 3 verification](../build3-verification.md) and [PA2 integration verification](integration-pa2-budget-verification.md) summarize earlier runs.

## Design and execute cases

1. Start with the official Use-Case Specification and Vision Document in restricted project storage. See [Requirements and traceability](../requirements/README.md) for how to map IDs, and consult the restricted case inventory for existing designs. PA4 requires at least five designed cases per documented UC, including planned functionality. The [v1.2 index](../requirements/use-case-index.md) contains 31 use cases, giving a design minimum of 155. Use the official PA4 test case document for submission. Keep existing IDs and use a format such as `TC-UC09-01` for new cases. The [case CSV](templates/test-case-template.csv) is a working template for collaboration.
2. Select the tested build and record `git rev-parse HEAD`. Record local environment details and use synthetic accounts and data. Choose browser, automated, or mixed execution according to the case steps and expected result. Record the operating system, browser version and database setup, including when a browser was unnecessary.
3. Fill in one [result row](templates/test-results-template.csv) per case and execution. Enter the actual result, status and evidence path. Use a role or an approved public handle as the tester reference. Include the exact pytest node ID in Remarks when applicable. Keep previous runs identifiable by commit and execution date, and append retest rows when results change.
4. Summarize each run in the [execution report](templates/test-execution-template.md). Include the case scope, environment, commands, totals, defects, limitations and relative links to real screenshots and logs. Use the official PA4 Test Report for submission and consolidate as described in the [Build 3 guide](results/build-3/README.md).

| Status | Meaning |
| --- | --- |
| PASS | Execution reached the expected result and has supporting evidence. |
| FAIL | An observed result differed from the expected result. Record the difference, evidence and defect reference when available. |
| BLOCKED | An environment, prerequisite or dependency prevented an otherwise applicable case from being completed. Record the blocker. |
| NOT RUN | The case has not been executed. For planned functionality outside Build 3, keep the design and record the missing implementation as the reason when reviewing execution. |
| SKIPPED | The run deliberately bypassed a case under a documented condition. Record the condition and reason. |

## Evidence and defects

- Save actual session screenshots in the component's `evidence/`, using names such as `TC-UC09-01-step-03.png`. Choose distinct filenames for different executions so a retest leaves earlier evidence intact.
- Export XML and console output to an ignored local directory first. After review, save approved copies in the component's `automated/` with names such as `pytest-budget-planning.xml` and `pytest-budget-planning.log`. Use relative paths from the corresponding CSV or Markdown file, such as `evidence/TC-UC09-01-step-03.png` or `automated/pytest-budget-planning.xml`. Use Markdown links from the execution report after files exist.
- Use the [defect template](templates/defect-report-template.md) to capture affected case IDs, build and commit, reproduction steps, expected and actual results, and evidence. Use an approved public issue reference in the defect entry. Keep internal issue links and identifiers in restricted project storage. Record the reference in the failing result and append a linked retest after the fix.
- Review filenames, text, screenshots and embedded metadata before committing any evidence. Use synthetic data and inspect log/XML payloads and screen captures for credentials, account data, student IDs and other personal information. Check PDF, image and document metadata, including any embedded original or hidden text.
- Keep private Jira screenshots, credentials, unreviewed or confidential evidence, and local databases and browser profiles in restricted storage. Cite relative paths only for approved public evidence. The official PA4 report and its supporting records are maintained separately in restricted project storage.
