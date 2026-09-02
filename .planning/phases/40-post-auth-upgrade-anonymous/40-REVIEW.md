---
phase: 40-post-auth-upgrade-anonymous
reviewed: 2026-09-02T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - .env.example
  - migrations/20260818_01_initial-release.sql
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/tables/auth.py
  - tests/e2e/conftest.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_upgrade_anonymous.py
  - tests/schema/test_constraints.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_upgrade_precedence.py
findings:
  critical: 0
  warning: 8
  info: 4
  total: 12
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-09-02
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Reviewed the `POST /auth/upgrade-anonymous` implementation and the `/auth/challenge` issuance
rules that gate it, at `git diff 6dcdaa2..HEAD` scope.

The four items the executors flagged for scrutiny all hold up under direct inspection:

- **`_apply_upgrade` guard ordering is correct and load-bearing.** `services/auth.py:135` (both-anonymous)
  precedes `:138` (idempotent) precedes `:142` (drift). A reorder is caught by
  `test_a_live_anonymous_read_against_a_stored_anonymous_row_is_not_linked`, so the ordering is
  regression-protected, not just correct today.
- **`flip_provider`'s `PendingRollbackError` fix is complete.** `crud/identities.py:125-127` captures
  `stored_provider` and `identity_row_id` before the first assignment, and the `except IntegrityError`
  block at `:140-143` reads only locals. No ORM attribute access remains inside it. Verified against
  the whole method — there is no second attribute read.
- **The route is reachable only by linked callers.** `routers/auth.py:88` declares `get_linked_identity`,
  `test_app_wiring.py` asserts it structurally, and `/auth/upgrade-anonymous` is in neither exemption set.
  An unauthenticated caller is stopped at `get_identity`; an account-less caller is stopped by
  `get_linked_identity` on the route and by `routers/auth.py:53` on `/auth/challenge`.
- **`UpgradeRefused` leaks nothing.** `errors.py:399` builds the message from `type(self).__name__.lower()`
  and `log_fields()` at `:401-405` emits exactly three keys, none carrying `provider_uid`.
  `inspect.signature` is asserted in `test_rejection_vocabulary.py`, so a fourth constructor argument fails.
- **`.env.example` is clean.** Every added value is a placeholder (`...`) or a suffix fragment
  (`...apps.googleusercontent.com`). Nothing token-shaped, no key material.

Also verified as correct and not findings: the flip and the challenge consume commit in one transaction
(`services/auth.py:139-207`); `_release_google_account` runs before signup so a leftover holder cannot
break the link; `_resolve_provider` (`auth/firebase.py:120`) rejects an empty uid so the production
adapter cannot produce a `provider_uid`-less registered read; `ruff check` passes on `src/` and `tests/`;
`pytest` `addopts` carries no `--showlocals`, so no secret reaches a traceback frame dump.

What follows is what does not hold up. The recurring shape is **guards and docstrings that assert more
than the code delivers** — three findings (WR-01, WR-02, WR-05) are cases where a comment, docstring or
structural test states a property the phase's own change violates.

## Narrative Findings (AI reviewer)

### Warnings

### WR-01: `_apply_upgrade` claims to revalidate the locked rows but revalidates only the provider

**File:** `src/nativespeaker/api/services/auth.py:123-153`, `src/nativespeaker/api/crud/identities.py:61-74`

**Issue:** The docstring says "Revalidate the caller's locked rows", and the lock exists precisely so
state can be re-read under it. But nothing after the lock checks `identity_row.identity_state` or
`user.active`. Those two were checked once, at admission, in `IdentitiesDB.resolve` (`crud/identities.py:49-52`).

Between that check and the flip the request performs: challenge locate, challenge claim, **a full commit**,
and `lookup_with_retry` against Firebase — a network round trip with a retry budget, so seconds. An account
retired (`identity_state = historical`) or blocked (`users.active = false`) inside that window is still
upgraded: `registered_at` is stamped and the identity row flips to `google`/`apple`.

That flip is not reversible in effect. `ix_external_identities_provider_account` is documented as
"Partial, and carrying no state predicate, so retirement never frees a provider account for reuse"
(`migrations/20260818_01_initial-release.sql:107-110`). So a blocked account permanently burns the
provider-account slot on its way out.

This is an asymmetry the phase introduced: the create-user path *does* revalidate both fields inside the
transaction, in `_reject_existing_identity` (`services/auth.py:174-182`). The upgrade path took a stronger
lock and did less with it.

