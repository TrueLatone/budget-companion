# Changelog

Dates use Asia/Bangkok (UTC+07). Build names describe milestones; they do not
imply that a GitHub Release or tag was published.

## Build 3 integration candidate — 26 November 2026

- Preserve Nhân's original `1656fc9` (KAN-71) and `d6cc3f1` (KAN-63), submitted
  in [PR #14](https://github.com/TrueLatone/budget-companion/pull/14): revised
  Budget setup, whole-thousand planning for new periods, customization, original
  schedule views, automatic confirmation/scheduling and Budget tests.
- Preserve Khiêm's `eaa30bd`, submitted in
  [PR #12](https://github.com/TrueLatone/budget-companion/pull/12): F18 sufficiency
  gating, stale ACCEPT protection and monthly feedback presentation. Merge
  `3092548` retains both members' histories.
- `bdb4825` (KAN-70) fixes omitted category controls rejecting valid custom
  expenses and removes migration recalculation of existing funding. Adds
  disposable migration-preservation and integrated acceptance regressions.
- The project lead approved automatic scheduling and threshold-based incomplete
  transaction handling on 26 November, superseding those two v1.1 contract clauses
  for this candidate. See [verification](docs/build3-verification.md).
- KAN-72/KAN-73 branches are missing; existing Expense defects and designed-case
  gaps remain. Main merge and Beta publication are pending review and owner work.

## Build 2 Core Alpha — retrospective, planned 15 November 2026

The latest main source before the milestone was `871aee6`, from 7 November:

- [PR #8](https://github.com/TrueLatone/budget-companion/pull/8), merge `df4d7eb`:
  KAN-38 recommendation logic/UI improvements (6 November).
- [PR #9](https://github.com/TrueLatone/budget-companion/pull/9), merge `8e1c75b`:
  KAN-39 recommendation experience (7 November).
- [PR #10](https://github.com/TrueLatone/budget-companion/pull/10), merge `1bec80c`:
  KAN-32 separate MANUAL draft, fixed P0, P1 minima, stale-form checks
  (7 November).
- [PR #11](https://github.com/TrueLatone/budget-companion/pull/11), merge `871aee6`:
  KAN-34/35 duplicate confirmation and Expense correction safeguards
  (7 November).

This documentation was prepared on 26 November. It does not backdate a Release.
See the [retrospective](docs/build2-retrospective.md) for evidence and limitations.

## Build 1 integration — 3 November 2026

- [PR #7](https://github.com/TrueLatone/budget-companion/pull/7), merge `4efb8f8`:
  authenticated Budget, Expense, Workspace/Dashboard and read-only analysis.
- Historical verification source `3d742a9`: 458 passed, as recorded at that time.
  [Original Build 1 evidence](docs/build1-verification.md) remains unchanged.
