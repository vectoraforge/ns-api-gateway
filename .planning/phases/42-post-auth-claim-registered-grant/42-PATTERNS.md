# Phase 42: POST /auth/claim-registered-grant - Pattern Map

**Mapped:** 2026-09-03
**Files analyzed:** 20 (7 source, 1 migration, 12 test)
**Analogs found:** 20 / 20 (every file is an edit of, or a sibling to, a Phase 41 file)

Every path below is git-tracked source in `/home/init/native-speaker/ns-api-gateway`. Line numbers
are as of this mapping.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/routers/auth.py` (edit: 6th route) | route | request-response | same file, `claim_anonymous_grant` :99-119 | exact |
| `src/nativespeaker/api/services/auth.py` (edit: seam + post-claim) | service | request-response | same file, `complete_claim_anonymous_grant` :83-92 + `_claim_anonymous_grant` :147-180 | exact |
| `src/nativespeaker/api/crud/grants.py` (edit: writer; remove anti-abuse) | crud | CRUD (transactional write) | same file, `activate_anonymous_device_grant` :86-133 | exact |
| `src/nativespeaker/api/errors.py` (edit: 4th `ClaimRefused` leaf) | model (error tree) | — | same file, `ClaimantNotAnonymous` :444-445 | exact |
| `src/nativespeaker/api/schemas/auth.py` (edit or sibling request model) | schema | request-response | same file, `AnonymousGrantClaimRequest` :31-35 | exact |
| `src/nativespeaker/api/tables/grants.py` (delete `AccessGrantAntiAbuse`) | model | — | same file :71-86 (the block to delete) | exact |
| `src/nativespeaker/api/tables/__init__.py` (drop 2 mentions) | config (barrel) | — | same file :2, :32 | exact |
| `migrations/20260818_01_initial-release.sql` (D-07 deletion) | migration | — | itself; ranges in RESEARCH.md "Pattern 5" | exact |
| `tests/e2e/test_claim_registered_grant.py` (**new**) | test (e2e) | request-response | `tests/e2e/test_claim_anonymous_grant.py` (348 lines) | exact |
| `tests/unit/test_claim_precedence*.py` registered sibling (**new**) | test (unit) | request-response | `tests/unit/test_claim_precedence.py` (632 lines) | exact |
| `tests/unit/test_grant_sources.py` (registered walk) | test (unit, AST) | transform | same file, `TestTheAnonymousDeviceGrantHasExactlyOneWriter` :67-85 | exact |
| `tests/unit/test_claim_ordering.py` (extend) | test (unit, AST) | transform | same file :100-114 | exact |
| `tests/unit/test_app_wiring.py` (2 parametrize lists) | test (unit) | — | same file :40-41, :48-49 | exact |
| `tests/unit/test_rejection_vocabulary.py` (4th arm) | test (unit) | — | same file :46, :56ff, :364-388 | exact |
| `tests/schema/test_claim_race.py` (2 new race classes) | test (schema) | event-driven (2 connections) | same file :251-344 | exact |
| `tests/schema/test_grant_locks.py` (registered writer fixture) | test (schema) | — | same file :250-317 | exact |
| `tests/schema/test_inventory.py` (4 literals) | test (schema) | — | itself | exact |
| `tests/schema/test_constraints.py` (drop anti-abuse cases) | test (schema) | — | itself | exact |
| `tests/e2e/conftest.py` (drop `with_anti_abuse`) | test fixture | — | same file, `seed_grant` :324-361 | exact |
| `.planning/REQUIREMENTS.md`, `.planning/STATE.md` | docs | — | the Phase 41 ANONGRANT entries | exact |

---

## Pattern Assignments

### `routers/auth.py` — the sixth route (route, request-response)

**Analog:** the same file, `claim_anonymous_grant`.

**Handler shape** (`src/nativespeaker/api/routers/auth.py:98-119`) — copy verbatim, changing the
path, the request model, the service method and the summary:

```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/claim-anonymous-grant",
             response_model=SyncResponse,
             summary="Claim the caller's one anonymous device grant",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, verifies the device through "
                         "Apple DeviceCheck and activates the grant.")
