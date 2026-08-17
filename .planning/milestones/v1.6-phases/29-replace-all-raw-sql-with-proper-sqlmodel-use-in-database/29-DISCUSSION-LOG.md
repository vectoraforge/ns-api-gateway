# Phase 29: Replace all raw SQL with proper SQLModel use in database/* - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 29-replace-all-raw-sql-with-proper-sqlmodel-use-in-database
**Areas discussed:** ORM purity level, Method return types, try_increment pattern

---

## ORM Purity Level

| Option | Description | Selected |
|--------|-------------|----------|
| Mixed (Recommended) | SQLModel select() for reads, pg_insert() for upserts, SA core update().returning() for atomic ops. Matches users.py and subscriptions.py patterns. | ✓ |
| Full SQLAlchemy core | SA core constructs for everything. Consistent within usage.py but diverges from chats.py. | |
| Full SQLModel ORM | Load model, modify, flush. Loses atomicity for try_increment. | |

**User's choice:** Mixed (Recommended)
**Notes:** User reviewed previews for all three approaches. Mixed aligns with existing codebase conventions.

---

## Method Return Types

| Option | Description | Selected |
|--------|-------------|----------|
| Keep scalar int (Recommended) | Return plain int. Callers only need the count — don't leak DB model into service layer. | ✓ |
| Return UsageMonthly \| None | Return full model instance. Gives callers access to all fields. | |

**User's choice:** Keep scalar int (Recommended)
**Notes:** User asked about using `scalar_one_or_none()` — left as Claude's discretion since both column-select + scalar and model-select + extract work.

---

## try_increment Pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Two statements, ORM rewrite (Recommended) | Same two-step logic (pg_insert + update().returning()), rewritten with ORM constructs. Proven pattern. | ✓ |
| Single INSERT ON CONFLICT DO UPDATE | Merge into one statement. Fewer round trips but more complex and edge cases around WHERE in ON CONFLICT. | |

**User's choice:** Two statements, ORM rewrite (Recommended)
**Notes:** User confirmed after reviewing preview showing the exact pg_insert + update().returning() pattern.

---

## Claude's Discretion

- Whether `get_usage` uses `select(UsageMonthly.used)` + `scalar_one_or_none()` or `select(UsageMonthly)` + `.first()` + extract `.used`
- Import organization and inline comments

## Deferred Ideas

None — discussion stayed within phase scope.
