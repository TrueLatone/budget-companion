# Defect report

| Defect detail | Value |
| --- | --- |
| Title | No Recommendation implementation defect reproduced in this execution |
| Defect ID or public issue link | N/A — no failing case; no issue created |
| Component | Recommendation |
| Affected Test Case IDs and Use Case IDs | F16-01–F16-06 / UC23; F17-01–F17-06 / UC24; F18-01–F18-07 / UC25; F19-01–F19-08 / UC26; supporting UI-E2E-01 |
| Build version and commit SHA | Build 3 / `440b3f75a9e233b08bed74e6053e36ce089df307` |
| Environment | Windows 11; Python 3.13.7; pytest 9.2.0; isolated SQLite; Chrome 158.0.8127.37 desktop for the supporting journey |
| Severity or priority | N/A — no confirmed implementation defect |

## Preconditions and test data

Synthetic authenticated accounts and disposable databases. Case-specific data and expectations are in [test-cases.csv](test-cases.csv). Malformed rows are simulated at the Recommendation boundary. Financial values are compared before and after analysis and decisions.

## Reproduction steps

Run the two commands in [test-execution.md](test-execution.md#automated-execution-commands), then inspect the [case results](test-results.csv). The browser observations describe the supporting Budget → Expense → Recommendation session.

## Expected result

Explained, financially read-only guidance; readiness follows the published completeness contract; unreliable month-end balances remain unknown; valid feedback persists and invalid feedback preserves the previous response.

## Actual result

27 functional cases and one supporting mixed-method journey passed. The 53 functional variants and all 127 Recommendation regression nodes passed; there were no pytest failures, errors or skips. Six deprecation warnings are recorded in the console log, not classified as functional failures.

## Evidence links

- [Result rows](test-results.csv).
- [Functional XML](automated/pytest-cases-20261128-440b3f7.xml) and [regression XML](automated/pytest-recommendation-20261128-440b3f7.xml).
- [Browser observations](evidence/browser-ui-20261128-440b3f7.json) and screenshots linked from the execution report.

## Retest and resolution

This is a fresh execution against integrated main. No application fix or defect-closing retest was performed. Previously submitted evidence is not overwritten or counted as this run.

The initial browser setup used an email under the reserved `.test` domain and could not complete login. Existing validation correctly rejected that fixture. Correcting only the synthetic email allowed the full journey to pass; no Recommendation defect is inferred. The attempt history is retained with the browser evidence.

Open requirements wording concerning the 110% boundary and completeness denominator remains documented in the [baseline review](../../../../requirements/baseline-review.md). The case expectations use the published current-build contract; this report does not silently resolve those wording questions or certify unimplemented planned features.
