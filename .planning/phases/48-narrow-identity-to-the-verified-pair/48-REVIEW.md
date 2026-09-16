---
phase: 48-narrow-identity-to-the-verified-pair
reviewed: 2026-09-16T16:25:00Z
depth: standard
files_reviewed: 34
files_reviewed_list:
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/crud/challenges.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/restore.py
  - tests/e2e/test_challenge_store.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_restore_race.py
  - tests/unit/conftest.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
findings:
  critical: 0
  warning: 4
  info: 0
  total: 4
status: issues_found
---

# Phase 48: Code Review Report

**Reviewed:** 2026-09-16T16:25:00Z
**Depth:** standard
**Files Reviewed:** 34
**Status:** issues_found

## Summary

The type split itself is correct. I traced every site that read `AuthIdentity.issuer` or
`AuthIdentity.subject` and every site that read the two rows, and the substitution holds: no code
in `src/` reads `linked.identity.issuer` or `linked.identity.subject` where D-08 requires `claims`
(`grep` over both patterns returns test code only), `verify_binding`'s two arms are logically
identical to the old ones, `resolve`'s three rejections are unchanged, and `get_identity` closes
its session before it raises. `ruff check src tests` passes, `ty check src` passes, and
`pytest tests/unit` answers 1915 passed.

The defects are one verified wire-behavior change that the phase records claim does not exist, and
three places where the test substrate that used to pin the admission matrix no longer does.

No BLOCKER-class defect found: I could not construct a case where a caller reaches an account it
does not own, where a challenge binds to the wrong presenter, or where a rejection is lost.

## Warnings

### WR-01: Body and vocabulary refusals now outrank the account-state rejections on `/auth/challenge` and `/auth/create-user`

**File:** `src/nativespeaker/api/routers/auth.py:57-66`, `src/nativespeaker/api/services/auth.py:81`

**Issue:** Before this phase both routes sat behind the router-level `Depends(get_identity)`, which
resolved the caller during dependency solving — that is, before the handler body and before FastAPI
validated the request body. A historical row, a blocked user or a broken link therefore answered
`403 account_unavailable` on every request to these routes, whatever the body said. After the phase
the router declares `get_claims` (no database read), and the resolution moved to
`routers/auth.py:63` (after the `AuthOperation` vocabulary check) and to `services/auth.py:81`
(after body validation). The account state is now consulted last.

Verified by driving the real `auth_router` with a stubbed session returning an active identity row
whose user is `active=False`:

```
{'operation': 'nope'}        -> 400 {'code': 'invalid_request'}    | identity statements: 0
{'operation': 'sync'}        -> 400 {'code': 'invalid_request'}    | identity statements: 0
{}                           -> 422 {'code': 'validation_error'}   | identity statements: 0
{'operation': 'create_user'} -> 403 {'code': 'account_unavailable'}| identity statements: 1
```

And the old shape, confirmed separately — a router-level dependency raising `BlockedUser` in front
of a route whose body model requires a field answers `403 account_unavailable`, never `422`.