async def claim_anonymous_grant(body: AnonymousGrantClaimRequest,
                                response: Response,
                                identity: Identity = Depends(get_linked_identity),
                                service: AuthService = Depends(get_auth_service),
                                sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Complete the operation the body's handle stands for, and report the entitlement it left."""
    # Forwarded untouched and never logged: the handle and the device token are secrets.
    await service.complete_claim_anonymous_grant(identity=identity,
                                                 challenge_id=body.challenge_id,
                                                 device_token=body.device_token)
    # Read after the completion committed, so the claim, the repeat and the race loser share one shape.
    entitlement = await sync_service.read_entitlement(identity.user.id)
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```

D-12 is satisfied purely by copying this: `identity_provider` is already the **stored** provider off
the identity row, and the repeat and the race loser share the post-commit read by construction.

**Module docstring** (`:1-3`) — currently exactly three lines and it names five routes. Pitfall 6:
`tests/unit/test_docstring_bar.py` asserts `== 0` overflow, so the rewrite must still be **three
lines** while naming six routes:

```python
"""The five auth routes: `/auth/challenge` issues a challenge, `/auth/create-user`,
`/auth/upgrade-anonymous` and `/auth/claim-anonymous-grant` spend one, and `/auth/sync` reports
what the caller's account entitles it to."""
```

---

### `services/auth.py` — the seam and the post-claim work (service, request-response)

**Analog:** the same file, `complete_claim_anonymous_grant` + `_claim_anonymous_grant`.

**The public seam** (`src/nativespeaker/api/services/auth.py:83-92`) — mirror exactly, swapping the
operation member and the private post-claim:

```python
    async def complete_claim_anonymous_grant(self, *,
                                             identity: Identity,
                                             challenge_id: str,
                                             device_token: str) -> None:
        """Claim the caller's one anonymous device grant; the entitlement is read back after commit."""
        await self._complete(identity=identity,
                             challenge_id=challenge_id,
                             operation=AuthOperation.claim_anonymous_grant,
                             post_claim=partial(self._claim_anonymous_grant,
                                                device_token=device_token))
```

`_complete` (`:94-139`) is **not** touched: it already does locate → verify_binding → operation
match → claim → commit → `post_claim` → consume, and it already rolls back and consumes quietly on
any `AppError`.

**The tier constant** (`:45-46`) — add the sibling immediately below:

```python
# The seeded `core.access_tiers` row an anonymous device grant points at.
ANONYMOUS_TIER_ID = "anonymous"
```

**The post-claim body — the model, and the four lines that must NOT be copied**
(`src/nativespeaker/api/services/auth.py:147-180`):

```python
    async def _claim_anonymous_grant(self, identity: Identity, *, device_token: str) -> None:
        """Refuse, or verify the device with Apple and activate the grant inside one transaction."""
        # D-08: the stored provider column is the sole classifier, and it is tested positively.
        if identity.identity.provider is not IdentityProvider.anonymous:
            raise ClaimantNotAnonymous

        held = await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at)
        if any(grant.source is AccessGrantSource.anonymous_device_grant for grant in held):
            # The repeat: nothing is written, Apple is never reached, and the entitlement is read after commit.
            return
        # D-03: an ineligible account never costs an Apple round trip, and both arms decide before Apple.
        consumed = identity.identity.free_grant_consumed_at is not None
        if consumed or await self.grants_db.has_prior_free_grant(identity.user.id):
            # Read at any status, as the lifetime index is: revocation and expiry never reopen the slot.
            raise FreeGrantAlreadyConsumed
        if held:
            raise OtherActiveGrantHeld

        # One token for both calls: the bit the read decided on is the bit the write then sets.
        state = await read_bits_with_retry(self.devicecheck, device_token)
        if state.bit0:
            raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")

        # bit1 is carried forward, never fabricated: Apple writes both bits in this one call.
        await write_bits_with_retry(self.devicecheck, device_token, bit0=True, bit1=state.bit1)

        activated = await self.grants_db.activate_anonymous_device_grant(
            user_id=identity.user.id,
            identity_row=identity.identity,
            tier_id=ANONYMOUS_TIER_ID,
            evaluated_at=self.evaluated_at)
        if not activated:
            # The unique indexes are the arbiter, and the loser answers exactly as the repeat does.
            await self.session.rollback()
```

**Copy from this:** the positive stored-provider test as the first statement; `read_effective_grants`
once into a local named `held`; the bare `return` for the repeat; the Apple read → `bit` check →
Apple write → writer order; `if not activated: await self.session.rollback()` as the last two lines.

**Do NOT copy** (Pitfall 4, D-09): the two lines

```python
        consumed = identity.identity.free_grant_consumed_at is not None
        if consumed or await self.grants_db.has_prior_free_grant(identity.user.id):
