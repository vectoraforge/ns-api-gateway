# Phase 40: POST /auth/upgrade-anonymous - Pattern Map

**Mapped:** 2026-09-02
**Files analyzed:** 19 (7 source, 3 new tests, 7 modified tests, 2 planning docs)
**Analogs found:** 17 / 19 (2 doc files need no code analog)

Every file this phase touches has an in-repo analog. This phase writes **no new module and no new
pattern** — the closest analog for most files is the create-user path in the same file.

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/routers/auth.py` | mod | route handler | request-response | `routers/auth.py::create_user` :62-73 + `::sync` :76-86 | exact (same file) |
| `src/nativespeaker/api/services/auth.py` | mod | service | request-response orchestration | `services/auth.py::AuthService.complete` :42-93 | exact (same method, shared) |
| `src/nativespeaker/api/crud/identities.py` | mod | crud | CRUD write + locked read | `crud/identities.py::insert_account` :63-98 + `crud/grants.py::lock_effective_grants` :37-42 | exact + role-match |
| `src/nativespeaker/api/errors.py` | mod | error tree | n/a (declaration) | `errors.py::AccountUnavailable` :317-330 (shared-base + two leaves) | exact |
| `src/nativespeaker/api/schemas/auth.py` | mod | schema | n/a | `schemas/auth.py::CreateUserRequest` :24-28 (the model being renamed) | exact |
| `src/nativespeaker/api/tables/auth.py` | mod | table/enum mirror | n/a | `tables/auth.py::AuthOperation` :11-19 (the enum being shrunk) | exact |
| `migrations/20260818_01_initial-release.sql` | mod | migration | n/a | its own `CREATE TYPE core.auth_operation` :17-24 + `auth_challenges` CHECK :392-399 | exact |
| `tests/e2e/test_upgrade_anonymous.py` | **new** | test | e2e request-response | `tests/e2e/test_create_user.py` (whole file) | exact |
| `tests/unit/test_upgrade_precedence.py` | **new** | test | unit, in-process app | `tests/unit/test_create_user_precedence.py` (whole file) | exact |
| `tests/schema/test_registration_pairing.py` | **new** | test | schema, asyncpg | `tests/schema/test_constraints.py::TestExternalIdentityConstraints` :184-246 | exact |
| `tests/e2e/test_flows.py` | mod | test | e2e multi-route flow | its own `TestChatLifecycle` :7-45 | exact (same file) |
| `tests/unit/test_challenge_endpoint.py` | mod | test | unit | its own `_NOT_ISSUABLE` :122-133 | exact (same file) |
| `tests/unit/test_app_wiring.py` | mod | test | unit, introspection | its own `:40-51` parametrizations | exact (same file) |
| `tests/unit/test_rejection_vocabulary.py` | mod | test | unit | its own `EVENT_NAMES` :35-84 + `CONSTRUCTOR_ARGUMENTS` :106-121 | exact (same file) |
| `tests/schema/test_inventory.py` | mod | test | schema | its own `EXPECTED_ENUM_LABELS["auth_operation"]` :71-74 | exact (same file) |
| `tests/schema/test_constraints.py` | mod | test | schema | its own `TestAuthChallengeConstraints` :563-582 | exact (same file) |
| `tests/unit/test_conflict_classification.py` | mod | test | unit, source scan | its own `TestTheModuleUsesNoSecondRaceArbiter` :271-280 | exact (same file) |
| `.env.example` | mod | config | n/a | its own `FIREBASE_TEST_EMAIL`/`FIREBASE_TEST_PASSWORD` :15-16 | exact |
| `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` | mod | planning doc | n/a | prior dated amendment entries in the same files | n/a |

---

## Pattern Assignments

### `src/nativespeaker/api/routers/auth.py` (route handler, request-response)

**Analog:** the two handlers already in the file.

**Completion-route shape** — copy `create_user` (:62-73) verbatim, changing only the path, the
summary/description and the service method:

```python
@router.post("/auth/create-user",
             response_model=CompletionResponse,
             summary="Create the account for a verified but unlinked identity",
             description="Spends a single-use challenge obtained from `POST /auth/challenge`, "
                         "supplied as `challenge_id` in the body, and creates the account.")