So a blocked user who posts `{}` to `/auth/create-user`, or `{"operation": "nope"}` to
`/auth/challenge`, gets a different status and a different code than it did before the phase. This
contradicts `48-CONTEXT.md` ("The admission matrix is unchanged, except for the one ordering change
recorded in D-07") and `.planning/WINDOWS.md` entry 33 ("Accepted under option B ... because every
wire outcome is preserved"). It is not the D-07 ordering change, which concerns a spent challenge on
create-user and does not ship at all.

The disclosure is small — both answers are refusals — but the record is wrong, and the next phase
that reasons from "the admission matrix is unchanged" will reason from a false premise.

**Fix:** Either restore the ordering by resolving before the vocabulary check, or amend the record.
To restore it in `routers/auth.py::issue_challenge`, move the read above the check:

```python
async def issue_challenge(body: ChallengeRequest, ...):
    # The row rejections outrank the body, as the router-level declaration made them.
    linked = await IdentitiesDB(session).resolve(issuer=claims.issuer, subject=claims.subject)
    if body.operation not in AuthOperation:
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest
    if body.operation != AuthOperation.create_user and linked is None:
        raise PreAuthIdentityNotAllowed
```

Note this costs one statement on a refused body, which is what
`tests/unit/test_challenge_endpoint.py::TestEveryRefusalLeavesNothingBehind` currently asserts
against (`session.statements == []`); that assertion would have to move with the decision.
`/auth/create-user`'s 422 arm cannot be restored without a route-level declaration, so if the
ordering is not restored, amend WINDOWS entry 33 and `48-CONTEXT.md` to name this change.

### WR-02: Nothing tests the three row rejections on the two routes that lost the router-level declaration

**File:** `src/nativespeaker/api/routers/auth.py:63`, `src/nativespeaker/api/services/auth.py:81`

**Issue:** `IdentityUnresolvable`, `HistoricalIdentity` and `BlockedUser` used to reach
`/auth/challenge` and `/auth/create-user` through the shared barrier, which
`tests/e2e/test_admission.py` pins (`test_a_historical_identity_is_refused`,
`test_a_blocked_user_is_refused`) — but only over `/`, `/examples?lang=en` and `/chats`
(`test_admission.py:83`). After this phase those two routes depend on two hand-written call sites
instead, and no test drives either route with a historical row or a blocked user:
`grep -rn "account_unavailable" tests/` returns `test_admission.py` and the error-vocabulary
modules, never `test_challenge_endpoint.py`, `test_create_user_precedence.py` or
`tests/e2e/test_create_user.py`.

Concrete consequence: delete the `resolve` call at `services/auth.py:81` and pass `linked=None`, and
a blocked user's create-user answers `409 challenge_required` instead of `403 account_unavailable`.
The only case that fails is `tests/e2e/test_create_user.py::test_an_active_linked_identity_is_
rejected_at_completion`, which covers the *active* row. The blocked and historical arms fail silently
into a wrong status.

**Fix:** Add two cases per route. In `tests/unit/test_challenge_endpoint.py` a session fixture
seeded with a non-active user and with `identity_state=IdentityState.historical` is enough:

```python
@pytest.fixture
def blocked_session() -> _RecordingSession:
    user = User(id=TEST_USER_ID, active=False)
    return _RecordingSession(row=(TEST_IDENTITY.identity, user))

def test_a_blocked_user_is_refused_before_a_handle_is_issued(self, blocked_session, store, ...):
    response = ... .post("/auth/challenge", json={"operation": "create_user"})
    assert response.json() == {"code": "account_unavailable"}
    assert store.issued == []
```

and the mirror case in `tests/unit/test_create_user_precedence.py`, whose `_StubSession` already
returns a row from `exec`.

### WR-03: The cache-contract test's `same` assertion can no longer fail

**File:** `tests/unit/test_app_wiring.py:243-245, 258`

**Issue:** The predecessor asserted `who.user is admitted.user and who.identity is admitted.identity`
— object identity, which proved the two declarations shared one resolution. The replacement compares
string fields:

```python
same = (linked.identity.issuer == admitted.issuer
        and linked.identity.subject == admitted.subject)
```

`_Result.first()` at line 212 returns the closure's fixed `identity, user` for every statement, and
that `identity` is built with `issuer=TEST_ISSUER, subject=subject` — the same values the token is
minted with at line 253. `same` is therefore `True` by construction, and `assert response.json()
["same"] is True` at line 258 can never fail. Change `get_identity` to resolve a hardcoded subject
rather than `claims.subject` and this test still passes: `counts["query"]` is still 1, and `same` is
still `True`.

Note also that the comparison reads the stored row's `issuer`/`subject`, which D-08 explicitly keeps
out of `src/` — the test now models the thing the decision forbids.

**Fix:** Keep the identity comparison the old test made, by handing the two declarations distinct
row objects is not possible under one cached resolution — so assert the resolution's own output
instead:

```python
@router.get("/chats/{chat_id}")
async def _handler(chat_id: str,
                   linked: LinkedIdentity = Depends(get_identity),
                   admitted: VerifiedClaims = Depends(get_claims)):
    return {"resolved_user": str(linked.user.id), "subject": admitted.subject}
...
assert response.json() == {"resolved_user": str(user.id), "subject": subject}
```

which fails if either declaration resolves something other than the token's subject.

### WR-04: The schema harness dereferences `resolve`'s `None` arm

**File:** `tests/schema/test_claim_race.py:247-262`

**Issue:** `resolve_identity` used to call `resolve(..., allow_preauth=False)`, which raised
`PreAuthIdentityNotAllowed` when the harness had not seeded the identity row. It now calls
`resolve(issuer=..., subject=...)`, which returns `None`, and `run_attempt` dereferences it two
lines later:

```python
linked = await resolve_identity(harness, attempt.subject)
attempt.caller_rows_detached = all(
    object_session(row) is None for row in (linked.user, linked.identity))
```

A seeding failure or a subject typo in this module now surfaces as
`AttributeError: 'NoneType' object has no attribute 'user'` inside a race harness, rather than the
named rejection that says what actually went wrong.

**Fix:**

```python
linked = await resolve_identity(harness, attempt.subject)
assert linked is not None, f"the harness seeded no identity row for {attempt.subject}"
```

---

_Reviewed: 2026-09-16T16:25:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