```

Both are already true on the conversion path. Phase 42's guard is the grant history read **by source
and status**, and the branch order is D-09 (a) repeat → (b) `OtherActiveGrantHeld` → (c) conversion →
(d) new grant → (e) `FreeGrantAlreadyConsumed`. Apple is reached only on (d), so the two
`*_with_retry` calls move inside that arm.

**Bit substitution** (D-01): read `state.bit1` instead of `state.bit0`, and write
`write_bits_with_retry(self.devicecheck, device_token, bit0=state.bit0, bit1=True)` — bit0 carried
forward exactly as bit1 is carried above. The `DeviceGrantExhausted(stage="devicecheck_read",
cause="already_set")` call is reused unchanged (same class, same copy, per D-01).

---

### `crud/grants.py` — the writer (crud, transactional CRUD)

**Analog:** the same file, `activate_anonymous_device_grant`.

**The lock-order prologue — verbatim, four lines, reused unchanged**
(`src/nativespeaker/api/crud/grants.py:92-98`):

```python
        grants = await self.lock_effective_grants(user_id, evaluated_at)
        for grant in grants:
            await self.lock_usage(grant.id)

        # A plain re-read, never `lock_identity_and_user`: a user-row lock ahead of the grant locks is forbidden.
        stored = await IdentitiesDB(self.session).resolve_existing(issuer=identity_row.issuer,
                                                                   subject=identity_row.subject)
```

`lock_usage` returns the usage row (`:69-72`), which the conversion needs anyway — capture it per
grant instead of discarding it.

**The in-lock re-check and the row build** (`:99-125`):

```python
        if stored is None or stored.provider is not IdentityProvider.anonymous:
            return False
        if grants or stored.free_grant_consumed_at is not None:
            return False
        if await self.has_prior_free_grant(user_id):
            return False

        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.anonymous_device_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=evaluated_at.strftime("%Y-%m"),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))
        stored.free_grant_consumed_at = evaluated_at
        stored.native_claim_platform = NativeClaimProvider.ios_devicecheck
        stored.updated_at = evaluated_at
```

(The `AccessGrantAntiAbuse(...)` block at `:113-117` and the import at `:14` are the D-07 deletion —
already elided above, so the excerpt is the post-deletion shape.)

For Phase 42, the re-check swaps to `stored.provider in (IdentityProvider.google,
IdentityProvider.apple)` (D-05) and the three-line eligibility block becomes the D-09 destination
re-decision. `free_grant_consumed_at` is set **where unset** (D-10), not unconditionally.

**The transaction close — verbatim, this exact shape** (`:127-133`):

```python
        # Only the flush is inside, and all three rows go in it: the two FKs are deferred to commit.
        try:
            await self.session.flush()
        except IntegrityError:
            # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
            return False
        return True
```

Nothing but the flush inside the `try`; no nested `try`; the constraint is never named. If the
conversion needs an early flush (Pitfall 1: the expiry UPDATE must be emitted before the INSERT, and
SQLAlchemy orders inserts before updates in one flush), that earlier flush needs the **same**
one-statement `try`/`except IntegrityError: return False` wrapper — not a widened one.

**Comment on the FK count:** the `# ... all three rows go in it: the two FKs are deferred to commit.`
comment is inaccurate after D-07 removes the anti-abuse row. Rewrite it in the same one-line style.

**Existing reads to reuse rather than rebuild:** `read_effective_grants` (`:63-67`),
`_prior_free_grant_statement` (`:44-48`), `has_prior_free_grant` (`:82-84`), `read_usage` (`:74-76`).
`_effective_grants_statement` (`:23-35`) must stay as it is — no `.limit()`, `== active` tested
positively.

**Module docstring** (`:1-2`) — the second line is the global lock order and stays; the first line
names one writer and must be rewritten to cover two, still within three lines:

```python
"""Entitlement reads over `core.access_grants`, and the one writer of an anonymous device grant.
Global lock order: grant rows ascending by id, then usage rows, and never a third tier."""
```

---

### `errors.py` — the fourth `ClaimRefused` leaf (model)

**Analog:** `src/nativespeaker/api/errors.py:436-453`.

```python
class ClaimRefused(AppError):
    """The claim's refusals share this shape, and its leaves add only their own name."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"


class ClaimantNotAnonymous(ClaimRefused):
    """The stored identity row is registered, so the anonymous claim is not the route that serves it."""


class FreeGrantAlreadyConsumed(ClaimRefused):
    """The account's one lifetime free grant is spent; revocation and expiry never reopen the slot."""


class OtherActiveGrantHeld(ClaimRefused):
    """The account already holds an active grant of another source, and one user holds at most one."""
```