async def create_user(body: CreateUserRequest,
                      identity: Identity = Depends(get_identity),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
    # Forwarded untouched and never logged: the handle is a secret.
    provider = await service.complete(identity=identity, challenge_id=body.challenge_id)
    return CompletionResponse(identity_provider=provider)
```

**Route-level narrowing** — copy the comment + dependency from `sync` (:76-83). The new route needs
`get_linked_identity`, not `get_identity`, because the router-level dependency (:33-34) is
deliberately unnarrowed:

```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/sync",
             response_model=SyncResponse, ...)
async def sync(identity: Identity = Depends(get_linked_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
```

**Issuance handler edit (D-10 + D-11)** — the block to replace is :44-55:

```python
    # One instant for this request, so `created_at` and `expires_at` cannot straddle a boundary.
    evaluated_at = datetime.now(UTC)

    if body.operation != AuthOperation.create_user.value:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=identity,
                                                           now=evaluated_at)
```

The membership test becomes `body.operation not in AuthOperation`; the `operation=` argument becomes
`AuthOperation(body.operation)`; D-10's condition sits between the two using the already-existing
`PreAuthIdentityNotAllowed` (`errors.py:304-307`). Keep the two comments and the `no-store` response
block (:56-59) unchanged.

**`Depends()`-only rule:** the handler takes no `Request`. Accessors live in `app/dependencies.py`;
`get_auth_service` (:102-109) already builds `AuthService` with `evaluated_at=datetime.now(UTC)` and
needs no change.

---

### `src/nativespeaker/api/services/auth.py` (service, request-response orchestration)

**Analog:** `AuthService.complete` (:42-93) — the sequence to *share*, not copy (D-16).

**The sequence, with the two seams marked** (:42-93):

```python
    async def complete(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        """Create the account and return the provider the read reported.
        The order of the rejections below is the precedence, and none of them carries a field."""
        # No rejection before the claim consumes anything, so a wrong presenter cannot burn a live challenge.
        located = await self.challenge_store.locate(self.session, challenge_id)
        if located is None:
            raise ChallengeNotFound()

        # Every line below reads `challenge`, which only the binding check produces: deleting it is a NameError.
        challenge = self.challenge_store.verify_binding(located, identity)
        if challenge.operation is not AuthOperation.create_user:   # <-- SEAM 1: the operation
            raise ChallengeOperationMismatch()

        if not await self.challenge_store.claim(self.session,
                                                challenge_id=challenge_id,
                                                now=self.evaluated_at):
            # `claimed_at` distinguishes the two losses; the claim's WHERE is the only expiry evaluation anywhere.
            await self.session.refresh(challenge)
            if challenge.claimed_at is None:
                raise ChallengeExpired()
            else:
                raise ChallengeConsumed()

        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()

        # Read off a just-committed instance, which the lifespan's `expire_on_commit=False` keeps loaded.
        challenge_row_id = str(challenge.id)

        try:
            facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
            await self.create_user(identity=identity,                # <-- SEAM 2: the write
                                   provider=facts.provider,
                                   provider_uid=facts.provider_uid,
                                   # The copy rule was evaluated once, inside the read; nothing re-derives it.
                                   email=facts.email)
        except AppError:
            # A conflicting insert leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
            try:
                await self._consume_and_commit(challenge_id=challenge_id,
                                               challenge_row_id=challenge_row_id)
            except Exception as failure:
                # The handle stays claimed and so stays unusable; the client keeps the status it earned.
                logger.error("challenge_consume_failed", challenge_row_id=challenge_row_id,
                             failure=type(failure).__name__)
            raise

        await self._consume_and_commit(challenge_id=challenge_id,
                                       challenge_row_id=challenge_row_id)
        return facts.provider
```

**Three things the planner must decide against this body:**

1. Only lines 53 and 74-78 differ between the two endpoints. Parameterise those two, leave the rest
   untouched.
2. The nested `try` at :82-88 violates D-17 for the *new* path once shared. The discharge D-17 itself
   prescribes: extract the swallow into a small named function whose whole job is not raising —
   `_consume_and_commit` (:124-135) is the existing example of a named boundary function in this file.
3. `return facts.provider` (:93) must become the value the transaction settled on for the upgrade
   path (the stored provider on an idempotent repeat).

**The `evaluated_at` convention** (:39-40) — one captured instant per request, nothing downstream
reads the clock again:

```python
        # One instant for this request; nothing below it reads the clock again.
        self.evaluated_at = evaluated_at
```

**The `NoReturn` rejection-only helper** (:114-122) is the shape for any "raise what this state
earned" branch of the case matrix:

```python
    async def _reject_existing_identity(self, existing: ExternalIdentity) -> NoReturn:
        """Raise what an already-present identity row earned. No mutation, and every test fails closed."""
        if existing.identity_state != IdentityState.active:
            raise HistoricalIdentity
        ...
```

---

### `src/nativespeaker/api/crud/identities.py` (crud, CRUD write + locked read)

**Analog A — the write and its `IntegrityError` arm:** `insert_account` (:63-98).

```python
    async def insert_account(self, *, evaluated_at, identity, provider, provider_uid, email) -> UUID:
        """Insert the user, its identity row and its purchase tokens, and return the new user's id."""
        try:
            user = User(email=email,
                        registered_at=None if provider is IdentityProvider.anonymous else evaluated_at,
                        created_at=evaluated_at,
                        updated_at=evaluated_at)
            self.session.add(user)
            await self.session.flush()
            ...
            await self.session.flush()
            return user.id
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict
```

Copy exactly: no constraint name, no message parse, no savepoint, no `commit()` (transaction
boundaries live in `services/`). **The one adaptation D-17 forces:** the flip's `try` wraps only the
`flush()`; the ORM attribute assignments sit outside it, because an assignment sends nothing to the
database.

**Analog B — the lock:** `crud/grants.py::lock_effective_grants` :37-42 and `lock_usage` :50-53.

```python
    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
        # No eager-loading option here: Postgres rejects FOR UPDATE combined with the join those emit.
        statement = _effective_grants_statement(user_id, evaluated_at).with_for_update()
        return list((await self.session.exec(statement)).all())
```

`.with_for_update()`, never raw SQL text. This is both the repo convention and the only form that
survives the forbidden-literal scan (RESEARCH Pitfall 1). Note the module docstring's lock-order
declaration at `crud/grants.py:1` — the new lock method should state its own ordering the same way.

**Analog C — the in-transaction re-resolution:** `resolve_existing` (:53-57), and the shape **not**
to reuse for the lock — `resolve` (:29-34) uses `isouter=True`, which PostgreSQL refuses to lock
(RESEARCH Pitfall 2):

```python
    async def resolve_existing(self, *, issuer: str, subject: str) -> ExternalIdentity | None:
        """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
        statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                                   col(ExternalIdentity.subject) == subject)
        return (await self.session.exec(statement)).first()
```

```python
        # Outer join: an identity row whose user_id resolves to nothing must stay distinct from no row.
        statement = (select(ExternalIdentity, User)
                     .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                     ...)
```

The new lock method is a **new** method with an **inner** join. Every `where` clause in this module
uses `col(...)`, never a bare attribute.

**Column set the flip writes** (from `tables/identities.py` and `tables/users.py`): `identity.provider`,
`identity.provider_uid`, `identity.updated_at`, `user.registered_at`, `user.updated_at`, and
`user.email` only when still `None`. Never `display_name`, `identity_state`, `historical_at`,
`free_grant_consumed_at`.

---

### `src/nativespeaker/api/errors.py` (error tree)

**Analog:** `AccountUnavailable` and its two leaves (:317-330) — a base declaring the pair once, two
leaves declaring nothing. This is the exact shape D-05's two classes need (both answer 403
`operation_not_allowed`), and it is what `test_rejection_vocabulary.py` asserts for the existing
groups:

```python
class AccountUnavailable(AppError):
    """A historical identity row, or an active row whose user is not active."""

    # Declared once here: making one leaf answer differently takes an override a reviewer sees.
    status = 403
    code = "account_unavailable"


class HistoricalIdentity(AccountUnavailable):
    """The identity row's state is anything other than active."""


class BlockedUser(AccountUnavailable):
    """The identity row is active, but the user it resolves to is not."""
```

The same shape at :386-391 for `ChallengeRejected` (409 declared once, five silent leaves).

**`log_fields()` with constructor-carried scalars:** `ProviderLookupError` (:345-358) — the shape for
D-06's stored/live provider names, including the "absent key rather than `None`" rule:

```python
class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")

    def log_fields(self) -> dict[str, str | None]:
        fields: dict[str, str | None] = {"stage": self.stage}
        if self.cause is not None:
            fields["cause"] = self.cause
        return fields
```

**Stringifying a non-str value into a log field:** `InvalidExternalJwt.log_fields` (:299-301) — D-06's
identity row id (a `UUID`) and the two `IdentityProvider` members go through this:

```python
    def log_fields(self) -> dict[str, str | None]:
        # A `StrEnum` member, stringified so the field's type in the log pipeline stays a plain str.
        return {"bounded_reason": None if self.bounded_reason is None else str(self.bounded_reason)}
```

**Do not touch** `ErrorCode` (:13-28) or `ErrorResponse` (:31-33) — no new client-visible code, and
`operation_not_allowed` already exists. `AppError`'s 500 default (:39-41) is the tripwire a class that
declares nothing falls into.

---

### `src/nativespeaker/api/schemas/auth.py` (schema, rename)

**Analog:** the model being renamed, `CreateUserRequest` (:24-28) — rename only, comments carried:

```python
class CreateUserRequest(BaseModel):
    """The completion body: the handle obtained from `/auth/challenge`, and nothing else."""
    # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.
    # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.
    challenge_id: str = Field(..., min_length=1)
```

`CompletionResponse` (:31-33) is reused unchanged. Import sites to update: `routers/auth.py:23` and
`tests/unit/test_create_user_body.py`.

---

### `src/nativespeaker/api/tables/auth.py` + `migrations/20260818_01_initial-release.sql` (enum shrink)

**Analog:** the enum's own three copies. The Python mirror (`tables/auth.py:11-19`):

```python
class AuthOperation(StrEnum):
    """Mirrors `core.auth_operation` -- the canonical state-changing auth operations."""
    create_user = "create_user"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    restore_subscription = "restore_subscription"   # dropped
    sign_out_all = "sign_out_all"                   # dropped
    sync = "sync"                                   # dropped
```

The migration's type (`:17-24`) and the CHECK that becomes redundant (`:392-399`, verbatim):

```sql
    -- Exactly the four challenge-bearing operations; restore, sign-out-all and sync have no challenge row.
    CHECK (
        operation IN (
            'create_user',
            'upgrade_anonymous_to_registered',
            'claim_anonymous_grant',
            'claim_registered_grant'
        )
    ),
```

Edit the single file in place and drop/re-apply the dev and test databases. There is no
`ALTER TYPE … DROP VALUE` in PostgreSQL and `tests/schema/test_apply_rollback.py::test_exactly_one_sql_file`
forbids a second migration.

---

### `tests/unit/test_upgrade_precedence.py` (NEW — unit test, in-process app)

**Analog:** `tests/unit/test_create_user_precedence.py` — copy its whole scaffolding.

**The four fakes** (:41-131): `_FakeChallengeStore` (an in-memory row whose `claim`/`consume` mirror
the real conditional updates clause for clause), `_RejectionLog`, `_StubSession`, `_RecordingCreator`.

```python
class _StubSession:
    """Records transaction boundaries and refuses queries: a statement here would mean the router resolves identity."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[object] = []

    async def commit(self) -> None:
        self.commits += 1
    ...
    async def exec(self, statement):
        raise AssertionError("the completion path issued a query of its own: "
                             f"{statement!r}")
```

**The rejection spy** (:139-146) — three loggers into one list, so a rejection logged at the wrong
site is still seen. `results` is the snake-cased class name, i.e. D-05's internal result:

```python
@pytest.fixture
def rejections(monkeypatch) -> _RejectionLog:
    """Spy on both loggers a rejection can come from, so one logged at the wrong site is still seen."""
    log = _RejectionLog()
    monkeypatch.setattr("nativespeaker.api.routers.auth.logger.warning", log.record)
    monkeypatch.setattr("nativespeaker.api.services.auth.logger.warning", log.record)
    monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.warning", log.record)
    return log
```

**The client fixture** (:166-188) — the real router with four dependency overrides, including the
async-generator `get_db` that mirrors `app/dependencies.py::get_db`:

```python
@pytest.fixture
def client(store, session, identity, creator, fake_firebase_adapter):
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_identity] = lambda: identity
    # An async generator, not a plain callable: `get_db` releases the read transaction itself, and a
    # callable has no `try`/`except` to do it with. Mirrors `app/dependencies.py::get_db` exactly.
    async def _db():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
```

**The row builder + the equality assertion** (:191-224) — the identical-body assertion is by
`==`, so a more helpful field fails the test:

```python
def _assert_challenge_required(response) -> None:
    """Byte-identical across all five rejections, asserted by equality so a more helpful field fails here."""
    assert response.status_code == 409
    assert response.json() == {"code": "challenge_required"}
```

**The case shape** (:229-273) — one internal result asserted, plus the disposition of the row and the
adapter's call list. This is exactly how D-14's "consumes at or after the Firebase call" and D-22's
"exactly one `getUser`" are asserted:

```python
    def test_a_challenge_for_another_operation_is_an_operation_mismatch(
            self, client, store, rejections, fake_firebase_adapter):
        """A challenge issued for another operation is still rejected, and still before the claim."""
        store.row = _issued_row(operation=AuthOperation.claim_anonymous_grant)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_operation_mismatch"]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []
```

Note: the upgrade route needs a **linked** identity, so `app.dependency_overrides[get_identity]` must
supply an `Identity` carrying `user` and `identity` rows (the precedence file's `identity` fixture at
:161-163 is pre-auth), and `_issued_row` must bind by `bound_external_identity_id` rather than the
preauth pair.

---

### `tests/e2e/test_upgrade_anonymous.py` (NEW — e2e test)

**Analog:** `tests/e2e/test_create_user.py`.

**Module head** (:1-20) — the marker, the stub-verifier client fixture, the `_auth` helper:

```python
pytestmark = pytest.mark.e2e

@pytest_asyncio.fixture(loop_scope="module")
async def create_user_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}
```

**The scripted-fake case shape** (:61-110) — script the seam's answer, drive both routes, then read
rows through `_db_transaction`:

```python
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None))
        ...
        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth())

        assert completion.status_code == 200
        assert completion.json() == {"identity_provider": "anonymous"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]
        ...
        async with _db_transaction() as session:
            user = (await session.exec(
                select(User).where(col(User.id) == identity.user_id))).one()
            assert user.display_name is None
            # NULL for anonymous, non-NULL for google/apple -- no third state.
            assert user.registered_at is None
```

**The real-path case shape** (:553-560) — `assert isinstance(adapter, FirebaseAdminLookup)` makes
"this test really did hit Firebase" an assertion rather than an absence:

```python
@pytest.mark.asyncio(loop_scope="module")
class TestTheRealAnonymousCompletion:
    """Nothing substituted, end to end against the live project; skips without an Admin credential."""

    async def test_a_genuinely_anonymous_user_completes_through_the_real_admin_sdk(
            self, anonymous_client, _db_transaction, _app_lifespan, _app_config,
            anonymous_firebase_credential):
        _, local_id = anonymous_firebase_credential
        adapter = _app_lifespan.state.firebase_adapter
        # scripted_firebase_adapter is deliberately not requested, and this is what makes that visible.
        assert isinstance(adapter, FirebaseAdminLookup)
```

**Fixtures from `tests/e2e/conftest.py` to reuse, not rebuild:**

| Fixture / helper | Lines | Use here |
|---|---|---|
| `scripted_firebase_adapter` | :153-162 | D-19's four fake cases; swaps `app.state.firebase_adapter` and restores it |
| `anonymous_firebase_credential` | :76-90 | D-18's skip-when-unconfigured pattern to copy for the Google-linked account |
| `_admin_credential_configured` + `_NO_ADMIN_CREDENTIAL` | :64-72 | the skip guard and its message |
| `stub_verifier` | :142-150 | ephemeral-RSA verifier over the real started app |
| `_db_transaction` | :116-139 | per-test rollback; the app's session factory is swapped so its writes join it |
| `seed_identity(..., provider=IdentityProvider.anonymous)` | :173-194 | the pre-upgrade row, and the second seeded identity for the already-taken case |

```python
async def seed_identity(factory, *, issuer, subject,
                        identity_state=IdentityState.active, user_active=True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a core.users row and its matching core.external_identities row; return both."""
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider is IdentityProvider.anonymous else f"{provider}-uid-{subject}"
```

**The fake's contract** (`tests/unit/conftest.py::FakeFirebaseAdapter` :192-210): `script()` takes a
raise-or-return value; `calls` is the list D-22's one-lookup-per-completion assertion reads.

---

### `tests/schema/test_registration_pairing.py` (NEW — schema test, asyncpg)

**Analog:** `tests/schema/test_constraints.py`.

**Module head** (:1-11) and the fixtures it relies on from `tests/schema/conftest.py` — `conn`
(:105-118) is a connection to a freshly migrated scratch database inside a transaction that always
rolls back, entirely separate from the e2e rollback fixture:

```python
"""The schema's rejection cases, exercised with real rows against a real PostgreSQL."""
import asyncpg
import pytest

from schema.helpers import insert_grant, insert_usage, insert_user

pytestmark = pytest.mark.schema
```

**The literal-statement + helper pattern** (:31-41, :82-115) — parameterised SQL literals at module
level, one helper per table that generates colliding-free values:

```python
_INSERT_IDENTITY = (
    "INSERT INTO core.external_identities "
    "(id, user_id, issuer, subject, provider, provider_uid, identity_state, historical_at, "
    "created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)

async def _insert_identity(conn, *, user_id, issuer=ISSUER, subject=None,
                           provider="google", provider_uid=None, identity_state=None) -> uuid.UUID:
    """Insert one core.external_identities row; provider_uid is generated so it never collides by accident."""
    identity_id = uuid.uuid4()
    if provider != "anonymous" and provider_uid is None:
        provider_uid = f"uid_{uuid.uuid4().hex[:16]}"
```

**The rejection context manager** (:72-79) — savepoint-wrapped so a follow-up query stays possible:

```python
@contextlib.asynccontextmanager
async def _rejects(conn: asyncpg.Connection, exc_type: type[Exception]):
    """A rejected statement aborts the whole transaction, so the savepoint is what keeps a follow-up query possible."""
    # Not usable for the COMMIT-time cases: a deferred failure leaves no savepoint to return to.
    await conn.execute("SAVEPOINT rejected_statement")
    with pytest.raises(exc_type) as exc_info:
        yield exc_info
    await conn.execute("ROLLBACK TO SAVEPOINT rejected_statement")
```

**The class D-12 mirrors** (:184-227) — `TestExternalIdentityConstraints`, which covers the
provider/provider_uid CHECK from both sides and asserts the row count after a rejection:

```python
class TestExternalIdentityConstraints:
    """The (issuer, subject) reservation, the provider/provider_uid agreement, and the identity FK."""

    async def test_identity_anonymous_with_provider_uid_rejected(self, conn):
        """An anonymous identity carrying a provider_uid violates the provider agreement CHECK."""
        user_id = await insert_user(conn)
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_identity(conn, user_id=user_id, provider="anonymous", provider_uid="uid_not_allowed")
```

D-12's test is a **scan**, not a rejection case, so the shape is a `conn.fetchval` counting rows in
the third state — see the count assertions at :571 and :580-582 for the idiom.

---

### `tests/e2e/test_flows.py` (modified — the D-20 criteria-3-and-4 case)

**Analog:** its own `TestChatLifecycle` (:1-45) — one class per multi-route flow, the module docstring
naming what the flow is for, and every step's status asserted:

```python
"""The only case that drives all five chat routes in sequence against one chat, over the real app."""
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestChatLifecycle:
    async def test_full_chat_lifecycle(self, async_client, linked_firebase_identity, quota_grant):
        """Full lifecycle: create -> followup -> read messages -> list chats -> delete."""
```

For the purchase-token half of D-20, `tests/e2e/conftest.py::seed_purchase_tokens` (:254-269) is the
seeding helper, and `test_create_user.py:111-116` is the read-and-compare idiom:

```python
        async with _db_transaction() as session:
            tokens = (await session.exec(
                select(StorePurchaseToken)
                .where(col(StorePurchaseToken.user_id) == identity.user_id))).all()
        assert {token.provider for token in tokens} == set(PurchaseProvider)
```

**Naming hazard:** `IdentityProvider.apple` and `PurchaseProvider.apple` are different things and this
one test reads both. Never derive one from the other.

---

### Existing test files to edit (each is its own analog)

| File | Edit | Excerpt to change |
|---|---|---|
| `tests/unit/test_rejection_vocabulary.py` | add two snake-cased names to `EVENT_NAMES` (:35-84) and, if the classes take `__init__` arguments, two rows to `CONSTRUCTOR_ARGUMENTS` (:106-121) | `errors_module.NotLinked: ((), {"stage": "provider_classification", "cause": "invalid-shape"}),` |
| " | the scalars-only gate (:141-144) is why D-06's UUID must be stringified | `assert isinstance(value, str \| None), f"{cls.__name__}.{key} is not a scalar"` |
| " | if the two classes sit under a shared base, copy `TestTheTwoAccountArmsDeclareNothingEither` (:203-215) as their group test | `assert set(_family(errors_module.AccountUnavailable)) == {...}` |
| `tests/unit/test_app_wiring.py` | add `"/auth/upgrade-anonymous"` to both parametrizations at :40 and :47; add it to **neither** `PUBLIC_PATHS` nor `PREAUTH_CALLABLE_PATHS` (:12-13) | `@pytest.mark.parametrize("path", ("/auth/sync", "/users/me"))` |
| `tests/unit/test_challenge_endpoint.py` | `_NOT_ISSUABLE` (:122-124) loses `claim_anonymous_grant` and its comment becomes false; `store.issued == ["create_user"]` (:113) needs widening; add a class for D-10's account-less refusal | `_NOT_ISSUABLE = ["sync", "sign_out_all", "restore_subscription", "claim_anonymous_grant", "nope", "", "create-user", "CREATE_USER"]` |
| `tests/schema/test_inventory.py` | `EXPECTED_ENUM_LABELS["auth_operation"]` (:71-74) drops three labels; order is asserted (`test_labels_match_in_declared_order` :188-195) so it must match the migration's declared order | `"auth_operation": ["create_user", "upgrade_anonymous_to_registered", "claim_anonymous_grant", "claim_registered_grant", "restore_subscription", "sign_out_all", "sync"],` |
| `tests/schema/test_constraints.py` | `test_challenge_for_a_challenge_free_operation_rejected` (:566-571) breaks: the three strings stop being enum labels, so the insert raises invalid-enum-input rather than `CheckViolationError`. The sibling at :573-582 becomes the sole partition proof | `@pytest.mark.parametrize("operation", ["restore_subscription", "sign_out_all", "sync"])` |
| `tests/unit/test_conflict_classification.py` | the forbidden-literal scan over `services/auth.py` + `crud/identities.py` (:271-280) passes with `.with_for_update()`; add one line recording that the upgrade path's lock is revalidation, not arbitration | `@pytest.mark.parametrize("forbidden", ["serializable", "advisory_lock", "pg_advisory", "isolation_level", "for update", "select_for_update"])` |
| `.env.example` | add the D-18 account UID variable next to the existing test credentials, with the by-hand creation note | `FIREBASE_TEST_EMAIL=...` / `FIREBASE_TEST_PASSWORD=...` (:15-16) |

---

## Shared Patterns

### Route wiring — `Depends()` only, accessors in one file
**Source:** `src/nativespeaker/api/app/dependencies.py:90-109`
**Apply to:** the new route in `routers/auth.py`

```python
# These two accessors exist so a challenge-bearing route can stay Depends()-only and never take Request itself.
def get_challenge_store(request: Request) -> ChallengesDB:
    """The one `ChallengesDB` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_auth_service(db: AsyncSession = Depends(get_db),
                     challenge_store: ChallengesDB = Depends(get_challenge_store),
                     adapter=Depends(get_firebase_adapter)) -> AuthService:
    return AuthService(db=db,
                       challenge_store=challenge_store,
                       adapter=adapter,
                       # One instant for this request; nothing downstream reads the clock again.
                       evaluated_at=datetime.now(UTC))
```

`get_auth_service` already supplies everything the second completion needs. No new accessor.

### The admission barrier — already complete, build nothing
**Source:** `src/nativespeaker/api/app/dependencies.py:58-62`
**Apply to:** the new route

```python
# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    if identity.user is None:
        raise PreAuthIdentityNotAllowed
    return identity
```

`IdentitiesDB.resolve` (`crud/identities.py:27-51`) already raises `PreAuthIdentityNotAllowed`,
`IdentityUnresolvable`, `HistoricalIdentity` and `BlockedUser` behind it. No admission error path
needs building, and the route re-verifies nothing.

### The provider read — reused unchanged
**Source:** `src/nativespeaker/api/auth/firebase.py:139-147`, `:110-122`, `:125-131`
**Apply to:** `services/auth.py`'s shared sequence

```python
async def lookup_with_retry(adapter, issuer: str, subject: str) -> VerifiedProviderIdentity:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times; return the identity or raise."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # Only the internal marker retries, so `UserNotFound` and `NotLinked` propagate after one attempt.
        retry=retry_if_exception_type(RetryableLookupError),
        retry_error_callback=_exhausted,
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
```

`_resolve_provider` returns `(anonymous, None)` for an empty `providerData` and raises
`NotLinked(cause="invalid-shape")` for anything outside the accept set; `_verified_email` returns the
address only when non-empty and verified. The flip adds one guard (stored email is still `None`) and
derives nothing else.

### Layering and transaction boundaries
**Source:** `ns-api-gateway/AGENTS.md` § Package layout (:29-36, :57-60)
**Apply to:** all three source files

Handler in `routers/`, orchestration and `commit()`/`rollback()` in `services/`, queries in `crud/`,
bodies in `schemas/`, tables in `tables/`, external-SDK seams in `auth/`. A fail-closed read may raise
its own rejection, so D-08's `IntegrityError` catch belongs in `crud/identities.py`, not the service.
The flip method must not commit.

### Comment and docstring bar
**Source:** `tests/unit/test_docstring_bar.py:40-46` (baseline 0 on every root)
**Apply to:** every file this phase writes, tests included

```python
BASELINE: dict[str, int] = {
    "src": 0, "tests": 0, "tests/e2e": 0, "tests/schema": 0, "tests/unit": 0,
}
```

Three lines maximum per docstring; comments one line each, only where they resolve a real ambiguity.
The prevailing house style is visible in every excerpt above: a comment states *why the alternative
was rejected*, not what the line does.

### Structured logging — the class name is the event
**Source:** `src/nativespeaker/api/app/error_handlers.py::app_error_handler` (writes
`camel_to_snake(type(exc).__name__)`), `errors.py::AppError.log_level = logging.WARNING` (:42)
**Apply to:** D-05's two new classes

No `logger.warning` call is written for a refusal — raising the class produces the line. D-07's
"all three at WARNING" is satisfied by the `AppError` default; nothing is overridden.

---

## No Analog Found

None. Every file has a close in-repo match.

Two items have an analog but a **verified-broken precondition** the planner must resolve rather than
copy blindly:

| File | Issue |
|---|---|
| `tests/e2e/test_upgrade_anonymous.py` (D-18 real case) | The analog `anonymous_firebase_credential` mints its user through the REST `signUp` endpoint, which needs no signer. D-18 needs `create_custom_token`, which **fails today** on this machine's ADC (RESEARCH § P-01). Three routes are costed there; the choice changes what the fixture looks like. |
| `crud/identities.py` lock method | The obvious analog `IdentitiesDB.resolve` (:29-34) uses `isouter=True`, and PostgreSQL rejects `FOR UPDATE` on the nullable side of an outer join. Copy `crud/grants.py`'s `.with_for_update()` over an **inner** join instead. |

## Metadata

**Analog search scope:** `src/nativespeaker/api/{routers,services,crud,auth,app,schemas,tables}`,
`tests/{unit,e2e,schema}`, `migrations/`, `.env.example`
**Files read this session:** 20
**Pattern extraction date:** 2026-09-02
