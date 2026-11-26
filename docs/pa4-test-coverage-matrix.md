# PA4 functional test coverage — KAN-60 / KAN-67

Audited **26 November 2026**. PA4.pdf, requirement d (page 2), requires at least
five designed functional cases for **every documented use case**; requirement e
requires execution for the implemented scope. PA3 supplies **G10-UCS-v1.1,
14 November 2026, sections 2.1–2.27**. UC27 was added after v1.0, so the design
minimum is **135**, not the v1.0 minimum of 130. The two project-lead-approved
Build 3 contract exceptions are recorded in [verification](build3-verification.md).

## Counting and evidence rules

Counts below come from readable original owner attachments, retaining their
IDs/templates. Revised versions replace the earlier version of the same ID;
parameterized pytest runs are not additional designed cases. Expense UI IDs
restart per UC, so `UC16/UI01` and `UC18/UI01` are distinct. Budget `BP-*` and
Expense `UC11/UI*` are separately designed cases with overlapping behavior;
neither becomes a new use case. Cross-owner `BP-29/30`, `INT/IT01–03` and
`WS01–03` remain supplemental checks.

Historical workbook Pass entries are **owner-reported**, not a new integrated
execution. New automated evidence is tied to source `bdb4825`; it does not
re-execute every workbook step or certify old screenshots against this source.
`MISSING` means no mapped designed case was supplied, even where pytest tests
exist. `PENDING` means owner correction/retargeting is needed. No missing case is
invented to reach the requirement.