The new leaf is `class <Name>(ClaimRefused):` plus a one-line docstring and nothing else — no
`status`, no `code`, no `__init__`, no fields. Those four absences are asserted per arm at
`tests/unit/test_rejection_vocabulary.py:371-382`. `FreeGrantAlreadyConsumed` and
`OtherActiveGrantHeld` are reused unchanged by D-09(e) and D-09(b); `DeviceGrantExhausted`
(`errors.py:427-430`, 403 `device_grant_exhausted`) is reused unchanged by D-01.

---

### `schemas/auth.py` — the request model (schema, request-response)

**Analog:** `src/nativespeaker/api/schemas/auth.py:31-35`:

```python
class AnonymousGrantClaimRequest(BaseModel):
    """The claim body: the handle, and the DeviceCheck token naming the device."""
    challenge_id: str = Field(..., min_length=1)
    # One token for the read and the write: two would let the bit read name a different device.
    device_token: str = Field(..., min_length=1)
```

Field-for-field identical to what D-04 requires. Discretion (CONTEXT "Claude's Discretion") is
whether to rename this to a shared name or add a sibling; either way `min_length=1` on both fields is
what produces the framework 422. `SyncResponse` (`:68-71`), `Entitlement` (`:58-65`) and
`EntitlementType.registered_account_grant` (`:48`) already exist and need no edit.

---

### `tables/grants.py` + `tables/__init__.py` — the D-07 model removal

Delete `src/nativespeaker/api/tables/grants.py:70-86` (the `# The table's one GENERATED ALWAYS AS
STORED column...` comment plus `class AccessGrantAntiAbuse`). Delete the two mentions in
`tables/__init__.py:2` (the `__all__` string) and `:32` (the import).

**Do not touch** `FREE_GRANT_SOURCES` (`tables/grants.py:29-30`) — Pitfall 5; it is bound to the live
index predicate by `tests/schema/test_grant_locks.py:324-331`. `NativeClaimProvider` stays imported
by `crud/grants.py` because `stored.native_claim_platform` is still written.

---

### `tests/schema/test_claim_race.py` — the two-connection race (test, event-driven)

**Analog:** the same file, in full. Everything below is reusable machinery; only the three seeding
helpers and the assertions change.

**Reuse unchanged:** `_Harness` / `harness` fixture (`:33-54`), `read` / `scalar` (`:83-91`),
`_NeverSetDevice` (`:125-138`), `_RacingSession` (`:140-170`), `_Attempt` (`:173-186`), `role_of` /
`status_of` (`:189-196`), `prepare_attempt` (`:199-201`), `resolve_identity` (`:204-209`),
`barrier_for` (`:238-248`), `NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)` (`:27`).

**The per-attempt entry point** (`:212-235`) — swap only the completion call:

```python
async def run_attempt(harness: _Harness, attempt: _Attempt, before_first_flush=None) -> _Attempt:
    """Drive the production completion once, on its own session and connection, as the route does."""
    store = ChallengesDB()
    identity = await resolve_identity(harness, attempt.subject)
    async with harness.factory() as real_session:
        session = _RacingSession(real_session, before_first_flush)
        attempt.caller_rows_detached = all(
            object_session(row) is None for row in (identity.user, identity.identity))
        service = AuthService(db=session, challenge_store=store, adapter=None,
                              evaluated_at=NOW, devicecheck=_NeverSetDevice())
        try:
            await service.complete_claim_anonymous_grant(
                identity=identity,
                challenge_id=attempt.challenge_id,
                device_token=f"device-{attempt.name}")
        except AppError as rejection:
            attempt.result = rejection
        else:
            # The route's own read, after the completion committed: the claim, the repeat and the loser share it.
            attempt.result = await SyncService(db=session,
                                               evaluated_at=NOW).read_entitlement(identity.user.id)
        attempt.integrity_at_flush = session.integrity_at_flush
        attempt.integrity_at_commit = session.integrity_at_commit
    return attempt
```

The `caller_rows_detached` assertion (`:276-278`) is a Phase 41 review addition — preserve it.

**Seeding helper to fork** (`:94-106`) — a `google` row **must** carry a non-empty `provider_uid`
(the table CHECK); the anonymous version leaves it NULL:

