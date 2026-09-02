---
phase: 39-get-users-me
reviewed: 2026-09-02T03:57:30Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - AGENTS.md
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/schemas/auth.py
  - tests/e2e/conftest.py
  - tests/e2e/test_users_me.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_users_me.py
findings:
  critical: 0
  warning: 7
  info: 6
  total: 13
status: issues_found
---

# Phase 39: Code Review Report

**Reviewed:** 2026-09-02T03:57:30Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

`GET /users/me` was reviewed adversarially against the live code, the migration DDL,
the import graph, the type checker and the executed test suite. The endpoint's
*runtime* behaviour is correct — I traced and cleared the leak paths the brief called
out, and found no Critical defect. What I did find is a cluster of type-safety
regressions, one missing regression guard on the single most security-relevant
property of the route, a new layering edge into `errors.py` that the repo's own
`AGENTS.md` warns against, a response field that can never be populated in
production, and a body of comments that violates the comment rules this same phase
edited.

**Verified clean (traced, not assumed):**

- **No cross-tenant read.** `PurchasesDB.read_tokens` filters on
  `col(StorePurchaseToken.user_id) == user_id`, parameterised, and `me()` passes
  `identity.user.id` from the barrier — never a client-supplied value.
- **No unreachable `None` deref.** `IdentitiesDB.resolve` (`crud/identities.py:36-51`)
  returns `identity` non-`None` whenever `user` is non-`None`, and
  `get_linked_identity` rejects `user is None`. `identity.identity.provider` cannot
  raise at runtime. (It still fails the type checker — see WR-01.)
- **No token in an error body or header.** `MissingPurchaseTokenError.__init__`
  (`errors.py:252-256`) formats only the user id and store names; the token column
  never reaches the message. `app_error_handler` builds the body from `code` alone.
- **No token in a log line.** `log_level = logging.ERROR` makes
  `app_error_handler` pass `exc_info=True`, but `structlog.dev.plain_traceback`
  renders no frame locals, and `log_fields()` is empty. The user id does reach the
  server log via the exception message — consistent with `MissingUsageRowError`
  and `UnknownTierError`, and acceptable for a server-side log.
- **No silently-collapsed duplicate rows.** `migrations/20260818_01_initial-release.sql:168`
  declares `UNIQUE (user_id, provider)`, so the dict comprehension at
  `crud/purchases.py:20` cannot drop a row.
- **No unreachable fail-closed 500 in practice.** `insert_account`
  (`crud/identities.py:89-93`) is the only user-creation path in `src/`, and it mints
  one token per `PurchaseProvider` in the same flush, so a complete set is a real
  invariant rather than an aspiration.
- **`Cache-Control: no-store` is actually emitted** (proven by the passing unit test,
  which exercises the real router through `TestClient`).
- 134 unit tests pass; `ruff check` is clean.

## Narrative Findings (AI reviewer)

### Critical Issues

None. I am reporting zero Critical findings on evidence, not on charity — the clearances
above are each traced to a specific line. The Warnings below are all real defects; none
of them causes incorrect behaviour on the current code paths.

### Warnings

#### WR-01: `/users/me` dereferences two `Optional` attributes with no narrowing — 4 new unsuppressed `ty` errors in `src/`

**File:** `src/nativespeaker/api/routers/users.py:22,25,26,27`

**Issue:** `identity.user` is `User | None` and `identity.identity` is
`ExternalIdentity | None` (`schemas/auth.py:85-86`). The handler dereferences both
without a narrowing check:

```python
purchase_tokens = await purchases.read_tokens(identity.user.id)      # :22
... Profile(email=identity.user.email,                                # :25
            display_name=identity.user.display_name),                 # :26
    identity_provider=identity.identity.provider,                     # :27
```

`uv run ty check src/nativespeaker/api/routers/users.py` reports four
`unresolved-attribute` errors. `ty` is a pinned **runtime** dependency
(`pyproject.toml:20`) and the codebase already suppresses a known false positive
explicitly (`app/main.py:52`), so unsuppressed errors in `src/` are a regression in
a gate the project actually uses. This phase moved `src/` from 2 such errors
(`routers/auth.py:85-86`) to 6.

