# Use-case index and Feature–UC mapping

The Use-Case Specification v1.2 (27 November 2026) includes all 31 use cases in its textual index and embedded model. The feature labels below come from the model. Build 3 status refers to the implementation and evidence on the [reviewed source baseline](../build3-verification.md). A passing regression covers its exercised behavior and does not certify the whole case.

| UC | Use case | Model features | Build 3 status | Source and coverage |
| --- | --- | --- | --- | --- |
| UC01 | Register an account | F35 | Verified | Email normalization, unique signup and password validation. `test_accounts.py`. |
| UC02 | Log in | F35 | Verified core | Authentication and safe workspace redirects are covered. The remember-me checkbox sets session persistence, which has no dedicated end-to-end check in the reviewed suite. |
| UC03 | Log out | F35 | Verified | Session clearing and protected-page behavior. `test_accounts.py`. |
| UC04 | Update profile and budgeting preferences | F36 | Planned · MUST gap | The account page is display-only for profile and preferences. |
| UC05 | Create a monthly budget period | F01, F37 | Verified | Owned calendar-month creation, starting funds, tracking start and duplicate prevention. `test_budget_periods.py`. |
| UC06 | View or switch budget period | F37 | Verified | Owned workspace context and rejection of inaccessible periods. `test_budget_periods.py`, `test_dashboard.py`. |
| UC07 | Manage notification preferences | F38 | Planned | No preference form or save workflow. UC07 does not deliver alerts. |
| UC08 | Set up a monthly budget | F01, F02, F03 | Verified core | Suggested and custom entries, priority/minimum validation and locked setup. `test_budgets.py`, `test_pa4_integration.py`. |
| UC09 | Generate budget plans | F05 | Verified core | Three deterministic proposals, protected minima and exact funds conservation. `test_budget_rules.py`. Optional savings targets are UC29. |
| UC10 | Select and confirm a budget plan | F06 | Divergent | Ownership, MANUAL snapshot and locking are verified. Live confirmation also generates the schedule. `test_budget_customization.py`, `test_expenses.py`. |
| UC11 | Generate spending schedule | F07 | Divergent handoff | The explicit route verifies or repairs schedules with ownership, exact splits and safe retries. Current confirmation normally creates the initial schedule first. `test_expenses.py`. |
| UC12 | View planned spending schedule | F07 | Verified core | Original scheduled limits, clipped weeks and monthly amounts. `test_sprint4_budget_planning.py`. |
| UC13 | View expense plan | F07 | Verified core | Day, Month and Year expense views with weekly periods and Unknown/confirmed zero behavior. `test_expense_presentation.py`, `test_expenses.py`. |
| UC14 | View task due dates | F08, F12 | Partial | Due dates and payment-status behavior have coverage. The Expense view lacks a payment-status edit control. `test_expenses.py`. |
| UC15 | Check in a planned expense | F09 | Verified | Late and recorded-state handling, future rejection, and result routing. `test_expenses.py`. |
| UC16 | Record expense for planned task | F09, F10 | Verified core · wording conflict | Actual/planned modes, payload-checked retries and browser duplicate review are covered. The baseline alternatives conflate some of these paths. |
| UC17 | Confirm no expense | F09 | Verified | Explicit zero without a record, safe retries and protection of existing purchases. `test_expenses.py`. |
| UC18 | Record unexpected expense | F10, F11 | Partial | Validation, duplicate behavior and optional scope handling exist in the service. The creation form lacks a scope selector. `test_expenses.py`. |
| UC19 | View expense history | F13 | Divergent | Date-range view and totals are covered. Current History sorts oldest-first and can span multiple owned months. Newest-first and selected-month boundaries are required by UC19. |
| UC20 | Edit expense record | F10, F13 | Verified | Owned edits, dates, amounts, eligible fields and updated totals. `test_expenses.py`. |
| UC21 | Delete expense record | F10, F13 | Verified | Deletion refreshes totals and returns a task to PENDING after its last transaction is removed. `test_expenses.py`. |
| UC22 | View monthly financial overview | F28, F29, F30, F31 | Partial | Verified current-month summary, donut, priority progress and recent spending. The v1.2 category drill-down, trend and per-expense Month/Day goal workflow are absent. |
| UC23 | Adaptive budget recommendations | F16 | Verified | Rule-based guidance, provisional early signals and persisted read-only recommendations gated by readiness. `test_recommendations.py`. |
| UC24 | Explain recommendation and respond | F17 | Verified | HTML dismisses. Eligible API ACCEPT records status only. Stale or unsafe proposals conflict. `test_recommendations.py`. |
| UC25 | Check data completeness | F18 | Verified | Thresholds, schedule readiness and data integrity checks. `test_recommendations.py`. |
| UC26 | Review monthly budget | F19, F34 | Verified | Closed-month reliability and optional feedback, independent of personalization thresholds. `test_recommendations.py`. |
| UC27 | Customize budget plan | F06 | Verified | Separate MANUAL proposal, exact P0 and P1 protection, stale-save checks and planned savings as the remainder. `test_budget_customization.py`. |
| UC28 | Reuse prior-month planned expenses | F06 | Proposed Build 4 | No copy workflow for all or recurring-only planned expense settings. |
| UC29 | Allocate to a monthly savings target | F05 | Proposed Build 4 · conflict | No user-entered target or maximum-feasible result. Confirmation/scheduling step conflicts with UC10/UC11. |
| UC30 | Compare monthly spending | F30, F31 | Planned · MUST gap | No dedicated same-period comparison or six-month history view on main. |
| UC31 | View payment reminders | F33 | Planned · MUST gap | No in-app reminder workflow. The reminder window is unspecified. |

## Model relationships

- UC16 and UC17 extend UC15. UC20 and UC21 extend UC19.
- UC27 extends UC10. The proposed UC28 and UC29 extend UC08 and UC09, respectively.
- UC30 extends UC22. UC23 includes UC25, and UC24 extends UC23.
- UC10 and UC11 appear separately, without a mandatory include. The UC11 prose identifies confirmation as the prerequisite for the later schedule action.

## Traceability gaps

- The diagram labels UC11 and UC12 with F07 and labels UC14 with F08/F12. The Vision's F08 and the UC11 flow directly describe schedule generation. F08 → UC11 is a prose link that should be reconciled with the diagram. UC12 also views generated schedule data.
- F13 labels UC19–UC21 in the model. The Vision's F13 description duplicates unexpected spending from F11. The History behavior above follows UC19 and its extensions, with the incorrect Vision text recorded as an open issue.
- The model links F34 to UC26. Vision F34 also explicitly references UC22. F30/F31 link to UC22 and UC30 in both the model and prose, although their Build 3 implementation is incomplete.
- F04, F14, F15, F20, F21–F27 and F32 have no dedicated model label. UC08's minimum input does not specify reference ranges. UC23 covers F16 category observations and UC26 records feedback, leaving forecasting and future adaptation untraced. UC16/UC22 give over-budget context but no proactive alert flow. F21–F27 belong to a later shared-living extension.
- N01–N12 are cross-cutting and are not diagram links. See [quality requirement traceability](functional-requirements.md#non-functional-requirements) for representative review mappings.

See the [baseline review](baseline-review.md) for source conflicts and the [PA4 component testing scope](../pa4-test-coverage-matrix.md) for system-test planning.
