# Phase 49: Delete the single-implementation auth Protocols - Research

**Researched:** 2026-09-16
**Domain:** Internal Python refactor — `nativespeaker.api.auth` package, `crud/challenges.py`, FastAPI dependencies
**Confidence:** HIGH (every finding below was read out of this repository this session)

No external package is added or changed by this phase, so there is no Package Legitimacy Audit and no
web research. Every claim is `[VERIFIED: path:lines]` unless tagged otherwise.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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
- **D-03: `issue_challenge` calls `ChallengesDB(session).issue(...)` in the route**, as it calls
  `IdentitiesDB(session).resolve` two lines above. The `challenge_store` parameter and the
  `get_challenge_store` import go. No new `AuthService` method: the route would then pull the
  Firebase and DeviceCheck dependencies, which it does not use.
- **D-04: One fixture in `tests/unit/conftest.py` serves the four precedence suites.**
  `FakeChallengeStore` stays in `conftest.py`, one copy. The fixture builds it, monkeypatches
  `ChallengesDB.locate`, `claim` and `consume` to call it, and returns it, so the suites still
  read `store.row` and `store.consume_calls`. `verify_binding` stays the real method; the fake's
  `self._binding = ChallengesDB()` and its `verify_binding` pass-through go if nothing else
  needs them. The per-file `store` fixtures and the `dependency_overrides[get_challenge_store]`
  lines in the four suites are removed.
- **D-05: `test_challenge_endpoint.py` and `test_create_user_body.py` each keep their own
  `_RecordingChallengeStore`** and monkeypatch `ChallengesDB.issue` in their own `store` fixture.
  The two recorders differ, so they are not merged.
- The tests that build `AuthService(..., challenge_store=...)` drop the argument
  (`test_create_user_rollback.py`, `test_conflict_classification.py`, `test_create_race.py`,
  `test_create_atomicity.py`, `test_claim_race.py`). `tests/e2e/test_challenge_store.py` no
  longer reads `app.state.challenge_store`.
- **D-06: `AuthService.__init__` annotates `adapter: FirebaseAdminLookup` and
  `devicecheck: AppleDeviceCheck`; `get_auth_service` annotates `adapter` the same way.** Today
  all three are unannotated. No criterion asks for this; the phase already edits both signatures
  to remove `challenge_store`, and `ty` then checks the calls. No `| None`: the lifespan always
  builds both (`lifespan.py:171, 180`). The 7 test sites that pass `adapter=None` do not change;
  tests are not type-checked.
- **D-07: The Phase 49 entry in `ROADMAP.md` is amended in the discuss commit** to name D-01:
  the goal says `ChallengesDB` takes the session in its constructor, and criterion 4 names
  `ChallengesDB(db)`. `REQUIREMENTS.md` maps nothing to this phase and is not edited.
- 37a5ac6 is the model for each Protocol: the Protocol and its docstrings are deleted, not moved
  onto the concrete class; the consumer's annotation names the class; a test that asserted "the
  class satisfies the Protocol" is deleted.
- 48 D-10: every comment this phase writes is ASD-STE100, one line, only where needed. Delete
  every comment whose subject is a removed Protocol, "the seam", or `get_challenge_store` (for
  example `dependencies.py:111, 119`).

### Claude's Discretion

- The order of the five commits (four Protocols, then or before the `ChallengesDB` change). The
  ROADMAP fixes one seam per commit, the three suites green at each, and the
  `test_auth_package_shape.py` tuple changed once at the end.
- Whether D-01 and the removal of `get_challenge_store` are one commit or two.
- Whether `tests/unit/test_adapter_interfaces.py` is deleted when criterion 3 leaves it empty.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

Reviewed todos not folded: `message-ordering-is-unspecified`, `secret-manager-integration`.
</user_constraints>

## Project Constraints (from AGENTS.md)

- First version of a startup app; no users yet. Do not over-engineer for theft of the product.
- Do not skip normal security measures. This phase touches no security control: the challenge
  binding, expiry and claim logic are moved, not changed.
- Keep specs short. Programming this app must not consume many tokens.
- Runs in Kubernetes behind Envoy Gateway (JWT auth, IP/user/URL rate limits). Not touched here.
- Codebase terms only: dependency, handler, service, crud, adapter. Do not coin new nouns.

## Summary

This is a mechanical, behaviour-preserving refactor with two independent halves. The first half
deletes four `Protocol` classes and repoints each annotation at the concrete class; commit 37a5ac6
is the exact template and includes the test-side moves. The second half gives `ChallengesDB` a
session-holding constructor like its two sibling crud classes, takes it off the lifespan and out of
`dependencies.py`, and converts six unit suites from `dependency_overrides[get_challenge_store]` to
`monkeypatch.setattr(ChallengesDB, ...)`.

The Protocol half is small and verifiable: 4 class definitions, 9 annotation sites in `src/`, 5 test
files. The `ChallengesDB` half is the bulk of the work: **~35 method call sites in
`tests/e2e/test_challenge_store.py` alone** plus 15 in `tests/unit/test_challenge_ids.py`, because
every `store.claim(session, ...)` becomes `ChallengesDB(session).claim(...)`.