```python
async def commit_anonymous_account(harness: _Harness, *, subject: str) -> uuid.UUID:
    """One anonymous identity and its user, committed, because each attempt reads them on its own connection."""
    user_id, identity_id = uuid.uuid4(), uuid.uuid4()
    async with harness.engine.begin() as conn:
        await conn.execute(text("INSERT INTO core.users (id) VALUES (:id)"), {"id": user_id})
        # provider_uid stays NULL, which is the table's CHECK for exactly the anonymous arm.
        await conn.execute(
            text("INSERT INTO core.external_identities "
                 "(id, user_id, issuer, subject, provider, identity_state, created_at, updated_at) "
                 "VALUES (:id, :user_id, :issuer, :subject, 'anonymous', 'active', :now, :now)"),
            {"id": identity_id, "user_id": user_id, "issuer": harness.issuer,
             "subject": subject, "now": NOW})
    return user_id
```

**Challenge seeding** (`:109-122`) — the only change is the operation literal
`'claim_anonymous_grant'` → `'claim_registered_grant'`. The enum member already exists in the
database type.

**Assertion style to copy** (`:284-344`) — one narrow case per fact, each reading on its own
connection: exactly one grant row `[("anonymous_device_grant", "active", "anonymous")]`; exactly one
usage row `[("2026-08", 0)]`; the marker read as a single value `[(NOW, "ios_devicecheck")]`; both
challenges consumed with `preauth_subject` cleared; the loser 200 with a field-for-field
`model_dump()` match; `(integrity_at_flush, integrity_at_commit) == (True, False)`.

**D-07 edits to this file:** the `DELETE FROM core.access_grants_anti_abuse ...` statement in
`clean_up` (`:66-68`), the `clean_up` docstring (`:58`),
`test_exactly_one_anti_abuse_row_carries_the_ios_provider` (`:292-301`), and the prose in the final
case's docstring (`:341`, "the deferred anti-abuse FKs are never reached" — the assertion holds, the
sentence does not).

**Conversion seeding (Pitfall 2):** seed the anonymous grant with `starts_at = NOW - timedelta(...)`,
strictly before `NOW`. The table CHECK is `ends_at IS NULL OR ends_at > starts_at` — strict `>`.

---

### `tests/schema/test_grant_locks.py` — the lock-order proof (test)

**Analog:** the `activation_statements` fixture (`:250-274`) and
`TestTheActivationAddsNoThirdLockTier` (`:286-317`). Add a **sibling fixture** driving the registered
writer, not a mirrored literal — the assertion reads emitted SQL at `before_cursor_execute`:

```python
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        recorded.append(" ".join(statement.split()))
```

```python
    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_claim_path(self,
                                                                               activation_statements):
        """Two, and never a third: a writer that locks the identity or user row first fails here, not in production."""
        taken = [relation_of(statement) for statement in locking(activation_statements["statements"])]
        assert len(set(taken)) == 2
        assert "core.external_identities" not in taken
        assert "core.users" not in taken
```

Copy also `test_the_identity_row_is_revalidated_by_a_plain_re_read` (`:306-316`) — it counts exactly
one non-`FOR UPDATE` `core.external_identities` statement, and asserts no `INSERT` ran, which is the
control that stops the two-tier count from passing vacuously.

---

### `tests/unit/test_grant_sources.py` — the single-writer AST walk (test, transform)

**Analog:** the whole file. The registered walk is the same code with `MEMBER`, `WRITER` and
`NAMING_MODULES` changed:

```python
MEMBER = "anonymous_device_grant"
ENUM = "AccessGrantSource"
WRITER = "activate_anonymous_device_grant"

# Every module under `src/` that names the member off its enum. A new entry is a new site to justify.
NAMING_MODULES = {
    "nativespeaker/api/crud/grants.py",
    "nativespeaker/api/services/auth.py",
    "nativespeaker/api/tables/grants.py",
}
```

```python
    def test_the_whole_tree_holds_exactly_one_construction_site(self):
        sites = {path.relative_to(SRC).as_posix(): _construction_sites(path.read_text())
                 for path in _modules()}
        found = {module: lines for module, lines in sites.items() if lines}
        assert list(found) == ["nativespeaker/api/crud/grants.py"]
        assert len(next(iter(found.values()))) == 1

    def test_the_one_site_is_inside_the_crud_activation_writer(self):
        """Not merely in the right module: in the one function that takes both lock tiers."""
        writer = _function(CRUD_GRANTS.read_text(), WRITER)
        assert sum(_names_the_member(node) for node in ast.walk(writer)) == 2
```

