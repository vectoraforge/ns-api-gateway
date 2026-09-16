# Phase 48: Narrow Identity to the verified pair - Context

**Gathered:** 2026-09-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Behavior-preserving refactor of the auth barrier types. Today `AuthIdentity` holds `issuer`,
`subject` and two nullable rows, and `LinkedIdentity` subclasses it. After this phase the token
result and the account are two types with no `None` field, served by two dependencies. The
admission matrix is unchanged, except for the one ordering change recorded in D-07.

**In scope:** `schemas/auth.py`, `app/dependencies.py`,
`crud/identities.py`, `crud/challenges.py`, `services/auth.py`, `services/restore.py`,
`routers/{auth,users,chats}.py`, the unit, e2e and schema tests that build or resolve an
identity, and the Phase 48 entry in `ROADMAP.md`.

**Out of scope:** the challenge store's lifespan wiring and the auth Protocols (Phase 49), the
lifespan and `app.state` (Phase 50), any change to the routes' status codes or bodies, either
matched todo.

</domain>

<decisions>
## Implementation Decisions

The discussion replaced the ROADMAP goal as written. The goal kept `AuthIdentity` as a class
holding `issuer` and `subject`; the user found that class would be a copy of `VerifiedClaims`,
which `auth/jwt_verifier.py:59` already defines, and deleted it. D-09 amends the ROADMAP entry.

### The two types

- **D-01: `AuthIdentity` is deleted.** The token result is `VerifiedClaims` in
  `auth/jwt_verifier.py`, holding `issuer` and `subject`, unchanged. It keeps the plural: `iss`
  and `sub` are two JWT claims. Every import, annotation and constructor of `AuthIdentity` in
  `src/` and `tests/` changes.
- **D-02:** `LinkedIdentity` holds `user: User` and `identity: ExternalIdentity`, both required.
  It loses `issuer`, `subject` and its base class. It stays a frozen, slotted dataclass in
  `schemas/auth.py`. `resolve` returns both rows or raises, so no reader gets a `None` warning.
  One class for both rows, not two: one joined query loads both, and 7 of 12 routes read the
  `ExternalIdentity` (`provider`, `id`, `free_grant_consumed_at`).

### The crud method

- **D-03:** `IdentitiesDB.resolve(*, issuer, subject) -> LinkedIdentity | None`. The
  `allow_preauth` parameter is removed: nothing in `src/` passes `False`. `None` means no
  `ExternalIdentity` row exists. The three rejections are unchanged: `IdentityUnresolvable` for
  a row whose user is missing, `HistoricalIdentity` for a non-active row, `BlockedUser` for a
  non-active user. `resolve` no longer raises `PreAuthIdentityNotAllowed`; that moves to D-05.

### The two dependencies

- **D-04: `get_claims` replaces today's `get_identity`.** It checks the bearer credential and the
  token exactly as today's `get_identity` does (`InvalidExternalJwt` with the same
  `BoundedReason` values) and returns `VerifiedClaims`. It does not read the database.
- **D-05: `get_identity` replaces today's `get_linked_identity`.** It declares `get_claims`, opens
  its own short session from `session_factory` as today's `get_identity` does, calls `resolve`,
  and returns the `LinkedIdentity`. On `None` it raises `PreAuthIdentityNotAllowed`. It is the
  authentication check for every route that needs an account. Router-level declarations:
  `routers/auth.py` declares `get_claims`; `routers/users.py` and `routers/chats.py` declare
  `get_identity`. FastAPI caches `get_claims`, so a route declaring both verifies the token once.
- **D-06:** The challenge route declares `get_claims` and `get_db` and calls
  `IdentitiesDB(session).resolve` itself. It is the one route that admits a caller with no
  row, because that caller issues the create-user challenge. `None` with any operation other
  than `create_user` is `PreAuthIdentityNotAllowed`, as today. The three rejections from
  `resolve` propagate as today.
- **D-07: Create-user declares `get_claims` only.** Consequence, accepted by the user: today the
  router-level `get_identity` rejects a historical row or a blocked user on create-user before
  the challenge is claimed. After this phase that rejection comes from
  `AuthService._reject_existing_identity` (`services/auth.py:358`), which runs after the claim,
  so that caller spends its challenge. Same status and code; one wasted challenge for a caller
  that is refused anyway. Record it in `.planning/WINDOWS.md` if the planner judges it a window.

### Parameters

- **D-08:** Services and the challenge store take the two values as separate parameters:
  `claims: VerifiedClaims` and `linked: LinkedIdentity`. The name `linked`, not `identity`, so
  reads are `linked.user` and `linked.identity`. `ChallengesDB.issue` and `verify_binding` take
  `claims` and `linked: LinkedIdentity | None`: they bind to `linked.identity.id` when a row
  exists and to `claims.issuer` and `claims.subject` when none does, as today. Wherever
  `identity.issuer` or `identity.subject` is read today, read `claims`; do not substitute
  `linked.identity.issuer`, because sign-out-all and the grant writers record what this request
  proved. `AuthService._complete[I: AuthIdentity, T]` loses its type variable and takes `claims`
  and `linked`. What each route needs:

  | Route | `claims` | `linked.user` | `linked.identity` |
  |---|---|---|---|
  | POST /auth/challenge | yes | no | `id`, when a row exists |
  | POST /auth/create-user | yes | no | no |
  | POST /auth/upgrade-anonymous | yes | no | `id` |
  | POST /auth/claim-anonymous-grant | yes | yes | yes |
  | POST /auth/claim-registered-grant | yes | yes | yes |
  | POST /auth/restore-subscription | no | yes | `provider` |
  | POST /auth/sync | no | yes | `provider` |
  | POST /auth/sign-out-all | yes | no | `id` |
  | GET /users/me | no | yes | `provider` |
  | 5 chat routes | no | `id` | no |

