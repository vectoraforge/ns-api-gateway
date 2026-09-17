# Phase 49: Delete the single-implementation auth Protocols - Pattern Map

**Mapped:** 2026-09-16
**Files analyzed:** 5 groups of modified files (no file is created)
**Analogs found:** 5 / 5

This phase creates no new file. Every entry below is an edit to an existing file, and the analog is
the in-repo edit or shape it must copy.

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/auth/{adapters,devicecheck,google_play,jwt_verifier}.py` | adapter | request-response | `git show 37a5ac6` (`auth/app_store.py` hunk) | exact |
| `src/nativespeaker/api/services/{auth,restore}.py`, `app/dependencies.py`, `auth/firebase.py` | service / dependency | request-response | `git show 37a5ac6` (`services/restore.py` hunk) | exact |
| `src/nativespeaker/api/crud/challenges.py` | crud | CRUD | `crud/identities.py:25-28`, `crud/grants.py:96-99` | exact |
| `src/nativespeaker/api/routers/auth.py` | handler | request-response | `routers/auth.py:63` (same file, `IdentitiesDB`) | exact |
| `src/nativespeaker/api/app/lifespan.py` | config | batch (boot) | `git show 37a5ac6` has no analog; deletion only | n/a |
| `tests/unit/conftest.py` + the 4 precedence suites | test | request-response | `tests/unit/test_conversion_carries_usage.py:63-88` | exact |
| `tests/unit/test_{challenge_endpoint,create_user_body}.py` | test | request-response | `tests/unit/test_conversion_carries_usage.py:100-104` | exact |
| `tests/unit/test_{devicecheck_adapter,google_play_notifications,firebase_adapter}.py` | test | request-response | `git show 37a5ac6` (`test_app_store_notifications.py` hunk) | exact |
| `tests/unit/test_auth_package_shape.py` | test | batch | `git show 37a5ac6` (`CURRENT` hunk) | exact |
| `tests/e2e/test_challenge_store.py`, `tests/unit/test_challenge_ids.py`, `tests/schema/test_{create_race,create_atomicity,claim_race}.py` | test | CRUD | `tests/unit/test_conversion_carries_usage.py:88` (`GrantsDB(_AddingSession())`) | role-match |

## Pattern Assignments

### The four Protocol deletions (adapter modules + their consumers)

**Analog:** commit `37a5ac6`, "refactor: drop the StoreNotificationVerifier protocol" (4 files, +8/-33).

**Delete the block and the `Protocol` import** (`auth/app_store.py` hunk):

```diff
 from datetime import UTC, datetime
-from typing import Protocol