One criterion as written cannot hold — see **Open Question 1**: `tests/unit/test_auth_package_shape.py`
goes red on the *first* Protocol deletion, so "the tuple changes once at the end" and "the three
suites exit 0 at every commit" are in direct conflict. The model commit 37a5ac6 resolves it by
changing the tuple in the same commit as the seam.

**Primary recommendation:** follow 37a5ac6 literally, one seam per commit, and carry the
`test_auth_package_shape.py` tuple in each seam commit rather than once at the end.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Protocol declaration and deletion | `auth/` adapter modules | — | Each Protocol sits beside its one implementation |
| Value type `VerifiedProviderIdentity` | `auth/firebase.py` | — | ROADMAP moves it to the module that produces it |
| Challenge row reads and writes | `crud/challenges.py` | — | Crud owns statements; it gains the session like its siblings |
| Challenge lifecycle across a completion | `services/auth.py` | — | The service owns locate → verify → claim → consume |
| Issuing one challenge | `routers/auth.py` | — | The handler already builds `IdentitiesDB(session)` inline |
| Object construction at boot | `app/lifespan.py` | — | Loses the `ChallengesDB` it should never have owned |
| Request-scoped wiring | `app/dependencies.py` | — | Loses `get_challenge_store` entirely |

## Standard Stack

No library is added, removed or upgraded. Verified tooling in this checkout:

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.14.7 | `.venv/bin/python --version` [VERIFIED: run this session] |
| pytest | present at `.venv/bin/pytest` | the three suites [VERIFIED] |
| ruff | 0.15.7, `line-length = 120`, `select = ["E","W","F","I","UP"]` | [VERIFIED: pyproject.toml:78-83] |
| ty | present at `.venv/bin/ty` | `ty check` — baseline **306** diagnostics [VERIFIED: 48-VERIFICATION.md:82] |

## The model commit — 37a5ac6

`git show 37a5ac6` — "refactor: drop the StoreNotificationVerifier protocol". Four files, +8/−33.
The pattern, in order [VERIFIED: git show 37a5ac6, run this session]:

1. Delete the `class X(Protocol):` block **and** its docstrings from the adapter module; drop
   `from typing import Protocol` when nothing else in the module uses it.
2. Repoint the consumer's import and annotation at the concrete class
   (`StoreNotificationVerifier` → `AppStoreNotifications` in `services/restore.py:44`).
3. Delete the test that asserted "the class satisfies the Protocol" — *"a class cannot fail to be
   itself"*.
4. **Keep** the "seam is the annotation" guard, rewritten against the concrete class: the
   `typing.get_protocol_members(P) <= set(dir(C))` assertion becomes a plain
   `assert {"verify", "verify_transaction"} <= set(dir(AppStoreNotifications))`, and the annotation
   assertion becomes `annotations["app_store"] is AppStoreNotifications`.
5. Update `CURRENT` in `tests/unit/test_auth_package_shape.py` **in the same commit**
   (`(8, 25, 70)` → `(8, 24, 68)`).

Note that step 4 diverges from ROADMAP criterion 3 for the two remaining seam classes, which says
`TestTheSeamIsTheAnnotation` and `TestThePushTokenSeamIsTheAnnotation` are **deleted**. The ROADMAP
wins; 37a5ac6 kept its one because WR-18 recorded a specific defect. See Pitfall 3.

## Enumeration: the four Protocols

### `PlaySubscriptionSource` → `PlayDeveloperSubscriptions`

| Site | What |
|------|------|
| `src/nativespeaker/api/auth/google_play.py:124-135` | the `class PlaySubscriptionSource(Protocol)` block, 2 methods [VERIFIED] |
| `src/nativespeaker/api/auth/google_play.py:248` | `class PlayDeveloperSubscriptions` — the one implementation [VERIFIED] |
| `src/nativespeaker/api/services/restore.py:13` | import [VERIFIED] |
| `src/nativespeaker/api/services/restore.py:44` | `play: PlaySubscriptionSource` annotation [VERIFIED] |

**No test names it.** Smallest seam: 4 edits, zero test edits.

### `FirebaseAdminAdapter` → `FirebaseAdminLookup`, and the `auth/adapters.py` removal

| Site | What |
|------|------|
| `src/nativespeaker/api/auth/adapters.py:21-30` | the Protocol, 2 methods [VERIFIED] |
| `src/nativespeaker/api/auth/adapters.py:9-18` | `VerifiedProviderIdentity` — moves to `auth/firebase.py` [VERIFIED] |
| `src/nativespeaker/api/auth/firebase.py:14` | imports both names from `adapters` [VERIFIED] |
| `src/nativespeaker/api/auth/firebase.py:62` | `class FirebaseAdminLookup` [VERIFIED] |
| `src/nativespeaker/api/auth/firebase.py:178, 198` | `adapter: FirebaseAdminAdapter` in `lookup_with_retry` / `revoke_with_retry` [VERIFIED] |
| `src/nativespeaker/api/app/dependencies.py:9, 117` | import and `get_firebase_adapter` return type [VERIFIED] |
| `src/nativespeaker/api/services/auth.py:10` | imports `VerifiedProviderIdentity` from `adapters` [VERIFIED] |
| `tests/unit/test_adapter_interfaces.py:11, 12, 24, 137-158` | the whole file is built on the module — see Pitfall 1 [VERIFIED] |
| `tests/unit/test_firebase_adapter.py:594-595` | `TestTheDeliberateNonImplementations` — the inheritance assertion, deleted by criterion 3 [VERIFIED] |

