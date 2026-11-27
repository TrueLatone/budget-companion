# Functional and quality requirements

This is the public technical summary of Vision v1.2 (27 November 2026). The Vision assigns priorities, and the Use-Case Model supplies the labeled links. A dash in **Model UCs** marks a feature without an explicit model link. Prose links and mapping gaps are explained in the [use-case index](use-case-index.md#traceability-gaps). See the [baseline review](baseline-review.md) for discrepancies.

| ID | Feature | Vision priority | Model UCs | Build 3 status | Scope or implementation boundary |
| --- | --- | --- | --- | --- | --- |
| F01 | Income setup | MUST | UC05, UC08 | Verified | Month-owned available funds. New-month inputs use the configured planning unit. |
| F02 | Expense prioritization | MUST | UC08 | Verified | P0/P1/P2, exact P0 reservations and user-defined P1 minima. |
| F03 | Custom expenses | MUST | UC08 | Partial | Planned/custom items and category creation work. Standalone category rename and organization are absent. |
| F04 | Minimum expense suggestions | SHOULD | — | Planned | Setup offers expense presets. Essential-cost reference ranges are absent. |
| F05 | Budget plan generation | SHOULD | UC09, UC29 | Verified core · proposed extension | Deterministic Saving/Balanced/Lifestyle and shortfall checks. UC29 adds a proposed optional target and maximum feasible savings. |
| F06 | Budget customization | MUST | UC10, UC27, UC28 | Verified core · proposed extension | Separate unconfirmed MANUAL proposal with protected P0/P1. UC28 adds proposed previous-month reuse. |
| F07 | Daily, weekly and monthly plans | MUST | UC11, UC12, UC13 | Verified core | Expense views are Day/Month/Year with weekly periods. Budget also has a separate read-only Week schedule view. |
| F08 | Expense scheduling | MUST | UC14 | Divergent | Repeat-safe schedule action exists. The Vision calls for explicit creation after confirmation, while current confirmation creates the initial tasks. UC11 is the prose trace. |
| F09 | Smart expense check-in | MUST | UC15, UC16, UC17 | Verified | Actual, eligible planned amount, or explicit no expense. Pending/unrecorded remains Unknown. |
| F10 | Actual expense recording | MUST | UC16, UC18, UC20, UC21 | Verified core | Owned purchase creation, edits and deletion, with distinct API and browser repeat handling. |
| F11 | Expense adjustment | MUST | UC18 | Partial | Unexpected spending is recorded. The create form lacks the optional impact-scope selector. Adjusting confirmed allocations or limits is later work. |
| F12 | Recurring expense tracking | MUST | UC14 | Partial | Due dates and self-declared payment status exist at the service level. The user-facing control is missing. |
| F13 | Spending history | MUST | UC19, UC20, UC21 | Divergent · source wording error | History and a date filter exist. The F13 description repeats F11, and UC19 requires newest-first within the selected month. |
| F14 | Spending pattern analysis | SHOULD | — | Partial | Rule-based category deviations exist under F16. No independent repeated-pattern workflow is traced. |
| F15 | Personalized expense forecasting | SHOULD | — | Planned | No verified spending forecast workflow. |
| F16 | Adaptive recommendations | MUST (basic) | UC23 | Verified | Deterministic signals, baseline guidance, and gated read-only personalized recommendations. |
| F17 | Explainable recommendations | MUST | UC24 | Verified core · proposed extension | Reasons and observations, HTML dismissal and status-only decisions. Applying eligible adjustments is proposed later. |
| F18 | Data completeness | MUST | UC25 | Verified | Eligibility gates and invalid-record handling. See the [readiness rules](#analysis-rules). |
| F19 | Monthly budget review | MUST (basic) | UC26 | Verified | Reliable closed-month results when fully resolved. Optional feedback changes metadata. |
| F20 | Feedback-based adaptation | SHOULD | — | Planned | Feedback is stored. No later-period adaptation is implemented. |
| F21 | Shared household setup | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F22 | Shared expense recording | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F23 | Expense splitting | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F24 | Member contribution tracking | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F25 | Settlement tracking | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F26 | Shared expense history | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F27 | Monthly group summary | LATER | — | Out of Build 3 scope | Later shared-living extension. |
| F28 | Budget overview | MUST | UC22 | Verified core | Selected owned month, totals, category breakdown and unknown remaining amount when incomplete. |
| F29 | Plan versus actual comparison | MUST | UC22 | Partial | Monthly priority totals and separate reliable F19 review work. Per-expense Dashboard progress and daily goals are missing. |
| F30 | Spending statistics | MUST | UC22, UC30 | Partial | Selected-month category breakdown is implemented. Trends across calendar months are absent. |
| F31 | Month-over-month comparison | MUST | UC22, UC30 | Planned · MUST gap | Same-period comparison and six-month history need implementation and a defined completeness policy. |
| F32 | Budget alerts | SHOULD | — | Partial | Over-budget task indicators exist. Proactive near-limit alerts have no dedicated UC or workflow. |
| F33 | Payment reminders | MUST | UC31 | Planned · MUST gap | In-app upcoming unpaid reminders. Delivery by push is outside UC31. |
| F34 | Monthly spending report | MUST | UC26 | Verified core | Dashboard and F19 provide on-screen summaries. Vision also links UC22. No export is required. |
| F35 | Registration and login | MUST | UC01, UC02, UC03 | Verified core | Registration, sign-in and sign-out tested. Remember-me persistence is source-reviewed without a dedicated end-to-end check. |
| F36 | Profile management | MUST | UC04 | Planned · MUST gap | No user-facing profile or budgeting-preference write flow. |
| F37 | Budget period management | MUST | UC05, UC06 | Verified | Owned calendar-month creation and selection, tracking start, and protected funds editing. |
| F38 | Notification preferences | SHOULD | UC07 | Planned | No saved alert/reminder category settings workflow. Notification delivery is separate. |

## Key business rules

- Budget months are owned calendar periods. Financial amounts use integer VND. P0 expenses are funded exactly, P1 floors are protected, and infeasible plans are rejected. Allocations and planned savings conserve available funds.
- Proposed UC28 copies editable planned-expense settings from the same user's preceding confirmed month into an empty destination. It leaves funds, savings targets, schedules and spending records in their original month.
- Proposed UC29 permits an optional savings target. It reduces P2 first and then P1 surplus above the protected minimum. An infeasible target must show the maximum achievable savings. Manual changes must preserve the target for confirmation.
- F08 requires an explicit Create / Verify action after confirmation. The current implementation confirms and generates tasks together. Track this discrepancy against UC10, UC11 and UC29.
- A task with no submitted check-in remains Unknown. An explicit `NO_EXPENSE` confirms zero without creating a purchase. `FUNDS_ADDED` is excluded from spending totals. Setting payment status only records the user's declaration.
- Purchase retries with the same key and payload are repeat-safe. Browser repeats present the saved purchase for confirmation or dismissal. Any permitted additional purchase is explicit and itself repeat-safe.
- F31 compares recorded spending through corresponding calendar days. The v1.2 requirement withholds the difference when comparison data is incomplete and allows browsing six months at a time. The comparison design distinguishes spending through the matching day from complete full-month totals. UC30 still needs short-month and comparison-completeness rules.

## Analysis rules

- F16 uses deterministic comparison by category and priority, with review signals at or above 110% and at or below 80% of the relevant limit. P0 is protected. An early signal remains provisional. Personalized guidance requires F18 eligibility.
- F18 requires at least 10 valid actual purchases, three recorded categories, at least 30 inclusive days between the first and last valid purchase, and at least 80% completeness. It also requires tracking to have started, a confirmed plan, a complete schedule, and no overdue or inconsistent tasks. Invalid purchases are reported and included in the completeness denominator. Confirmed zero resolves a task without adding a purchase, category, or transaction date. A short tracking period can fail the 30-day gate.
- F17 keeps decisions financially read-only in Build 3. HTML can dismiss. Eligible API acceptance changes the stored decision status. Stale or unsupported proposals conflict, and repeat dismissal is safe.
- F19 reliable month-end reporting has its own criteria. The month must be closed and fully resolved, with a confirmed plan, ready schedule, and consistent, complete records. Otherwise the review shows valid observed spending and withholds unsupported plan variance and remaining amounts. Ratings and comments are optional metadata.

## Non-functional requirements

The model has no NFR labels. These are **review mappings** from the Vision to representative use cases, evidence, and verification gaps.

| ID | Vision priority | Expectation | Review trace and status |
| --- | --- | --- | --- |
| N01 | High | Desktop and mobile browser compatibility with documented supported versions | UC08, UC15–UC18, UC22, UC23. Chrome desktop and mobile viewport checks were recorded. Other browsers and physical devices remain unverified. |
| N02 | High | Core setup and simple check-in around 360 px with no horizontal scrolling | UC08, UC15–UC18. Existing browser evidence used a 390 px mobile viewport. The 360 px target remains unverified. |
| N03 | Medium | Dashboard loads in about three seconds on a documented demo dataset | UC22. Dashboard implementation exists. No timed acceptance measurement was found. |
| N04 | High | Consistent totals and separate Unknown and confirmed zero states | UC11, UC15–UC19, UC22, UC25–UC26. Verified in `test_expenses.py`, `test_dashboard.py` and `test_recommendations.py`. |
| N05 | High | Clear failures, repeat-safe API saves and explicit duplicate confirmation for web forms | UC10–UC11, UC16, UC18, UC24. Covered by expense and recommendation regressions. The UC16 alternative flows need wording clarification. |
| N06 | High | Owned data access and mutation | UC01–UC07 and every authenticated flow, especially UC05–UC06, UC16, UC22 and UC24–UC26. Covered by account, ownership and CSRF regressions on the tested stack. |
| N07 | High | Protect P0/P1 constraints and reject shortfalls | UC08–UC10, UC27, proposed UC29. Core constraints are verified. The new-month planning unit is stricter than the unrestricted integer wording. |
| N08 | High | Explainable recommendations and no Build 3 financial effects | UC23–UC26. Recommendation regressions verify read-only effects and stale/unsafe decision handling. |
| N09 | High | Manual expense entry and user-declared payment status | UC14, UC16, UC18, UC31. Manual expense and service-level payment status are supported. Payment processing and invoice validation are outside scope. |
| N10 | Medium | Understandable status text with cues beyond color | UC13–UC19, UC22, UC25–UC26. Text labels are present. Usability and broader accessibility acceptance remain unverified. |
| N11 | Medium | Setup, tests and basic usage documentation | Applies across use cases. Instructions exist in the [project README](../../README.md) and [pytest guide](../../tests/README.md). |
| N12 | Medium | Calendar months, VND and clearly labeled synthetic demo data | UC05–UC06, UC08–UC09, UC16, UC22 and UC30. Calendar and VND invariants have regression coverage. The UC30 workflow is absent. Review labeling for each demo dataset. |
