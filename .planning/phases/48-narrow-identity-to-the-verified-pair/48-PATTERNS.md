# Phase 48: Narrow Identity to the verified pair - Pattern Map

**Mapped:** 2026-09-16
**Files analyzed:** 14 in `src/`, 24 in `tests/`
**Analogs found:** 14 / 14 for `src/`; the test sites copy four harness patterns

The phase creates no file. Every target exists. For each target the map gives two things: the
current shape at that site, and the one place in the tree that already does what the site must
become. All paths below are git-tracked.

## File Classification

| Modified file | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `src/nativespeaker/api/schemas/auth.py` | model | transform | `auth/jwt_verifier.py:58-62` (`VerifiedClaims`) | exact |
| `src/nativespeaker/api/app/dependencies.py` | middleware | request-response | itself, `dependencies.py:58-85` | exact |
| `src/nativespeaker/api/crud/identities.py` | crud | CRUD | `crud/identities.py:56-61` (`resolve_existing`, returns `\| None`) | exact |
| `src/nativespeaker/api/crud/challenges.py` | crud | CRUD | `crud/challenges.py:42-61` and `:90-104` | exact |
| `src/nativespeaker/api/services/auth.py` | service | request-response | `services/auth.py:114-163` (`_complete`) | exact |
| `src/nativespeaker/api/services/restore.py` | service | request-response | `services/restore.py:54-59` | exact |
| `src/nativespeaker/api/routers/auth.py` | route | request-response | `routers/auth.py:49-54` (the one route that already declares `get_db`) | exact |
| `src/nativespeaker/api/routers/users.py` | route | request-response | `routers/users.py:10, 19` | exact |
| `src/nativespeaker/api/routers/chats.py` | route | request-response | `routers/users.py:10, 19` | exact |
| `src/nativespeaker/api/routers/root.py` | route | request-response | `routers/users.py:10` | exact |
| `src/nativespeaker/api/routers/examples.py` | route | request-response | `routers/users.py:10` | exact |
| `tests/unit/conftest.py` | test | fixture | `tests/unit/conftest.py:115-126` | exact |
| `tests/unit/test_identity_accessors.py` | test | request-response | `tests/unit/test_jwt_security.py:205-228` | exact |
| `tests/unit/test_challenge_endpoint.py` | test | request-response | `tests/unit/test_identities_crud.py:24-45` (`_StubSession(row)`) | exact |
| the 3 precedence suites | test | request-response | `tests/unit/test_app_wiring.py:238-241` | exact |
| `tests/schema/test_restore_race.py` | test | CRUD | `tests/unit/conftest.py:115-126` | exact |

## Pattern Assignments

### `schemas/auth.py` (model)

**Analog:** `src/nativespeaker/api/auth/jwt_verifier.py:58-62`. It is the frozen slotted
dataclass with two required fields and a one-line docstring:

```python
@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str
```

**Current shape** (`schemas/auth.py:94-108`): `AuthIdentity` with four fields, two of them
defaulted to `None`, and `LinkedIdentity(AuthIdentity)` re-declaring the two rows. Both go. The
new `LinkedIdentity` copies the shape above with `user: User` and `identity: ExternalIdentity`.
The imports at `schemas/auth.py:8-10` already supply both row types.

### `app/dependencies.py` (middleware)

**Analog for `get_claims`:** `dependencies.py:58-72`, the credential check and the threadpool
verify, cut before the session:

```python
async def get_identity(request: Request,
                       credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
                       ) -> AuthIdentity:
    if credential is None:
        if request.headers.get("authorization") is None:
            raise InvalidExternalJwt(bounded_reason=BoundedReason.missing_token)
        else:
            raise InvalidExternalJwt(bounded_reason=BoundedReason.malformed)

    # `verify` can block on a JWKS fetch
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify,
                                             credential.credentials)
    if claims is None:
        raise InvalidExternalJwt(bounded_reason=reason or BoundedReason.bad_signature)
```

`verify` already returns a `VerifiedClaims`, so `get_claims` returns `claims` unchanged.

**Analog for the new `get_identity`:** `dependencies.py:74-76`, the same short session, plus the
`Depends` chain of `get_linked_identity` at `:80-85`:

```python
    async with request.app.state.session_factory() as session:
        return await IdentitiesDB(session).resolve(issuer=claims.issuer,
                                                   subject=claims.subject, allow_preauth=True)
```

```python
# Declared, never called directly: FastAPI's cache only sees solver-resolved deps, so a direct call re-verifies.
async def get_linked_identity(identity: AuthIdentity = Depends(get_identity)) -> LinkedIdentity:
    if identity.user is None or identity.identity is None:
        raise PreAuthIdentityNotAllowed
```

