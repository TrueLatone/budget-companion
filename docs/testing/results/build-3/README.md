# Build 3 testing workspaces

| Component | Use-case scope |
| --- | --- |
| [Account and period](account-and-period/) | UC01–UC07, UC31 (planned) |
| [Budget planning](budget-planning/) | UC08–UC12, UC27–UC29 (UC28/UC29 proposed) |
| [Expense and check-in](expense-and-checkin/) | UC11–UC21, including the schedule handoff |
| [Dashboard](dashboard/) | UC22, UC30 (comparison unavailable) |
| [Recommendation](recommendation/) | UC23–UC26 |
| [Integration](integration/) | The use cases exercised by each cross-component flow |

Each workspace contains a results CSV, execution report, defect log and directories for reviewed evidence. Use the [shared workflow and status definitions](../../README.md) and the [component testing scope](../../../pa4-test-coverage-matrix.md) when planning work.

For the official PA4 Test Report, collect the component reports, result rows and actual testing-session screenshots for the selected Build 3 commit. Reconcile totals by unique case ID for the chosen run, resolve overlaps such as UC11–UC12 across components, and keep retest history with its original commit and outcome. Summarize the build, environment, scope, status totals, open defects, evidence and limitations. Keep coverage counts for designed cases distinct from counts of pytest nodes or repeated runs.

Earlier runs are summarized in [Build 3 verification](../../../build3-verification.md). Original reports, screenshots and other raw evidence are maintained separately in restricted project storage. Cite the original run and source revision when referencing them in the official report.