`VerifiedProviderIdentity` importers that must be repointed at `auth/firebase.py`
[VERIFIED: grep over `src tests`, this session]:

`src/nativespeaker/api/services/auth.py:10` · `src/nativespeaker/api/auth/firebase.py:14` ·
`tests/unit/conftest.py:20` · `tests/unit/test_adapter_interfaces.py:12` ·
`tests/unit/test_firebase_retry.py:7` · `tests/unit/test_upgrade_precedence.py:18` ·
`tests/unit/test_firebase_adapter.py:8` · `tests/unit/test_create_user_precedence.py:16` ·
`tests/e2e/test_upgrade_anonymous.py:10` · `tests/e2e/test_create_user.py:9` ·
`tests/e2e/test_flows.py:7` · `tests/schema/test_create_atomicity.py:12` ·
`tests/schema/test_create_race.py:13`

**13 import lines across 13 files.** This is the widest-reaching single commit of the phase.

### `DeviceCheckAdapter` → `AppleDeviceCheck`

| Site | What |
|------|------|
| `src/nativespeaker/api/auth/devicecheck.py:46-57` | the Protocol, 2 methods [VERIFIED] |
| `src/nativespeaker/api/auth/devicecheck.py:128` | `class AppleDeviceCheck` [VERIFIED] |
| `src/nativespeaker/api/auth/devicecheck.py:182, 187` | `adapter: DeviceCheckAdapter` in both retry helpers [VERIFIED] |
| `src/nativespeaker/api/app/dependencies.py:10, 123, 131` | import, `get_devicecheck_adapter` return, `get_auth_service` parameter [VERIFIED] |
| `tests/unit/test_devicecheck_adapter.py:25, 433-444` | import + `TestTheSeamIsTheAnnotation`, deleted by criterion 3 [VERIFIED] |
| `tests/unit/test_claim_ordering.py:36-39` | `SEAM_NAMES` frozenset — drop the `"DeviceCheckAdapter"` member [VERIFIED] |

### `TokenVerifier` → `JWTVerifier`

| Site | What |
|------|------|
| `src/nativespeaker/api/auth/jwt_verifier.py:69-72` | the Protocol, 1 method [VERIFIED] |
| `src/nativespeaker/api/auth/jwt_verifier.py:102` | `class JWTVerifier` [VERIFIED] |
| `src/nativespeaker/api/auth/google_play.py:18` | import [VERIFIED] |
| `src/nativespeaker/api/auth/google_play.py:211-212` | `verifier: TokenVerifier \| None` and `build: Callable[[], TokenVerifier \| None] \| None` on `PubSubPushTokens.__init__` [VERIFIED] |
| `tests/unit/test_google_play_notifications.py:44, 1064-1074` | import + `TestThePushTokenSeamIsTheAnnotation`, deleted by criterion 3 [VERIFIED] |

The lifespan already builds the concrete type: `build_google_push_verifier(play) -> JWTVerifier | None`
at `lifespan.py:84`, passed at `lifespan.py:213-215` [VERIFIED].

## Enumeration: the challenge store

### `src/`

| Site | Today | After |
|------|-------|-------|
| `crud/challenges.py:37-41` | `class ChallengesDB`, no `__init__`, `__repr__` names only the TTL | add `def __init__(self, session: AsyncSession)`; docstring drops "the session is a parameter on every one of them" |
| `crud/challenges.py:43, 71, 76, 81` | `issue/locate/claim/consume(self, session, ...)` | drop `session`, read `self.session` |
| `crud/challenges.py:92` | `verify_binding(self, row, claims, linked)` | unchanged (D-01) |
| `services/auth.py:14` | `from ...crud import ChallengesDB, GrantsDB, IdentitiesDB` | unchanged |
| `services/auth.py:66, 72` | `challenge_store: ChallengesDB` parameter, `self.challenge_store = challenge_store` | parameter gone; `self.challenges_db = ChallengesDB(db)` beside `self.grants_db` (line 71) |
| `services/auth.py:136, 142, 146, 400` | `self.challenge_store.{locate,verify_binding,claim,consume}(self.session, ...)` | `self.challenges_db.…`, no `self.session` argument except `verify_binding`'s unchanged three |
| `app/dependencies.py:20` | `from ...crud.challenges import ChallengesDB` | deleted |
| `app/dependencies.py:111` | the two-accessor comment | rewritten for the one accessor that remains, or deleted |
| `app/dependencies.py:112-114` | `get_challenge_store` | deleted |
| `app/dependencies.py:119` | `# The Protocol declares both methods async…` | deleted (48 D-10) |
| `app/dependencies.py:129, 134` | `challenge_store=` parameter and argument in `get_auth_service` | deleted; D-06 annotates `adapter: FirebaseAdminLookup` |
| `app/lifespan.py:42` | `from ...crud.challenges import ChallengesDB` | deleted |
| `app/lifespan.py:162` | `app.state.challenge_store = ChallengesDB()` | deleted |
| `routers/auth.py:11` | `get_challenge_store` in the import block | deleted |
| `routers/auth.py:21` | `from ...crud.challenges import ChallengesDB` | kept — the handler now builds one |
| `routers/auth.py:54` | `challenge_store: ChallengesDB = Depends(get_challenge_store)` | deleted |
| `routers/auth.py:68` | `await challenge_store.issue(session, operation=…, claims=…, linked=…)` | `await ChallengesDB(session).issue(operation=…, claims=…, linked=…)` |

