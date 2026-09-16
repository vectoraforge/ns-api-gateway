# Phase 48: Narrow Identity to the verified pair - Research

**Researched:** 2026-09-16
**Domain:** FastAPI dependency declarations, Python dataclasses, in-repo refactor
**Confidence:** HIGH — every claim below was measured against the working tree in this session.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: `AuthIdentity` is deleted.** The token result is `VerifiedClaims` in
  `auth/jwt_verifier.py`, holding `issuer` and `subject`, unchanged. It keeps the plural: `iss`
  and `sub` are two JWT claims. Every import, annotation and constructor of `AuthIdentity` in
  `src/` and `tests/` changes.
- **D-02: `LinkedIdentity` holds `user: User` and `identity: ExternalIdentity`, both required.**
  It loses `issuer`, `subject` and its base class. It stays a frozen, slotted dataclass in
  `schemas/auth.py`. `resolve` returns both rows or raises, so no reader gets a `None` warning.
  One class for both rows, not two: one joined query loads both, and 7 of 12 routes read the
  `ExternalIdentity` (`provider`, `id`, `free_grant_consumed_at`).
- **D-03: `IdentitiesDB.resolve(*, issuer, subject) -> LinkedIdentity | None`.** The
  `allow_preauth` parameter is removed: nothing in `src/` passes `False`. `None` means no
  `ExternalIdentity` row exists. The three rejections are unchanged: `IdentityUnresolvable` for
  a row whose user is missing, `HistoricalIdentity` for a non-active row, `BlockedUser` for a
  non-active user. `resolve` no longer raises `PreAuthIdentityNotAllowed`; that moves to D-05.
- **D-04: `get_claims` replaces today's `get_identity`.** It checks the bearer credential and the
  token exactly as today's `get_identity` does (`InvalidExternalJwt` with the same
  `BoundedReason` values) and returns `VerifiedClaims`. It does not read the database.
- **D-05: `get_identity` replaces today's `get_linked_identity`.** It declares `get_claims`, opens
  its own short session from `session_factory` as today's `get_identity` does, calls `resolve`,
  and returns the `LinkedIdentity`. On `None` it raises `PreAuthIdentityNotAllowed`. It is the
  authentication check for every route that needs an account. Router-level declarations:
  `routers/auth.py` declares `get_claims`; `routers/users.py` and `routers/chats.py` declare
  `get_identity`. FastAPI caches `get_claims`, so a route declaring both verifies the token once.
- **D-06: The challenge route declares `get_claims` and `get_db` and calls
  `IdentitiesDB(session).resolve` itself.** It is the one route that admits a caller with no
  row, because that caller issues the create-user challenge. `None` with any operation other
  than `create_user` is `PreAuthIdentityNotAllowed`, as today. The three rejections from
  `resolve` propagate as today.
- **D-07: Create-user declares `get_claims` only.** Consequence, accepted by the user: today the
  router-level `get_identity` rejects a historical row or a blocked user on create-user before
  the challenge is claimed. After this phase that rejection comes from
  `AuthService._reject_existing_identity` (`services/auth.py:358`), which runs after the claim,
  so that caller spends its challenge. Same status and code; one wasted challenge for a caller
  that is refused anyway. Record it in `.planning/WINDOWS.md` if the planner judges it a window.
- **D-08: Services and the challenge store take the two values as separate parameters:**
  `claims: VerifiedClaims` and `linked: LinkedIdentity`. The name `linked`, not `identity`, so
  reads are `linked.user` and `linked.identity`. `ChallengesDB.issue` and `verify_binding` take
  `claims` and `linked: LinkedIdentity | None`: they bind to `linked.identity.id` when a row
  exists and to `claims.issuer` and `claims.subject` when none does, as today. Wherever
  `identity.issuer` or `identity.subject` is read today, read `claims`; do not substitute
  `linked.identity.issuer`, because sign-out-all and the grant writers record what this request
  proved. `AuthService._complete[I: AuthIdentity, T]` loses its type variable and takes `claims`
  and `linked`.
- **D-09: Amend the Phase 48 entry in `ROADMAP.md`** (done in the discuss commit).
  `REQUIREMENTS.md` maps nothing to this phase and is not edited.
- **D-10: Every comment this phase writes is ASD-STE100, one line, only where needed.**
  Delete every comment whose subject is the removed fields, the `allow_preauth` flag or the old
  `get_identity` return value.
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

### Deferred Ideas (OUT OF SCOPE)

- Whether routes that read both `claims` and `linked` should instead read `issuer` and
  `subject` off `linked.identity` — raised, not decided; D-08 keeps `claims` for
  behavior preservation.
- `message-ordering-is-unspecified` (score 0.6). Not folded, as in Phase 46.
- `secret-manager-integration` (score 0.2). Not folded, as in Phase 46.
</user_constraints>

## Summary

This phase is a type split across 36 files. No new package is added. No new pattern is needed.
The work is an exact inventory and a mechanical rewrite, plus four sites where the rewrite is
not mechanical.

The inventory below is measured, not recalled. Every file:line was read or grepped in this
session. Four findings change the plan's shape:

1. `routers/root.py:9` and `routers/examples.py:8` declare `get_linked_identity` at router
   level. CONTEXT's "In scope" list does not name them. They must follow the rename, and
   `tests/e2e/test_admission.py:83` pins both paths.
