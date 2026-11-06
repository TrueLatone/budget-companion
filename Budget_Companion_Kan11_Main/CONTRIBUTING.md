# Contributing – Group 10

## 1. Principles

- Use one shared GitHub repository; use Jira to track issues and acceptance criteria.
- `main` is the stable branch used for demos. Do not push directly to `main` after the initial setup.
- Every major change requires a Jira issue, a feature branch, and a Pull Request.
- Do not commit passwords, `.env` files, real personal data, or Supabase credentials.
- Discuss and update `docs/api-contracts.md` and `docs/database-design.md` before changing a shared schema or API.

## 2. Branch and Commit Naming

Branch examples: `feature/KAN-14-repository-setup`, `feature/KAN-16-shared-ui`, `fix/KAN-22-checkin-duplicate`.
Commit example: `chore(KAN-14): initialize flask application structure`.

## 3. Daily Workflow

```bash
git switch main
git pull origin main
git switch -c feature/KAN-XX-short-description
# implement and test
python -m pytest -q
git add .
git commit -m "feat(KAN-XX): describe change"
git push -u origin feature/KAN-XX-short-description
```

Open a Pull Request against `main`, link the Jira issue, and complete the PR template. Ask another team member to review it before merging. Configure branch protection or a ruleset if the GitHub repository supports it.

## 4. Responsibilities

| Team member | Primary area |
|---|---|
| Thịnh | Application factory, configuration, models/core, `modules/accounts`, integrations, and recurring bills |
| Nhân | `modules/budgets` |
| Tuấn Anh | `modules/expenses`, check-ins, and payment confirmation |
| Thiện | `modules/dashboard`, `templates/components`, and shared static UI |
| Khiêm | `modules/recommendations` |

Notify the relevant team members before merging changes to `app/models`, `app/__init__.py`, navigation, shared CSS, or API contracts.

## 5. Definition of Done

- Acceptance criteria are clear, and the Jira issue has the correct status.
- Tests pass
- No secrets or personal data are included in commits.
- The PR is reviewed by someone other than its author, when possible.
- New functionality does not break the P0/P1/P2 rules, the distinction between Unknown and No Expense, or duplicate prevention.