The invariant that makes this safe lives in a different module
(`crud/identities.py:39` vs `:51`) and is enforced by a different function
(`get_linked_identity`). Nothing in the type system, and no test, prevents a future
change to `resolve()` from returning `user` set and `identity` unset — which would
turn line 27 into an `AttributeError` and a 500 on the happy path.

**Fix:** make the linked case a distinct type rather than re-asserting the invariant
at each call site. Minimum viable version:

```python
# schemas/auth.py
@dataclass(frozen=True, slots=True)
class LinkedIdentity:
    issuer: str
    subject: str
    user: User
    identity: ExternalIdentity

# app/dependencies.py
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> LinkedIdentity:
    if identity.user is None or identity.identity is None:
        raise PreAuthIdentityNotAllowed
    return LinkedIdentity(issuer=identity.issuer, subject=identity.subject,
                          user=identity.user, identity=identity.identity)
```

`routers/users.py` and `routers/auth.py:85-86` then type-check with no change and no
suppression. If that is too large for this phase, the fallback is an explicit
`assert identity.user is not None and identity.identity is not None` in
`get_linked_identity` plus a narrowing return — a bare `# ty: ignore` here would
suppress the one signal that the invariant is unmodelled.

#### WR-02: `PurchasesDB.read_tokens` does not type-check against its own return annotation

**File:** `src/nativespeaker/api/crud/purchases.py:20,26`

**Issue:** `ty` reports
`expected dict[PurchaseProvider, str], found dict[Unknown | Sequence[Unknown], Unknown | str]`.
The multi-column `select(...)` at line 18 produces a statement whose row type the
checker cannot resolve through `AsyncSession.exec`, so the comprehension at line 20
is inferred as untyped. The declared return type is therefore unverified: if the
select's column order were swapped to
`select(StorePurchaseToken.identity_value, StorePurchaseToken.provider)`, the
resulting `dict[str, PurchaseProvider]` would be a *token-keyed* map, the
completeness check at line 22 would report both stores missing, and every caller
would get a permanent 500. The type checker cannot catch that today.

**Fix:** unpack explicitly and re-assert the element types, so the annotation is
carried by the code rather than by inference:

```python
rows = (await self.session.exec(statement)).all()
tokens: dict[PurchaseProvider, str] = {PurchaseProvider(provider): str(value)
                                       for provider, value in rows}
```

#### WR-03: Nothing tests that the token read is scoped to the caller — cross-tenant token disclosure has no regression guard

**File:** `tests/unit/test_purchases_crud.py:44-46`, `tests/unit/test_users_me.py:54-56`

**Issue:** Both fakes return the seeded token map regardless of what statement they
were handed:

```python
async def exec(self, statement):
    self.statements.append(statement)
    return _StubResult(self._tokens.items())   # `statement` is never consulted
```

The only assertions made against the compiled statement are that it names
`core.store_purchase_tokens`, does not name `core.users`, and carries no
`FOR UPDATE` (`test_purchases_crud.py:123-137`). **No test in the repository asserts
that the statement filters on `user_id` at all** — `grep -n user_id` over both new
test files returns only fixture-construction lines.

Consequence: deleting `.where(col(StorePurchaseToken.user_id) == user_id)` from
`crud/purchases.py:19` leaves all 134 unit tests green. That single deletion turns
`/users/me` into an endpoint that hands every authenticated caller an arbitrary
other user's purchase-attribution tokens. The e2e suite would not catch it either —
no e2e test seeds a second user with its own tokens, and the whole e2e suite is
deselected by default (`pyproject.toml` `addopts = "-m 'not e2e and not schema'"`).

This is the single most security-relevant property of a route whose entire payload
is described in-code as secret, and it is the one property with no guard.

**Fix:** two additions.