2. `tests/unit/test_challenge_endpoint.py:204` asserts the challenge route issues no statement.
   D-06 adds one. The assertion stays true only if the route calls `resolve` after the
   `AuthOperation` vocabulary check.
3. Three precedence suites override `get_identity` today and receive `get_linked_identity` for
   free, because the second declares the first. After D-04/D-05 that chain is reversed. Each
   suite must override two dependencies, not one.
4. `tests/schema/test_restore_race.py:222` builds an identity holding a `User` and no
   `ExternalIdentity`. D-02 makes both fields required, so this site needs a new row object.

**Primary recommendation:** Plan three waves. Wave 1 rewrites `schemas/auth.py`,
`crud/identities.py`, `crud/challenges.py`, `app/dependencies.py`, the five routers and the two
services in one commit, because the type change breaks every site at once. Wave 2 rewrites the
24 test files. Wave 3 re-measures the three suites, `ruff` and `ty`.

## Project Constraints (from AGENTS.md)

| Directive | Effect on this phase |
|-----------|---------------------|
| Docstrings — three lines maximum, state what the entity does | `get_claims`, `get_identity`, `resolve`, `LinkedIdentity` |
| Comments — only where needed, one line each, default to none | D-10 |
| `schemas/` holds domain value types | `LinkedIdentity` stays there |
| `crud/` holds database access; a fail-closed read may raise its own rejection | The three rejections stay in `resolve` |
| `routers/` use `Depends()` only | The challenge route takes `get_db`, never `Request` |
| `BoundedReason` stays in `auth/jwt_verifier.py` to avoid an import cycle | `VerifiedClaims` stays there too |
| The spec must not consume many tokens | Keep the plan short |

## Baseline (measured 2026-09-16 at HEAD `937864c`)

| Command | Result |
|---------|--------|
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 [VERIFIED: run this session] |
| `.venv/bin/ty check` | `Found 311 diagnostics` [VERIFIED: run this session] |
| `.venv/bin/pytest -q -m ''` | 1 failed, 2579 passed, 137.81 s [VERIFIED: run this session] |
| `.venv/bin/pytest -q -m e2e` | 1 failed, 360 passed, 2219 deselected, 47.89 s [VERIFIED] |
| `.venv/bin/pytest -q -m schema` | 297 passed, 2283 deselected, 35.33 s [VERIFIED] |

The one failing case is pre-existing and is not this phase's:
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`.
Root cause recorded in STATE.md: `PurchaseProofRejected` carries `code = "proof_rejected"`, but
the log event name comes from the class name. Criterion 5 must not be charged for it.

`ty` reads 311 diagnostics. Six of the in-scope files already carry diagnostics
(`services/auth.py:63`, `services/restore.py:43` and `:54`, `crud/challenges.py:42` and `:69`,
`crud/identities.py:27`). The count is the control: the phase must not raise it.

**PostgreSQL:** `pg_isready` is not on PATH, but `-m schema` and `-m e2e` both ran and passed
against a live server, so a database is reachable on localhost:5432. Do not treat the denied
Docker socket as a blocker.

**Test tools:** `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/ty`. None is on PATH.
`addopts` in `pyproject.toml` carries `-m 'not e2e and not schema'`, so a bare run deselects
both suites. An all-deselected run is not a pass.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bearer credential check and token verification | `app/dependencies.py` (`get_claims`) | — | D-04; it reads no table |
| Resolving the two rows | `crud/identities.py` (`resolve`) | — | Database access, AGENTS.md `crud/` |
| Refusing a never-linked caller | `app/dependencies.py` (`get_identity`) | `routers/auth.py` for the challenge route | D-05, D-06 |
| Refusing a broken, historical or blocked row | `crud/identities.py` | — | AGENTS.md exception 4: a fail-closed read raises its own rejection |
| The two value types | `auth/jwt_verifier.py` (`VerifiedClaims`), `schemas/auth.py` (`LinkedIdentity`) | — | D-01, D-02 |

## The two types after the phase

`auth/jwt_verifier.py:58-62`, unchanged, quoted verbatim
[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:57-62]:

```python
@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str
```

`schemas/auth.py:94-108` today, quoted verbatim
[VERIFIED: src/nativespeaker/api/schemas/auth.py:94-108]:

```python
@dataclass(frozen=True, slots=True)
class AuthIdentity:
    """A verified `(issuer, subject)` and the rows it resolved to, both `None` when it is unlinked."""
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None


@dataclass(frozen=True, slots=True)
class LinkedIdentity(AuthIdentity):
    """The same pair once the linked check has run: both rows are present by construction."""
    user: User
    identity: ExternalIdentity
```

Both classes become one class with two fields and no base. `schemas/auth.py` keeps its imports
of `User` and `ExternalIdentity` (`schemas/auth.py:8-10`).

**Import direction:** `auth/jwt_verifier.py` imports nothing from this project
[VERIFIED: src/nativespeaker/api/auth/jwt_verifier.py:2-23]. No `crud/` module imports from
`auth/` today. `crud/challenges.py` and `crud/identities.py` will be the first. No cycle can
arise, because `jwt_verifier.py` is a leaf.

## Inventory: `src/` (12 files)

### `src/nativespeaker/api/schemas/auth.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 94-101 | `class AuthIdentity` with four fields | deleted | D-01 |
| 103-108 | `class LinkedIdentity(AuthIdentity)` | `@dataclass(frozen=True, slots=True) class LinkedIdentity` with `user: User` and `identity: ExternalIdentity` | D-02 |

