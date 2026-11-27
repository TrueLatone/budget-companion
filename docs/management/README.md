# Project roadmap and release scope

The Software Development Plan v1.2 is dated 27 November 2026. The original plan, weekly reports and project management evidence are in restricted project storage.

| Sprint | Target | Planned outcome |
| --- | --- | --- |
| 1 · 5–18 Oct 2026 | Initial documentation on 18 Oct | Initial plan, Vision, and prototypes. |
| 2 · 19 Oct–1 Nov 2026 | Build 1 demo on 1 Nov | Initial budget and check-in flow with basic analysis. The documented integration landed through PR #7 on 3 Nov. |
| 3 · 2–15 Nov 2026 | Build 2 Core Alpha on 15 Nov | Plan, record, monitor and basic review. The milestone is documented retrospectively. |
| 4 · 16–29 Nov 2026 | Build 3 Beta and PA4 on 29 Nov | Integrate and stabilize core flows, update architecture and UI, design cases for all documented use cases, execute implemented cases, and prepare a tested release. |
| 5 · 30 Nov–13 Dec 2026 | Build 4 course release candidate on 13 Dec | Resolve high-impact defects, deliver agreed scope, complete regression and usability checks, and prepare the final demonstration. |

## Build 3

The integrated individual workflow covers account access, calendar-month budgeting, deterministic plans and customization, schedule/check-in, the core Dashboard, and rule-based read-only recommendations and review. The [Build 3 verification summary](../build3-verification.md) records the integrated candidate and earlier evidence. Budget setup through confirmation and Expense check-in through Dashboard update are the two core acceptance flows. Compare their actual schedule behavior with the v1.2 [requirements review](../requirements/baseline-review.md).

The Beta target requires a tested source revision, release notes with limitations, a system test report with actual evidence, and a published release. PA4 also requires updated architecture and UI documentation and test designs covering UC01–UC31. The automated suite and a merge to `main` are milestones. The release and PA4 acceptance still require their own evidence.

## Build 4 and later

- **Proposed Build 4 extensions, subject to approval** include previous-month planned-expense reuse (UC28/F06) and optional monthly savings targets (UC29/F05). Resolve the schedule handoff before confirming the savings-target design.
- **Priority gaps for release triage** include F31/UC30 comparison, F33/UC31 in-app reminders, F36/UC04 profile changes, the unfinished Dashboard workflow, and Build 3 integration discrepancies. The Vision's MUST priorities stand. The plan does not assign a confirmed delivery date to each gap.
- **Other later proposals** include richer History filters, proactive near-limit alerts, feedback-based adaptation, forecasting, and user-confirmed future limit changes with P0/P1 and funding constraints. External AI hints and browser push would need separate scope decisions.
- **Outside the initial individual scope** are shared households and settlement (F21–F27), bank connections, payments, invoice verification, automatic imports, offline-first mobile, and multi-currency support. The current product uses calendar months and VND.

See the [requirements and traceability index](../requirements/README.md) and [software changelog](../../CHANGELOG.md).