```python
# tests/unit/test_purchases_crud.py — the predicate is in the statement
async def test_the_statement_filters_on_the_requested_user(self):
    _, session = await _read(SEEDED)
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    assert "user_id = " in str(compiled)
    assert USER_ID in compiled.params.values()

# tests/unit/test_purchases_crud.py — a session that honours the predicate
class _FilteringSession(_StubSession):
    """Returns rows only for the user the statement actually binds."""
    async def exec(self, statement):
        self.statements.append(statement)
        bound = set(statement.compile(dialect=postgresql.dialect()).params.values())
        return _StubResult(self._tokens.items() if USER_ID in bound else [])
```

and one e2e case that seeds a *second* user holding two different tokens and asserts
neither value appears in the first caller's body.

#### WR-04: `errors.py` now imports the whole `tables` package, creating the cycle hazard `AGENTS.md` documents

**File:** `src/nativespeaker/api/errors.py:10`

**Issue:** `from nativespeaker.api.tables.purchases import PurchaseProvider` executes
`tables/__init__.py`, which imports every SQLModel table plus `schemas.api` and
`schemas.llm`. Measured before/after:

```
$ uv run python -c "import nativespeaker.api.errors, sys; \
    print(len([m for m in sys.modules if m.startswith('nativespeaker')]))"
15   # was 3 before this phase: nativespeaker, .api, .api.auth(.jwt_verifier), .api.errors
```

`errors.py` is the lowest layer in this codebase — it is imported by `crud/`,
`services/`, `routers/`, `auth/firebase.py` and `resilience.py`. `AGENTS.md`
exception 2 exists specifically because of this: *"`BoundedReason` stays in
`auth/jwt_verifier.py`. Moving it to `schemas/` creates an import cycle, because
`errors.py` imports it."* This phase adds a second such edge with no corresponding
exception and no note. The moment any module under `tables/` needs an error class —
a validator, a `sa_type` coercion, a check-constraint helper — the cycle is real and
the fix is a refactor of `errors.py`.

The import is also only needed for an annotation and a `.value` access
(`errors.py:252`, `:256`), both of which work on any `StrEnum`.

**Fix:** keep the edge type-only.

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nativespeaker.api.tables.purchases import PurchaseProvider

class MissingPurchaseTokenError(InternalError):
    def __init__(self, user_id: UUID, missing: "Sequence[PurchaseProvider]"):