`routers/auth.py:63` already reads `IdentitiesDB(session).resolve(...)` — D-03's stated model
[VERIFIED: routers/auth.py:63].

### `dependency_overrides[get_challenge_store]` — six unit files

| File | Override line | `store` fixture | Fake |
|------|---------------|-----------------|------|
| `tests/unit/test_challenge_endpoint.py` | :128 | :86-88 | own `_RecordingChallengeStore` :46-56 (`issue` only) — **D-05** |
| `tests/unit/test_create_user_body.py` | :96 | :66-68 | own `_RecordingChallengeStore` :26-40 (`issue`, `locate`) — **D-05** |
| `tests/unit/test_create_user_precedence.py` | :178 | :128-130 | `conftest.FakeChallengeStore` :37 — **D-04** |
| `tests/unit/test_claim_precedence.py` | :274 | :211-213 | `conftest.FakeChallengeStore` :43 — **D-04** |
| `tests/unit/test_claim_precedence_registered.py` | :154 | :91-93 | `conftest.FakeChallengeStore` :37 — **D-04** |
| `tests/unit/test_upgrade_precedence.py` | :180 | :106-108 | `conftest.FakeChallengeStore` :29 — **D-04** |

`tests/unit/conftest.py:236-274` holds `FakeChallengeStore`; `:242` is the
`self._binding = ChallengesDB()` line D-04 removes, `:251-252` the `verify_binding` pass-through
[VERIFIED].

### `AuthService(..., challenge_store=...)` — five files

`tests/unit/test_conflict_classification.py:128` · `tests/unit/test_create_user_rollback.py:76` ·
`tests/schema/test_create_race.py:169, 172` · `tests/schema/test_create_atomicity.py:175, 178` ·
`tests/schema/test_claim_race.py:256, 264` [VERIFIED]

The three schema files bind a local `store = ChallengesDB()` on the line before the call. Dropping
the argument leaves the local unused — **delete the local too**, or ruff F841 turns the lint red.

### `ChallengesDB` method call sites in tests

| File | Sites | Note |
|------|-------|------|
| `tests/e2e/test_challenge_store.py` | ~35 (`:45, 98, 152, 159, 170, 179, 204-205, 214, 221, 232, 241, 252-253, 265-266, 277-279, 286-288, 305, 319, 334, 347, 354-355, 360, 384, 401, 405`) | module-scoped `store` fixture at `:31-34` reads `_app_lifespan.state.challenge_store`; helpers `issue(factory, store, ...)` at `:38-51` take the store as a parameter; a second engine and factory are built at `:85-88` |
| `tests/unit/test_challenge_ids.py` | 15 (`:98, 169, 222, 230, 239, 247, 256, 266, 275, 286, 297, 308, 311, 320, 327`) [RE-MEASURED with `grep -n 'store()' tests/unit/test_challenge_ids.py`; the earlier count of 13 was wrong and `:99` was off by one] | plain helper `def store() -> ChallengesDB: return ChallengesDB()` at `:39-40`, called as `store()` |

`tests/schema/test_claim_race.py:136` mentions `ChallengesDB.issue` in a docstring — update the
prose if the signature it describes changes.

## Architecture Patterns

### Pattern 1: a crud class takes the session in its constructor

```python
# Source: src/nativespeaker/api/crud/identities.py:25-28 (VERIFIED)
class IdentitiesDB:

    def __init__(self, session: AsyncSession):
        self.session = session
```

`GrantsDB` is byte-identical at `crud/grants.py:96-99` [VERIFIED]. `ChallengesDB` adopts exactly
this: a **required positional** `session: AsyncSession`.

### Pattern 2: a handler builds its own crud object

```python
# Source: src/nativespeaker/api/routers/auth.py:63 (VERIFIED)
linked = await IdentitiesDB(session).resolve(issuer=claims.issuer, subject=claims.subject)
```

### Pattern 3: monkeypatch the crud class, not a dependency

```python
# Source: tests/unit/test_conversion_carries_usage.py:84-90 (VERIFIED)
monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
monkeypatch.setattr(GrantsDB, "holds_grant_of_source", holds_grant_of_source)
monkeypatch.setattr(IdentitiesDB, "resolve_existing", resolve_existing)
return GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]
```

Two facts that make this work for `ChallengesDB` [VERIFIED by reading both imports]:

- `services/auth.py:14` binds the class via `from nativespeaker.api.crud import ChallengesDB` and
  `routers/auth.py:21` via `from nativespeaker.api.crud.challenges import ChallengesDB`. **Both bind
  the same class object**, so one `monkeypatch.setattr(ChallengesDB, "locate", ...)` reaches the
  service and the handler at once. Patching a module attribute would reach only one.
- The patched functions must take `self` as their first parameter, because they are set on the class.
  The `_AddingSession` line above is also the precedent for handing a stub session to a crud
  constructor with a `# ty: ignore[invalid-argument-type]` comment.

### Anti-Patterns to Avoid