The new `get_identity` takes `request` and `claims: VerifiedClaims = Depends(get_claims)`,
because it reads `request.app.state.session_factory`. The comment at `:79` stays.

### `crud/identities.py` (crud)

**Analog for the new return type:** `crud/identities.py:56-61`, the sibling method that already
answers `None` for no row:

```python
    async def resolve_existing(self, *, issuer: str, subject: str) -> ExternalIdentity | None:
        """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
```

**Current shape** (`:30-54`): the outer join, then the `allow_preauth` branch at `:39-43`, then
the three rejections at `:45-53`. The branch becomes `return None`. The rejections are copied
without a character changed. The return at `:54` becomes `LinkedIdentity(user=user,
identity=identity)`.

**Analog for `insert_account`:** the method reads `identity.issuer` and `identity.subject` at
`:105-106` only. Copy the read pattern from `services/auth.py:337-338`, which reads the same two
values off the same value and passes them as keywords.

### `crud/challenges.py` (crud)

**Analog:** the two methods themselves, `:44-61` and `:90-104`. The branch keeps its shape; only
the source of each value changes:

```python
        if identity.identity is not None:
            bound_identity_id = identity.identity.id
        else:
            preauth_issuer = identity.issuer
            preauth_subject = identity.subject
```

becomes `if linked is not None: bound_identity_id = linked.identity.id` and
`claims.issuer` / `claims.subject`. The same substitution runs over `verify_binding` at `:93-103`.
This file is the one place that declares `LinkedIdentity | None`.

### `services/auth.py` and `services/restore.py` (service)

**Analog:** `services/restore.py:54-59`, the smallest method that takes a `LinkedIdentity` and
reads one row off it:

```python
    async def restore(self, identity: LinkedIdentity, provider: PurchaseProvider,
                      restore_proof: str) -> None:
        """Verify the store proof and attach the entitlement the subscription it names carries."""
        instant = datetime.now(UTC)
        proof = await self._verify(provider, restore_proof)
        destination = identity.user.id
```

Rename the parameter to `linked` and the read to `linked.user.id`. `services/auth.py` runs the
same two substitutions over its own reads: `identity.user.` becomes `linked.user.`,
`identity.identity.` becomes `linked.identity.`, and `identity.issuer` / `identity.subject`
become `claims.issuer` / `claims.subject`.

**Analog for the `_complete` signature:** `services/auth.py:114-118` today:

```python
    async def _complete[I: AuthIdentity, T](self, *,
                                            identity: I,
                                            challenge_id: str,
                                            operation: AuthOperation,
                                            post_claim: PostClaim[I, T]) -> T:
```

The type variable `I` exists only to carry `AuthIdentity` or `LinkedIdentity` to `post_claim`.
With two parameters it has no work. `post_claim(identity)` at `:147` and
`verify_binding(located, identity)` at `:128` both take the two values.

### `routers/auth.py` (route)

**Analog for the challenge route:** the route already declares `get_db` beside the identity
(`routers/auth.py:49-54`), so D-06 adds a call, not a declaration:

```python
async def issue_challenge(body: ChallengeRequest,
                          response: Response,
                          identity: AuthIdentity = Depends(get_identity),
                          session: AsyncSession = Depends(get_db),
                          challenge_store: ChallengesDB = Depends(get_challenge_store)
                          ) -> PrepareResponse:
```

`IdentitiesDB` is imported by `app/dependencies.py:21`; `routers/auth.py` imports `ChallengesDB`
the same way at `:20`. Place `IdentitiesDB(session).resolve(...)` between the vocabulary check at
`:56-59` and the row check at `:62`, because `tests/unit/test_challenge_endpoint.py:204` asserts
`session.statements == []` on every body refusal.

**Analog for a route that declares two dependencies:** `tests/unit/test_app_wiring.py:238-241`
already builds one and counts one verify and one query:

```python
        @router.get("/chats/{chat_id}")
        async def _handler(chat_id: str,
                           who: LinkedIdentity = Depends(get_linked_identity),
                           admitted: AuthIdentity = Depends(get_identity)):
```

`upgrade_anonymous`, the two grant claims and `sign_out_all` copy that shape as
`claims: VerifiedClaims = Depends(get_claims)` and `linked: LinkedIdentity = Depends(get_identity)`.

### `routers/users.py`, `routers/chats.py`, `routers/root.py`, `routers/examples.py` (route)

**Analog:** `routers/users.py:10` and `:19`, the router-level declaration with its comment and the
route-level one:

```python
# Router-level auth protects an endpoint added later whose own Depends is forgotten; the same callable runs once.
router = APIRouter(tags=["users"], dependencies=[Depends(get_linked_identity)])
...
async def me(response: Response,
             identity: LinkedIdentity = Depends(get_linked_identity),
             purchases: PurchasesDB = Depends(get_purchases_db)) -> MeResponse:
```

Both levels take the new `get_identity`. The handler parameter is renamed `linked`. `root.py:9`
and `examples.py:8` change the router-level name only; neither handler declares an identity.

### `tests/unit/conftest.py` (test)

**Analog:** the fixture itself, `tests/unit/conftest.py:115-126`. Every construction site in
`tests/` uses keywords, so the edit is deleting two lines:

```python
TEST_IDENTITY = LinkedIdentity(
    user=User(id=TEST_USER_ID, active=True),
    identity=ExternalIdentity(id=uuid7(), ...),
    issuer=TEST_ISSUER,      # deleted
    subject=TEST_SUBJECT,    # deleted
)
```

`tests/schema/test_restore_race.py:220-222` has no `ExternalIdentity` today. Copy the row from
the lines above.

### `tests/unit/test_identity_accessors.py` (test)

**Analog for the replacement field case:** `tests/unit/test_jwt_security.py:205-217`:

```python
    def test_carries_the_two_verified_claims_and_no_other_field(self):
        assert sorted(VerifiedClaims.__dataclass_fields__) == ["issuer", "subject"]

    def test_frozen(self):
        claims = VerifiedClaims(issuer=TEST_ISSUER, subject="abc123")
        with pytest.raises(AttributeError):
            claims.subject = "changed"  # type: ignore[invalid-assignment]
```

The new case reads `sorted(LinkedIdentity.__dataclass_fields__) == ["identity", "user"]`, that
the class is frozen and slotted, and that its base is `object` alone.

**Analog for the signature case:** `test_identity_accessors.py:276-280` keeps its shape; the two
expected lists become `["request", "credential"]` for `get_claims` and `["request", "claims"]`
for `get_identity`. The probe route at `:106-107` returns `{"linked": identity.user is not None}`;
a `VerifiedClaims` has no `user`, so the `get_claims` probe returns `claims.subject` instead.

### `tests/unit/test_challenge_endpoint.py` (test)

**Analog:** `tests/unit/test_identities_crud.py:24-45`, the stub session that returns a row:

```python
class _StubSession:
    def __init__(self, row=None):
        self._row = row
        self.statements = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._row)
```

`_RecordingSession` (`test_challenge_endpoint.py:50-64`) returns `_EmptyResult` always. Give it a
row, as above, so `linked_client` reads as linked after D-06. `tests/unit/test_identities_crud.py:47-55`
supplies the `(identity, user)` builder to copy.

### The three precedence suites (test)

**Analog:** `tests/unit/test_app_wiring.py:238-241` again: after the rename a suite that needs a
`LinkedIdentity` must override both names, because `get_identity` no longer derives from
`get_linked_identity`:

```python
    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_identity] = lambda: linked
```

The override style is `tests/unit/conftest.py:186-188`.

## Shared Patterns

### The rejection is an exception class raised from `crud/`
**Source:** `crud/identities.py:45-53`
**Apply to:** `crud/identities.py`, `app/dependencies.py`, `routers/auth.py`
```python
        if identity.identity_state != IdentityState.active:
            raise HistoricalIdentity
        if user.active is not True:
            raise BlockedUser
```
`PreAuthIdentityNotAllowed` is raised the same way from the new `get_identity` and from
`issue_challenge`.

### The dependency opens its own short session
**Source:** `app/dependencies.py:74-76`; the same reason is written at `:92`
**Apply to:** the new `get_identity`
```python
    async with request.app.state.session_factory() as session:
```
`get_db` is the request session and never fits here: it stays open for the handler.

### Keyword construction only
**Source:** `tests/unit/conftest.py:115-126`
**Apply to:** all 20 `LinkedIdentity(` and `AuthIdentity(` sites
The field order changes, so a positional call would bind the wrong values. Every site passes
keywords today. Keep it.

### Comments
**Source:** `AGENTS.md` § Comments and docstrings; `app/dependencies.py:79`
**Apply to:** every file this phase touches
One line, only where a later edit would go wrong without it. Delete each comment whose subject is
`allow_preauth`, the `None` row fields, or the old return value: `crud/identities.py:40`,
`crud/identities.py:41` and the docstrings at `schemas/auth.py:96` and `:105`.

## No Analog Found

None. Every target has an analog in the tree.

## Metadata

**Analog search scope:** `src/nativespeaker/api/{app,auth,crud,routers,schemas,services}`,
`tests/unit`, `tests/schema`, `tests/e2e`
**Files read this session:** 14
**Pattern extraction date:** 2026-09-16