```

Python 3.14's deferred annotation evaluation (`requires-python >= 3.14`) means no
`from __future__` import is needed and no runtime behaviour changes. If a runtime
value is genuinely wanted, `', '.join(str(store) for store in missing)` on a
`Sequence[str]` removes the dependency entirely.

#### WR-05: `profile.display_name` can never be non-null in production, and both tests for it are tautologies

**File:** `src/nativespeaker/api/routers/users.py:26`, `src/nativespeaker/api/schemas/auth.py:70`

**Issue:** `core.users.display_name` exists in the DDL and on the model
(`tables/users.py:18`), but **no code path in `src/` ever writes it**. The sole
user-creation path, `IdentitiesDB.insert_account` (`crud/identities.py:71-74`), sets
`email`, `registered_at`, `created_at` and `updated_at` — never `display_name`. No
update path exists. So `/users/me` returns `"display_name": null` for every account
this service can create, forever.

The tests are constructed so this is invisible:

- e2e `test_a_linked_caller_reads_its_profile_and_both_store_tokens`
  (`tests/e2e/test_users_me.py:65-68`) asserts
  `body["profile"]["display_name"] == user.display_name` where `seed_identity`
  builds `User(active=user_active)` — so the assertion is `None == None`.
- unit `_linked_identity` (`tests/unit/test_users_me.py:74`) constructs the `User`
  object in memory with `display_name=DISPLAY_NAME`, bypassing every write path.

Neither proves the field is reachable. `TestANullContactFieldIsNotAMissingToken`
tests the null case, which is the *only* case.

**Fix:** decide and record which. Either (a) drop `display_name` from `Profile` until
a write path exists, or (b) populate it in `insert_account` from the provider record
(the Firebase adapter already returns `displayName` in `providerData`) and add an
e2e assertion against a non-null seeded value. Shipping a permanently-null field in a
closed response body that the tests claim to cover is the worst of the three options.

#### WR-06: The new code violates the § "Comments and docstrings" rules that this same phase edited

**File:** `AGENTS.md:5-23` (the rules), violated at `src/nativespeaker/api/crud/purchases.py:1,17,24`, `src/nativespeaker/api/routers/users.py:9,23`, `src/nativespeaker/api/app/dependencies.py:118`, `src/nativespeaker/api/errors.py:249`, `src/nativespeaker/api/schemas/auth.py:68,74`

**Issue:** `AGENTS.md` states: *"Do not describe what lives somewhere else, what the
entity is not, or how the application works in general"* and *"A comment ... never
explains the design, the request lifecycle, a rule enforced in another module, or a
decision that was made elsewhere."* The phase amended this file and then wrote code
that breaks the rules in it:

| Location | Text | Rule broken |
|---|---|---|
| `crud/purchases.py:1` | "Takes no lock and mints nothing." | defines by what it is not |
| `crud/purchases.py:17` | "...taking no lock, or raise if..." | defines by what it is not |
| `crud/purchases.py:24` | "Completeness, never emptiness: one row present and one absent is the same broken invariant." | explains the design |
| `routers/users.py:9` | "Router-level auth protects an endpoint added later whose own Depends is forgotten; the same callable runs once." | explains a rule enforced in another module (FastAPI's dependency cache) |
| `routers/users.py:23` | "`no-store` rather than `no-cache`: the tokens are secrets, and a revalidatable copy is a copy." | explains a decision made elsewhere |
| `app/dependencies.py:118` | "This accessor exists so the profile route can stay `Depends()`-only and never construct a database class itself." | explains a rule enforced in `AGENTS.md` |
| `errors.py:249` | "Never minted here: that would turn a detectable broken invariant into a silently repaired one." | explains a decision made elsewhere |
| `schemas/auth.py:68,74` | "...both left NULL until a provider record fills them" / "...and nothing else." | how the app works / what it is not |

This is not a style preference: it is a written, checked-in project rule, and the
phase touched the file that carries it. Uncorrected, it re-establishes the exact
register D-16/Phase 37.1 was created to remove.

**Fix:** reduce each to the specific line it clarifies, or delete it. E.g.
`crud/purchases.py:1` → `"""Purchase-attribution reads over core.store_purchase_tokens."""`;
`crud/purchases.py:24` → delete (the `set(PurchaseProvider) - set(tokens)` on the line
above already says "completeness"); `app/dependencies.py:118` → delete (the function is
three tokens long and self-evident).

#### WR-07: A test named for a cache-header assertion makes none, and its token assertions are vacuous for a third of its cases

**File:** `tests/unit/test_users_me.py:206-214`

**Issue:**

```python
@pytest.mark.parametrize("seeded", _INCOMPLETE_ACCOUNTS)
def test_the_refusal_carries_no_cache_header_and_no_identifier(self, identity, seeded):
    """The 500 body is the whole disclosure: no user id, no provider name, no token value."""
    ...
    assert set(response.json()) == {"code"}
    assert APPLE_TOKEN not in response.text
    assert GOOGLE_TOKEN not in response.text
```

Three defects: (1) the name promises an assertion about the cache header and the body
contains none — a regression that added `Cache-Control` to the 500 path would pass;
(2) the docstring promises "no user id" and nothing asserts the caller's id is absent
— `set(response.json()) == {"code"}` is a shape check, and `identity.user.id` never
appears in `response.text` for a *different* reason (the handler never reaches the
serialiser); (3) for the `no-store-row` parametrisation neither token is seeded, so
both token assertions are vacuous.

**Fix:**

```python
assert "cache-control" not in response.headers
assert set(response.json()) == {"code"}
assert str(identity.user.id) not in response.text
for token in (APPLE_TOKEN, GOOGLE_TOKEN):
    assert token not in response.text