- **Moving a Protocol's docstring onto the concrete class.** 37a5ac6 deletes both.
- **Adding an `AuthService` method for the challenge route.** D-03 rejects it: the route would then
  resolve `get_firebase_adapter` and `get_devicecheck_adapter` for nothing.
- **Coining a new noun.** The class is `ChallengesDB`, the attribute is `challenges_db`, and the
  word "store" does not appear in new code or new comments (D-02).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Substituting the challenge crud in a test | a new fake class per suite | `monkeypatch.setattr(ChallengesDB, ...)` over the one `conftest.FakeChallengeStore` | D-04 keeps one copy; two drifting fakes of the only serialization point is the recorded hazard (`tests/unit/conftest.py:237-239`) |
| Re-checking a Protocol's members | `typing.get_protocol_members` | plain `{"a","b"} <= set(dir(Concrete))` | the Protocol is gone; 37a5ac6 shows the rewrite |
| Measuring the auth package shape | a new counter | `_measure` in `tests/unit/test_auth_package_shape.py` | already walks the AST at any nesting depth |

## Common Pitfalls

### Pitfall 1: `tests/unit/test_adapter_interfaces.py` is mostly *not* about the Protocol

`SOURCE_PATH`, `SOURCE` and `TREE` are read at **module import** from `auth/adapters.py`
(`:11-17`), so deleting that module makes the file fail at **collection**, not at a single case.
Beyond the Protocol cases at `:134-166`, the file holds two properties that have nothing to do with
`FirebaseAdminAdapter` [VERIFIED: tests/unit/test_adapter_interfaces.py]:

- `TestNoProviderDependency` (`:56-96`) — a **package-wide** guard that no `auth/` module except
  `firebase` pulls `firebase_admin` into `sys.modules`. Its control at `:73` asserts
  `"adapters" in SDK_FREE_MODULES`, which is false the moment the module is deleted.
- `TestTheValueTypeIsImmutable` (`:99-131`) — `VerifiedProviderIdentity` is frozen, slotted, has no
  `__dict__`, and `email` defaults to `None`. That behaviour survives the move to `auth/firebase.py`.

**Warning sign:** a plan that only deletes `TestFirebaseAdminAdapter` and the `PROTOCOLS` tuple
leaves a file that cannot import. **Avoidance:** decide the file's fate explicitly (CONTEXT leaves
it to discretion). If it is deleted, the two properties above must land somewhere —
`test_firebase_adapter.py` already imports `VerifiedProviderIdentity` at `:8`, and
`TestNoProviderDependency` can be re-pointed at any SDK-free auth module or moved to a package-level
test. Silently dropping the `firebase_admin` guard is a real loss.

