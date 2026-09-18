---
phase: 49-delete-the-single-implementation-auth-protocols
reviewed: 2026-09-18T01:15:06Z
depth: standard
files_reviewed: 33
files_reviewed_list:
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/crud/challenges.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/restore.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_upgrade_anonymous.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/unit/conftest.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_upgrade_precedence.py
findings:
  critical: 0
  warning: 8
  info: 5
  total: 13
status: issues_found
---

# Phase 49: Code Review Report

**Reviewed:** 2026-09-18T01:15:06Z
**Depth:** standard
**Files Reviewed:** 33
**Status:** issues_found

## Summary

The behaviour-preserving claim holds for the production diff. I traced the session
plumbing end to end and found no correctness defect: `get_db` is cached per request,
so the `ChallengesDB(session)` the handler builds and the `ChallengesDB(db)`
`AuthService.__init__` builds are bound to the same session object the old
lifespan-owned crud was handed per call; `_complete`'s locate/claim/commit/consume
order, the rollback before `_consume_quietly`, and the `expire_on_commit=False`
read of `challenge.id` are all unchanged. No reference to any of the four deleted
Protocol names, to `auth.adapters`, to `get_challenge_store` or to
`app.state.challenge_store` survives in `src/` or `tests/`. `ChallengesDB()` is
never called without a session. `ruff check` is clean. The `auth/` shape tuple
`(7, 20, 60)` matches the seven modules now on disk.

The defects are in the phase's handling of its own fallout, and two of them
contradict written project rules rather than merely being untidy.

The lead finding is WR-01: `issue_challenge` now constructs a crud class in the
handler body, which `AGENTS.md` forbids in as many words, while `get_purchases_db`
survives three screens below in the same dependency module as the counter-example
of the rule being obeyed. WR-02 is the other rule breach: `AGENTS.md` still lists
the module this phase deleted.

On plan 49-03's ten `# ty: ignore[invalid-argument-type]` marks: I measured the
tool rather than trusting the plan. Baseline `22a02d27^` reports 306 ty
diagnostics; HEAD reports 306. Each of the ten marks suppresses exactly one error
the phase's own new concrete annotations created, so they are load-bearing and not
noise -- except one, which ty now reports as an unused directive (WR-06). But the
same phase left six new unsuppressed errors of the same rule in
`tests/e2e/test_challenge_store.py` (16 -> 22 for that file, WR-05). The marks are
therefore a symptom fix applied inconsistently: they suppress the check the phase
just introduced, at line scope rather than argument scope, instead of giving the
tests doubles of the declared type (WR-04). Judgement: no, that was not the right
fix.

## Warnings

### WR-01: The challenge handler constructs a crud class in its body, against the written rule