| UC ID | UC name | Implemented? | Test-case IDs/source | Case count | Meets >=5? | Execution status | Evidence | Owner | Gaps |
|---|---|---|---|---:|---|---|---|---|---|
| 2.1 | Register an Account | Yes | MISSING designed-case source | 0 | No | Automated integration passed; workbook NOT EXECUTED | `test_accounts.py`, `test_pa4_integration.py` | Thịnh | 5 designed cases |
| 2.2 | Log In | Yes | MISSING designed-case source | 0 | No | Automated integration passed; workbook NOT EXECUTED | `test_accounts.py`, integrated flow | Thịnh | 5 designed cases |
| 2.3 | Log Out | Yes | MISSING designed-case source | 0 | No | Automated regression; workbook NOT EXECUTED | `test_accounts.py` | Thịnh | 5 designed cases |
| 2.4 | Update Profile and Budgeting Preferences | No; account display only | MISSING | 0 | No | NOT EXECUTED | `/account` has no profile-update write | Thịnh | 5 designs; implementation pending |
| 2.5 | Create a Monthly Budget Period | Yes | B: BP-01/02/03/31/32 | 5 | Yes | Historical 5 Pass; mapped automation passed | B, `test_sprint4_budget_planning.py` | Nhân / Thịnh | Retarget owner report to integrated SHA |
| 2.6 | View or Switch a Budget Period | Yes | B: BP-04/33/34/35/36 | 5 | Yes | Historical 5 Pass; BP-04 browser evidence remains historical | B, Budget tests | Nhân | Current case-level browser retest PENDING |
| 2.7 | Manage Notification Preferences | No | MISSING | 0 | No | NOT EXECUTED | No notification-preferences route | Thịnh | 5 designs; implementation pending |
| 2.8 | Set Up Monthly Budget | Yes | B: BP-05/06/07/08/09 | 5 | Yes | Historical 4 Pass/1 Fail; BP-05 defect reproduced and fixed/retested | B, new HTTP regressions and Chrome custom entry | Nhân | Preserve old failure; attach new retest |
| 2.9 | Generate Budget Plans | Yes | B: BP-10/11/12/13/37 | 5 | Yes | Historical 5 Pass; automated and new browser flow passed | B, Budget and integrated tests | Nhân | Update source reference |
| 2.10 | Select and Confirm Budget Plan | Yes; approved auto-schedule | B: BP-20/21/22/23/38 | 5 | Yes | Historical 5 Pass; current confirmation/rollback tests passed | B, customization/Expense/integrated tests | Nhân | Reflect approved contract exception |
| 2.11 | Generate Spending Schedule | Yes; confirmation plus retry service | B: BP-24/25/26/27/39; E: UC11/UI01–05 | 10 | Yes | Owner Pass entries; current scheduling/replay tests passed | B/E, migration and Expense tests | Nhân / Tuấn Anh | E/UI04 actual result does not demonstrate expected conflict; clarify |
| 2.12 | View Planned Spending Schedule | Yes | B: BP-28/40/41/42/43; E: UC12/UI01 | 6 | Yes | B historical 5 Pass; E historical Fail (B001) | B/E, original-limit regression | Nhân / Tuấn Anh | B001 rendering exists; case-specific browser retest PENDING |
| 2.13 | View Expense Plan (Day / Week / Month / Year) | Partial; Expense Day/Month/Year, Budget schedule Week | E: UC13/UI01–02 | 2 | No | Historical 2 Pass; current regression passed | E, `test_expenses.py` | Tuấn Anh | 3 designs; clarify view scope |
| 2.14 | View Task Due Dates | Partial; service works, payment UI absent | E: UC14/UI01 | 1 | No | Historical Fail B002; current UI control absent | E, payment-status service tests | Tuấn Anh | 4 designs; owner UI fix |
| 2.15 | Check In Planned Expense | Yes | E: UC15/UI01 | 1 | No | Historical Pass; current future/ownership/CSRF tests passed | E, Expense/integrated tests | Tuấn Anh | 4 designs |
| 2.16 | Record Expense for Planned Task | Yes | E: UC16/UI01–07 | 7 | Yes | Historical 7 Pass; actual/planned/replay regressions passed | E, Expense/integrated tests | Tuấn Anh | Case-level integrated report PENDING |
| 2.17 | Confirm No Expense | Yes | E: UC17/UI01–04 | 4 | No | Historical 4 Pass; current NO_EXPENSE flow passed | E, Expense/integrated tests | Tuấn Anh | 1 design |
| 2.18 | Record Unexpected Expense | Partial; impact-scope UI absent | E: UC18/UI01–05 | 5 | Yes | Historical 4 Pass/1 Fail B003; service regression passed | E, unexpected-record tests | Tuấn Anh | Owner B003 UI fix/retest |
| 2.19 | View Expense History | Partial; current service orders oldest first | E: UC19/UI01 | 1 | No | Historical Fail B004; current history access/totals passed | E, service `list_records` | Tuấn Anh | 4 designs; newest-first requirement unresolved |
| 2.20 | Edit Expense Record | Yes | E: UC20/UI01–02 | 2 | No | Historical 2 Pass; correction regressions passed | E, `test_expenses.py` | Tuấn Anh | 3 designs |
| 2.21 | Delete Expense Record | Yes | E: UC21/UI01–03 | 3 | No | Historical 3 Pass; deletion regressions passed | E, `test_expenses.py` | Tuấn Anh | 2 designs |
| 2.22 | View Monthly Financial Overview | Yes | D: DB01–05 | 5 | Yes | Historical 5 Pass on `871aee6`; current Dashboard regression passed | D, `test_dashboard.py` | Thiện | KAN-66 traceability and new report PENDING |
| 2.23 | Adaptive Budget Recommendations | Partial; rule-based/read-only | R: F16-01–06 | 6 | Yes | Historical owner results; current F16 regression passed | R, `test_recommendations.py` | Khiêm | F16-06 early-signal evidence refers to unavailable newer source |
| 2.24 | Explain Recommendation and Respond | Yes, status-only decisions | R: F17-01–06 | 6 | Yes | Historical owner results; current stale/legacy/ownership tests passed | R, Recommendation tests | Khiêm | Retarget KAN-65 tests to pushed source |
| 2.25 | Data Completeness Check | Yes; approved threshold rule | R: F18-01–07 | 7 | Yes | Current threshold behavior passed; KAN-65 F18-01/05 expect a superseded contract | R, sufficiency regression | Khiêm | PENDING owner case revision; retain original evidence |
| 2.26 | Monthly Budget Review | Yes | R: F19-01–07 | 7 | Yes | Historical owner results; current review/feedback regression passed | R, Recommendation tests | Khiêm | New KAN-65 source/log cannot be treated as this build's execution |
| 2.27 | Customize Budget Plan | Yes | B: BP-14/15/16/17/18/19 | 6 | Yes | Historical 6 Pass; current CSRF/customization/integrated flow passed | B, `test_budget_customization.py` | Nhân | Current BP-14 case-specific screenshot retest PENDING |

## Totals

- **27 use cases; 15 meet five-case design coverage; 12 do not.**
- **104 UC-mapped designed cases:** Budget 41 + Expense 32 + Recommendations 26
  + Dashboard 5. There are **8 supplemental checks** (Budget 2, Expense 3,
  Workspace 3), giving **112 distinct IDs in the supplied owner case sets**.