Note the move's premise does change: `auth/firebase.py` is the one module that legitimately imports
the SDK, so `VerifiedProviderIdentity` will live there. For `src/` this costs nothing — importing
`nativespeaker.api.services.auth` **already** pulls `firebase_admin` into `sys.modules`
[VERIFIED: probe run this session, prints `True` at today's HEAD]. Test modules that import the
value type do gain the SDK transitively.

### Pitfall 2: `verify_binding` needs no session but the constructor demands one

D-01 keeps `verify_binding(row, claims, linked)` unchanged, yet a caller must still write
`ChallengesDB(session)` to reach it. 15 call sites are affected:
`tests/unit/test_challenge_ids.py:222, 230, 239, 247, 256, 266, 275, 286, 297` (via the `store()`
helper) and `tests/e2e/test_challenge_store.py:305, 319, 334, 347, 360` [VERIFIED].

**Avoidance:** in `test_challenge_ids.py`, change the `store()` helper to take the session it is
already constructing around (`_RecordingSession`), following the
`GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]` precedent. Do **not** give the
session a default of `None` to make these sites shorter — it would make `ChallengesDB` a different
shape from `IdentitiesDB` and `GrantsDB`, which is the whole point of D-01.

### Pitfall 3: criterion 3 deletes two guards that 37a5ac6 deliberately kept

37a5ac6 **rewrote** its seam guard against the concrete class because WR-18 recorded a specific
defect. Criterion 3 instead **deletes** `TestTheSeamIsTheAnnotation`
(`tests/unit/test_devicecheck_adapter.py:433-444`) and `TestThePushTokenSeamIsTheAnnotation`
(`tests/unit/test_google_play_notifications.py:1064-1074`), which record WR-23 and WR-24. Follow
the ROADMAP, not the commit, and note in the plan that two recorded guards are being retired — the
class-name assertion in each is meaningless once there is no other class it could name, but the
`<= set(dir(Concrete))` control is not.

### Pitfall 4: the schema tests leave a dead local

`store = ChallengesDB()` at `tests/schema/test_create_race.py:169`,
`test_create_atomicity.py:175` and `test_claim_race.py:256` becomes unused when the
`challenge_store=` argument goes. `ruff` runs `F` rules (`pyproject.toml:83`), so F841 fails the
lint. Delete the locals with the arguments.

### Pitfall 5: the e2e store fixture spans two engines

`tests/e2e/test_challenge_store.py:31-34` is `scope="module"` and hands one store to cases that open
sessions from **two** factories — the lifespan's and a second engine built at `:85-88` for the
8-contender claim race. D-01 requires one `ChallengesDB` per session, so the fixture disappears and
each `async with factory() as session:` block constructs its own. The module-level helpers
`issue(factory, store, ...)` (`:38-51`), `read`, `row_count` and `expire` must lose the `store`
parameter [VERIFIED].

### Pitfall 6: `ty` diagnostics move under D-06

`ty check` reads 306 diagnostics at the phase-48 gate [VERIFIED: 48-VERIFICATION.md:82]. D-06 adds
concrete annotations to `AuthService.__init__` and `get_auth_service`, and `ty` will then check
those call sites. Measure the number; do not copy it.

## Code Examples

### The challenge route after D-03

```python
# Pattern from: src/nativespeaker/api/routers/auth.py:63 (VERIFIED)
linked = await IdentitiesDB(session).resolve(issuer=claims.issuer, subject=claims.subject)
if body.operation != AuthOperation.create_user and linked is None:
    raise PreAuthIdentityNotAllowed

challenge_id, expires_at = await ChallengesDB(session).issue(
    operation=AuthOperation(body.operation), claims=claims, linked=linked)
```

### `AuthService.__init__` after D-02 and D-06

```python
# Existing shape: src/nativespeaker/api/services/auth.py:64-76 (VERIFIED)
def __init__(self, db: AsyncSession, adapter: FirebaseAdminLookup,
             devicecheck: AppleDeviceCheck) -> None:
    self.session = db
    self.identities_db = IdentitiesDB(db)
    self.grants_db = GrantsDB(db)
    self.challenges_db = ChallengesDB(db)
    self.adapter = adapter
    # Named for the vendor API, never for the company: two unrelated enums are already called apple.
    self.devicecheck = devicecheck
```

### A precedence suite's `store` fixture after D-04

```python
@pytest.fixture
def store(monkeypatch) -> FakeChallengeStore:
    fake = FakeChallengeStore()

    async def locate(self, challenge_id):
        return await fake.locate(challenge_id)

    async def claim(self, *, challenge_id):
        return await fake.claim(challenge_id=challenge_id)

    async def consume(self, *, challenge_id):
        return await fake.consume(challenge_id=challenge_id)

    monkeypatch.setattr(ChallengesDB, "locate", locate)
    monkeypatch.setattr(ChallengesDB, "claim", claim)
    monkeypatch.setattr(ChallengesDB, "consume", consume)
    return fake
```

`verify_binding` stays the real method (D-04), so `FakeChallengeStore` drops
`self._binding = ChallengesDB()` (`tests/unit/conftest.py:242`) and its pass-through (`:251-252`),
and its four fake methods lose the `session` parameter they currently accept.

## Commit sequence

Five seams, one commit each, plus the tuple. The recommended order puts the cheapest and least
entangled first:

| # | Seam | Files touched | Notes |
|---|------|---------------|-------|
| 1 | `PlaySubscriptionSource` | 2 src | no test edits at all |
| 2 | `TokenVerifier` | 2 src, 1 test | deletes `TestThePushTokenSeamIsTheAnnotation` |
| 3 | `DeviceCheckAdapter` | 2 src, 2 tests | deletes `TestTheSeamIsTheAnnotation`; edits `SEAM_NAMES` |
| 4 | `FirebaseAdminAdapter` + `VerifiedProviderIdentity` move + `adapters.py` removal | 3 src, 11 tests | the widest; settles Pitfall 1 |
| 5 | `ChallengesDB` constructor + `get_challenge_store` removal | 5 src, ~12 tests | may split in two (discretion) |
| 6 | `test_auth_package_shape.py` tuple | 1 test | see Open Question 1 |

Seams 1-4 are independent of seam 5 — they touch no shared line, so the order between the two halves
is free.

## Runtime State Inventory

This is a code rename/refactor. Every category was checked [VERIFIED: greps run this session].

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None. No Protocol name, `challenge_store` or `get_challenge_store` is persisted; `core.auth_challenges` columns are untouched and no migration is added | none |
| Live service config | None. No Envoy route, helm value or env var names any of these symbols | none |
| OS-registered state | None. No scheduled task or process name carries them | none |
| Secrets/env vars | None. `.env` keys are config names (`DEVICECHECK_*`, `GOOGLE_PLAY_*`), not class names | none |
| Build artifacts | `.venv` installs the package; `auth/adapters.py` deletion leaves a stale `__pycache__/adapters.*.pyc`. Harmless — Python ignores an orphan `.pyc` in `__pycache__` — but `git clean -xdf src` or a fresh `.venv` removes any doubt | optional cleanup |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.14.7 | — |
| pytest | the three suites | ✓ | `.venv/bin/pytest` | — |
| ruff | lint gate | ✓ | 0.15.7 | — |
| ty | type gate | ✓ | `.venv/bin/ty` | — |
| PostgreSQL on 127.0.0.1:5432 | `-m e2e`, `-m schema` | ✓ | port open (TCP probe this session) | — |
| `pg_isready` CLI | — | ✗ | — | TCP probe on 5432, used above |

No missing dependency blocks this phase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest, `asyncio_mode = "auto"` [VERIFIED: pyproject.toml:65-76] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Default `addopts` | `-v --tb=short -m 'not e2e and not schema'` — **e2e and schema are silently deselected unless `-m` is given** |
| Quick run command | `.venv/bin/pytest -q <the files this commit touched>` |
| Full suite command | the three suites below |

### The three suites (verbatim, as Phase 48 ran them)

```
.venv/bin/pytest -q -m ''
.venv/bin/pytest -q -m e2e
.venv/bin/pytest -q -m schema
```

Plus the lint and type gates:

```
.venv/bin/ruff check src tests
.venv/bin/ty check
```

### Phase-48 baseline to measure against [VERIFIED: 48-VERIFICATION.md:54-56, 82]

| Command | Result at the phase-48 gate |
|---------|-----------------------------|
| `.venv/bin/pytest -q -m ''` | `1 failed, 2572 passed` |
| `.venv/bin/pytest -q -m e2e` | `1 failed, 360 passed, 2212 deselected` |
| `.venv/bin/pytest -q -m schema` | `297 passed, 2276 deselected` — exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!`, exit 0 |
| `.venv/bin/ty check` | `Found 306 diagnostics` |

The **one** failing case is the pre-existing restore four-arms case, the same case in both suites,
and it is not this phase's [VERIFIED: STATE.md:60-68]. "The three suites exit 0" is therefore
unreachable literally; measure against this baseline and name the case, as Phases 47 and 48 both did.

### Behaviour → test map

| Behaviour | Test type | Automated command |
|-----------|-----------|-------------------|
| The four Protocol names are gone from `src/` and `tests/` | grep | `grep -rn 'PlaySubscriptionSource\|FirebaseAdminAdapter\|DeviceCheckAdapter\|TokenVerifier' src tests` prints nothing |
| `auth/adapters.py` is gone; `VerifiedProviderIdentity` comes from `auth/firebase.py` | grep | `ls src/nativespeaker/api/auth/adapters.py` fails; `grep -rn 'auth.adapters' src tests` prints nothing |
| Each annotation names the concrete class | unit | `.venv/bin/pytest -q tests/unit/test_devicecheck_adapter.py tests/unit/test_google_play_notifications.py tests/unit/test_firebase_adapter.py tests/unit/test_claim_ordering.py` |
| The auth package measures the new shape | unit | `.venv/bin/pytest -q tests/unit/test_auth_package_shape.py` |
| `get_challenge_store` does not exist | grep | `grep -rn 'get_challenge_store\|challenge_store' src tests` prints nothing |
| The challenge route still issues one row and refuses a bad body first | integration | `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py tests/unit/test_create_user_body.py` |
| The four precedence orders are unchanged under the monkeypatch | integration | `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py tests/unit/test_upgrade_precedence.py tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py` |
| `ChallengesDB` behaviour is unchanged against real PostgreSQL | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` (32 cases at the 48 gate) |
| The handle, TTL and binding rules are unchanged | unit | `.venv/bin/pytest -q tests/unit/test_challenge_ids.py` |
| Each race still commits exactly one row with `AuthService` building its own crud | schema | `.venv/bin/pytest -q -m schema tests/schema/test_claim_race.py tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` |

### Sampling rate

- **Per task commit:** the touched files plus `.venv/bin/pytest -q tests/unit/test_auth_package_shape.py`, and `.venv/bin/ruff check src tests`
- **Per seam commit:** `.venv/bin/pytest -q -m ''`, and `-m e2e` / `-m schema` for any commit touching `crud/challenges.py`
- **Phase gate:** the three suites, `ruff` and `ty`, all re-run rather than copied

### Wave 0 gaps

None — every behaviour above already has a test file. This phase writes no new test; it deletes,
repoints and rewires existing ones.

## Security Domain

`security_enforcement` is not disabled in `.planning/config.json`, so the section stands.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no change | JWT verified at Envoy and again by `JWTVerifier`; this phase renames its annotation only |
| V3 Session Management | **touched** | the challenge handle is a single-use capability; `issue`/`claim`/`consume` move their session argument and change no SQL |
| V4 Access Control | no change | `verify_binding` is byte-unchanged (D-01) |
| V5 Input Validation | no change | no request body or schema is edited |
| V6 Cryptography | no change | `new_challenge_id` and its CSPRNG are untouched |

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A claimed challenge becomes re-presentable | Elevation of Privilege | `_claim_statement` (`crud/challenges.py:27-34`) is the one serialization point and the only expiry check — it must move unchanged, statement for statement |
| A handle reaches a log | Information Disclosure | `crud/challenges.py:1` records that the module holds no logger; keep it that way |
| A per-request `ChallengesDB` leaks state across requests | Tampering | the class holds only the session after D-01, and `get_db` opens one session per request (`dependencies.py:44-51`) |

The only real hazard here is a silent behaviour change hidden inside a mechanical edit. The e2e and
schema suites are the control: they exercise `claim`, `consume` and the expiry predicate against a
live PostgreSQL, and they must be run on every commit that touches `crud/challenges.py` — pytest
deselects them by default.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The new `CURRENT` tuple is `(7, 20, 60)`, computed from the measured `(8, 24, 67)` minus one module, four classes and seven Protocol methods, plus `VerifiedProviderIdentity` re-landing in `auth/firebase.py` | Open Question 1 | A wrong literal fails the shape case. The arithmetic is from a real AST count run this session, but **measure it from the failing run's own text**, as Phase 46 did |
| A2 | Deleting `tests/unit/test_adapter_interfaces.py` outright is acceptable if `TestNoProviderDependency` and `TestTheValueTypeIsImmutable` are relocated | Pitfall 1 | Dropping them loses a package-wide SDK-isolation guard silently |

## Open Questions (RESOLVED)

1. **RESOLVED 2026-09-16 (CONTEXT D-08): the tuple changes in each seam commit.** Criterion 5 contradicted itself, and the model commit resolved it the other way.
   - What we know: `test_auth_package_shape.py:13` is a literal `CURRENT = (8, 24, 67)`, compared
     against a live AST walk of `auth/` (`:16-27`). Measured this session, the current value is
     exactly `(8, 24, 67)`. Deleting *any one* Protocol changes the measurement — deleting
     `PlaySubscriptionSource` alone makes it `(8, 23, 65)` — so the unit suite is **red from the
     first seam commit until the last**. 37a5ac6 solved this by editing `CURRENT` in the same commit
     as the Protocol (`tests/unit/test_auth_package_shape.py | 2 +-` in its stat).
   - What's unclear: whether "changed in one commit at the end" (criterion 5) or "the three suites
     exit 0 at every commit" (criterion 5, same sentence) is the one the user wants kept.
   - Recommendation: **follow 37a5ac6** — carry the tuple in each seam commit, and let the final
     commit be the one that records the phase's end-state number after a re-measurement. Raise it
     with the user before planning, since CONTEXT records that the user challenges any change the
     ROADMAP does not name.

2. **RESOLVED (49-02-PLAN.md Task 2): the file is deleted; `TestNoProviderDependency` and `TestTheValueTypeIsImmutable` move to `tests/unit/test_firebase_adapter.py`.** What becomes of `tests/unit/test_adapter_interfaces.py`?
   - What we know: CONTEXT leaves it to discretion; criterion 3 removes only its adapter-shape class
     and Protocol list. Two unrelated properties live in the same file (Pitfall 1), and the file
     cannot import once `auth/adapters.py` is gone.
   - Recommendation: delete the file and move `TestTheValueTypeIsImmutable` into
     `tests/unit/test_firebase_adapter.py` (it already imports `VerifiedProviderIdentity` at `:8`),
     and re-point `TestNoProviderDependency` at an auth module that still exists — its
     `assert "adapters" in SDK_FREE_MODULES` control at `:73` must be re-written whatever is chosen.

3. **RESOLVED (49-04-PLAN.md Task 1): the repr keeps the TTL.** Does `ChallengesDB.__repr__` keep the TTL?
   - What we know: `crud/challenges.py:40-41` returns `f"ChallengesDB(ttl_seconds={CHALLENGE_TTL_SECONDS})"`.
     D-01 says "the class docstring and `__repr__` follow the new shape". `IdentitiesDB` and
     `GrantsDB` declare no `__repr__` at all.
   - Recommendation: keep the TTL in the repr — it is the one fact about the class a reader wants —
     and let "follow the new shape" mean only that the docstring stops saying the session is a
     parameter on every method.

## Sources

### Primary (HIGH confidence) — read directly this session

- `git show 37a5ac6` — the model commit, all four files
- `src/nativespeaker/api/auth/adapters.py`, `crud/challenges.py`, `crud/identities.py:25-33`,
  `crud/grants.py:96-104`
- `src/nativespeaker/api/app/dependencies.py:1-200`, `app/lifespan.py:155-220`,
  `routers/auth.py:1-85`, `services/auth.py:55-90, 125-160, 295-325, 390-410`
- `src/nativespeaker/api/auth/{devicecheck,google_play,jwt_verifier,firebase}.py` — Protocol blocks
  and annotation sites
- `tests/unit/{test_adapter_interfaces,test_auth_package_shape,conftest,test_challenge_ids,test_challenge_endpoint,test_create_user_body,test_devicecheck_adapter,test_google_play_notifications,test_firebase_adapter,test_claim_ordering,test_conversion_carries_usage,test_app_wiring}.py`
- `tests/e2e/test_challenge_store.py`, `tests/schema/{test_create_race,test_create_atomicity,test_claim_race}.py`
- `pyproject.toml:65-84`
- `.planning/ROADMAP.md` Phase 49 and Phase 50 entries
- `.planning/phases/48-narrow-identity-to-the-verified-pair/48-VERIFICATION.md:54-56, 82`
- `.planning/STATE.md:46-96` (the one pre-existing failing case)
- Probes run this session: an AST count of `auth/` giving `(8, 24, 67)`; a TCP connect to
  127.0.0.1:5432; `import nativespeaker.api.services.auth` printing `firebase_admin in sys.modules: True`

### Secondary / Tertiary

None. No web source was consulted; none was needed.

## Metadata

**Confidence breakdown:**
- Enumeration (every file:line above): HIGH — grep and Read over the working tree at this HEAD
- The 37a5ac6 pattern: HIGH — the diff was read in full
- Commit sequencing: HIGH for independence (no shared lines), MEDIUM for the order itself (discretion)
- The projected `CURRENT` tuple: MEDIUM — arithmetic on a measured count, to be confirmed by running

**Research date:** 2026-09-16
**Valid until:** until the next commit that touches `auth/`, `crud/challenges.py` or the six unit
suites above — the line numbers are the fragile part, the file set is not.
