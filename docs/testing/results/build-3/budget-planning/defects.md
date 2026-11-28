# Budget Planning defects

## BP-D02 Confirmation creates tasks before the schedule action

| Defect detail | Value |
| --- | --- |
| Title | Confirmation creates tasks before the schedule action |
| Defect ID | BP-D02 |
| Component | Budget Planning |
| Affected case and use case | BP-39 · UC10 and UC11 |
| Build version and commit SHA | Build 3, `440b3f75a9e233b08bed74e6053e36ce089df307` |
| Environment | Debian 13, Python 3.12.14, Flask 3.1.3, SQLite and Chromium 158 or Flask test client |
| Severity | Medium |

### Preconditions and test data

Use D2, an owned November 2026 period with tracking from 6 November, six configured expenses and a generated Balanced proposal.

### Reproduction steps

1. Confirm Balanced using its Budget page.
2. Count assigned tasks before using Create / Verify.
3. Run Create / Verify and compare task IDs.

### Expected result

Under UCS v1.2 §§2.10–2.11, confirmation locks the plan and redirects to Expense Planning with zero tasks. The separate action creates 34 tasks.

### Actual result

The redirect succeeded. All 34 tasks already existed after confirmation. Create / Verify preserved all 34 IDs. No actual expense was created.

### Evidence links

[Request and task counts](automated/schedule-check.log) · [Focused pytest, BP-39](automated/pytest-budget-planning.log)

### Retest and resolution

Open at this commit. Agree on the UC10/11 and UC29 schedule contract. Repeat the same three steps on the selected revision.

## BP-D03 Vietnamese schedule displays Rent in English

| Defect detail | Value |
| --- | --- |
| Title | Vietnamese schedule displays Rent in English |
| Defect ID | BP-D03 |
| Component | Budget Planning |
| Affected case and use case | BP-59 · UC12 language case |
| Build version and commit SHA | Build 3, `440b3f75a9e233b08bed74e6053e36ce089df307` |
| Environment | Debian 13, Python 3.12.14, Flask 3.1.3, SQLite and Chromium 158 or Flask test client |
| Severity | Low |

### Preconditions and test data

Use D4 December with a standard Rent entry and a custom expense named Cinema. Confirm the plan and select Vietnamese.

### Reproduction steps

1. Open the original schedule in Day view for 1 December 2026.
2. Read the names of Rent and Cinema.
3. Repeat in Expense Planning and switch to English as a control.

### Expected result

The supplied Vietnamese case expects the standard label “Tiền trọ”. The custom name remains “Cinema”.

### Actual result

Both pages used “Rent” for the standard item in Vietnamese. Cinema retained its custom name. The English control showed Rent and Cinema.

### Evidence links

[Vietnamese original schedule](evidence/BP-59-vietnamese-label.png) · [Language results on both pages](automated/browser-session.log)

### Retest and resolution

Open at this commit. Repeat BP-59 and BP-60 with the same month and labels.