### `src/nativespeaker/api/crud/identities.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 16 | imports `PreAuthIdentityNotAllowed` | import deleted | D-03 |
| 19 | imports `AuthIdentity` | imports `LinkedIdentity`, plus `VerifiedClaims` for line 91 | D-01 |
| 30 | `resolve(*, issuer, subject, allow_preauth: bool) -> AuthIdentity` | `resolve(*, issuer, subject) -> LinkedIdentity \| None` | D-03 |
| 40-43 | comment, `if allow_preauth: return AuthIdentity(...)`, `raise PreAuthIdentityNotAllowed` | `return None` | D-03, D-10 |
| 54 | `return AuthIdentity(issuer=..., subject=..., user=user, identity=identity)` | `return LinkedIdentity(user=user, identity=identity)` | D-02 |
| 91 | `insert_account(*, identity: AuthIdentity, ...)` | `claims: VerifiedClaims` | D-08 |
| 105-106 | `issuer=identity.issuer`, `subject=identity.subject` | reads `claims` | D-08 |

Lines 45-53 (the three rejections) are unchanged. They are what criterion 2 pins.

### `src/nativespeaker/api/app/dependencies.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 26 | imports `PreAuthIdentityNotAllowed` | kept; the raise moves here | D-05 |
| 28 | imports `AuthIdentity, LinkedIdentity` | imports `LinkedIdentity` and `VerifiedClaims` | D-01 |
| 58-76 | `get_identity(request, credential) -> AuthIdentity` | split: `get_claims(request, credential) -> VerifiedClaims` returns at line 72, and `get_identity(request, claims=Depends(get_claims)) -> LinkedIdentity` holds lines 74-76 | D-04, D-05 |
| 74-76 | `resolve(..., allow_preauth=True)` | `resolve(issuer=claims.issuer, subject=claims.subject)`; `None` raises `PreAuthIdentityNotAllowed` | D-03, D-05 |
| 79 | comment on the FastAPI cache | keep; it still states why nothing calls the dependency directly | D-10 |
| 80-85 | `get_linked_identity` | deleted; its name is taken by the new `get_identity` | D-05 |

`get_identity` must take `request` as well as `claims`, because it reads
`request.app.state.session_factory` (line 74). Today's `get_linked_identity` takes one parameter
and `tests/unit/test_identity_accessors.py:279-280` asserts that. That case must change.

### `src/nativespeaker/api/crud/challenges.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 11 | imports `AuthIdentity` | imports `LinkedIdentity` and `VerifiedClaims` | D-08 |
| 42-44 | `issue(session, *, operation, identity: AuthIdentity)` | `issue(session, *, operation, claims: VerifiedClaims, linked: LinkedIdentity \| None)` | D-08 |
| 53-57 | `if identity.identity is not None: bound_identity_id = identity.identity.id` else `preauth_issuer = identity.issuer` | `if linked is not None: ... linked.identity.id` else `claims.issuer`, `claims.subject` | D-08 |
| 90 | `verify_binding(self, row, identity: AuthIdentity)` | `verify_binding(self, row, claims: VerifiedClaims, linked: LinkedIdentity \| None)` | D-08 |
| 93-94 | `identity.identity is not None and identity.identity.id == ...` | `linked is not None and linked.identity.id == ...` | D-08 |
| 101, 103 | `identity.issuer`, `identity.subject` | `claims.issuer`, `claims.subject` | D-08 |

This file is the one place criterion 3 allows a `LinkedIdentity | None` parameter.

### `src/nativespeaker/api/services/auth.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 37 | imports `AuthIdentity, LinkedIdentity` | imports `LinkedIdentity` and `VerifiedClaims` | D-01 |
| 50 | `Write = Callable[[AuthIdentity, VerifiedProviderIdentity], Awaitable[IdentityProvider]]` | `Callable[[VerifiedClaims, VerifiedProviderIdentity], ...]` | D-08 |
| 52 | `type PostClaim[I, T] = Callable[[I], Awaitable[T]]` | must take two values, or two aliases | D-08, planner's call |
| 76 | `complete(*, identity: AuthIdentity, challenge_id)` | `claims: VerifiedClaims` only | D-08 |
| 84 | `complete_upgrade(*, identity: LinkedIdentity, challenge_id)` | `claims` and `linked` | D-08 |
| 93, 104 | `complete_claim_anonymous_grant`, `complete_claim_registered_grant` | `claims` and `linked` | D-08 |
| 114-118 | `_complete[I: AuthIdentity, T](*, identity: I, ...)` | loses the type variable; takes `claims` and `linked` | D-08 |
| 128 | `verify_binding(located, identity)` | `verify_binding(located, claims, linked)` | D-08 |
| 147 | `settled = await post_claim(identity)` | passes both values | D-08 |
| 159-163 | `_read_then_write(self, identity: AuthIdentity, *, write)`; reads `identity.issuer`, `identity.subject` | `claims` | D-08 |
| 165-211 | `_claim_anonymous_grant(self, identity: LinkedIdentity, *, device_token)` | `claims` and `linked` |  |
| 168, 178 | `identity.identity.provider`, `identity.identity.free_grant_consumed_at` | `linked.identity...` | D-08 |
| 171, 173, 179, 186, 197 | `identity.user.id` | `linked.user.id` | D-08 |
| 198-199 | `issuer=identity.issuer`, `subject=identity.subject` | `claims` — the grant writer records what the request proved | D-08 |
| 213-269 | `_claim_registered_grant` | same split |  |
| 216 | `identity.identity.provider` | `linked.identity.provider` | D-08 |
| 219, 222, 231, 234, 242, 253 | `identity.user.id` | `linked.user.id` | D-08 |
| 254-255 | `issuer=`, `subject=` | `claims` | D-08 |
| 271-286 | `_settle(self, identity: LinkedIdentity, ...)`; reads `identity.user.id` at 280 | `linked` | D-08 |
| 288-296 | `_apply_create_user(self, identity: AuthIdentity, facts)` | `claims` | D-08 |
| 298-329 | `_apply_upgrade(self, identity: AuthIdentity, facts)` | `claims` |  |
| 303-304 | `lock_identity_and_user(issuer=identity.issuer, subject=identity.subject)` | `claims` | D-08 |
| 331-356 | `create_user(*, identity: AuthIdentity, ...)` | `claims` |  |
| 337-338, 345, 353 | `identity.issuer`, `identity.subject`, `insert_account(identity=...)` | `claims` | D-08 |
| 358-366 | `_reject_existing_identity` | unchanged; D-07 makes it the create-user rejection site |  |

