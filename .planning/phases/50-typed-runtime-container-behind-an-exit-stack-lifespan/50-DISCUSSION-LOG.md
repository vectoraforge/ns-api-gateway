# Phase 50: Typed runtime container behind an exit-stack lifespan - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-17
**Phase:** 50-typed-runtime-container-behind-an-exit-stack-lifespan
**Areas discussed:** Container names, The sign-out-all route, Builders

---

## Todos

| Option | Description | Selected |
|--------|-------------|----------|
| Fold none | Both stay reviewed-not-folded, as in Phases 46, 48 and 49 | ✓ |
| Fold secret-manager-integration | Adds a config source to a refactor | |
| Fold message-ordering-is-unspecified | Chats domain | |

**User's choice:** Fold none.
**Notes:** The user asked how to stop the two todos from matching every phase. Answer: `todo.match-phase` has no score threshold, so only moving them out of `todos/pending/` stops it. Noted as deferred.

---

## Container names

| Option | Description | Selected |
|--------|-------------|----------|
| app/runtime.py, Runtime, app.state.runtime | Matches get_runtime; shortest name | ✓ |
| app/runtime.py, RuntimeContainer, app.state.runtime | Longer annotation on every dependency | |
| app/container.py, Container, app.state.container | Getter and attribute disagree | |

| Option | Description | Selected |
|--------|-------------|----------|
| Delete get_config | A one-line step with no caller after the rewrite | ✓ |
| Keep as a one-liner over get_runtime | A dead function today | |

| Option | Description | Selected |
|--------|-------------|----------|
| Build order | config, session_factory, jwt_verifier, adapters, notifications, llm_service | ✓ |
| The order the ROADMAP goal lists | Today's lifespan order | |

| Option | Description | Selected |
|--------|-------------|----------|
| async_sessionmaker[SQLModelAsyncSession] | The parametrised generic | ✓ |
| async_sessionmaker, bare | What dependencies.py declares today | |

**User's choice:** All four recommended options.

---

## The sign-out-all route

| Option | Description | Selected |
|--------|-------------|----------|
| Declare get_runtime, read runtime.firebase_adapter | Still Depends()-only; opens no session | ✓ |
| Keep get_firebase_adapter as a one-liner | A second way to one field, for one route | |
| Move the revocation into AuthService | Needs a session the route must not take | |

| Option | Description | Selected |
|--------|-------------|----------|
| Amend the ROADMAP entry in the discuss commit | As 48 D-09 and 49 D-07 did | ✓ |
| Leave the entry; CONTEXT.md carries it | Criterion 5 silent on the route | |

**User's choice:** Both recommended options.

---

## Builders

| Option | Description | Selected |
|--------|-------------|----------|
| jwt: JWTConfig; narrow build_admin_apps | build_admin_apps reads only config.jwt | ✓ |
| config: AppConfig passed through | No edit outside lifespan.py | |

| Option | Description | Selected |
|--------|-------------|----------|
| Pins read once | A None verifier has one meaning | ✓ |
| Twice, code moved as is | | |

**User's choice:** Both recommended options. The one-builder-or-two question for Google Play was
asked three times and never answered as posed; it was closed by the merge below.

**Notes (free text, in order):**
- The user asked why `build_google_push_verifier` returns `None` instead of raising, then why
  `PubSubPushTokens` takes a value and a function that makes the value, then rejected that
  pattern outright ("don't start the pod"). Decision: a failed warm-up raises and the pod does
  not start; absent settings still start it (D-08).
- The user asked for every other instance. Found: `PlayDeveloperSubscriptions` (same pattern),
  and three relatives that treat a transient failure as absent configuration
  (`_play_credential`, `_application_default_credential`, `build_app_store_verifier`). The
  user applied the rule to all (D-08).
- The user rejected the `PubSubPushTokens` docstring ("a verified token") and asked for a
  rename, then decided to merge both Play classes into `GooglePlayNotifications`, like
  `AppStoreNotifications` (D-09, D-10).
- Builder names: named after the `Runtime` field each fills; no objection (D-06).
- The user asked several times for plain English and for no AskUserQuestion dialogs while
  asking questions. Later answers were plain text.

---

## Claude's Discretion

- How tests build a `Runtime` from fakes (shared helper or per file); one e2e swap helper or
  seven fixtures; a wiring test for the route clause; docstrings on `Runtime` and
  `get_runtime`; commit granularity and wave order.

## Deferred Ideas

- Move the two pending todos into backlog phases of `ROADMAP.md` so `todo.match-phase` stops
  matching them.
