# Shared database design — KAN-19

The canonical schema contains 13 entities and 17 foreign-key relationships.
Models live in `app/models/` and are exported through `app.models` for
Flask-Migrate. See [the entity dictionary](entity-dictionary.md) for all attributes.

## Tracking interval and existing data

Tracking start is required and has the same calendar year/month as month_start.
Legacy NULL values backfill to month_start, preserving prior full-month semantics.
Creation time does not establish historical tracking start. Explicit tracking dates
supplied during expansion are preserved. Backfill leaves IDs, funds, created_at
and updated_at unchanged and generates no tasks or financial transactions.

Period creation accepts an optional date; omission defaults to the first day,
including direct ORM inserts. The existing UI accepts it on creation and shows
it in the list. Funds editing leaves it unchanged. Changing it after financial
activity requires a separate reviewed workflow.

## Database guarantees

- One preference per user and one review per month at most.
- One CONFIRMED plan per month at most (partial unique index); multiple GENERATED
  alternatives may coexist.
- One allocation per (plan, planned expense), one task per (allocation, assigned
  date), and one detail per (adjustment, task).
- At most one adjustment per non-NULL recommendation; multiple manual adjustments
  may have NULL recommendation references.
- Nonnegative funds, savings, estimates, task limits and adjustment limits;
  positive allocations, transactions and optional minimums; valid due days/ratings.
- Allowed plan types, stored statuses, priorities, record types and frequencies.
- PLANNED requires task/category; UNEXPECTED requires category/priority and no
  task; FUNDS_ADDED has no task/category/priority. Scope follows the rule above.
- FKs and lookup indexes for relations, transaction dates and payment due dates.

Preference/category owner FKs use CASCADE. The existing users-to-budget-months
cascade remains unchanged. New financial FKs use RESTRICT to prevent silent
loss of referenced history. Thus deleting a user/month with financial children
is blocked pending an explicit deletion workflow; no deletion UI is introduced.
ORM parent relationships defer restrictions to the database even when loaded.

## Rules that require services

Models do not implement financial workflows or authorize arbitrary writes.
Services must derive ownership from the existing authenticated session and check
every referenced month/category/plan/task and JSON task ID. Simple FKs do not
prove common ownership or that a plan and planned expense share a month.

Services must enforce P0 requirements, P1 minimums, funding feasibility,
confirmed-plan immutability and original-funds conservation/snapshots. Mutable
available_vnd is not historical truth. Weekly boundaries, partial periods,
pre-tracking bills, cross-month late payments and automatic versus accepted
adjustments remain feature decisions; no scheduling/reallocation policy is
silently selected by the models.

Check-in services must sum all task transactions, reject NO_EXPENSE while spending
exists, and recalculate outcomes on edits/deletions. Completeness excludes
pre-tracking dates and never treats missing data as zero. Reports exclude
FUNDS_ADDED from spending. Funds additions must atomically insert the record and
update funds once using a token and replay-payload validation. Uniqueness alone
does not implement idempotent financial behavior.

Adjustments must be accepted if recommendation-driven, contain at least one
detail, touch eligible future tasks in one authorized month, protect minimums,
preserve original limits and atomically update current limits plus history.
Budget/expense/report/recommendation feature routes remain placeholders; these
workflows are not implemented merely by adding tables.

## Append-only migration history

```text
de12e989405f  existing foundation (unchanged)
    -> 19a01e000001  add nullable tracking_start_date
    -> 19a01e000002  backfill/enforce tracking; create 11 missing tables
```

For rolling deployment: expand, deploy writers supplying the tracking date, then
finalize. Old writers must not remain active after NOT NULL is enforced. SQLite
parent-table batch alteration occurs before adding incoming financial FKs.

## Security

Existing Flask session authentication, password hashing, CSRF and ownership checks
remain in place. Credentials stay server-side. Supabase Data API exposure and
RLS require separate review: using a server-side SQLAlchemy connection does not
implicitly provide per-user database authorization.