`_apply_upgrade` is typed `AuthIdentity` today but only ever receives a `LinkedIdentity`. It
reads `claims` only, so it takes `claims`.

### `src/nativespeaker/api/services/restore.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 29 | imports `LinkedIdentity` | unchanged | — |
| 54 | `restore(self, identity: LinkedIdentity, provider, restore_proof)` | `linked: LinkedIdentity` | D-08 |
| 59 | `destination = identity.user.id` | `linked.user.id` | D-08 |

This is the only read in the file [VERIFIED: grep `identity\.` over
src/nativespeaker/api/services/restore.py returns line 59 alone].

### `src/nativespeaker/api/routers/auth.py`

| Line | Today | Becomes | Decision |
|------|-------|---------|----------|
| 14-15 | imports `get_identity, get_linked_identity` | imports `get_claims, get_identity` | D-04, D-05 |
| 27, 32 | imports `AuthIdentity`, `LinkedIdentity` | imports `LinkedIdentity`; imports `VerifiedClaims` from `auth/jwt_verifier` | D-01 |
| 43 | `APIRouter(..., dependencies=[Depends(get_identity)])` | `Depends(get_claims)` | D-05 |
| 49-54 | `issue_challenge(body, response, identity=Depends(get_identity), session=Depends(get_db), challenge_store=...)` | `claims=Depends(get_claims)`; keeps `session`; calls `IdentitiesDB(session).resolve` itself | D-06 |
| 62 | `if body.operation != AuthOperation.create_user and identity.identity is None` | `linked is None` after the `resolve` call | D-06 |
| 65-67 | `challenge_store.issue(session, operation=..., identity=identity)` | passes `claims=` and `linked=` | D-08 |
| 80-86 | `create_user(body, identity=Depends(get_identity), service=...)` | `claims=Depends(get_claims)`; `service.complete(claims=...)` | D-07 |
| 95-100 | `upgrade_anonymous(..., identity=Depends(get_linked_identity), ...)` | `claims=Depends(get_claims)` **and** `linked=Depends(get_identity)` | D-08 table |
| 110-124 | `claim_anonymous_grant` | `claims` and `linked`; 121 `linked.user.id`; 124 `linked.identity.provider` | D-08 |
| 133-147 | `claim_registered_grant` | same; 144 `linked.user.id`; 147 `linked.identity.provider` | D-08 |
| 156-175 | `restore_subscription` | `linked=Depends(get_identity)` only; 168 `service.restore(linked=...)`; 172 `linked.user.id`; 175 `linked.identity.provider` | D-08 table: no `claims` |
| 183-187 | `sync` | `linked` only; 186 `linked.user.id`; 187 `linked.identity.provider` | D-08 table |
| 196-202 | `sign_out_all(identity=Depends(get_linked_identity), adapter=...)` | `claims` and `linked`; 200 `revoke_with_retry(adapter, claims.issuer, claims.subject)`; 202 `linked.identity.id` | D-08; the comment at 199 stays true |

**Ordering in `issue_challenge`.** Today lines 56-59 check the operation vocabulary, then line 62
checks the row. Keep that order and place the `resolve` call between them. The reason is
measured: `tests/unit/test_challenge_endpoint.py:204` asserts `session.statements == []` for
every body-validation refusal. A `resolve` call at the top of the handler makes that assertion
false.

### `src/nativespeaker/api/routers/users.py`

| Line | Today | Becomes |
|------|-------|---------|
| 5 | imports `get_linked_identity` | imports `get_identity` |
| 10 | `APIRouter(..., dependencies=[Depends(get_linked_identity)])` | `Depends(get_identity)` |
| 19 | `identity: LinkedIdentity = Depends(get_linked_identity)` | `linked: LinkedIdentity = Depends(get_identity)` |
| 22, 25-27 | `identity.user.id`, `identity.user.email`, `identity.user.display_name`, `identity.identity.provider` | `linked.` |

