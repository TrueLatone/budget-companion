# Build 3 integration verification

On 26 November 2026 the team verified runtime source `bdb4825` using disposable SQLite databases and offline PostgreSQL migration SQL. The integration candidate subsequently landed in `main` at `d61475d` through [PR #15](https://github.com/TrueLatone/budget-companion/pull/15).

## Verified behavior

| Check | Result |
| --- | --- |
| Full pytest suite on `bdb4825` | 564 passed, 0 failures, errors or skips, and 284 warnings |
| Budget planning and scheduling | Confirmation validates the saved plan and creates its schedule in one transaction. A failed schedule rolls back confirmation, and a retry preserves tasks and check-ins. |
| Migration and legacy funds | Tests upgraded previously populated SQLite databases and verified that funding, plan allocations, task limits and expense records were preserved. |
| Expense check-in and Dashboard | Tests verified repeat-safe recording, confirmed zero, History persistence and Dashboard totals. Unrecorded check-ins remain unknown. |
| Recommendations | Tests covered early guidance and data-ready recommendations. Accepting a supported recommendation updates its status and preserves confirmed allocations, task limits and savings. |
| Browser checks | All 16 Chrome HTTP and layout checks passed across four routes, two languages and desktop/mobile viewport sizes. The run used synthetic data in a disposable local database. |

The [API contracts](architecture/api-contracts.md) describe the implemented scheduling and data-completeness rules. The [pytest guide](../tests/README.md) provides regression commands.

The browser run used viewport emulation. Physical devices, additional browsers, and live PostgreSQL migration and concurrency remained outside that run. The payment-status and budget-impact-scope controls, History ordering, and some translated strings remained open UI issues. The automated and browser summaries cover the recorded runs. The official PA4 case designs, raw evidence and consolidated execution report are maintained separately in restricted project storage. See the [public component testing scope](pa4-test-coverage-matrix.md).