Note `== 2` counts mentions inside the writer (the construction plus the eligibility comparison) —
recount it for the registered writer rather than copying the number.

**Copy `TestTheWalkFires` (`:108-128`) too** — it is the mutation control that RESEARCH.md asks for:
a synthetic two-site module counts as two, and three near-misses count as zero. The `another_table`
near-miss at `:120` names `AccessGrantAntiAbuse`; after D-07 that id is misleading — replace the
synthetic source, keeping the case (it is parsed by `ast`, never imported, so it still passes today).

---

### `tests/unit/test_claim_ordering.py` — the no-network-under-a-lock proof (test)

**Analog:** the same file. Extend the two constants and add a registered case:

```python
WRITER = "activate_anonymous_device_grant"
CLAIM = "_claim_anonymous_grant"

# Every name the device-gate seam exposes. None of them may appear inside the crud writer.
SEAM_NAMES = frozenset({"devicecheck", "read_bits", "write_bits",
                        "read_bits_with_retry", "write_bits_with_retry",
                        "DeviceCheckAdapter", "AppleDeviceCheck", "BitState"})

# The crud module's import roots: the standard library, the ORM it is written in, and this project.
ALLOWED_IMPORT_ROOTS = {"datetime", "uuid", "sqlalchemy", "sqlmodel", "nativespeaker"}
```

```python
    def test_the_read_and_the_write_both_appear_before_the_activation_call(self):
        claim = _function(SERVICE_SOURCE, CLAIM)
        read, write, activate = _order(claim, ("read_bits_with_retry",
                                                "write_bits_with_retry",
                                                WRITER))
        assert read < write < activate

    def test_the_claim_takes_no_lock_of_its_own_before_reaching_the_seam(self):
        """Locking is the crud writer's job alone, and it runs last; a lock here would straddle the call."""
        claim = _function(SERVICE_SOURCE, CLAIM)
        assert {"lock_effective_grants", "lock_usage",
                "lock_identity_and_user"} & set(_called_names(claim)) == set()
```

`ALLOWED_IMPORT_ROOTS` must stay as it is — the registered writer adds no import root.

---

### `tests/unit/test_claim_precedence.py` — the precedence and consumption matrix (test)

**Analog:** the whole 632-line file; the registered sibling reuses its scaffolding wholesale.

**Reusable stubs, unchanged:** `_FakeChallengeStore` (`:50-84` — its `claim`/`consume` mirror the
real conditional updates clause for clause), `_StubSession` (`:87-115` — records boundaries and
refuses queries, so an unstubbed write shows up), `_RecordingGrants` (`:117-142`),
`_ScriptedDeviceCheck` (`:145-174`), `_StubSync` (`:176-186`), the `timeline`/`store`/`session`/
`account`/`identity`/`grants`/`devicecheck`/`client` fixtures (`:189-263`), `_issued_row` (`:265`),
`_claim` (`:285`), `_a_grant` (`:290`).

**The three test-class shapes to mirror:**
- `TestTheRejectionsBeforeTheClaimSpendNothing` (`:295-336`) — nothing consumes before the claim.
- `TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce` (`:370-512`) — one case per destination.
  Phase 42 has ten outcomes: repeat, conversion, new grant, `OtherActiveGrantHeld`,
  `FreeGrantAlreadyConsumed`, the anonymous-caller leaf, `DeviceGrantExhausted`, `ProofRejected`,
  `Unavailable`, race loss.
- `TestTheConsumptionCounterIsOneForEveryPostClaimOutcome` (`:589-603`) — the same outcomes again as
  a parametrized setup-function table (`_registered`, `_slot_spent`, ... `:544-585`).
- `TestNoVendorCallHappensUnderALockOrInsideTheTransaction` (`:605-628`).

The header constants are reusable as written:

```python
REFUSED = {"code": "operation_not_allowed"}
CHALLENGE_REQUIRED = {"code": "challenge_required"}
```

---

### `tests/e2e/test_claim_registered_grant.py` (new) — end to end (test)

**Analog:** `tests/e2e/test_claim_anonymous_grant.py`, in full.

**Module header and helpers** (`:1-46`):

```python
"""The anonymous device-grant claim, end to end through the real router against a real database."""
...
pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-anonymous-subject"

# One token, naming the device the read and the write both act on.
DEVICE_TOKEN = "device-token-tracer"


@pytest_asyncio.fixture(loop_scope="module")
async def claim_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}
```

