# Build 2 Core Alpha retrospective — KAN-68

Prepared **26 November 2026**, Asia/Bangkok. Planned Core Alpha milestone:
**15 November 2026**, consistent with the supplied PA2 Project Plan v1.1.

## Actual source baseline

The latest main commit before 15 November was
`871aee6961e3f2c94f9881feb02b12bfe2afb043`, committed/merged on **7 November**.
Fetching origin on 26 November returned the same main SHA. Build 3 feature
commits dated 21/24 November are excluded from this retrospective.

Build 1 entered main through [PR #7](https://github.com/TrueLatone/budget-companion/pull/7)
on 3 November (`4efb8f8`). Subsequent verified source history:

| Change | Original source / merge | Date (UTC+07) | Actual behavior |
|---|---|---|---|
| KAN-38, PR #8 | `710f869` / `df4d7eb` | 6 November | Recommendation improvements |
| [KAN-39, PR #9](https://github.com/TrueLatone/budget-companion/pull/9) | `9ca7dc1`, `1790084` / `8e1c75b` | 7 November | Recommendation experience, safe status-only ACCEPT |
| [KAN-32, PR #10](https://github.com/TrueLatone/budget-companion/pull/10) | `203178f` / `1bec80c` | 7 November | Independent MANUAL draft, fixed P0, P1 floors, conservation and stale-form checks |
| [KAN-34/35, PR #11](https://github.com/TrueLatone/budget-companion/pull/11) | `c7f23a2` / `871aee6` | 7 November | Duplicate-purchase review/confirmation, history corrections and task/Dashboard consistency |

PR #10 records selective adaptation of Nhân's `aa011ac`; PR #11 records selective
adaptation from Tuấn Anh's branch. These historical integration commits already
existed before this task. This task does not reattribute or rewrite them.

## Evidence and limits

Git history and GitHub PR metadata support the source dates and included changes.
The supplied PA3 `Changes.md` was reviewed on 15 November and records document
changes, including Use-Case Specifications v1.1 dated 14 November; it explicitly
does not establish that every described feature was implemented.

The historical [Build 1 verification](build1-verification.md) records 458 passing
tests against `3d742a9`. That total is not a new execution against Build 2.
KAN-57's 22 November report names `871aee6961e3`: five Dashboard cases and three
Workspace checks passed, plus an owner-reported 23-test Dashboard run. KAN-55's
21 November Expense workbook records four UI/history failures. These are later
owner observations, not evidence that those results existed on 15 November.
See the [source inventory and coverage assessment](pa4-test-coverage-matrix.md).

Build 2 retained separate confirmation and explicit schedule creation, one-VND
integer planning, read-only financial recommendations, nullable unknown totals,
and the 13-entity schema at Alembic `19a01e000002`. Funds additions, automatic
reallocation, bank/LLM integration, alerts and cross-month reporting were not
completed. Live PostgreSQL staging and full browser coverage were not established
by the available milestone evidence.

## Publication status

Build 2 is a **retrospectively documented source milestone**. Its README still
identified Build 1 when this task began. No Build 2 Release is claimed or
backdated here; no historical release tag/URL was supplied. Current tag/release
inspection is recorded in the Build 3 evidence. This retrospective is distinct
from any future genuine published GitHub Release.

Reproduce the source-history boundary with:

```powershell
git log origin/main --first-parent --date=iso-strict --format='%H %aI %s'
git show --stat 871aee6
git log origin/main --before='2026-11-16T00:00:00+07:00' -1 --oneline
```