```

...and either rename to match, or split the cache-header case out.

### Info

#### IN-01: The app-level `responses` map omits 403 and 409, so `/users/me`'s documented error set is missing the rejection its own e2e test asserts

**File:** `src/nativespeaker/api/app/main.py:29-38`

**Issue:** The map declares 400, 401, 404, 405, 422, 429, 500, 503. `/users/me`
returns 403 `preauth_identity_not_allowed` — asserted at
`tests/e2e/test_users_me.py:193-194` — and `/auth/create-user` returns 409. Neither
status is in the map or declared per-route, so a generated client would not know the
403 exists. Low impact because `openapi_url=None`, but the schema is still
introspected by `tests/unit/test_error_contract.py:107-121`.

**Fix:** add `403: {"model": ErrorResponse, "description": "Forbidden"}` and
`409: {"model": ErrorResponse, "description": "Conflict"}` to the map.

#### IN-02: The code and the migration disagree on whether `identity_value` is a secret

**File:** `src/nativespeaker/api/routers/users.py:23` vs `migrations/20260818_01_initial-release.sql:162`

**Issue:** The migration comments the table as *"Deliberately PK-less: the two UNIQUE
constraints carry the rules, over an **opaque non-secret value**."* The new code
(`routers/users.py:23`) and three test docstrings call the same column a secret and
justify `no-store` on that basis. Both statements cannot govern. The distinction
decides whether the value may appear in a client-side crash report, an analytics
payload or a support ticket.

**Fix:** settle it in one place — either update the migration comment, or record the
reclassification as a decision — and make the other reference the same conclusion.

#### IN-03: e2e test imports a private helper from a sibling test module

**File:** `tests/e2e/test_users_me.py:12`

**Issue:** `from .test_sync import _stored_provider` couples this module to another
test module's private name. Renaming or deselecting `test_sync` breaks collection
here, not there.

**Fix:** move `_stored_provider` to `tests/e2e/conftest.py` next to `seed_identity`
and import it from there.

#### IN-04: `_TABLE_COUNTS` asserts whole-table counts against a shared e2e database

**File:** `tests/e2e/test_users_me.py:36-38,48`

**Issue:** `SELECT count(*) FROM core.users` (and the other two) is stable only
because `_db_transaction` isolates the test. Any concurrent writer — a parallel
`pytest -n`, a second developer against the same instance — makes
`test_a_successful_read_leaves_every_row_untouched` flaky in a way that reads as a
product failure.

**Fix:** scope the counts to the caller
(`SELECT count(*) FROM core.users WHERE id = :user_id`, etc.); the per-row `SELECT *`
snapshots already carry the "nothing changed" property for the account under test.

#### IN-05: `seed_purchase_tokens` has an untyped default that is a class, not a sequence

**File:** `tests/e2e/conftest.py:254-256`

**Issue:** `providers=PurchaseProvider` defaults to the enum *class*, which happens to
be iterable. Callers pass a `list` (`test_users_me.py:165`), so the parameter's real
type is "iterable of `PurchaseProvider`" and the signature says nothing.

**Fix:** `providers: Iterable[PurchaseProvider] = tuple(PurchaseProvider)`.

#### IN-06: The route's OpenAPI copy calls `identity_provider` the "registration state"

**File:** `src/nativespeaker/api/routers/users.py:15-17`, `src/nativespeaker/api/schemas/auth.py:74`

**Issue:** `summary` says *"profile, registration state and store tokens"* but the
field is `identity_provider: IdentityProvider` — the identity provider, not a
registration state. `tables/users.py:19` is explicit that
`external_identities.provider` is a classifier and `registered_at` is the
reporting-only registration field. The wording is copied from `SyncResponse`, so it
is consistent but consistently wrong.

**Fix:** say "identity provider" in both the `summary` and the `MeResponse`
docstring; fix `SyncResponse` at the same time or leave a note that it is knowingly
inherited.

---

_Reviewed: 2026-09-02T03:57:30Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