### `src/nativespeaker/api/routers/chats.py`

| Line | Today | Becomes |
|------|-------|---------|
| 7 | imports `get_linked_identity` | imports `get_identity` |
| 14 | router-level `Depends(get_linked_identity)` | `Depends(get_identity)` |
| 21, 34, 52, 69, 83 | `identity: LinkedIdentity = Depends(get_linked_identity)` | `linked: LinkedIdentity = Depends(get_identity)` |
| 23, 36, 54, 71, 85 | `identity.user.id` | `linked.user.id` |

### `src/nativespeaker/api/routers/root.py` — NOT in CONTEXT's scope list

| Line | Today | Becomes |
|------|-------|---------|
| 5 | `from ... import get_chat_service, get_linked_identity` | `get_identity` |
| 9 | `APIRouter(tags=["root"], dependencies=[Depends(get_linked_identity)])` | `Depends(get_identity)` |

The handler declares no identity. Only the router-level name changes.
`tests/e2e/test_admission.py:83` pins `/` at 403 for a never-linked caller.

### `src/nativespeaker/api/routers/examples.py` — NOT in CONTEXT's scope list

| Line | Today | Becomes |
|------|-------|---------|
| 3 | `from ... import get_chat_service, get_linked_identity` | `get_identity` |
| 8 | `APIRouter(tags=["examples"], dependencies=[Depends(get_linked_identity)])` | `Depends(get_identity)` |

`tests/e2e/test_admission.py:83` pins `/examples?lang=en` at 403 too.

### `src/nativespeaker/api/auth/google_play.py`

| Line | Today | Becomes |
|------|-------|---------|
| 240 | a docstring naming `get_identity` | the name still exists, so no edit is required |

## Inventory: `tests/` (24 files)

### Not mechanical — four sites

| File:line | Why it is not a rename | What is needed |
|-----------|----------------------|----------------|
| `tests/unit/test_challenge_endpoint.py:104, 235-245` | `linked_client` overrides `get_identity` with `TEST_IDENTITY`. After D-06 the route resolves from the `get_db` session, whose `exec` returns `_EmptyResult` (lines 46-60), so the caller reads as never-linked | `_RecordingSession` must return `(identity, user)` for the linked fixture |
| `tests/unit/test_challenge_endpoint.py:197-206` | asserts `session.statements == []` on every refusal arm | true only if `resolve` runs after the vocabulary check; otherwise the expectation changes |
| `tests/unit/test_upgrade_precedence.py:158`, `test_claim_precedence.py:261`, `test_claim_precedence_registered.py:141` | each overrides `get_identity` alone and lets `get_linked_identity` derive from it. After D-04/D-05 the chain is reversed | override `get_claims` (a `VerifiedClaims`) **and** `get_identity` (a `LinkedIdentity`) |
| `tests/schema/test_restore_race.py:220-222` | builds `AuthIdentity(issuer=..., subject=..., user=User(id=user_id))` with no `identity` row | D-02 makes `identity` required; build an `ExternalIdentity` too |

### The pinning tests that name the dependencies

| File:line | What it asserts | Change |
|-----------|-----------------|--------|
| `tests/unit/test_app_wiring.py:8-9` | imports both names | rename |
| `:19` | `PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}` | unchanged; both declare `get_claims` only |
| `:57-62` | every route but the exemptions declares `get_linked_identity` | keys on the new `get_identity` |
| `:64-69` | the preauth-callable routes declare `get_identity` | keys on `get_claims` |
| `:71-80` | seven named routes declare `get_linked_identity` | keys on `get_identity` |
| `:92-98` | the public allowlist is exactly `/health/ready` | both names change |
| `:100-105` | no route serves without one of the two | both names change |
| `:107-113` | no route declares a wrapper around an accessor | both names change |
| `:132-138` | callback routes declare neither identity | both names change |
| `:183-255` | one verify and one query for a doubly declared route; imports `AuthIdentity, LinkedIdentity` at 193; the handler at 239-240 declares both | rewrite: `who: LinkedIdentity = Depends(get_identity)` and `admitted: VerifiedClaims = Depends(get_claims)`; line 241 compares `who.user is admitted.user`, which no longer typechecks |

| `tests/unit/test_identity_accessors.py` line | What it asserts | Change |
|-----------|-----------------|--------|
| `:15, 25` | imports `AuthIdentity`; `ACCESSORS = (get_identity, get_linked_identity)` | `(get_claims, get_identity)` |
| `:33-53` | `_linked()` and `_unlinked()` build `AuthIdentity` | `LinkedIdentity` and `VerifiedClaims` |
| `:102-111` | two probe routes, one per accessor | rename |
| `:107` | `{"linked": identity.user is not None}` | a `VerifiedClaims` has no `user` |
| `:152-156` | a refused token opens no session | criterion 2's pin — keep |
| `:159-185` | `TestTheNarrowingHoldsInBothDirections`, four cases | rename; 175-179 still admits a never-linked caller on the `get_claims` route |
| `:254-260` | no accessor declares an optional return | keep; both still return a non-optional |
| `:276-280` | `get_identity` takes `["request", "credential"]`; `get_linked_identity` takes `["identity"]` | the new `get_claims` takes `["request", "credential"]`; the new `get_identity` takes `["request", "claims"]` |
| `:287-297` | one session, one statement, closed before the handler | criterion 2's pin — keep |
| `:300-331` | `TestTheIdentityShape`, six cases | deleted by D-11 |
| `:334-346` | `TestNoClientAddressIsCarried`, two cases over `AuthIdentity` | the string-field case has no subject after D-02; `tests/unit/test_jwt_security.py:207-227` already pins `VerifiedClaims.__dataclass_fields__ == ["issuer", "subject"]` |

