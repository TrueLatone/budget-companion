# Test execution report

| Run detail | Value |
| --- | --- |
| Component | Recommendation |
| Testing scope | F16–F19 / UC23–UC26; 27 designed functional cases and one supporting Budget → Expense → Recommendation journey |
| Build version | Build 3, integrated main |
| Tested commit SHA | `440b3f75a9e233b08bed74e6053e36ce089df307` |
| Tester | TTKhiem |
| Execution date and timezone | 28 November 2026; Asia/Ho_Chi_Minh (UTC+07:00) |
| Operating system | Windows 11, build 26200 |
| Browser and version | Chrome 158.0.8127.37; 1440 × 1000 desktop; Vietnamese UI |
| Database and environment | Python 3.13.7, pytest 9.2.0; disposable SQLite. Flask request fixtures disable CSRF; the real browser session enables it. |
| Tested Use Case IDs | UC23–UC26; the supporting journey also exercises prerequisite UC05/UC09/UC10/UC16 |

Application sources match this main commit. The test file retains main's 126 recommendation nodes and adds F19-08 (one node) for provisional-month feedback. That test extension is included with these results; no application fix was made for this run. [Environment](automated/environment-20261128-440b3f7.json)

Expectations use the published [F16–F19 analysis rules](../../../../requirements/functional-requirements.md#analysis-rules) and [API/readiness contract](../../../../architecture/api-contracts.md). The 27 existing case IDs and their expectations are preserved in [case designs](test-cases.csv). The baseline's open 110% wording and completeness-denominator clarifications remain requirements-review items; this run does not declare the entire v1.2 baseline reconciled.

## Automated execution commands

Run from the project root in PowerShell. Unique temporary directories avoid the earlier Windows pytest permission issue.

```powershell
$runId = [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider "--basetemp=$PWD\.tmp\recommendation-$runId" tests/test_recommendations.py -v --tb=short --junitxml=instance/test-output/pytest-recommendation.xml

$caseRunId = [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider "--basetemp=$PWD\.tmp\recommendation-cases-$caseRunId" tests/test_recommendations.py -k 'test_kan65_ and not test_kan65_ui_e2e' -v --tb=short --junitxml=instance/test-output/pytest-recommendation-cases.xml
```

## Result counts

One result per distinct case in this run: 27 functional cases plus UI-E2E-01.

| Outcome | Count |
| --- | ---: |
| Total test cases | 28 |
| PASS | 28 |
| FAIL | 0 |
| BLOCKED | 0 |
| SKIPPED | 0 |
| NOT RUN | 0 |

| Functional coverage | Cases | PASS |
| --- | ---: | ---: |
| UC23 / F16 | 6 | 6 |
| UC24 / F17 | 6 | 6 |
| UC25 / F18 | 7 | 7 |
| UC26 / F19 | 8 | 8 |
| Supporting integration journey | 1 | 1 |

The functional selection executed **53 passing input variants for 27 case IDs**. The complete Recommendation file executed **127 nodes: 127 passed, 0 failed/errors/skips, 6 deprecation warnings** (2 Flask-SQLAlchemy `get_engine`, 4 WTForms SelectField tuple-choice warnings). Its totals include the functional selection and the automated UI-E2E-01 variant; do not add these totals. There are 73 additional supporting regression nodes. The same UI-E2E-01 journey passed in Chrome and is counted once as a mixed-method case. [Case-to-node mapping](automated/case-node-map-20261128-440b3f7.json)

## Identified defects

No implementation defect was reproduced against the stated case expectations. [Defect report](defects.md)

F18-01 reports/excludes the malformed purchase while readiness remains SUFFICIENT at 90.91%. F18-05 passes at exactly 80% and fails readiness at 75%. F17-03 rejects changed-source ACCEPT with HTTP 409. F19-08 saves provisional-month feedback without making the remaining balance known. No financial reallocation occurs.

## Testing limitations

- Only the listed UC23–UC26 cases and supporting journey are claimed. This is not a full-project regression or certification of every flow in the official specification.
- No planned/unimplemented feature is included among these 28 designs. Push delivery, multi-month reports, feedback-based future adaptation and applying financial adjustments are outside this execution; no PASS is claimed for them.
- Malformed purchases are injected at the Recommendation service boundary because canonical database fields reject missing required values. This does not demonstrate a UI path that creates malformed transactions.
- Chrome covers one insufficient-data desktop journey, not every functional case. No new mobile, other-browser, physical-device, PostgreSQL or load/concurrency session was run. Month-boundary cases use an explicit test clock.
- The first Chrome setup attempt did not reach Recommendation: a reserved `.test` fixture email was rejected at login. After correcting only the synthetic account, the full journey passed. This prerequisite attempt is retained in [browser history](evidence/browser-ui-20261128-440b3f7.json) and is not counted as a failing Recommendation case.

## Evidence links

- [Result rows](test-results.csv) and [case designs](test-cases.csv), in the shared CSV formats.
- [Functional-case XML](automated/pytest-cases-20261128-440b3f7.xml) and [actual console output](automated/pytest-cases-20261128-440b3f7.log): 53 passed.
- [Recommendation regression XML](automated/pytest-recommendation-20261128-440b3f7.xml) and [actual console output](automated/pytest-recommendation-20261128-440b3f7.log): 127 passed.
- [Browser observations and attempt history](evidence/browser-ui-20261128-440b3f7.json); [environment](automated/environment-20261128-440b3f7.json).

Actual session screenshots, all from the same browser journey and source revision:

1. [UI-E2E-01, step 1: saved BALANCED plan](evidence/20261128-440b3f7-UI-E2E-01-step-01.png). The screenshot precedes confirmation; subsequent confirmation and scheduling are checked by the session script.
2. [UI-E2E-01, step 2: recorded Food purchase](evidence/20261128-440b3f7-UI-E2E-01-step-02.png). The Expense screen shows 12,785 VND and a successful check-in.
3. [UI-E2E-01, step 3: Recommendation reads the same purchase](evidence/20261128-440b3f7-UI-E2E-01-step-03.png). One transaction/category/day gives insufficient readiness; the monthly summary shows recorded spending without asserting a reliable remaining balance.

Evidence contains synthetic data. Workstation hostnames were removed from approved XML copies and absolute workspace paths were normalized in logs; assertions, outcomes and totals are unchanged. Official submission documents and private Jira attachments remain separate from this public workspace.