**The happy-path assertion block** (`:58-110`) — the prepare/claim pair, the `no-store` header, the
six entitlement fields, the two device-gate call lists, and the row reads. For Phase 42:
`"claim_registered_grant"`, `"/auth/claim-registered-grant"`, `identity_provider == "google"`,
`type == "registered_account_grant"`, `tier_id == "registered"`, `monthly_credits == 50`, and the
write call becomes `[(DEVICE_TOKEN, False, True)]` (bit0 carried forward, bit1 set).

```python
        assert claim.status_code == 200, claim.text
        assert claim.headers["Cache-Control"] == "no-store"
        body = claim.json()
        assert body["identity_provider"] == "anonymous"
        assert body["entitlement"]["type"] == "anonymous_device_grant"
        ...
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        # The update carried the query's bit1 forward, set only bit0, and named the device that was read.
        assert scripted_devicecheck_adapter.write_calls == [(DEVICE_TOKEN, True, False)]
```

**The class layout to mirror:** `TestTheAnonymousDeviceGrantHappyPath` (`:50`),
`TestTheRepeatIsIdempotent` (`:178`), `TestTheFourRefusals` (`:211`),
`TestTheThreeAppleFailureArms` (`:292`). Phase 42's conversion case is a fifth class with no
counterpart — assert the anonymous row is `expired` with `ends_at = evaluated_at`, exactly one active
grant, and the usage row's `monthly_period`/`monthly_used` carried unchanged.

`test_a_registered_caller_is_refused_and_waits_for_phase_42` (`:272`) in the **anonymous** file is
still correct and is not changed by this phase (Phase 41 D-08 declined that direction).

**D-07 edits:** drop the `AccessGrantAntiAbuse` import (`:20`), the `NativeClaimProvider` import if
unused (`:25`), and the anti-abuse assertions at `:96-103`.

---

### `tests/e2e/conftest.py::seed_grant` — the D-07 fixture edit

**Analog:** the same function (`:324-361`). Delete the `with_anti_abuse` parameter (`:334`), its
branch (`:348-353`), the `AccessGrantAntiAbuse` / `NativeClaimProvider` imports (`:23`, `:32`), the
comment at `:339`, and every caller passing `with_anti_abuse=True`. Afterwards a free-source grant is
seedable with no companion row — which is what the registered e2e cases need:

```python
async def seed_grant(factory, *,
                     user_id: UUID,
                     tier_id: str = REGISTERED_TIER_ID,
                     source: AccessGrantSource = AccessGrantSource.manual,
                     status: AccessGrantStatus = AccessGrantStatus.active,
                     monthly_period: str | None = None,
                     monthly_used: int = 0,
                     starts_at: datetime | None = None,
                     ends_at: datetime | None = None,
                     with_usage: bool = True):
```

`REGISTERED_TIER_ID = "registered"` already exists at `tests/e2e/conftest.py:40`.

---

### `tests/unit/test_app_wiring.py` and `tests/unit/test_rejection_vocabulary.py` — the literal sets

`test_app_wiring.py:40-41` and `:48-49` — add the path to **both** parametrize lists, and to neither
exemption set at `:12-13`:

```python
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
...
    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant", "/users/me"))
```

`test_rejection_vocabulary.py` — four coordinated edits for the fourth leaf:

```python
# The three leaves under the claim's 403 base, listed on the same terms.
CLAIM_ARMS = (ClaimantNotAnonymous, FreeGrantAlreadyConsumed, OtherActiveGrantHeld)
```

```python
class TestTheThreeClaimArmsAnswerOneThingAndLogThree:
    """T-41-16: distinguishable refusals would make the claim an account-state oracle for a token holder."""

    def test_the_three_are_exactly_the_leaves_under_the_shared_base(self):
        """A fourth arm added without coming here would be a refusal nobody checked the answer of."""
        assert set(_family(ClaimRefused)) == set(CLAIM_ARMS)
    ...
    def test_the_three_are_three_distinct_log_events_and_one_client_answer(self):
        events = [camel_to_snake(arm.__name__) for arm in CLAIM_ARMS]
        assert sorted(events) == sorted(set(events))
        assert set(events) == {"claimant_not_anonymous", "free_grant_already_consumed",
                               "other_active_grant_held"}
```

