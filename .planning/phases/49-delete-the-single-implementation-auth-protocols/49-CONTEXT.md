# Phase 49: Delete the single-implementation auth Protocols - Context

**Gathered:** 2026-09-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Behavior-preserving refactor. The four Protocols in `auth/` that have one implementation are
deleted (`PlaySubscriptionSource`, `FirebaseAdminAdapter`, `DeviceCheckAdapter`,
`TokenVerifier`), and each annotation names the concrete class. `VerifiedProviderIdentity` moves
to `auth/firebase.py` and `auth/adapters.py` is removed. The lifespan stops building
`ChallengesDB`; `AuthService` and the challenge route build it themselves, and
`get_challenge_store` is deleted.

**In scope:** `auth/{adapters,devicecheck,firebase,google_play,jwt_verifier}.py`,
`crud/challenges.py`, `services/{auth,restore}.py`, `app/{dependencies,lifespan}.py`,
`routers/auth.py`, and the unit, e2e and schema tests that name a Protocol, override
`get_challenge_store`, or build a `ChallengesDB` or an `AuthService`.

**Out of scope:** the concrete adapter classes, the build callables, the retry helpers and the
value types (the ROADMAP goal leaves them alone); the rest of the lifespan and `app.state`
(Phase 50); any change to a route's status code or body; both matched todos.

</domain>

<decisions>
## Implementation Decisions

The ROADMAP goal and its five criteria fix most of this phase. The decisions below are the
points the goal left open.

### `ChallengesDB`

- **D-01: `ChallengesDB(db)` holds the session**, as `IdentitiesDB(db)` and `GrantsDB(db)` do.
  `issue`, `locate`, `claim` and `consume` lose their `session` parameter and read
  `self.session`. `verify_binding` does not read the session and keeps its parameters. No ROADMAP
  criterion asks for this; the user chose it so the three crud classes `AuthService` builds have
  one shape. Every one of the 8 `ChallengesDB()` sites in `src/` and `tests/` changes. A test
  that uses one store across many sessions (`tests/e2e/test_challenge_store.py`, the schema race
  tests) builds one `ChallengesDB` per session. The class docstring and `__repr__` follow the new
  shape.
- **D-02: `AuthService` names the attribute `self.challenges_db`**, beside `self.identities_db`
  and `self.grants_db`, built as `ChallengesDB(db)` in `__init__`. The four read sites
  (`services/auth.py:136, 142, 146, 400`) follow. The word "store" does not name this class in
  new code or new comments.

### The challenge route

- **D-03: `issue_challenge` calls `ChallengesDB(session).issue(...)` in the route**, as it calls
  `IdentitiesDB(session).resolve` two lines above. The `challenge_store` parameter and the
  `get_challenge_store` import go. No new `AuthService` method: the route would then pull the
  Firebase and DeviceCheck dependencies, which it does not use.

### The tests that replaced the dependency

- **D-04: One fixture in `tests/unit/conftest.py` serves the four precedence suites.**
  `FakeChallengeStore` stays in `conftest.py`, one copy. The fixture builds it, monkeypatches
  `ChallengesDB.locate`, `claim` and `consume` to call it, and returns it, so the suites still
  read `store.row` and `store.consume_calls`. `verify_binding` stays the real method; the fake's
  `self._binding = ChallengesDB()` and its `verify_binding` pass-through go if nothing else
  needs them. The per-file `store` fixtures and the `dependency_overrides[get_challenge_store]`
  lines in the four suites are removed.
- **D-05: `test_challenge_endpoint.py` and `test_create_user_body.py` each keep their own `_RecordingChallengeStore`**
  and monkeypatch `ChallengesDB.issue` in their own `store` fixture.
  The two recorders differ, so they are not merged.
- The tests that build `AuthService(..., challenge_store=...)` drop the argument
  (`test_create_user_rollback.py`, `test_conflict_classification.py`, `test_create_race.py`,
  `test_create_atomicity.py`, `test_claim_race.py`). `tests/e2e/test_challenge_store.py` no
  longer reads `app.state.challenge_store`.

### Annotations

- **D-06: `AuthService.__init__` annotates `adapter` as `FirebaseAdminLookup` and `devicecheck` as `AppleDeviceCheck`; `get_auth_service` annotates `adapter` the same way.**
  Today
  all three are unannotated. No criterion asks for this; the phase already edits both signatures
  to remove `challenge_store`, and `ty` then checks the calls. No `| None`: the lifespan always
  builds both (`lifespan.py:171, 180`). The 7 test sites that pass `adapter=None` do not change;
  tests are not type-checked.

### Records

- **D-07: The Phase 49 entry in `ROADMAP.md` is amended in the discuss commit** to name D-01:
  the goal says `ChallengesDB` takes the session in its constructor, and criterion 4 names
  `ChallengesDB(db)`. `REQUIREMENTS.md` maps nothing to this phase and is not edited.