-class StoreNotificationVerifier(Protocol):
-    """The Apple store seam: one verified notification or one verified proof, or a raise."""
-
-    def verify(self, signed_payload: str) -> VerifiedNotification:
-        """The verification call: this project's value type, or a raise."""
-        ...
```

The docstrings go with the Protocol; nothing moves onto the concrete class. Drop
`from typing import Protocol` only when nothing else in the module uses it.

**Repoint the consumer's import and annotation** (`services/restore.py` hunk):

```diff
-from nativespeaker.api.auth.app_store import StoreNotificationVerifier
+from nativespeaker.api.auth.app_store import AppStoreNotifications

     def __init__(self, db: AsyncSession, evaluated_at: datetime,
-                 app_store: StoreNotificationVerifier, play: PlaySubscriptionSource,
+                 app_store: AppStoreNotifications, play: PlaySubscriptionSource,
```

**Delete the "satisfies the Protocol" test** (`test_app_store_notifications.py` hunk):

```diff
-    def test_the_seam_satisfies_the_protocol_declared_beside_it(self, chain):
-        """Phase 44's own class must satisfy this same Protocol, so it is asserted rather than assumed."""
-        seam: StoreNotificationVerifier = _notifications(chain)
-        assert isinstance(seam.verify(_full(chain)), VerifiedNotification)
```

**Carry `CURRENT` in the same commit** (`test_auth_package_shape.py:13`):

```diff
-CURRENT = (8, 25, 70)
+CURRENT = (8, 24, 68)
```

Today's literal is `CURRENT = (8, 24, 67)` [verified this session]. The tuple is compared with a live
AST walk (`test_auth_package_shape.py:16-26`), so read the new value out of the failing run's own
text rather than computing it.

**Divergence the ROADMAP owns:** 37a5ac6 *rewrote* its seam guard against the concrete class
(`assert {"verify", "verify_transaction"} <= set(dir(AppStoreNotifications))` and
`annotations["app_store"] is AppStoreNotifications`). Criterion 3 instead **deletes**
`TestTheSeamIsTheAnnotation` and `TestThePushTokenSeamIsTheAnnotation`. Follow the ROADMAP.

---

### `crud/challenges.py` (crud, CRUD) — D-01

**Analog:** `src/nativespeaker/api/crud/identities.py:25-28` (byte-identical at `crud/grants.py:96-99`):

```python
class IdentitiesDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve(self, *, issuer: str, subject: str) -> LinkedIdentity | None:
        ...
        row = (await self.session.exec(statement)).first()
```

A required positional `session: AsyncSession`, no default, no `| None`. Copy the blank line after
the class statement and the no-docstring `__init__`.

**What changes in `crud/challenges.py`:**

- `:37-41` — add the `__init__`; the docstring at `:38` stops saying "the session is a parameter on
  every one of them". `__repr__` keeps `ttl_seconds` (neither sibling declares a `__repr__`, so the
  repr has no analog to copy; the TTL is the one fact worth printing).
- `:43, 71, 76, 81` — `issue`, `locate`, `claim`, `consume` drop the `session` parameter; every
  `session.add` / `session.flush` / `session.exec` inside becomes `self.session.…`.
- `:92` — `verify_binding(self, row, claims, linked)` is byte-unchanged (D-01).
- `_claim_statement` (`:27-34`) moves not at all: it is the one serialization point and the only
  expiry check.

---

### `services/auth.py` (service, request-response) — D-02, D-06

**Analog:** the same `__init__` two lines above, `services/auth.py:69-71`.

Today (`:64-75`):

```python
    def __init__(self,
                 db: AsyncSession,
                 challenge_store: ChallengesDB,
                 adapter,
                 devicecheck) -> None:
        self.session = db
        self.identities_db = IdentitiesDB(db)
        self.grants_db = GrantsDB(db)
        self.challenge_store = challenge_store
        self.adapter = adapter
        # Named for the vendor API, never for the company: two unrelated enums are already called apple.
        self.devicecheck = devicecheck
```

After: the `challenge_store` parameter goes, `self.challenges_db = ChallengesDB(db)` joins the two
sibling lines, and D-06 annotates `adapter: FirebaseAdminLookup`, `devicecheck: AppleDeviceCheck`.
The vendor-API comment stays as it is.

The four read sites follow (`:136, 142, 146, 400`), losing `self.session` everywhere except
`verify_binding`:

```python
        located = await self.challenge_store.locate(self.session, challenge_id)
        challenge = self.challenge_store.verify_binding(located, claims, linked)
        if not await self.challenge_store.claim(self.session, challenge_id=challenge_id):
```

becomes `self.challenges_db.locate(challenge_id)`, `self.challenges_db.verify_binding(located,
claims, linked)`, `self.challenges_db.claim(challenge_id=challenge_id)`.

---

### `routers/auth.py` (handler, request-response) — D-03

**Analog:** `routers/auth.py:63`, five lines above the site being changed:

```python
    linked = await IdentitiesDB(session).resolve(issuer=claims.issuer, subject=claims.subject)
```

`issue_challenge` drops the `challenge_store: ChallengesDB = Depends(get_challenge_store)` parameter
(`:54`) and the `get_challenge_store` name from the import block (`:11`); `:21` keeps
`from nativespeaker.api.crud.challenges import ChallengesDB`. `:68-71` becomes
`await ChallengesDB(session).issue(operation=…, claims=…, linked=…)`. The `session.commit()` and the
`Cache-Control: no-store` lines are untouched.

---

### `app/dependencies.py` (dependency, request-response)

No analog to copy — this is deletion plus a comment rewrite. Today (`:111-136`):

```python
# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengesDB:
    """The one `ChallengesDB` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_firebase_adapter(request: Request) -> FirebaseAdminAdapter:
    """The provider seam the lifespan built."""
    # The Protocol declares both methods async, which is what the concrete class implements.
    return request.app.state.firebase_adapter
```

`get_challenge_store` and its `:111` comment go; the `:119` comment goes with the Protocol
(48 D-10 — no comment may keep a removed Protocol, "the seam" or `get_challenge_store` as its
subject). `get_auth_service` (`:128-136`) loses the `challenge_store` parameter and argument and
gains D-06's `adapter: FirebaseAdminLookup`.

---

### The four precedence suites (test) — D-04

**Analog:** `tests/unit/test_conversion_carries_usage.py:63-88` — a fixture that monkeypatches the
crud class and returns the object the cases read:

```python
@pytest.fixture
def writer(account, monkeypatch) -> GrantsDB:
    """The writer with both lock tiers and the re-read scripted; only the usage row varies per case."""
    identity_row, superseded = account

    async def lock_active(self, user_id):
        return []

    monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
    monkeypatch.setattr(IdentitiesDB, "resolve_existing", resolve_existing)
    return GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]
```

Three facts this analog carries:

1. Each replacement takes `self` first — it is set on the class, not on an instance.
2. One `monkeypatch.setattr(ChallengesDB, …)` reaches both binders: `services/auth.py:14`
   (`from nativespeaker.api.crud import ChallengesDB`) and `routers/auth.py:21`
   (`from nativespeaker.api.crud.challenges import ChallengesDB`) bind the same class object.
3. `GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]` is the precedent for handing a
   stub session to a crud constructor.

The one `store` fixture in `tests/unit/conftest.py` patches `locate`, `claim` and `consume` onto
`ChallengesDB` and returns the `FakeChallengeStore`, so the suites still read `store.row` and
`store.consume_calls`. `verify_binding` stays the real method, so `conftest.py:242`
(`self._binding = ChallengesDB()`) and the pass-through at `:251-252` go, and the fake's four
methods lose their `session` parameter:

```python
    async def locate(self, session, challenge_id: str) -> AuthChallenge | None:
    async def claim(self, session, *, challenge_id) -> bool:
    async def consume(self, session, *, challenge_id) -> bool:
```

`test_challenge_endpoint.py` and `test_create_user_body.py` use the same analog for their own
`_RecordingChallengeStore`, patching `ChallengesDB.issue` only (D-05).

---

### The tests that construct `ChallengesDB` per session

**Analog:** `GrantsDB(_AddingSession())` above, and the existing e2e helper shape
(`tests/e2e/test_challenge_store.py:40-50`):

```python
async def issue(factory, store, linked: LinkedIdentity | None = None, *,
                operation: AuthOperation = AuthOperation.claim_anonymous_grant
                ) -> tuple[str, datetime]:
    """Issue one challenge and commit it, the way a real prepare handler would."""
    async with factory() as session:
        handle, expires_at = await store.issue(session, operation=operation, ...)
        await session.commit()
```

The module-scoped `store` fixture at `:30-33` reads `_app_lifespan.state.challenge_store` and spans
two engine factories, so it is deleted; `issue`, `read`, `row_count` and `expire` lose the `store`
parameter and each `async with factory() as session:` block builds `ChallengesDB(session)`.
`tests/unit/test_challenge_ids.py:39-40` changes its `store()` helper to take the
`_RecordingSession` it already builds. The three schema files delete the now-unused
`store = ChallengesDB()` local with the `challenge_store=` argument (ruff runs `F`, so F841 is red).

## Shared Patterns

### Comment rule (48 D-10)
**Apply to:** every file this phase touches.
One line, ASD-STE100, only where a later edit would go wrong without it. Delete every comment whose
subject is a removed Protocol, "the seam", or `get_challenge_store` (`dependencies.py:111, 119`).
Keep unrelated comments verbatim — for example `services/auth.py:74` and `crud/challenges.py:28`.

### Naming (D-02, AGENTS.md)
**Apply to:** all new code and comments.
`ChallengesDB`, `challenges_db`, `AuthService`, `FirebaseAdminLookup`, `AppleDeviceCheck`,
`JWTVerifier`, `PlayDeveloperSubscriptions`. The word "store" names no class in new code. Codebase
terms only: dependency, handler, service, crud, adapter.

### The package-shape literal
**Source:** `tests/unit/test_auth_package_shape.py:13`
**Apply to:** every commit that changes the module, class or function count under `auth/`.
`CURRENT = (8, 24, 67)` today. Update it in the same commit as the seam (D-08, as 37a5ac6 did), and
take the new tuple from the failing run's own output.

### Moving `VerifiedProviderIdentity`
**Source:** `src/nativespeaker/api/auth/adapters.py:9-18` — copy the block verbatim into
`auth/firebase.py`, including both comments:

```python
@dataclass(frozen=True, slots=True)
class VerifiedProviderIdentity:
    """What one completed providerData read established: which provider owns the caller, and its uid.
    Every field here has already passed its rule -- the shape classified, the address verified."""

    provider: IdentityProvider
    # `None` exactly for the anonymous arm: `core.external_identities`' CHECK requires NULL there.
    provider_uid: str | None
    # Absent by default because an anonymous record has no verified address to carry.
    email: str | None = None
```

13 import lines across 13 files re-point at `auth.firebase` (enumerated in 49-RESEARCH.md:182-188).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/lifespan.py:42, 162` | config | batch (boot) | Pure deletion of the import and `app.state.challenge_store = ChallengesDB()`; no analog needed |
| `tests/unit/test_adapter_interfaces.py` | test | batch | Its fate is discretion (RESEARCH Open Question 2). `TestNoProviderDependency` (`:56-96`) is a package-wide `firebase_admin` isolation guard with no sibling to copy; `assert "adapters" in SDK_FREE_MODULES` (`:73`) must be rewritten whatever is chosen |

## Metadata

**Analog search scope:** `src/nativespeaker/api/{auth,crud,services,routers,app}`, `tests/{unit,e2e,schema}`, `git show 37a5ac6`
**Tracked-source check:** every path above verified with `git ls-files` inside the `ns-api-gateway` submodule
**Pattern extraction date:** 2026-09-16