The likelihood is low today — nothing in the codebase writes `identity_state` or `users.active`, so only a
manual ops action triggers it. That is why this is a WARNING and not a BLOCKER. But the guard is cheap and
the docstring already promises it.

**Fix:** revalidate under the lock, reusing the classes `resolve` already raises:

```python
identity_row, user = located
if identity_row.identity_state != IdentityState.active:
    raise HistoricalIdentity
if user.active is not True:
    raise BlockedUser
stored = identity_row.provider
```

`HistoricalIdentity` and `BlockedUser` are already imported in `services/auth.py`; `IdentityState` is too.
Both answer 403 `account_unavailable`, matching the admission-time answer, so no new client-visible
vocabulary appears. Add a case to `TestTheUpgradeCaseMatrix` that flips `user.active` on the `account`
fixture and asserts `blocked_user`.

---

### WR-02: `/auth/challenge` issues handles for two operations no route can spend, and became a name oracle

**File:** `src/nativespeaker/api/routers/auth.py:47-59`

**Issue:** The check widened from `body.operation != AuthOperation.create_user.value` to
`body.operation not in AuthOperation`. `AuthOperation` has four members; only two —
`create_user` and `upgrade_anonymous_to_registered` — have a completion route. `AuthService._complete`
is invoked with nothing else (`services/auth.py:50-62`).

Two consequences, both of which the phase's own tests were edited to stop objecting to:

1. **Unspendable rows.** Any linked caller can now mint `core.auth_challenges` rows for
   `claim_anonymous_grant` and `claim_registered_grant`. Nothing consumes them and there is no reaper —
   grep for `auth_challenges` in `src/` finds `issue`, `locate`, `claim`, `consume` and no delete or
   expiry sweep. `ix_auth_challenges_expires_at` exists but nothing reads it. Expired rows accumulate
   forever, now at 4x the previous rate of operation names.

2. **A 200-vs-400 discriminator on operation names.** A linked caller gets `200` for
   `claim_registered_grant` and `400` for `nope`. An account-less caller gets `403 preauth_identity_not_allowed`
   for the former and `400 invalid_request` for the latter. Either way the four real names are
   distinguishable from invented ones.

   The docstring of `TestTheStringsOutsideTheVocabulary` (`tests/unit/test_challenge_endpoint.py:159`)
   asserts the opposite: *"One 400 for every one of them, so the route cannot be asked which operation
   names are real."* Its parametrize list was quietly narrowed in this phase — `claim_anonymous_grant`
   was **removed** from `_NOT_ISSUABLE`, whose old comment read "Members of the operation vocabulary
   whose phases are unbuilt". The prior code deliberately refused unbuilt operations; this phase removed
   that protection and edited the test that guarded it rather than the code.

The enum labels are public (they are in the committed migration), so this is disclosure of nothing secret —
hence WARNING, not Critical. But the row growth is real and the removed guard was deliberate.

**Fix:** gate issuance on the operations that actually have a completion route, not on enum membership:

```python
# The operations a route can spend today. A member with no completion route is not issuable.
_ISSUABLE = frozenset({AuthOperation.create_user,
                       AuthOperation.upgrade_anonymous_to_registered})

if body.operation not in _ISSUABLE:
    logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
    raise InvalidRequest
```

Note this collides with `TestTheIssuableSetIsTheEnumAndNothingElse` (see IN-02), which forbids any
module-level collection in the router — that test should be deleted rather than worked around, since its
premise ("the issuable set is the enum") is the defect. Restore `claim_anonymous_grant` and
`claim_registered_grant` to the not-issuable parametrize list, and re-enable
`TestTheRefusalOrderDisclosesNothing` over them.

---

### WR-03: `flip_provider` reports every `IntegrityError` as `ProviderAccountAlreadyLinked`

**File:** `src/nativespeaker/api/crud/identities.py:138-144`