- **D-08: Each seam commit that changes the `auth/` count updates `CURRENT` in `tests/unit/test_auth_package_shape.py`**,
  as 37a5ac6 did. The test compares a literal with a
  live count, so a tuple changed once at the end fails the unit suite at each commit before it.
  The user chose this at planning, 2026-09-16; ROADMAP criterion 5 is amended to match.

### Carried forward

- 37a5ac6 is the model for each Protocol: the Protocol and its docstrings are deleted, not moved
  onto the concrete class; the consumer's annotation names the class; a test that asserted "the
  class satisfies the Protocol" is deleted.
- 48 D-10: every comment this phase writes is ASD-STE100, one line, only where needed. Delete
  every comment whose subject is a removed Protocol, "the seam", or `get_challenge_store` (for
  example `dependencies.py:111, 119`).

### Claude's Discretion

- The order of the five commits (four Protocols, then or before the `ChallengesDB` change). The
  ROADMAP fixes one seam per commit and the three suites green at each; D-08 fixes the
  `test_auth_package_shape.py` tuple.
- Whether D-01 and the removal of `get_challenge_store` are one commit or two.
- Whether `tests/unit/test_adapter_interfaces.py` is deleted when criterion 3 leaves it empty.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The phase entry
- `.planning/ROADMAP.md` Phase 49 — the goal and the five criteria, as amended by D-07.
- `.planning/ROADMAP.md` Phase 50 — depends on this phase; it rewrites `lifespan.py` and
  `dependencies.py` after the challenge store has left both.

### The model commit
- `git show 37a5ac6` — "refactor: drop the StoreNotificationVerifier protocol"; the pattern for
  each of the four Protocols.

### Prior-phase decisions
- `.planning/phases/48-narrow-identity-to-the-verified-pair/48-CONTEXT.md` — D-08
  (`ChallengesDB.issue` and `verify_binding` take `claims` and `linked`), D-10 (comment rule).

### Conventions
- `AGENTS.md` (repo root) — package layout, comment and docstring rules.

No spec file: Phases 47 to 50 are refactors added after the spec phases closed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/auth.py:64-76` — `AuthService.__init__`; builds `IdentitiesDB(db)` and `GrantsDB(db)`,
  takes `challenge_store`, `adapter` and `devicecheck`.
- `crud/challenges.py:37` — `ChallengesDB`, no constructor, session on each method.
- `tests/unit/conftest.py:236` — `FakeChallengeStore`, imported by the four precedence suites.
- `tests/unit/test_conversion_carries_usage.py:83-104` — `monkeypatch.setattr(GrantsDB, ...)`,
  the pattern the ROADMAP goal names for D-04 and D-05.

### Established Patterns
- A crud class takes the session in its constructor and is built where it is used
  (`IdentitiesDB(session).resolve` in `routers/auth.py`).
- `PubSubPushTokens.__init__` (`auth/google_play.py:211`) takes `TokenVerifier | None` and a
  `build` callable that returns one; both become `JWTVerifier`.

### Integration Points
- The Protocols: `auth/adapters.py:21`, `auth/devicecheck.py:46`, `auth/google_play.py:124`,
  `auth/jwt_verifier.py:69`. Their annotation sites: `auth/firebase.py:178, 198`,
  `auth/devicecheck.py:182, 187`, `auth/google_play.py:211-212`, `services/restore.py:44`,
  `app/dependencies.py:117, 123, 131`.
- `VerifiedProviderIdentity` is imported from `auth/adapters.py` by `auth/firebase.py:14` and
  `services/auth.py:10`.
- The challenge store: `app/lifespan.py:42, 162`, `app/dependencies.py:112-114, 129, 134`,
  `routers/auth.py:11, 21, 54, 68`.
- Six unit files override `get_challenge_store`; five test files pass `challenge_store=` to
  `AuthService`; `tests/e2e/test_challenge_store.py:33` reads `app.state.challenge_store`.

</code_context>

<specifics>
## Specific Ideas

- The user asks "what requirement is that?" of a change the ROADMAP does not name. D-01 and
  D-06 are the two such changes, both chosen by the user. Add no other.
- Name things by their identifiers: `ChallengesDB`, `challenges_db`, `AuthService`,
  `FirebaseAdminLookup`, `AppleDeviceCheck`, `JWTVerifier`, `PlayDeveloperSubscriptions`.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.6) — chats; matched on the words "ordering",
  "phase", "two". Not folded, as in Phases 46 and 48.
- `secret-manager-integration` (score 0.6) — config; matched on the words "google", "phase".
  Not folded, as in Phases 46 and 48.

</deferred>

---

*Phase: 49-delete-the-single-implementation-auth-protocols*
*Context gathered: 2026-09-16*