Edit `CLAIM_ARMS` (`:46`), the import block (`:14-33`), `EVENT_NAMES` (`:56ff`), the class name and
docstring (`:364-365`), and the exact-string set (`:387-388`). The leaf's class name **is** the log
event name — `camel_to_snake` derives it mechanically.

---

## Shared Patterns

### Lock order — the fixed global order, in every writer

**Source:** `src/nativespeaker/api/crud/grants.py:92-98` (excerpted in full above).
**Apply to:** the Phase 42 writer, and nothing else.
Grant rows ascending by id (`ORDER BY core.access_grants.id ASC`), then their usage rows, then a
**plain re-read** of the identity row. Never `lock_identity_and_user` on a claim path. Proven over
emitted SQL by `tests/schema/test_grant_locks.py:291-304`.

### Transaction close — one flush, one narrow `try`

**Source:** `src/nativespeaker/api/crud/grants.py:127-133`.
**Apply to:** every write in `crud/grants.py`.
Only the flush inside the `try`; no nested `try`; `IntegrityError` → `return False`; the constraint is
never named and the message never parsed. `commit()`/`rollback()` stay in `services/` (AGENTS.md
exception 3) — see `services/auth.py:180`.

### Post-claim seam — `_complete(post_claim=partial(...))`

**Source:** `src/nativespeaker/api/services/auth.py:83-92` and `:94-139`.
**Apply to:** the new completion. `_complete` already consumes on **every** post-claim outcome,
including the `AppError` path (`:128-135` rolls back, then `_consume_quietly`). Do not fork it.

### Apple seam — one token, both calls, bit carried forward

**Source:** `src/nativespeaker/api/auth/devicecheck.py:164-171` and the call site at
`services/auth.py:165-171`.
**Apply to:** the new-grant arm only (D-02: conversion makes no Apple call).

```python
async def read_bits_with_retry(adapter, device_token: str) -> BitState:
    """Call the adapter's query up to `DEVICECHECK_ATTEMPTS` times; return the state or raise."""
    return await _retrying(_read_exhausted)(adapter.read_bits, device_token)


async def write_bits_with_retry(adapter, device_token: str, *, bit0: bool, bit1: bool) -> None:
    """Call the adapter's update up to `DEVICECHECK_ATTEMPTS` times; return on confirmation or raise."""
    await _retrying(_write_exhausted)(adapter.write_bits, device_token, bit0=bit0, bit1=bit1)
```

`_retrying` (`:154-161`) retries only `RetryableDeviceCheckError` and converts exhaustion to
`Unavailable`. Do not add a loop.

### Refusal vocabulary — status and code declared once, at the base

**Source:** `src/nativespeaker/api/errors.py:436-442`.
**Apply to:** the new leaf. Leaves carry a docstring and nothing else, so the refusal cannot become
an account-state oracle. The class name is the structured-log event name.

### Docstring bar — three lines, everywhere

**Source:** `tests/unit/test_docstring_bar.py:42-62`, an equality check at zero overflow across
`src`, `tests`, `tests/e2e`, `tests/schema`, `tests/unit`.
**Apply to:** every new function, class and test class, and to the two module docstrings this phase
must rewrite (`routers/auth.py:1-3`, `crud/grants.py:1-2`).

### Comment style — one line, explaining the lines below it

**Source:** every excerpt above. Observed convention: a comment states *why the next line is written
that way*, never what it does and never the design. Examples worth copying literally in spirit:
`# No `.limit(...)`: the caller must see a second effective grant and fail closed on it.`
(`crud/grants.py:33`), `# A plain re-read, never `lock_identity_and_user`: ...` (`:96`).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| The conversion branch of the new `crud/grants.py` writer | crud | CRUD (update-then-insert in one transaction) | No existing writer expires a grant row. `activate_anonymous_device_grant` only inserts. The ordering constraint (expiry UPDATE flushed before the INSERT, forced by the non-deferrable `ix_access_grants_one_active_per_user`) has no precedent in this codebase — see RESEARCH.md Pitfall 1 and Assumption A1, which asks for an empirical proof of the emitted order against real PostgreSQL. |
| `migrations/20260818_01_initial-release.sql` deletion | migration | — | There is one migration and it has never been edited. RESEARCH.md "Pattern 5" carries the exact line ranges; no precedent edit exists to copy. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/{routers,services,crud,schemas,tables,auth,app}`,
`tests/{unit,schema,e2e}`, `migrations/`.
**Files scanned:** 19 read this session, all git-tracked.
**Pattern extraction date:** 2026-09-03