**Issue:** The `except IntegrityError` arm attributes the failure to
`ix_external_identities_provider_account` unconditionally. The flush can raise `IntegrityError` for other
reasons on this table — most directly the `CHECK` at
`migrations/20260818_01_initial-release.sql:94-100`, which rejects a non-anonymous provider with a NULL or
empty `provider_uid`. If that fired, the client would receive `403 operation_not_allowed` ("the provider
account is held by another row") for what is actually a corrupted read or a caller bug, and the log line
would name a conflict that never happened.

Reachability through the shipped adapter is nil: `_resolve_provider` (`auth/firebase.py:120`) raises on a
falsy uid, so `VerifiedProviderIdentity` cannot carry `google` with `provider_uid=None`. But `flip_provider`
is a public CRUD method whose signature accepts `provider_uid: str | None` and which does not enforce
that invariant itself — it inherits it from a different module. A future second caller, or a change to the
classifier, turns a 500 into a misleading 403 silently. The same over-broad pattern exists in
`insert_account` (`:114-115`), so this is a shape being propagated rather than introduced.

**Fix:** discriminate on the constraint name, which asyncpg surfaces without any locale dependence
(and therefore does not violate `test_conflicts_are_never_discriminated_by_message_text`, which only
forbids `str(exc)`):

```python
except IntegrityError as conflict:
    constraint = getattr(getattr(conflict.orig, "__cause__", None), "constraint_name", None)
    if constraint != "ix_external_identities_provider_account":
        raise
    raise ProviderAccountAlreadyLinked(identity_row_id=identity_row_id,
                                       stored_provider=stored_provider,
                                       live_provider=provider) from conflict
```

A re-raised `IntegrityError` reaches `generic_error_handler` as a 500, which is the honest answer for a
broken invariant. If constraint-name coupling is unwanted, the cheaper alternative is an explicit
precondition before the assignments: `assert (provider is IdentityProvider.anonymous) == (provider_uid is None)`.

---

### WR-04: `google_linked_firebase_credential` leaks a real Firebase user when the link step fails

**File:** `tests/e2e/conftest.py:135-152`

**Issue:** `try`/`finally` opens at line 150, but the user is created at line 138 (`accounts:signUp`).
Three statements sit between creation and the guard:

- `link.raise_for_status()` (:147) — any non-2xx from `accounts:signInWithIdp`
- `assert linked["localId"] == local_id` (:149)
- a `KeyError` on `link.json()["idToken"]` at :150

Each aborts the fixture with `local_id` already created and never deleted. The leaked user is a *bare
anonymous* user with no Google link, so the self-healing path does not cover it either:
`_release_google_account` only finds users holding `ProviderIdentifier("google.com", ...)`. The leak is
permanent, in a shared Firebase project, and it accumulates one user per failed run.

`test_the_firebase_user_is_deleted_when_the_module_tears_down` does not catch this — it only exercises the
path where the fixture already reached its `yield`.

No secret leaks here: `httpx.HTTPStatusError` carries the URL and status, not the request body, so the
`client_secret` and `refresh_token` posted in `_google_id_token` stay out of the message, and `addopts`
carries no `--showlocals`. (The Firebase Web API key *is* interpolated into the URL at :140 and :145 and
would appear in a failure message, but that key is distributed in every client build and is not a secret.)

**Fix:** open the guard immediately after the user exists:

```python
signup.raise_for_status()
local_id = signup.json()["localId"]
try:
    link = httpx.post(...)
    link.raise_for_status()
    linked = link.json()
    assert linked["localId"] == local_id
    yield linked["idToken"], local_id
finally:
    auth.delete_user(local_id, app=admin_app)
```

---

### WR-05: the "no second race arbiter" structural guard now asserts a property this phase violated

**File:** `tests/unit/test_conflict_classification.py:271-281`

**Issue:** `_CREATION_SOURCE` concatenates `services/auth.py` and `crud/identities.py`, and the
parametrized case asserts that `"for update"` and `"select_for_update"` do not appear in either.
`lock_identity_and_user` (`crud/identities.py:69`) now calls `.with_for_update()` — a row lock, which the
case's own docstring names as forbidden: *"An advisory lock, a stricter isolation level or **a row lock**
would each be an arbiter that can disagree."*

The test passes only because `ast.unparse` emits `with_for_update` — underscore, not space — so neither
forbidden literal matches. The phase's response was to append a paragraph to the class docstring
rationalizing the exception, leaving the parametrize list untouched.

The result is a guard that reads as proving "this module takes no row lock" while the module takes one.
A future reviewer trusting it is misled, and a future genuinely-arbitrating `SELECT ... FOR UPDATE` added
via `.with_for_update()` would sail through unnoticed. The rationale itself is sound — the challenge claim
is the serialization point and this lock is revalidation — but a rationale belongs in the assertion, not
beside it.

**Fix:** make the exemption explicit and narrow, so a second lock still fails:

```python
    @pytest.mark.parametrize("forbidden", ["serializable", "advisory_lock", "pg_advisory",
                                           "isolation_level", "for update", "select_for_update",
                                           "with_for_update"])
    def test_no_second_serialization_mechanism_appears_in_the_code(self, forbidden):
        code = _code_only(_CREATION_SOURCE).lower()
        if forbidden == "with_for_update":
            # The upgrade path's one revalidation lock, named so a second one fails here.
            assert code.count(forbidden) == 1
            return
        assert forbidden not in code
```

---

### WR-06: the initial-release migration was edited in place, so applied databases silently diverge

**File:** `migrations/20260818_01_initial-release.sql:18-23`, `:385-396`

**Issue:** Three labels were dropped from `core.auth_operation` and the `operation IN (...)` CHECK was
deleted from `core.auth_challenges` — by rewriting the one existing migration file rather than adding a
new one. `pogo-migrate` (`pyproject.toml:37`) records applied migrations by id, so any database that already
ran `20260818_01` will never see these edits. Its `core.auth_operation` keeps seven labels and its
`auth_challenges` keeps the CHECK.

That is not a silent divergence for long — it breaks the phase's own tests against such a database:

- `tests/schema/test_inventory.py:71` asserts exactly four labels → fails on a stale DB.
- `tests/schema/test_constraints.py:566` now expects `InvalidTextRepresentationError`, but a stale DB still
  has the CHECK and raises `CheckViolationError` → fails.

So the new schema suite passes only against a freshly created database, and nothing in the repo says so.

For a pre-release app with no users this is the right *shape* of change (a follow-up `ALTER TYPE` that
cannot remove enum labels in PostgreSQL would be far worse). The gap is that the requirement to
drop-and-recreate is undocumented.

**Fix:** either add the recreate step to the migration file's header comment and to whatever runbook
`docs/` carries, or add a schema-test session guard that fails with an actionable message:

```python
async def test_the_schema_matches_the_current_migration_file(conn):
    """A database that applied an older revision of the one migration must be recreated, not patched."""
    labels = await conn.fetchval(
        "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'auth_operation'")
    assert labels == 4, "stale schema: drop and recreate the database, the migration was edited in place"
```

---

### WR-07: two different predicates decide "account-less", over a dataclass that couples neither field

**File:** `src/nativespeaker/api/routers/auth.py:53`, `src/nativespeaker/api/app/dependencies.py:59-63`,
`src/nativespeaker/api/schemas/auth.py:80-86`

**Issue:** This phase added `identity.identity is None` as the account-less test in `issue_challenge`.
The route-narrowing dependency `get_linked_identity` tests `identity.user is None` for the same concept.
`Identity` is a frozen dataclass with two independent `| None` fields and no validator tying them together:

```python
user: User | None = None
identity: ExternalIdentity | None = None
```

The coupling exists only as a convention inside `IdentitiesDB.resolve`, which returns either both or
neither. Nothing enforces it at the type or construction level, and the two consumers disagree about which
field is authoritative.

The consequence is already latent in the same file: `/auth/sync` (`routers/auth.py:106`) dereferences
`identity.identity.provider` after only `get_linked_identity`'s `user is None` check ran. An `Identity`
with `user` set and `identity` unset — constructible today, one line of a future resolver away — is an
`AttributeError` and a 500. `ChallengesDB.verify_binding` reads `identity.identity` too, and would silently
take the pre-auth branch for such a value, answering `ChallengeConsumed` for a linked caller.

**Fix:** make the coupling structural so both predicates become the same question:

```python
@dataclass(frozen=True, slots=True)
class Identity:
    issuer: str
    subject: str
    user: User | None = None
    identity: ExternalIdentity | None = None

    def __post_init__(self) -> None:
        # Both or neither: `resolve` is the only producer and never mixes them, and this is what says so.
        if (self.user is None) != (self.identity is None):
            raise ValueError("Identity carries a user without an identity row, or the reverse")

    @property
    def is_linked(self) -> bool:
        return self.identity is not None
```

Then use `not identity.is_linked` in both `issue_challenge` and `get_linked_identity`.

---

### WR-08: the e2e Google fixture makes two concurrent test runs mutually destructive

**File:** `tests/e2e/conftest.py:110-114`, `:132-133`

**Issue:** `_release_google_account` deletes *every* Firebase user currently holding the test Google
account, unconditionally, at fixture setup. There is one shared dedicated Google account and no lease,
lock or per-run namespacing.

Two runs against the same Firebase project — two CI jobs, or a developer running locally while CI runs —
interleave destructively: run B's setup deletes the linked user run A is mid-flight against. Run A's next
`/auth/upgrade-anonymous` then gets `UserNotFound` from the Admin SDK and answers 401, and
`TestTheRealGoogleLinkedUpgrade` fails for a reason that has nothing to do with the code under test.
The module-scoped `finally: auth.delete_user(local_id)` can also delete a user that run B has since
re-created under the same Google account.

`.env.example:20-24` documents the single-account design as intentional, but not the
"never run this suite twice at once" constraint that follows from it.

**Fix:** minimally, document the constraint where it will be read — in the `google_linked_firebase_credential`
docstring and in `.env.example` alongside the block that describes the account. Better, make the collision
detectable rather than silent: record `local_id` at setup and assert it is still the account's holder before
the real-upgrade case runs, so a concurrent run fails with a message naming the cause:

```python
found = auth.get_users([auth.ProviderIdentifier("google.com", google_subject)], app=admin_app)
assert [u.uid for u in found.users] == [local_id], \
    "another run took the shared test Google account; this suite cannot run concurrently"
```

---

### Info

### IN-01: `cause="empty"` misdescribes the condition it is attached to

**File:** `src/nativespeaker/api/services/auth.py:136`

**Issue:** `NotLinked(stage="upgrade_confirmation", cause="empty")` fires when the live read *classified
successfully as anonymous* — not when providerData was empty. `NotLinked` is documented in `errors.py:378`
as "A providerData shape outside the accept set", and the classifier's own causes are values like
`invalid-shape`. Reusing the class is defensible (identical 403 `operation_not_allowed`, no new
vocabulary), but `cause="empty"` sends an operator triaging `not_linked` looking for a malformed
provider record that does not exist. The `stage` field is doing all the real discrimination.

**Fix:** name the actual condition — `cause="still-anonymous"` — and update the assertion at
`tests/unit/test_upgrade_precedence.py:262`.

---

### IN-02: `test_the_router_module_declares_no_module_level_collection` guards almost nothing

**File:** `tests/unit/test_challenge_endpoint.py:250-258`

**Issue:** The case parses the router module and asserts no module-level `Assign` has a
`List`/`Set`/`Dict`/`Tuple` value. It passes today because the module happens to declare only `logger` and
`router`. It does not establish that the issuable set is the enum — a `frozenset(...)` call, a set
comprehension, a class attribute or a module constant built by any other expression all slip through, while
an unrelated future `_RETRYABLE = (...)` would fail it for no reason.

It is also the test that will obstruct the correct fix for WR-02.

**Fix:** delete it. The property it gestures at is better stated by
`TestTheIssuableOperations`, which drives the real route over the real vocabulary.

---

### IN-03: schema test docstring and parametrize ids drift after the CHECK removal

**File:** `tests/schema/test_constraints.py:563-573`

**Issue:** `TestAuthChallengeConstraints`'s docstring still opens "The challenge operation partition,
and the lifecycle and binding CHECKs" — the partition CHECK was deleted from the migration in this phase.
The parametrize list still enumerates `restore_subscription`, `sign_out_all`, `sync`, which are now just
three arbitrary non-members of the enum type; the case tests the enum type, not a partition, and the
three names no longer mean anything.

**Fix:** drop "the challenge operation partition" from the class docstring and note that the enum type
itself is now the only partition; either keep the three former names with a comment saying why
(regression value: these were once legal) or replace them with an arbitrary invalid string.

---

### IN-04: the deletion-proof fixture silently no-ops when its recording case is deselected

**File:** `tests/e2e/test_upgrade_anonymous.py:44-56`

**Issue:** `_google_user_deleted_after_teardown` performs its `pytest.raises(auth.UserNotFoundError)`
check only if `holder["local_id"]` was populated, which happens only inside
`test_the_firebase_user_is_deleted_when_the_module_tears_down`. Any `-k` selection, `-x` abort, or an
earlier failure in the class that skips that one case turns the whole deletion proof into a silent pass.
The comment at :50 acknowledges the deselection case; it does not acknowledge that the proof therefore
holds only when the full module runs.

Fixture ordering itself is fine — `autouse=True` at module scope places it before the credential fixture
in the closure, so its finalizer runs after.

**Fix:** state the coupling in the docstring, or record `local_id` from the credential fixture directly
rather than from a test body, so the proof runs whenever the credential was built:

```python
@pytest.fixture(scope="module", autouse=True)
def _google_user_deleted_after_teardown(_app_lifespan, _app_config, request):
    yield
    ...
```

---

_Reviewed: 2026-09-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
