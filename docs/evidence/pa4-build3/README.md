# PA4 Build 3 evidence

Date: 26 November 2026, Asia/Bangkok. Runtime source:
`bdb4825f193b691a226ede2254434cd843eccb32`.
Review: [PR #15](https://github.com/TrueLatone/budget-companion/pull/15).

Read [the verification report](../../build3-verification.md) and
[coverage matrix](../../pa4-test-coverage-matrix.md) for interpretation. Logs are
actual execution artifacts; overlapping focused runs must not be added. Earlier
probe failures intentionally preserve evidence of defects before the KAN-70 fix.

| Artifact | Meaning |
|---|---|
| `full-pytest.log/xml` | Final committed-source run: 564 passed, zero failures/errors/skips |
| `pa4-flows.log/xml` | Six new preservation and acceptance regressions, including both flows |
| `recommendations-focused.log/xml` | 93 Recommendations/Dashboard cases after KAN-59 integration |
| `nhan-focused.log/xml` | 71 original feature-focused tests before integration fixes |
| `reproduced-defects.log/xml` | Corrected probes before fix: four failed, one passed |
| `budget-fixed.log/xml` | 128 focused tests after form/migration fixes, before KAN-59 merge |
| `environment.txt` | Exact isolated-environment packages used for the final run |
| `preliminary-installed-environment.txt` | Installed Python environment used only for preliminary Budget/probe runs |
| `platform.json` | Actual operating system and Python |
| `browser-results.json` | Actual browser/source/date; 16 layout checks and functional interaction outcomes |
| Three `.png` files | Genuine screenshots after successful Chrome interactions; captions in report |
| `browser_verify.py` | Reproduction runner using disposable SQLite and local Chrome |
| `static-checks.txt` | Seven node syntax checks, whitespace check and zero conflict entries |
| `remote-tags.txt`, `remote-releases.json` | Remote inspection: no tags, no published releases |
| `input-inventory.json` | SHA-256 and original metadata of supplied/read owner inputs |
| `jira-snapshot.json` | Read-only source/attachment/status inventory; not a Jira status update |
| `owner-case-inventory.json` | Distinct original IDs and owner historical statuses; not current Pass certification |
| `extract_inputs.py` | PDF/Office/ODS extractor used to inspect originals; handles repeated/covered ODS cells |

`browser_verify.py` runs from the repository root and writes this folder. It
requires application dependencies plus Playwright and an installed Chrome at the
configured Windows path. It starts only a temporary local database/server.
Original Jira/ZIP inputs are retained locally under ignored
`instance/pa4-evidence/inputs`; the original owner files were not modified or
redistributed here. To use the extractor elsewhere, provide an `inputs` directory
beside its copy. Original file names/attachment IDs and hashes are in the inventory.

No live Supabase connection was used. A local pytest/Chrome pass does not
establish live PostgreSQL concurrency, physical mobile device compatibility,
case-design completeness or a reviewed/published Beta.
