# Build 3 integration verification — KAN-70 / KAN-68

Verified **26 November 2026**, Asia/Bangkok (UTC+07). PA4 is due 29 November.
Status: **tested integration candidate; main merge and Beta Release pending**.
Review PR: [#15](https://github.com/TrueLatone/budget-companion/pull/15) — open
as a draft; no merge or release has been performed.
Automated acceptance passes; unresolved owner defects, formal case coverage and
review gates prevent declaring the PA4 package complete.

## Source and history

- Initial/fetched main: `871aee6961e3f2c94f9881feb02b12bfe2afb043`.
- Verified integrated runtime source: **`bdb4825f193b691a226ede2254434cd843eccb32`**.
- Branch: `integration/pa4-build3`. Documentation/evidence is added in one
  subsequent `docs(KAN-68)` commit; runtime and test source remains at the SHA above.
- Working tree was clean before branch creation; `main` was not modified.
  No force-push, reset, squash, amend or authorship rewrite was used.

| Owner / branch | Disposition | Original commits / PR |
|---|---|---|
| Nhân — `feature/KAN-71-KAN-63-budget-planning-and-system-tests` | Fast-forwarded from latest main; focused verification passed | Danh Dao's `1656fc9`, `d6cc3f1`; [PR #14](https://github.com/TrueLatone/budget-companion/pull/14) |
| Tuấn Anh — KAN-72 | **WAITING FOR FEATURE OWNER**; no new branch after fetch | Old `feature/KAN-34-AND-KAN-35` was not blindly merged; prior adaptation is already in PR #11 |
| Khiêm — `feature/KAN-59` | Merged cleanly; both members' overlapping route/test changes retained | TietTrongKhiem's `eaa30bd`; [PR #12](https://github.com/TrueLatone/budget-companion/pull/12) |
| Thiện — KAN-73 | **WAITING FOR FEATURE OWNER**; no new branch | Old `feature/UI` is 29 commits behind / 3 ahead of main and was skipped |

New task-authored commits are one ordinary merge, `3092548`, and one focused
implementation commit, `bdb4825` (`fix(KAN-70)`). One consolidated documentation
commit accompanies this report. Original feature history and authors are intact.

GitHub initially showed open PRs #14, #12 and older #5. PR #5 is the historical
Recommendation prototype, not an additional Build 3 branch. Review lists on
#12/#14 were empty at inspection. PR #9/#10/#11 and source history establish
the [Build 2 retrospective](build2-retrospective.md); no Release is backdated.

## Approved contracts

The supplied PA3 **G10-UCS-v1.1 (14 November)** has 27 use cases. It differs from
the pasted request's v1.0 interpretation: §2.10/11 specifies separate scheduling,
and §2.25 requires no incomplete transactions. The project lead explicitly
answered **“Approve automatic scheduling for Build 3”** and **“Approve v1.0
threshold-based rule”** on 26 November. These are the two accepted Build 3
exceptions, documented in [API contracts](api-contracts.md). They do not silently
rewrite the submitted requirements or the SAD; owner document reconciliation
remains a handoff item.

Confirmation uses one locked transaction: saved plan validation → CONFIRMED →
task creation → commit. Retries preserve allocations, task IDs, check-ins and
current limits. Injected task-insert failures roll back both confirmation and
schedule. Authentication, MANUAL fingerprints and global CSRF remain enforced.

F18 still requires 10 valid transactions, three categories, 30 inclusive days,
80% completeness, a confirmed plan, complete schedule, started tracking and no
overdue/inconsistent completed tasks. Incomplete transactions remain issues and
count in the denominator, but do not override passing sufficiency gates.
Guidance/decisions do not alter allocations, funds, savings or limits. Safe
current ACCEPT changes status only; stale/unsafe proposals return 409.

## Environment and actual commands

Windows 11, CPython **3.13.14**, pytest **9.2.0**, Flask **3.1.3**, SQLAlchemy
**2.1.9**, Alembic **1.20.1**, Flask-Migrate **4.1.0**, Flask-WTF **1.3.0**.
Full package versions are in [environment.txt](evidence/pa4-build3/environment.txt).
The old `.venv` points to a removed temporary interpreter; verification used an
isolated environment under ignored `instance/pa4-tools/venv`. A preliminary
Budget run used the working installed Python; its environment is separately
recorded and its totals are not substituted for the final integrated run.
No GitHub Actions workflow is present, and the pushed source's combined GitHub
status query returned no statuses. Results here are local verification, not CI.

All tests use in-memory/temporary SQLite or offline PostgreSQL SQL. No live
Supabase migration, seed, reset or production write was performed. No authorized
PostgreSQL staging environment was available. Chrome used a fresh context and
a disposable migrated database served on a loopback ephemeral port.

From repository root, the final suite command was:

```powershell
$env:PYTHONUTF8='1'
& 'instance\pa4-tools\venv\Scripts\python.exe' -m pytest -q -o cache_dir=instance/pa4-evidence/pytest-cache --junitxml=instance/pa4-evidence/full-pytest.xml *> instance/pa4-evidence/full-pytest.log
```

The same Python ran focused Recommendations/Dashboard and new acceptance tests:

```powershell
& 'instance\pa4-tools\venv\Scripts\python.exe' -m pytest -q tests/test_recommendations.py tests/test_dashboard.py -o cache_dir=instance/pa4-evidence/pytest-cache --junitxml=instance/pa4-evidence/recommendations-focused.xml
& 'instance\pa4-tools\venv\Scripts\python.exe' -m pytest -q tests/test_pa4_integration.py -o cache_dir=instance/pa4-evidence/pytest-cache --junitxml=instance/pa4-evidence/pa4-flows.xml
```

| Execution | Actual outcome | Evidence |
|---|---|---|
| Nhân focused, original feature before integration fixes | **71 passed, 53 warnings, 16.79s** | `nhan-focused.log/xml`; original test source `d6cc3f1` |
| Added defect probes before fixes | **4 failed, 1 passed, 28 warnings, 1.14s** | `reproduced-defects.log/xml`; two changed funding values, two valid browser-form failures |
| Budget/migration/customization/flow focused after fixes | **128 passed, 116 warnings, 26.84s** | `budget-fixed.log/xml`; before KAN-59 merge |
| Integrated Recommendations and Dashboard | **93 passed, 20 warnings, 62.30s** | `recommendations-focused.log/xml` |
| New preservation and combined acceptance flows | **6 passed, 40 warnings, 2.36s** | `pa4-flows.log/xml` |
| **Full suite on committed `bdb4825`** | **564 passed, 0 failed/errors/skipped, 284 warnings, 283.03s** | [Full log](evidence/pa4-build3/full-pytest.log), [JUnit XML](evidence/pa4-build3/full-pytest.xml) |
| JavaScript | **7 files passed `node --check`** | `static-checks.txt` |
| Whitespace / conflicts | `git diff --check` passed; no unresolved conflicts | `static-checks.txt` |
| Real HTTP application startup | Passed; authenticated Chrome flow served by Werkzeug | `browser-results.json` and screenshots |

Focused totals overlap and must not be added. The full suite contains the six
new regressions and both main flows. Warnings are Flask-Migrate engine-access,
WTForms tuple-choice and Python SQLite adapter deprecations plus SQLite
expression-index reflection warnings; they are not assertion failures.
Raw logs, runner and commands are in [the evidence folder](evidence/pa4-build3/).

## Migration and data preservation

One Alembic head: **`19a01e000003`**. Existing migration tests verify clean
upgrade, earlier foundation upgrades, downgrade/upgrade, metadata parity and
offline PostgreSQL SQL generation. New tests upgrade a populated Build 2 schema
(`19a01e000002`) containing a confirmed plan, non-thousand allocation, modified
task current limit and actual expense. Every pre-existing column/row in the
13-table model is compared before/after, including IDs and audit timestamps.
Funds below/equal/above the original 5,000,000-VND confirmed total are tested.
Legacy `planning_unit=1`, new-period `1000`, and repeated upgrades pass.

The original feature migration changed funding **4,000,000 → 5,000,000** and
**6,000,000 → 5,000,000** in those disposable fixtures. The KAN-70 fix removes
that recalculation; no financial correction is inferred from saved allocations.
A database already upgraded using the earlier feature migration requires its
owner's backup/audit comparison; re-upgrade cannot recover its previous funds.
No such external database was inspected or changed here.

## Acceptance flows on the same integrated source

**Flow A — passed:** real registration/login with CSRF → owned monthly period →
suggested expenses plus custom Entertainment without hidden category controls →
three persisted strategies → compare → customize a separate MANUAL draft →
preserve P0 and P1 floors, recalculate savings → confirm → automatic schedule.
The 7,000,000-VND fixture retains exact allocation+savings conservation and 40
unique tasks. Confirmation replay creates no second task set. New-period
planning amounts/limits are multiples of 1,000; real purchases retain single-VND
precision. Existing customization tests also cover stale forms and concurrent
saves, and Expense tests cover transactional scheduling failure/retry.

**Flow B — passed:** generated schedule → actual **12,785 VND** and explicit
NO_EXPENSE → identical replay creates one purchase, changed replay returns 409 →
History retains the purchase → Dashboard reports observed spending **12,785**,
remaining **Unknown** while other check-ins are missing → Recommendations report
one valid purchase and insufficient actual data. Factory restart/re-upgrade
preserves tasks, allocations, record and NO_EXPENSE. The existing migrated
cross-module test also exercises ten purchases/three categories/31 days and a
sufficient, read-only Recommendation path. Ownership and missing-CSRF checks
pass in the full suite. These are synthetic disposable test-account records.

## Browser/device evidence

**Chrome 158.0.8127.38**, headless on Windows, Playwright **1.65.2**. Desktop
**1440×1000**, mobile viewport **390×844**, timezone Asia/Bangkok. This is Chrome
viewport emulation, not physical Android/iOS/Safari testing.
Four routes (`/budget`, `/expenses`, `/dashboard`, `/recommendations`) × two
languages × two widths: **16/16 HTTP/layout checks passed**, no page horizontal
overflow, no JavaScript page errors. The browser also submitted actual
registration, monthly setup, custom expense, generation, customization,
confirmation, a mobile **12,785-VND actual check-in**, and verified History
persistence. Dashboard database totals were cross-checked. Other check-ins
remain unknown. These checks do not resolve every owner-reported UI issue.

1. [Desktop Budget comparison](evidence/pa4-build3/desktop-budget.png): three saved
   strategies after real suggested/custom input on 26 November.
2. [Mobile Expense session](evidence/pa4-build3/mobile-expenses.png): generated
   schedule and actual check-in on a 390×844 viewport.
3. [Desktop Dashboard](evidence/pa4-build3/desktop-dashboard.png): observed
   12,785-VND spending with incomplete-data state after that browser check-in.

All screenshots are genuine captures from the successfully executed runner,
not mockups. [Browser results](evidence/pa4-build3/browser-results.json) record
the source SHA and browser version. Reproduce using the supplied
`browser_verify.py` after installing Playwright and adjusting the Chrome path.

## Defects, limitations and merge/release gates

| Item | Current disposition / owner |
|---|---|
| BP-D01 / BP-05 valid custom expense HTTP 400 | **Fixed/retested**, KAN-70; absent category field now defaults to the validated blank choice |
| Migration funding recalculation | **Fixed/retested**, KAN-70; legacy funding preserved |
| B001 meal guidance not visible in old owner test | Rendering exists in current source; original failing case needs owner retest |
| B002 bill PAID/UNPAID control absent | **OPEN**, Tuấn Anh; service endpoint works, current UI has no payment-status form |
| B003 unexpected Budget Impact Scope control absent | **OPEN**, Tuấn Anh; service validates scope but form omits it |
| B004 newest-first Expense History requirement | **OPEN**, Tuấn Anh; `list_records` still orders date/ID ascending |
| UI01 EN/VI mixed Expense content | **OPEN**, Thiện / Tuấn Anh; visible in current mobile capture |
| KAN-72 / KAN-73 current branches | **WAITING FOR FEATURE OWNER** |
| KAN-65 newer tests | Source for attached `test_kan65_*` execution is not on inspected remote refs; F18-01/05 also need the approved contract revision |
| Designed functional coverage | **INCOMPLETE**: 15/27 UCs meet five cases; 46 additional UC-specific designs needed |
| Feature review | No submitted reviews on #12/#14 at inspection; integrated PR requires owner review, including new month-deletion/funds-lock/unit behaviors |
| Deployment | Live PostgreSQL migration/concurrency and physical mobile/browser diversity NOT EXECUTED |

No automatic reallocation, bank integration, external AI, alerts, cross-month
reports or complete profile/preferences workflows are claimed. F18's 30-day
gate remains unreachable for February/short tracked periods. Confirmed planned
savings are not a bank balance.

Automated and migration gates pass. Outstanding owner defects, incomplete PA4
case/report artifacts and the normal reviewed-PR gate remain unresolved; main
merge and Beta publication are **pending**, not bypassed. Remote tag inspection
returned no tags and GitHub's public releases endpoint returned `[]` on
26 November. **No release tag/URL exists for this candidate and none is invented.**

See [the coverage matrix and member handoff](pa4-test-coverage-matrix.md) for
KAN-60/64/65/66/67 ownership. Thịnh must coordinate the integrated PR review,
requirements reconciliation, remaining defects and release decision; Nhân and
Khiêm retain their original case/report templates and contributions.