**File:** `src/nativespeaker/api/routers/auth.py:65`
**Issue:** `AGENTS.md:48-50` states: "`Depends()` only still binds the handler,
whichever it calls: take the session and the barrier from a dependency, never
construct a database class in the body." The escape hatch on the next line -- "The
rule binds new code; leave the existing services as they are" -- does not apply:
this is new code, written into a handler by this phase. The deleted dependency's
own comment said why it existed ("These two accessors exist so a challenge-bearing
route can stay `Depends()`-only"), and the identical accessor for the sibling case
is still in the tree with the rule restated in its comment:

```python
# dependencies.py:188-190 -- survives, and now contradicts the auth router
# This accessor exists so the profile route can stay Depends()-only and never construct a database class itself.
def get_purchases_db(db: AsyncSession = Depends(get_db)) -> PurchasesDB:
    return PurchasesDB(db)
```

The codebase now holds both conventions at once. Deleting `get_challenge_store`
was correct -- it read the crud off `app.state` -- but the replacement should have
been the `get_purchases_db` shape, not an inline constructor.
**Fix:**
```python
# dependencies.py, beside get_purchases_db
def get_challenges_db(db: AsyncSession = Depends(get_db)) -> ChallengesDB:
    return ChallengesDB(db)

# routers/auth.py
async def issue_challenge(body: ChallengeRequest,
                          response: Response,
                          claims: VerifiedClaims = Depends(get_claims),
                          session: AsyncSession = Depends(get_db),
                          challenges_db: ChallengesDB = Depends(get_challenges_db)
                          ) -> PrepareResponse:
    ...
    challenge_id, expires_at = await challenges_db.issue(operation=AuthOperation(body.operation),
                                                         claims=claims,
                                                         linked=linked)
```
`get_db` is cached per request, so the injected crud holds the same session the
handler commits.

### WR-02: AGENTS.md still lists the module this phase deleted

**File:** `AGENTS.md:34-36`
**Issue:** The package map reads "`auth/` -- external-SDK seams: `adapters.py`,
`app_store.py`, `devicecheck.py`, ...". `auth/adapters.py` was deleted in commit
`65b1c91`. `AGENTS.md` is loaded by `CLAUDE.md` on every session, so this is the
one document every future agent reads to decide where a file belongs, and it now
names a module that does not exist. The phase updated the machine-checked count in
`tests/unit/test_auth_package_shape.py` but not the prose map, which nothing
checks.
**Fix:** Drop `adapters.py` from the list:
```markdown
- `auth/` — external-SDK seams: `app_store.py`, `devicecheck.py`,
  `firebase.py`, `google_play.py`, `jwt_verifier.py`, and the verified
  notification both store seams fill, `store_notifications.py`.
```

### WR-03: The session-holding constructor forces fourteen call sites to fabricate a session for a pure method

**File:** `src/nativespeaker/api/crud/challenges.py:95-110`, `tests/e2e/test_challenge_store.py:300-302,316-319,331-335,346-349,361-364`, `tests/unit/test_challenge_ids.py:221,229,238,246,255,265,274,285,296`
**Issue:** `verify_binding` touches no session -- it is a pure comparison over a
row, claims and the linked identity. Making the session a constructor argument
made it unreachable without one anyway, so fourteen call sites now build a session
purely to reach it. Five of them are worse than cosmetic: they open a real
PostgreSQL transaction that issues no statement, only so the constructor can be
satisfied:

```python
# tests/e2e/test_challenge_store.py:300-302 -- a database transaction for an in-memory comparison
async with _db_transaction() as session:
    assert ChallengesDB(session).verify_binding(row, claims=claims_for(),
                                                linked=linked) is row
```

The other nine pass a throwaway `_RecordingSession()` that is never read. This is
also the direct cause of WR-05: those five sites are where the six new ty errors
appeared.
**Fix:** Move the pure check out of the session-bound class, leaving `ChallengesDB`
the four operations its docstring claims:
```python
# crud/challenges.py, module level
def verify_binding(row: AuthChallenge, claims: VerifiedClaims,
                   linked: LinkedIdentity | None) -> AuthChallenge:
    """Return `row` when the caller is the presenter it was bound to, and raise otherwise."""
    ...

# services/auth.py:148
challenge = verify_binding(located, claims, linked)
```
Fourteen test sites then drop their fabricated session, and the six unsuppressed ty
errors in WR-05 go with them.

### WR-04: The ten ty suppressions hide the check the phase's own annotations added, at line scope

**File:** `tests/schema/test_claim_race.py:263-264`, `tests/schema/test_create_atomicity.py:177-178`, `tests/schema/test_create_race.py:172-173`, `tests/unit/test_conflict_classification.py:127`, `tests/unit/test_create_user_rollback.py:75`
**Issue:** Two problems, one of them durable.

First, the suppressions discard the only benefit the phase bought. Before,
`AuthService.__init__` took `adapter` and `devicecheck` unannotated, so nothing was
checked. The phase annotated them `FirebaseAdminLookup` and `AppleDeviceCheck` --
and then silenced every call site that would have been checked. `_ScriptedAdapter`
and `_NeverSetDevice` are real doubles whose shape the checker can now verify, and
the mark is exactly what stops it verifying them. Drift in those doubles is again
invisible, which is the failure the two deleted guard classes
(`TestTheSeamIsTheAnnotation`, `TestThePushTokenSeamIsTheAnnotation`) were written
to catch.

Second, a `# ty: ignore[rule]` comment suppresses every diagnostic of that rule on
its line, not the one argument it was aimed at. Two sites put one mark on a line
carrying three arguments:

```python
# tests/unit/test_conflict_classification.py:127 -- one mark, three arguments
service = AuthService(db=session, adapter=None, devicecheck=None)  # ty: ignore[invalid-argument-type]
```
A later mismatch on `db=` is now silent at both sites.
**Fix:** Give the tests doubles of the declared type, which removes six of the ten
marks and restores the checking:
```python
class _ScriptedAdapter(FirebaseAdminLookup):
    """The scripted read; the SDK constructor is deliberately not called."""

    def __init__(self, provider, provider_uid) -> None:
        self._facts = VerifiedProviderIdentity(provider=provider, provider_uid=provider_uid)

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        return self._facts
```
For the four remaining `adapter=None` / `devicecheck=None` arguments, the mark
documents a claim the type denies. Either pass a double of the declared type there
too, or -- if a completion that reaches neither provider is a real shape -- say so
in the signature rather than in a comment the checker obeys and the reader does
not.

### WR-05: The phase left six new unsuppressed ty errors of the rule it suppressed elsewhere

**File:** `tests/e2e/test_challenge_store.py:301,317,333,348,363,387`
**Issue:** Measured, not inferred. At `22a02d27^` this file reports 16 ty
diagnostics; at HEAD it reports 22. The six new ones are the phase's own:

```
error[invalid-argument-type]: Argument to bound method `verify_binding` is incorrect
   --> tests/e2e/test_challenge_store.py:301:57
    | assert ChallengesDB(session).verify_binding(row, claims=claims_for(),
    |                                             ^^^ Expected `AuthChallenge`, found `AuthChallenge | None`
```
plus `unresolved-attribute` at 387. They appeared because the old module-scope
`store` fixture resolved to `Any` off `app.state`, so nothing was checked; the
direct `ChallengesDB(session)` construction is typed and now is. That is the phase
working as intended -- but the same phase decided five other sites of the same rule
were worth marking. One tool, one phase, two policies.
**Fix:** Pick one. The root fix for five of the six is WR-03 (the pure
`verify_binding` takes the row the caller already asserted non-`None`). For
line 387, bind and assert first:
```python
located = await ChallengesDB(session).locate(handle)
assert located is not None
assert located.challenge_id == handle
```

### WR-06: A new ty ignore directive is unused and ty reports it

**File:** `tests/unit/test_firebase_adapter.py:656`
**Issue:** ty emits `warning[unused-ignore-comment]: Unused ty: ignore directive`
for this line. The baseline has five unused directives, HEAD has five, but the set
changed: the one this phase added is new, and the one it removed went with the
deleted `test_adapter_interfaces.py`. ty does not model assignment to an
undeclared attribute on a slotted dataclass as `unresolved-attribute`, so the mark
never had anything to suppress -- it was copied verbatim from the deleted file
along with the test body. The sibling mark at line 649 is load-bearing and should
stay.
**Fix:**
```python
with pytest.raises(AttributeError):
    identity.email_verified = True
```

### WR-07: A package-wide `store` fixture that patches production methods collides with a same-named helper

**File:** `tests/unit/conftest.py:273-290`, `tests/unit/test_challenge_ids.py:39-40`
**Issue:** The fixture is fine in kind -- patching crud methods on the class is the
established pattern (`tests/unit/test_conversion_carries_usage.py:83-87`) and the
ROADMAP asked for it. The problem is the name and the scope. Living in
`tests/unit/conftest.py`, a fixture called `store` that rebinds
`ChallengesDB.locate`, `.claim` and `.consume` on the class is visible to all
sixty unit test modules, and `tests/unit/test_challenge_ids.py` -- the module that
tests that very class against real statements -- declares a module-level helper
with the same name:

```python
# tests/unit/test_challenge_ids.py:39 -- a plain function, not a fixture
def store(session) -> ChallengesDB:
    return ChallengesDB(session)
```
Every test in that module calls it directly today, so nothing is broken. But a
test added there that declares `store` as a parameter gets the conftest fixture
silently, with the three methods under test replaced by fakes, and its assertions
about real SQL still pass.
**Fix:** Name the fixture for what it patches and leave `store` to the module:
```python
@pytest.fixture
def challenges_db(monkeypatch) -> FakeChallengeStore:
```
and rename the four precedence suites' uses with it.

### WR-08: One adapter parameter was left unannotated, so the phase's new annotation checks nothing for its caller

**File:** `src/nativespeaker/api/routers/auth.py:205,208`
**Issue:** The phase's stated goal was to annotate every parameter that named a
deleted Protocol with the concrete class. `get_auth_service` got
`adapter: FirebaseAdminLookup`; `revoke_with_retry`'s own parameter went from
`FirebaseAdminAdapter` to `FirebaseAdminLookup`. The one remaining consumer was
left as it was:

```python
async def sign_out_all(claims: VerifiedClaims = Depends(get_claims),
                       linked: LinkedIdentity = Depends(get_identity),
                       adapter=Depends(get_firebase_adapter)) -> Response:
    await revoke_with_retry(adapter, claims.issuer, claims.subject)
```
`adapter` is Unknown, so the new annotation on `revoke_with_retry` verifies nothing
at the only place in `src/` that calls it. The bare parameter was a workaround for
the Protocol era and has no reason left to exist. FastAPI ignores the annotation
when the default is `Depends`, so adding it is safe -- `get_auth_service` already
does exactly this.
**Fix:**
```python
adapter: FirebaseAdminLookup = Depends(get_firebase_adapter)) -> Response:
```

## Info

### IN-01: Two dependency docstrings still name a seam that no longer exists

**File:** `src/nativespeaker/api/app/dependencies.py:111,116`
**Issue:** "The provider seam the lifespan built" and "The device-gate seam the
lifespan built" survive, but the seam was the Protocol and it is gone; both
accessors now return a concrete class. `AGENTS.md`'s own map calls the package
"external-SDK seams", so the word is codebase vocabulary rather than a coined
noun -- but these two lines describe a structure this phase deleted.
**Fix:** "The Firebase lookup the lifespan built." / "The DeviceCheck adapter the
lifespan built."

### IN-02: `ChallengesDB`'s docstring undercounts its own methods

**File:** `src/nativespeaker/api/crud/challenges.py:38`
**Issue:** "The four operations. No method commits." The class exposes five public
methods: `issue`, `locate`, `claim`, `consume` and `verify_binding`. The phase
edited this line to drop the now-false session clause and left the count. WR-03's
fix makes the sentence true.
**Fix:** Move `verify_binding` out (WR-03), or say five.

### IN-03: `__repr__` renders a call the constructor no longer accepts

**File:** `src/nativespeaker/api/crud/challenges.py:43-44`
**Issue:** `ChallengesDB(ttl_seconds=300)` was never a real constructor call and is
now a signature that would raise. No test asserts it. Keeping the session out of
the repr is right -- a DSN must not reach a log -- but the method as written claims
state the object does not hold.
**Fix:** Delete it, or render the module constant plainly:
`return f"ChallengesDB(ttl_seconds={CHALLENGE_TTL_SECONDS}, session=<bound>)"`.

### IN-04: The value type now sits behind the Firebase SDK import, and two guards on that went with the deleted module

**File:** `src/nativespeaker/api/auth/firebase.py:62-72`
**Issue:** `VerifiedProviderIdentity` moved from an SDK-free module into the one
module that imports `firebase_admin` at module scope. `services/auth.py` already
imported `firebase` for `lookup_with_retry`, so nothing regressed today, but any
future consumer of the value type -- a second provider adapter, a schema, a crud
class -- now pulls the SDK in to name it. The deleted
`tests/unit/test_adapter_interfaces.py` carried two guards that are gone with no
replacement: `test_the_source_imports_only_the_stdlib_and_this_project` (the value
type's module may import nothing but stdlib and this project) and
`test_the_seam_declares_no_enum_at_all` / `test_the_seam_declares_exactly_one_value_type`
(no outcome vocabulary crosses the provider boundary). The other twelve deleted
cases were either Protocol-shape assertions made moot, or are covered
behaviourally by `TestSelection` and `TestTheRevocation` in
`tests/unit/test_firebase_adapter.py`, so only these two are a real loss.
**Fix:** If the value type is meant to stay SDK-free, `schemas/` is where
`AGENTS.md:31` puts domain value types; otherwise record the coupling as accepted.

### IN-05: A stale build artifact still lists the deleted module

**File:** `src/ns_api_gateway.egg-info/SOURCES.txt:14`
**Issue:** Lists `src/nativespeaker/api/auth/adapters.py`. Generated, harmless, and
regenerates on the next build -- noted only so a future grep for the deleted module
is not read as a live reference.
**Fix:** None required; it should not be tracked if it is.

---

_Reviewed: 2026-09-18T01:15:06Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