### Records

- **D-09: Amend the Phase 48 entry in `ROADMAP.md`** to this shape (done in the discuss commit):
  the goal names `VerifiedClaims`, `LinkedIdentity`, `get_claims` and `get_identity`; criteria 1
  to 4 are rewritten; criterion 5 is unchanged. `REQUIREMENTS.md` maps nothing to this phase and
  is not edited.
- **D-10: Every comment this phase writes is ASD-STE100, one line, only where needed** (46 D-11,
  `AGENTS.md` § "Comments and docstrings"). Delete every comment whose subject is the removed
  fields, the `allow_preauth` flag or the old `get_identity` return value.

### Tests

- **D-11:** Tests that build an `AuthIdentity` build a `VerifiedClaims` (no rows) or a
  `LinkedIdentity` (rows). `TestTheIdentityShape` in `tests/unit/test_identity_accessors.py`
  and the two cases in `tests/unit/test_identities_crud.py` that assert `identity.user is None`
  are deleted. The cases that pass `allow_preauth=False`
  (`tests/unit/test_exception_handlers.py:360`, `tests/schema/test_claim_race.py:251`) and the
  crud test's `preauth_callable` parametrization change to the new signature. Every test that
  overrides `get_identity` or `get_linked_identity` by name follows the rename.

### Claude's Discretion

- Commit granularity and plan wave order. The type change breaks every site at once.
- Whether `get_identity` and `get_claims` keep their docstrings, within the three-line rule.
- How `tests/unit/test_identity_accessors.py` asserts the two dependencies' signatures after the
  rename.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The phase entry
- `.planning/ROADMAP.md` Phase 48 — the goal and criteria as amended by D-09.

### Prior-phase decisions this phase builds on
- `.planning/phases/46-post-auth-sign-out-all/46-CONTEXT.md` — D-01 (the request-verified
  values go to the provider, never the stored row) and D-11 (comment rule); "Carried forward":
  the barrier is `get_identity` then `get_linked_identity`, renamed here by D-04/D-05.
- `.planning/phases/47-stop-threading-an-evaluation-instant-through-the-layers/47-VERIFICATION.md`
  — the current suite counts and the one pre-existing failing case criterion 5 must not be
  charged for.

### Conventions
- `AGENTS.md` (repo root) — package layout (`schemas/` holds domain value types; a fail-closed
  read may raise its own rejection from `crud/`), comment and docstring rules.

No spec file: Phases 47 to 50 are refactors added after the spec phases closed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth/jwt_verifier.py:59` — `VerifiedClaims(issuer, subject)`, already returned by
  `verify`; D-01 renames it and makes it the type `get_claims` returns.
- `app/dependencies.py:58-84` — today's `get_identity` (credential check, `run_in_threadpool`
  verify, own session, `resolve`) and `get_linked_identity`; D-04/D-05 split the first and
  rename both.
- `crud/identities.py:30-54` — `resolve`, one outer-joined query with the three rejections.
- `crud/challenges.py:44-61, 90-104` — `issue` and `verify_binding`, the two places that bind
  to a row or to the token values.
- `services/auth.py:114-163, 288-345` — `_complete`, `_read_then_write`, `_apply_create_user`,
  `_apply_upgrade`, `create_user`: the readers of `identity.issuer` and `identity.subject`.
- `tests/unit/conftest.py:115` — `TEST_IDENTITY`, a `LinkedIdentity` built with rows.

### Established Patterns
- A narrowed route declares the account dependency at route level; the router-level
  declaration on `routers/auth.py` stays the unnarrowed one (today `get_identity`, after this
  phase `get_claims`).
- Outcomes are exception classes; `resolve` raises its own rejections from `crud/`.
- `get_identity` resolves in its own short session, closed before the handler runs;
  `tests/unit/test_identity_accessors.py::test_the_declaration_resolves_once` pins one
  statement per request.

### Integration Points
- `routers/auth.py` (8 routes), `routers/users.py`, `routers/chats.py` (5 routes) — the
  dependency declarations.
- `services/auth.py`, `services/restore.py`, `crud/challenges.py` — the parameter split.
- 23 files in `src/` and `tests/` name `AuthIdentity`, `get_identity` or
  `get_linked_identity`.

</code_context>

<specifics>
## Specific Ideas

- The user reads the code, not the prose. Name things only by the identifiers in the code:
  `VerifiedClaims`, `LinkedIdentity`, `User`, `ExternalIdentity`, `get_claims`, `get_identity`,
  `resolve`. Do not coin shorthand such as "pair", "rows", "narrow" or "admission".
- `linked.user` and `linked.identity`, never `identity.identity`.

</specifics>

<deferred>
## Deferred Ideas

- Whether routes that read both `claims` and `linked` should instead read `issuer` and
  `subject` off `linked.identity` — raised, not decided; D-08 keeps `claims` for
  behavior preservation.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.6) — chats; matched on the word "phase". Not
  folded, as in Phase 46.
- `secret-manager-integration` (score 0.2) — config; matched on the word "phase". Not folded,
  as in Phase 46.

</deferred>

---

*Phase: 48-narrow-identity-to-the-verified-pair*
*Context gathered: 2026-09-16*