- At least **46 additional UC-specific designs** are needed: UC1–4/7: 25;
  UC13: 3; UC14: 4; UC15: 4; UC17: 1; UC19: 4; UC20: 3; UC21: 2. Surplus
  cases on UC11/16/etc. cannot fill another UC's gap.
- B reports **43 cases: 42 Pass, 1 Fail**, plus 40 automated nodes and three
  browser-only cases. BP-05 passed at service level but failed browser input;
  its final workbook disposition remains Fail. Do not report all 43 passed.
- E has **35 cases including INT: 31 Pass, 4 Failed** (32 UC cases: 28/4).
  UI04's expected conflict and its reported retry-success outcome disagree;
  IT02 describes multi-tab scenarios, which do not prove simultaneous DB writes.
- R combines 16 KAN-58 IDs with 13 KAN-65 entries, three of which revise existing
  IDs: **26 distinct designs**. KAN-65 reports **13 Pass / 39 automated variants**,
  not 39 designed cases. Its 39-test log names `test_kan65_*` nodes absent from
  the pushed branch; this execution is not reproduced or transferred to Build 3.
- D reports **8 Pass** (five UC22 designs + three supplemental Workspace checks)
  on `871aee6961e3`; this is historical source evidence.

There is no honest combined historical Pass total for the integrated candidate:
sources use different dates, commits, rules and execution methods. Current
pytest/Chrome totals are recorded separately in [Build 3 verification](build3-verification.md).

## Original sources and missing inputs

All attachment IDs below were readable/downloaded on 26 November; owners'
original workbooks were not edited. Hashes are in
[the evidence inventory](evidence/pa4-build3/input-inventory.json).

| Ref | Jira source | Attachments reviewed |
|---|---|---|
| B | [KAN-52](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-52), [KAN-53](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-53), [KAN-63](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-63), KAN-71 | `10096/10097` initial workbook/plan; `10106–10109` updated plan/workbook/logs; `10121` **Budget_Planning_Test_Cases_PA4_v1.2.ods**; `10120` PA4 plan; `10118/10119` focused/full logs; `10116/10122` update/verification reports |
| E | [KAN-54](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-54), [KAN-55](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-55), KAN-64 | `10101` earlier case workbook; `10103` latest **KAN-54-test-cases template-v1.1.xlsx**; `10102` **KAN-55-test-report template-v1.1.xlsx**; no KAN-64 attachment |
| D | [KAN-56](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-56), [KAN-57](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-57), KAN-66 | `10111` usability review; `10112` **KAN57-Test-Report.xlsx**; `10113` report with embedded screenshots; KAN-56 ZIP `10110` listed but not needed for counts; no KAN-66 attachment |
| R | [KAN-58](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-58), [KAN-59](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-59), [KAN-65](https://clc-team-sv4ti5es.atlassian.net/browse/KAN-65) | `10098` **KAN-58-Sprint-4-Test-Cases.docx**; `10115` **KAN-65.docx**; `10125` coverage/report input; `10124` execution log; KAN-59 screenshot `10105` listed, not evidence of a new execution here |

Missing inputs: original unfilled Moodle/RUP master templates were not supplied
independently; owner-filled templates above are available. KAN-60's final Test
Plan and KAN-67's consolidated Test Report have no attachments in the inspected
issues. KAN-64/66 extensions and the source revision for KAN-65's newer tests are
missing. Repository pytest sources and `tests/f18_f19_.csv` were inspected; the
standalone CSV/demo cannot substitute for UC-traced current application cases.

## Handoff

**Nhân — KAN-60:** retain original IDs and revision history, add UC27 to the
denominator, coordinate the 46 design gaps, record the two approved Build 3
exceptions, and incorporate the BP-05 retest without erasing its historical Fail.

**Khiêm — KAN-67:** separate historical owner outcomes from the integrated run,
revise F18-01/05 expectations for the approved threshold contract, identify/push
the newer KAN-65 source, and complete the supplied report with the actual SHA,
environment and [three new session screenshots](build3-verification.md).
Do not import the older 39-test Pass claim into this candidate's results.

**Tuấn Anh — KAN-64/72:** add the 21 missing Expense designs, reconcile UI04 and
IT02 evidence, fix/retest B002/B003/B004 and provide a current branch.
**Thiện — KAN-66/73:** map DB01–05 to UC22, retain WS checks as supplemental,
retest mixed-language UI01 and provide a current branch. **Thịnh:** supply the
25 missing account/preferences designs, coordinate review and resolve release
gates before publication.