### Every remaining test site

| File:line | Today | Becomes |
|-----------|-------|---------|
| `tests/unit/conftest.py:17, 188` | imports and overrides `get_linked_identity` | `get_identity` |
| `tests/unit/conftest.py:34, 115-126` | `TEST_IDENTITY = LinkedIdentity(user=..., identity=..., issuer=..., subject=...)` | drop `issuer=` and `subject=` |
| `tests/unit/conftest.py:253-254` | `FakeChallengeStore.verify_binding(self, row, identity)` | follow `ChallengesDB.verify_binding`'s new signature |
| `tests/unit/test_identities_crud.py:60-83` | `_resolve`, `_rejected`, `_drive` each pass `allow_preauth=preauth_callable` | drop the parameter |
| `:89-98` | two cases asserting the unlinked shape | deleted by D-11; replace with one case asserting `resolve` returns `None` |
| `:100-109` | `PreAuthIdentityNotAllowed` for no row | moves to `get_identity`; the crud case is deleted |
| `:120-125, 174-178` | `preauth_callable=True` on the rejection arms | drop the argument; the rejections are unchanged |
| `tests/unit/test_exception_handlers.py:356-362` | `resolve(..., allow_preauth=False)` in the admission fixture | drop the argument |
| `tests/schema/test_claim_race.py:246-251` | `resolve_identity` calls `resolve(..., allow_preauth=False)` | drop the argument |
| `tests/schema/test_claim_race.py:261-262` | `identity.user`, `identity.identity` | `linked.` |
| `tests/schema/test_create_atomicity.py:16, 69-71, 166` | `identity_for(...) -> AuthIdentity`; `identity: AuthIdentity \| None = None` | `VerifiedClaims` |
| `tests/schema/test_create_race.py:16, 144, 158` | `identity: AuthIdentity` on the attempt record; `AuthIdentity(issuer=..., subject=...)` | `VerifiedClaims` |
| `tests/schema/test_restore_race.py:17, 220-222` | `identity_of(user_id) -> AuthIdentity` with `user=` only | `LinkedIdentity` with both rows |
| `tests/e2e/test_challenge_store.py:16, 35-36` | `preauth(...) -> AuthIdentity` | `VerifiedClaims` |
| `tests/e2e/test_challenge_store.py:298, 311-312, 328-329` | `AuthIdentity(user=..., identity=..., issuer=..., subject=...)` | `LinkedIdentity(user=..., identity=...)`; `issue` and `verify_binding` take `claims` and `linked` |
| `tests/unit/test_challenge_ids.py:19, 77-90` | `linked_identity()` and `preauth_identity()` return `AuthIdentity` | `LinkedIdentity` and `VerifiedClaims` |
| `tests/unit/test_challenge_ids.py:93-100, 167, 220-294` | `issue(session, operation=..., identity=...)`, `verify_binding(row, identity)` | pass `claims=` and `linked=` |
| `tests/unit/test_create_user_body.py:13, 17, 82-83` | `AuthIdentity(issuer=..., subject=...)`; overrides `get_identity` | `VerifiedClaims`; override `get_claims` |
| `tests/unit/test_create_user_precedence.py:13, 26, 131-132, 141` | same shape | `VerifiedClaims`; override `get_claims` |
| `tests/unit/test_create_user_rollback.py:10, 71-72, 78` | `AuthIdentity(issuer=..., subject=...)`; `service.create_user(identity=...)` | `VerifiedClaims`; `claims=` |
| `tests/unit/test_conflict_classification.py:21, 111-112` | `_identity() -> AuthIdentity` unlinked | `VerifiedClaims` |
| `tests/unit/test_upgrade_precedence.py:14, 21, 137-140, 158` | `AuthIdentity` with rows; overrides `get_identity` | see "Not mechanical" above |
| `tests/unit/test_claim_precedence.py:17, 26, 232-235, 261` | same | see "Not mechanical" above |
| `tests/unit/test_claim_precedence_registered.py:15, 24, 112-115, 141` | same | see "Not mechanical" above |
| `tests/unit/test_challenge_endpoint.py:17, 22, 85, 97` | overrides `get_identity` with an unlinked `AuthIdentity` | override `get_claims` with a `VerifiedClaims` |
| `tests/unit/test_users_me.py:14, 75-83, 87, 93, 107` | `LinkedIdentity(issuer=..., subject=..., user=..., identity=...)`; overrides `get_linked_identity` | drop `issuer=`/`subject=`; override `get_identity` |
| `tests/unit/test_restore_proof.py:26, 620-629` | `LinkedIdentity(issuer=..., subject=..., user=..., identity=...)` | drop `issuer=`/`subject=` |
| `tests/unit/test_restore_proof.py:640-1166` | `service.restore(identity=_caller(), ...)`, 11 call sites | `linked=` |
| `tests/unit/test_auth_security.py:8, 38` | `_probe(identity: AuthIdentity = Depends(get_linked_identity))` | `linked: LinkedIdentity = Depends(get_identity)` |
| `tests/unit/test_jwks_offload.py:16, 105` | same shape | same |
| `tests/unit/test_google_play_notifications.py:843` | a docstring naming `get_identity` | no edit needed |

## Common Pitfalls

### Pitfall 1: `AuthIdentity` does not survive the grep

**What goes wrong:** `grep -rn 'AuthIdentity' src tests` matches `PreAuthIdentityNotAllowed`
28 times where `grep -rn '\bAuthIdentity\b'` matches 24. Criterion 1 reads "`AuthIdentity` does
not exist in `src/` or `tests/`". A plain grep on the phase gate always prints matches.
**How to avoid:** the gate command is `grep -rn '\bAuthIdentity\b' src tests`, and it must print
nothing. `PreAuthIdentityNotAllowed` stays in `errors.py:362` and is raised from two new places.

### Pitfall 2: the FastAPI cache keys on the callable

**What goes wrong:** `get_identity` declares `get_claims`. A route declaring both gets one
token verification, because FastAPI caches solver-resolved sub-dependencies.
`app/dependencies.py:79` already carries the comment. A helper that wraps either name breaks the
cache and verifies twice.
**How to avoid:** `tests/unit/test_app_wiring.py:107-113` fails on a `wraps` wrapper, and
`:186-255` counts one verify and one query. Keep both cases green.

### Pitfall 3: `resolve` opens a second session on the challenge route

**What goes wrong:** D-06 makes the challenge route call `IdentitiesDB(session).resolve` on the
`get_db` session. `get_identity` opens its own short session. If the challenge route declared
`get_identity` too, one request would issue two identical SELECTs.
**How to avoid:** the challenge route declares `get_claims` and `get_db` only, never
`get_identity`. `tests/unit/test_app_wiring.py:92-105` reads the declarations off the live app.

### Pitfall 4: the dataclass field order

**What goes wrong:** today `LinkedIdentity` inherits `issuer` and `subject` first, so every
constructor that passes positional arguments passes them in that order. After D-02 the first
two positions are `user` and `identity`.
**How to avoid:** every construction site in `tests/` uses keyword arguments today
[VERIFIED: all 20 `LinkedIdentity(` and `AuthIdentity(` sites listed above use `name=`], so
deleting `issuer=` and `subject=` is enough. Do not add positional calls.

### Pitfall 5: `ty` diagnostics are a control, not a target

**What goes wrong:** the tree carries 311 diagnostics. A phase that reads the number as a target
spends time on pre-existing findings.
**How to avoid:** re-measure `ty check` at the end. The number must not rise above 311. Six of
the in-scope files already appear in the output.

### Pitfall 6: the pre-existing failing case

**What goes wrong:** `-m ''` and `-m e2e` both exit 1 today on one restore case. A plan that
requires exit 0 cannot pass.
**How to avoid:** criterion 5 is met when the failure set is exactly that one case. Compare the
short test summary, not the exit code.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 with pytest-asyncio >=1.3, `asyncio_mode = "auto"` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` |
| Full suite command | `.venv/bin/pytest -q -m ''` then `-m e2e` then `-m schema` |

`addopts` carries `-m 'not e2e and not schema'`. A bare `pytest` deselects 658 cases.

### Success criterion to test map

| Criterion | Pinned by | Automated command |
|-----------|-----------|-------------------|
| 1 — `AuthIdentity` gone, `LinkedIdentity` has two fields, no base class | `grep -rn '\bAuthIdentity\b' src tests` prints nothing; a new case over `LinkedIdentity.__dataclass_fields__` replacing `test_identity_accessors.py:304` | `grep`, then `.venv/bin/pytest -q tests/unit/test_identity_accessors.py` |
| 2 — `get_claims` issues no SQL; `get_identity` answers `PreAuthIdentityNotAllowed`; `resolve` has no `allow_preauth` and keeps the three rejections | `test_identity_accessors.py:152-156, 162-166, 287-297`; `test_identities_crud.py:112-186`; `test_exception_handlers.py:350-370` | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py` |
| 3 — no `.user`/`.identity` off anything but a `LinkedIdentity`; no `LinkedIdentity \| None` outside `crud/challenges.py`; the challenge route still admits a never-linked caller for `create_user` only | `test_app_wiring.py:54-113`; `test_challenge_endpoint.py`; `tests/e2e/test_admission.py:78-87`; `grep -rn 'LinkedIdentity | None' src` returns `crud/challenges.py` alone | `.venv/bin/pytest -q tests/unit/test_app_wiring.py tests/unit/test_challenge_endpoint.py`; `.venv/bin/pytest -q -m e2e tests/e2e/test_admission.py` |
| 4 — tests build `VerifiedClaims` or `LinkedIdentity`; no test asserts a `None` row field or passes `allow_preauth` | `grep -rn 'allow_preauth\|preauth_callable' tests` prints nothing | `grep` |
| 5 — three suites exit 0 | the whole suite | the three pytest commands, with the one pre-existing failure named |

### Sampling rate

- **Per task commit:** `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` and `.venv/bin/ruff check src tests`
- **Per wave merge:** `.venv/bin/pytest -q -m ''`
- **Phase gate:** all three suites plus `ruff` and `ty`, each run rather than copied

### Wave 0 gaps

None. Every criterion has an existing test file. Two cases must be **written**, not only
renamed:

- [ ] a replacement for `test_identity_accessors.py:300-331` asserting
      `sorted(LinkedIdentity.__dataclass_fields__) == ["identity", "user"]`, that the class is
      frozen and slotted, and that it has no base class beyond `object`
- [ ] a case in `tests/unit/test_identities_crud.py` asserting `resolve` returns `None` for no
      row, which replaces the two deleted unlinked-shape cases

## Security Domain

The phase changes the authentication barrier. It adds no new control.

| ASVS category | Applies | Standard control in this repo |
|---------------|---------|-------------------------------|
| V2 Authentication | yes | `JWTVerifier.verify` in `auth/jwt_verifier.py`, unchanged |
| V3 Session Management | no | Envoy Gateway holds the JWT check; this service has no session |
| V4 Access Control | yes | `get_identity` is the account check; `resolve` raises the three rejections |
| V5 Input Validation | yes | `ChallengeRequest.operation` is a bounded `str`; unchanged |
| V6 Cryptography | no | nothing cryptographic is touched |

| Threat | STRIDE | Mitigation this phase must preserve |
|--------|--------|-------------------------------------|
| A never-linked caller reaches an account route | Elevation of privilege | `get_identity` raises `PreAuthIdentityNotAllowed`; `test_app_wiring.py:57-62` and `tests/e2e/test_admission.py:78-87` |
| A historical row or blocked user is admitted | Elevation of privilege | `resolve` lines 45-53; `tests/e2e/test_admission.py:94-137` |
| A caller spends another caller's challenge | Spoofing | `ChallengesDB.verify_binding`; `tests/e2e/test_challenge_store.py:306-335` |
| A route reads the stored row instead of the request-verified values | Repudiation | D-08: sign-out-all and the grant writers read `claims` |
| A refused token opens a database connection | Denial of service | `get_claims` reads no table; `test_identity_accessors.py:152-156` |

**One accepted weakening, from D-07.** Create-user loses its pre-claim rejection for a
historical row and a blocked user. `AuthService._reject_existing_identity`
(`services/auth.py:358-366`) answers the same status and code after the claim. The caller spends
one challenge. It is refused either way. Record it in `.planning/WINDOWS.md`.

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | `routers/root.py` and `routers/examples.py` are in scope, although CONTEXT's "In scope" list omits them | Summary, `src/` inventory | Criterion 3 fails and `tests/e2e/test_admission.py:83` goes red |
| A2 | `resolve` is called after the `AuthOperation` vocabulary check in `issue_challenge` | Pitfall, `routers/auth.py` | `test_challenge_endpoint.py:204` goes red |
| A3 | `PostClaim[I, T]` becomes two parameters rather than a tuple or a new value class | `services/auth.py` inventory | Rework inside `_complete`; D-08 names the values but not the alias shape |
| A4 | `crud/` may import `VerifiedClaims` from `auth/jwt_verifier.py` | The two types | AGENTS.md § Package layout gives no ruling; `jwt_verifier.py` imports nothing from this project, so no cycle can arise |
| A5 | The 2579-case count for `-m ''` is 7 higher than the 2572 STATE.md records for Phase 47 | Baseline | None for this phase; the counts were measured today, and the failing set is the same one case |

## Open Questions

1. **Does `LinkedIdentity` keep `slots=True`?**
   - What we know: D-02 says frozen and slotted.
   - What's unclear: nothing. It is locked.
2. **What replaces `test_identity_accessors.py:343-346`?**
   - What we know: the case asserts the only `str` fields are `issuer` and `subject`. After D-02
     `LinkedIdentity` has no `str` field at all.
   - Recommendation: delete it. `tests/unit/test_jwt_security.py:207-227` already pins
     `VerifiedClaims`, which is where a client address could now arrive.
3. **Does `_complete` still need `verify_binding` to take both values?**
   - What we know: create-user binds on `claims`, the other three bind on `linked.identity.id`.
   - Recommendation: keep one signature taking both, as D-08 states. One method, one precedence.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/pytest` | every criterion | yes | pytest >=9.0 | — |
| `.venv/bin/ruff` | the lint gate | yes | prints `All checks passed!` | — |
| `.venv/bin/ty` | the type control | yes | reads 311 diagnostics | — |
| PostgreSQL on localhost:5432 | `-m schema`, `-m e2e` | yes | both suites ran and collected | — |
| `pg_isready` | — | no | — | run the suites; they prove the server |

## Sources

### Primary (HIGH confidence)
- The working tree at HEAD `937864c`, read and grepped in this session. Every file:line above.
- `.venv/bin/ruff`, `.venv/bin/ty`, `.venv/bin/pytest`, run in this session.

### Secondary (MEDIUM confidence)
- `.planning/phases/48-.../48-CONTEXT.md` — D-01 to D-11.
- `.planning/STATE.md` — the Phase 47 outcome and the pre-existing failing case.
- `AGENTS.md` — package layout, comments and docstrings, function shape.

## Metadata

**Confidence breakdown:**
- Inventory: HIGH — every line was read or grepped today.
- Baseline: HIGH — every command was run today, not copied.
- The four non-mechanical sites: HIGH — each was read in full.
- A3 (the `PostClaim` alias): MEDIUM — the planner decides the shape.

**Research date:** 2026-09-16
**Valid until:** the next commit to `src/nativespeaker/api/` or `tests/`
