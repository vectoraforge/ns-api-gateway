"""CREATE-01/02/03 end to end: an unlinked caller goes from no account to an account.

**This is the phase tracer's proof, and it is deliberately one case rather than a per-layer suite.**
What it exercises is every layer at once, unstubbed: the real barrier admitting a pre-auth identity
because the registry declares this route -- and only this route -- pre-auth callable; the real
`ChallengeStore` issuing, claiming and consuming; the real mode-signal partition dispatching; the
real consuming transaction against a real PostgreSQL; and the real audit writer. Two things are
substituted, each for a stated reason: the token verifier, so an unlinked subject is expressible
without minting a Firebase account per case, and the provider adapter, per D-09.

**Why the provider adapter has to be substituted here.** The package's real credential fixture signs
in with `accounts:signInWithPassword`, so its providerData is `[{providerId: "password"}]` -- a
single *unrecognized* entry, which §02 step 9's closed classifier rejects. The real credential can
therefore only ever drive a rejection, never this success. 37-10 adds the genuinely-anonymous
Firebase fixture that proves the SDK really returns the empty shape this case scripts.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome
from nativespeaker.api.auth.firebase import FirebaseAdminLookup
from nativespeaker.api.models.auth import AuthChallenge, AuthEvent, AuthEventResult, AuthOperation
from nativespeaker.api.models.grants import AccessGrant, UserMonthlyUsage
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.purchase_tokens import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.models.users import User

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-unlinked-subject"


@pytest_asyncio.fixture(loop_scope="module")
async def create_user_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


async def _count(factory, statement) -> int:
    async with factory() as session:
        return (await session.exec(statement)).one()


_CHALLENGES = select(func.count()).select_from(AuthChallenge)
_ALREADY_LINKED_EVENTS = (select(func.count()).select_from(AuthEvent)
                          .where(col(AuthEvent.result) == AuthEventResult.identity_already_linked))

_GRANTS = select(func.count()).select_from(AccessGrant)
_MONTHLY_USAGE = select(func.count()).select_from(UserMonthlyUsage)
_USERS_CARRYING_A_NAME = (select(func.count()).select_from(User)
                          .where(col(User.display_name).is_not(None)))


async def _assert_step_10s_global_invariants(factory) -> None:
    """The two §02 step 10 rules that hold after **every** completion in this file, on every branch.

    They are asserted globally rather than per-user on purpose. A per-user check answers "this
    account got no grant"; these answer "this *request* created no entitlement anywhere and named
    nobody", which is the invariant §02 states -- and it is the form that would still catch a write
    landing on the wrong row. The whole `core.*` set is visible here because each case runs inside
    the per-test transaction with a clean database beneath it.

    * **No entitlement whatsoever.** `POST /auth/create-user` mints no `core.access_grants` row and
      no `core.user_monthly_usage` row -- not for anonymous, not for google, not for apple. A new
      account correctly answers `quota_exceeded` on its first chat until Phase 41/42 ships.
    * **`display_name` is never populated**, on any branch (§02 DELETIONS). Not defaulted, not
      copied from the provider record, not derived from the address.
    """
    assert await _count(factory, _GRANTS) == 0
    assert await _count(factory, _MONTHLY_USAGE) == 0
    assert await _count(factory, _USERS_CARRYING_A_NAME) == 0


@pytest.mark.asyncio(loop_scope="module")
class TestTheAnonymousHappyPath:
    """One unlinked caller, one prepare, one completion, and the exact row set §02 step 10 names."""

    async def test_an_unlinked_caller_creates_an_anonymous_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        # The classifier answers `anonymous` to an EMPTY providerData and to nothing else, so an
        # `ok` with no entries is precisely the anonymous first-time account.
        scripted_firebase_adapter.script(entries=(), email=None, email_verified=False)

        users_before = await _count(_db_transaction, select(func.count()).select_from(User))

        # --- Prepare -------------------------------------------------------------------------
        prepare = await create_user_client.post("/auth/create-user?challenge=true",
                                                headers=_auth())

        assert prepare.status_code == 200
        # §6.1 / §02 prepare step 5: exactly two fields, and the key set is asserted rather than
        # the presence of two known keys -- a third field would pass the weaker check.
        assert set(prepare.json()) == {"challenge_id", "expires_at"}
        assert prepare.headers["cache-control"] == "no-store"
        handle = prepare.json()["challenge_id"]

        # Prepare mutates no business state.
        assert await _count(_db_transaction, select(func.count()).select_from(User)) == users_before
        # It has not called the provider either: §02 pins exactly one read, at completion.
        assert scripted_firebase_adapter.calls == []

        # --- Completion ----------------------------------------------------------------------
        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth())

        assert completion.status_code == 200
        # D-10 / §02 step 14: registration state only. No backend token, no session, no cookie, no
        # generation counter, and (D-11) no attribution token.
        assert completion.json() == {"identity_provider": "anonymous"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]

        # --- Exactly one account -------------------------------------------------------------
        assert await _count(_db_transaction,
                            select(func.count()).select_from(User)) == users_before + 1

        async with _db_transaction() as session:
            identities = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == SUBJECT))).all()
            assert len(identities) == 1
            identity = identities[0]
            assert identity.identity_state is IdentityState.active
            assert identity.provider is IdentityProvider.anonymous
            # NULL, not a sentinel: the row must fall outside the provider-account reservation.
            assert identity.provider_uid is None

            user = (await session.exec(
                select(User).where(col(User.id) == identity.user_id))).one()
            # Never populated, on any branch (§02 DELETIONS).
            assert user.display_name is None
            # NULL for anonymous, non-NULL for google/apple -- no third state.
            assert user.registered_at is None
            # The scripted result carried no address, so step 10's copy rule yields NULL.
            assert user.email is None

        # --- Both attribution tokens, minted eagerly, distinct --------------------------------
        async with _db_transaction() as session:
            tokens = (await session.exec(
                select(StorePurchaseToken)
                .where(col(StorePurchaseToken.user_id) == identity.user_id))).all()
        assert {token.provider for token in tokens} == set(PurchaseProvider)
        assert len({token.identity_value for token in tokens}) == 2

        # --- No entitlement whatsoever (§02 step 10) ------------------------------------------
        # A brand-new account correctly answers `quota_exceeded` on its first chat until Phase
        # 41/42 ships. That is the specified behaviour, not a regression.
        async with _db_transaction() as session:
            grants = (await session.exec(
                select(AccessGrant)
                .where(col(AccessGrant.user_id) == identity.user_id))).all()
            assert grants == []
            usage = (await session.exec(
                select(func.count()).select_from(UserMonthlyUsage)
                .where(col(UserMonthlyUsage.grant_id).in_(
                    select(col(AccessGrant.id))
                    .where(col(AccessGrant.user_id) == identity.user_id))))).one()
            assert usage == 0

        # --- The challenge is consumed and its binding cleared --------------------------------
        async with _db_transaction() as session:
            challenge = (await session.exec(
                select(AuthChallenge)
                .where(col(AuthChallenge.challenge_id) == handle))).one()
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject_hash is None

        # --- Exactly one audit row, and it carries no handle ----------------------------------
        # Correlated on the NON-SECRET row id. The public handle is a secret capability and never
        # reaches a row, a log, or error text.
        async with _db_transaction() as session:
            events = (await session.exec(
                select(AuthEvent)
                .where(col(AuthEvent.challenge_row_id) == challenge.id))).all()
        assert len(events) == 1
        assert events[0].operation is AuthOperation.create_user
        assert events[0].result is AuthEventResult.succeeded
        assert not _mentions(events[0].details, "challenge_id")
        assert handle not in repr(events[0].details)

        await _assert_step_10s_global_invariants(_db_transaction)


def _mentions(payload, needle: str) -> bool:
    """True if `needle` appears as a key at ANY nesting depth.

    A top-level-only check is the one that looks right in review and misses the leak, so this walks
    mappings and sequences the way the redactor itself does.
    """
    if isinstance(payload, dict):
        return any(needle in str(key) or _mentions(value, needle)
                   for key, value in payload.items())
    if isinstance(payload, list | tuple):
        return any(_mentions(item, needle) for item in payload)
    return False


@pytest.mark.asyncio(loop_scope="module")
class TestPrepareRejectsAnAlreadyLinkedCaller:
    """§02 prepare step 1's fail-fast.

    A caller who already has an account does not need one, and telling them so at prepare saves a
    challenge, a provider read and a transaction. It is **best-effort only** -- the resolution that
    decides is the one inside the consuming transaction -- but a cheap early no is still the right
    answer to give.

    Note what reaching this rejection requires: the barrier resolves an ACTIVE identity for such a
    caller and hands the handler a *linked* context, so the route cannot demand a pre-auth one. It
    is the only route in the system that admits both variants, and answering 409 rather than 401 to
    the linked one is the whole point of §02 step 1.
    """

    async def test_an_active_linked_identity_is_rejected(self, create_user_client, _db_transaction):
        subject = "already-linked-prepare"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)

        response = await create_user_client.post("/auth/create-user?challenge=true",
                                                 headers=_auth(subject))

        assert response.status_code == 409
        # The shared one-field body, and the key set asserted exactly: `ErrorResponse` carries
        # exactly one field and D-12 removed the one place §02 asked for a second.
        assert response.json() == {"code": "identity_already_linked"}

    async def test_the_rejection_issues_no_challenge(self, create_user_client, _db_transaction):
        subject = "already-linked-issues-nothing"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)
        before = await _count(_db_transaction, _CHALLENGES)

        await create_user_client.post("/auth/create-user?challenge=true", headers=_auth(subject))

        assert await _count(_db_transaction, _CHALLENGES) == before

    async def test_the_rejection_writes_exactly_one_audit_row(self, create_user_client,
                                                              _db_transaction):
        """Standalone-durable, because no consuming transaction exists at prepare time.

        The route carries a non-`None` `operation`, which is what puts it on the audited path, so
        this rejection owes exactly one row -- written before the response returns, not as a side
        effect of having sent it.
        """
        subject = "already-linked-audited"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)
        before = await _count(_db_transaction, _ALREADY_LINKED_EVENTS)

        await create_user_client.post("/auth/create-user?challenge=true", headers=_auth(subject))

        assert await _count(_db_transaction, _ALREADY_LINKED_EVENTS) == before + 1
        async with _db_transaction() as session:
            event = (await session.exec(
                select(AuthEvent)
                .where(col(AuthEvent.result) == AuthEventResult.identity_already_linked)
                .order_by(col(AuthEvent.created_at).desc()))).first()
        assert event is not None
        assert event.operation is AuthOperation.create_user
        # The actor is known -- the token was verified -- so the all-or-nothing CHECK requires
        # every actor field. The raw subject is never stored; only its keyed hash is.
        assert event.actor_issuer == TEST_ISSUER
        assert event.actor_subject_hash is not None
        assert event.actor_subject_hash_key_version is not None
        # No challenge existed to correlate on, and none was issued.
        assert event.challenge_row_id is None


@pytest.mark.asyncio(loop_scope="module")
class TestPrepareStillIssuesForAnUnlinkedCaller:
    """The fail-fast must not have narrowed the path it guards."""

    async def test_an_unlinked_caller_still_gets_the_two_field_body(self, create_user_client,
                                                                    _db_transaction):
        response = await create_user_client.post("/auth/create-user?challenge=true",
                                                 headers=_auth("still-unlinked"))

        assert response.status_code == 200
        assert set(response.json()) == {"challenge_id", "expires_at"}

    async def test_two_prepares_issue_two_distinct_challenges(self, create_user_client,
                                                              _db_transaction):
        """Prepare is not idempotent and never reuses a row.

        Each call mints fresh CSPRNG bytes and inserts its own challenge. A "reuse the outstanding
        one" optimisation would hand two concurrent client attempts the same single-use capability,
        so exactly one of them could ever complete.
        """
        headers = _auth("prepares-twice")

        first = await create_user_client.post("/auth/create-user?challenge=true", headers=headers)
        second = await create_user_client.post("/auth/create-user?challenge=true", headers=headers)

        assert first.status_code == second.status_code == 200
        assert first.json()["challenge_id"] != second.json()["challenge_id"]


# ---------------------------------------------------------------------------
# 37-08: the rejection arms, over real HTTP and a real database.
#
# `tests/unit/test_create_user_precedence.py` proves the full precedence against fakes, at unit
# speed. What only a real database can prove is the part the fakes stand in for: that a rejection
# really wrote its `audit.auth_events` row and really moved the challenge's lifecycle, rather than
# calling a recorder that agreed with the test.
# ---------------------------------------------------------------------------

_USERS = select(func.count()).select_from(User)


def _events_with(result: AuthEventResult):
    return select(func.count()).select_from(AuthEvent).where(col(AuthEvent.result) == result)


@pytest.mark.asyncio(loop_scope="module")
class TestCompletionRejectionsOnTheWire:
    """Two rejections from opposite sides of the consumption boundary, and the replay behind them.

    They are chosen deliberately: `challenge_not_found` is the earliest rejection there is and
    consumes nothing, while the `password`-entry classification rejection is the latest one before
    the consuming transaction and consumes everything. Proving both anchors the boundary from each
    side against real rows.
    """

    async def test_an_unknown_handle_is_challenge_required_and_audited(
            self, create_user_client, _db_transaction):
        users_before = await _count(_db_transaction, _USERS)
        events_before = await _count(_db_transaction,
                                     _events_with(AuthEventResult.challenge_not_found))

        response = await create_user_client.post("/auth/create-user",
                                                 json={"challenge_id": "no-such-handle"},
                                                 headers=_auth("e2e-unknown-handle"))

        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert await _count(_db_transaction,
                            _events_with(AuthEventResult.challenge_not_found)) == events_before + 1
        assert await _count(_db_transaction, _USERS) == users_before
        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_a_password_entry_is_operation_not_allowed_and_consumes_the_challenge(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """The shape the package's own email/password credential really produces (Pitfall 8).

        One *unrecognized* entry: the closed classifier rejects it, which is an unclassifiable
        account rather than a declaration mismatch (D-12), so it is terminal `operation_not_allowed`
        and it persists nothing.
        """
        subject = "e2e-password-shape"
        scripted_firebase_adapter.script(
            entries=(ProviderDataEntry("password", "someone@example.test"),))
        users_before = await _count(_db_transaction, _USERS)

        prepare = await create_user_client.post("/auth/create-user?challenge=true",
                                                headers=_auth(subject))
        handle = prepare.json()["challenge_id"]

        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth(subject))

        assert completion.status_code == 403
        assert completion.json() == {"code": "operation_not_allowed"}
        # No flow is named: D-12 removed `create_flow_mismatch` and its `required_flow` field, so
        # the shared one-field body is the whole response.
        assert set(completion.json()) == {"code"}
        assert await _count(_db_transaction, _USERS) == users_before

        async with _db_transaction() as session:
            challenge = (await session.exec(
                select(AuthChallenge)
                .where(col(AuthChallenge.challenge_id) == handle))).one()
        # §02 step 13: every rejection at or after the Admin lookup consumes.
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject_hash is None

        async with _db_transaction() as session:
            events = (await session.exec(
                select(AuthEvent)
                .where(col(AuthEvent.challenge_row_id) == challenge.id))).all()
        assert len(events) == 1
        assert events[0].result is AuthEventResult.provider_not_linked
        assert events[0].operation is AuthOperation.create_user
        assert events[0].details["failure"]["cause"] == "invalid-shape"
        assert not _mentions(events[0].details, "challenge_id")
        assert handle not in repr(events[0].details)

        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_the_same_handle_replayed_after_a_rejection_mints_nothing(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """No idempotent replay and no `challenge_replayed` result (§02 DELETIONS, T-37-36).

        The second attempt is not told what the first one earned -- it is told to prepare again, and
        the client reconciles through `/auth/sync`.
        """
        subject = "e2e-replayed-handle"
        scripted_firebase_adapter.script(
            entries=(ProviderDataEntry("password", "someone@example.test"),))
        users_before = await _count(_db_transaction, _USERS)

        prepare = await create_user_client.post("/auth/create-user?challenge=true",
                                                headers=_auth(subject))
        handle = prepare.json()["challenge_id"]
        first = await create_user_client.post("/auth/create-user",
                                              json={"challenge_id": handle},
                                              headers=_auth(subject))
        second = await create_user_client.post("/auth/create-user",
                                               json={"challenge_id": handle},
                                               headers=_auth(subject))

        assert first.status_code == 403
        assert second.status_code == 409
        assert second.json() == {"code": "challenge_required"}
        assert await _count(_db_transaction, _USERS) == users_before
        await _assert_step_10s_global_invariants(_db_transaction)


@pytest.mark.asyncio(loop_scope="module")
class TestCreate01AdmittedHereAndRefusedEverywhereElse:
    """CREATE-01's observable half, on the wire rather than in a registry assertion.

    `preauth_callable` is a property of exactly one route, and the way to see it is one token
    getting two different answers. A registry test proves the declaration; only this proves the
    barrier acts on it.
    """

    async def test_one_unlinked_token_is_admitted_at_create_user_and_refused_at_examples(
            self, create_user_client, _db_transaction):
        headers = _auth("e2e-create01-unlinked")

        admitted = await create_user_client.post("/auth/create-user?challenge=true",
                                                 headers=headers)
        refused = await create_user_client.get("/examples?lang=en", headers=headers)

        assert admitted.status_code == 200
        assert set(admitted.json()) == {"challenge_id", "expires_at"}
        # 403 and this specific class -- not `auth_required`. The token is fine; the *identity* is
        # not admissible on an authenticated route.
        assert refused.status_code == 403
        assert refused.json() == {"code": "preauth_identity_not_allowed"}


# ---------------------------------------------------------------------------
# 37-10: the registered flow, §02 step 10's field rules, and the provider-account reservation.
#
# **D-09's substituted half, and why it is the right instrument for exactly these cases.** A real
# google.com- or apple.com-linked Firebase account cannot be minted from a test: there is no REST
# call that links a Google or Apple provider without a real consent screen, so a "real" registered
# fixture would mean a hand-provisioned account living in shared CI state that nothing can
# reproduce or reset. 37-CONTEXT.md § Deferred Ideas records that trade explicitly, and records the
# one condition worth revisiting it under -- the fake drifting from the SDK's shape.
#
# What bounds that drift is the *other* half of the same decision: the genuinely anonymous fixture
# below in `tests/e2e/conftest.py`, which mints a real Firebase user through
# `accounts:signUp` and proves the real Admin SDK returns the empty providerData this file's
# anonymous cases script. The one shape that CAN be minted reproducibly is minted for real; the
# ones that cannot are scripted, and the scripting is confined to the provider seam.
#
# Nothing below required a source change. §02 step 10's email carrier -- `ProviderDataResult.email`
# and `.email_verified` -- was built and recorded as a Phase 35 foundation amendment by 37-05, and
# `auth/classifier.py::email_to_persist` is its single evaluation site. These cases script that
# carrier; they do not extend it.
# ---------------------------------------------------------------------------


async def _prepare_and_complete(client, subject: str | None = None):
    """One prepare then one completion for `subject`; return `(handle, completion_response)`.

    The prepare is asserted here rather than in each caller: every case below is about what the
    *completion* answers, and a case whose prepare had quietly failed would otherwise assert
    against a completion for a handle that never existed.

    `subject=None` sends **no** `Authorization` header and lets the client's own stand -- which is
    what the real-anonymous case needs, because its client already carries a genuine Firebase ID
    token and a per-request `_auth(...)` header would replace it with a stub-verifier token the
    real verifier rejects.
    """
    headers = {} if subject is None else _auth(subject)
    prepare = await client.post("/auth/create-user?challenge=true", headers=headers)
    assert prepare.status_code == 200, prepare.text
    handle = prepare.json()["challenge_id"]
    completion = await client.post("/auth/create-user",
                                   json={"challenge_id": handle},
                                   headers=headers)
    return handle, completion


async def _identity_and_user(factory, subject: str,
                             issuer: str = TEST_ISSUER) -> tuple[ExternalIdentity, User]:
    """The single identity row for `(issuer, subject)` and the `core.users` row it points at.

    `.one()` on both, deliberately: "exactly one identity" is itself part of what step 10 promises,
    so a second row must fail here rather than be silently narrowed away by a `.first()`.

    `issuer` is a parameter rather than the module constant because the real-anonymous case's rows
    carry the **live project's** issuer, not the stub verifier's. Defaulting it to `TEST_ISSUER`
    hid that from the first run of this helper: the query simply matched nothing and reported it as
    "no account was created" for a completion that had in fact returned 200.
    """
    async with factory() as session:
        identity = (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                           col(ExternalIdentity.subject) == subject))).one()
        user = (await session.exec(select(User).where(col(User.id) == identity.user_id))).one()
    return identity, user


async def _challenge_and_events(factory, handle: str):
    """The challenge row for `handle` and every audit row correlated on its **row id**.

    Correlating on `challenge_row_id` rather than on the handle is not a convenience: the public
    handle is a secret capability and never reaches a row (§4.4), so the row id is the only
    correlation key there is.
    """
    async with factory() as session:
        challenge = (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()
        events = (await session.exec(
            select(AuthEvent).where(col(AuthEvent.challenge_row_id) == challenge.id))).all()
    return challenge, events


# The two recognized provider ids, verbatim from §02 step 9, each with the `uid` the classifier is
# required to carry through to `provider_uid` unchanged.
_REGISTERED_SHAPES = [
    pytest.param("google.com", IdentityProvider.google, "g-123", id="google"),
    pytest.param("apple.com", IdentityProvider.apple, "a-456", id="apple"),
]


@pytest.mark.asyncio(loop_scope="module")
class TestTheRegisteredFlow:
    """§02 step 10 for a caller whose providerData carries exactly one recognized entry.

    The anonymous branch is the tracer's; this is the other one, and the two differ in precisely
    three columns -- `provider`, `provider_uid` and `registered_at`. Everything else, the
    attribution tokens included, is common to both and is asserted here again rather than assumed
    from the tracer: "both tokens are minted on the registered branch as well" is a claim about
    *this* branch.
    """

    @pytest.mark.parametrize(("provider_id", "expected", "uid"), _REGISTERED_SHAPES)
    async def test_one_recognized_entry_creates_a_registered_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter,
            provider_id, expected, uid):
        subject = f"registered-{expected}-subject"
        scripted_firebase_adapter.script(entries=(ProviderDataEntry(provider_id, uid),))
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _prepare_and_complete(create_user_client, subject)

        assert completion.status_code == 200, completion.text
        # One field, the classified provider, and nothing else -- no backend token, no session, no
        # generation counter, no attribution value (D-10 / D-11).
        assert completion.json() == {"identity_provider": expected.value}
        # §02 step 8: exactly one provider read per completion. A second would be invisible here
        # without this assertion, because a repeat lookup returns the same scripted answer.
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, subject)]
        assert await _count(_db_transaction, _USERS) == users_before + 1

        identity, user = await _identity_and_user(_db_transaction, subject)
        assert identity.identity_state is IdentityState.active
        assert identity.provider is expected
        # §02 makes the matching entry's `uid` the SOLE source of `provider_uid` -- never a token
        # claim, never client input, never an email or a display name. Asserting the exact value
        # is what catches a derivation creeping in where a copy belongs.
        assert identity.provider_uid == uid
        # Non-NULL exactly for google and apple, NULL exactly for anonymous, with no third state.
        assert user.registered_at is not None
        assert user.display_name is None

        async with _db_transaction() as session:
            tokens = (await session.exec(
                select(StorePurchaseToken)
                .where(col(StorePurchaseToken.user_id) == user.id))).all()
        assert len(tokens) == 2
        assert {token.provider for token in tokens} == set(PurchaseProvider)
        # Distinct, because each is a fresh `uuid4()` and nothing derived: two equal values would
        # be a cross-store correlation key.
        assert len({token.identity_value for token in tokens}) == 2

        challenge, events = await _challenge_and_events(_db_transaction, handle)
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject_hash is None
        assert len(events) == 1
        assert events[0].operation is AuthOperation.create_user
        assert events[0].result is AuthEventResult.succeeded

        await _assert_step_10s_global_invariants(_db_transaction)


# §02 step 10's copy rule has two independent conditions and they are ANDed: a non-empty address
# AND `emailVerified` true. Each row below fails at most one of them, so a case that started
# passing because the rule had collapsed to a single condition would show up as exactly one
# failure rather than as a suite that still agrees with itself.
_EMAIL_CASES = [
    pytest.param("verified@example.test", True, "verified@example.test", id="non-empty-and-verified"),
    pytest.param("unverified@example.test", False, None, id="non-empty-but-unverified"),
    pytest.param("", True, None, id="empty-though-verified"),
    pytest.param("   ", True, None, id="whitespace-only-though-verified"),
    pytest.param(None, True, None, id="absent-though-verified"),
]


@pytest.mark.asyncio(loop_scope="module")
class TestStep10sEmailCopyRule:
    """The address that lands in `core.users.email`, over the wire and against a real column.

    `tests/unit/` proves `email_to_persist` in isolation. What only this can prove is that the
    resolved value actually travels -- adapter result -> classifier -> router -> `create_account`
    -> the column -- without a second evaluation site quietly re-deciding it (T-37-34).

    Both fields are driven through 37-05's already-committed `ProviderDataResult.email` /
    `.email_verified`; nothing under `src/` changes for these cases.
    """

    @pytest.mark.parametrize(("email", "email_verified", "persisted"), _EMAIL_CASES)
    async def test_the_address_is_copied_only_when_both_conditions_hold(
            self, create_user_client, _db_transaction, scripted_firebase_adapter,
            email, email_verified, persisted):
        subject = f"email-rule-{email!r}-{email_verified}"
        scripted_firebase_adapter.script(entries=(ProviderDataEntry("google.com", "g-email-case"),),
                                         email=email,
                                         email_verified=email_verified)

        _, completion = await _prepare_and_complete(create_user_client, subject)

        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": "google"}

        _, user = await _identity_and_user(_db_transaction, subject)
        # Exactly as the provider gave it when it is copied at all -- not lowercased, not trimmed.
        assert user.email == persisted
        assert user.display_name is None
        assert user.registered_at is not None

        await _assert_step_10s_global_invariants(_db_transaction)


@pytest.mark.asyncio(loop_scope="module")
class TestTheProviderAccountReservation:
    """§02 step 11 on the wire: one provider account, one identity, forever.

    `tests/unit/test_conflict_classification.py` proves that `ix_external_identities_provider_account`
    maps to `provider_account_already_linked`. What is proved here is that the index really fires
    for a second subject presenting the same `uid` -- against real PostgreSQL, through the real
    savepoint arm, ending in the real 403.

    **Retirement never frees a provider account**, which is why the historical variant exists. The
    index is partial on `provider_uid IS NOT NULL` and says nothing about `identity_state`, so a
    tombstoned row still holds its reservation. The alternative reading -- that a retired identity
    releases its Google account for re-linking to a fresh `core.users` row -- is exactly the silent
    account-takeover path the reservation exists to close.
    """

    @pytest.mark.parametrize("owner_state", [IdentityState.active, IdentityState.historical],
                             ids=["owner-active", "owner-historical"])
    async def test_a_reserved_provider_account_refuses_a_second_subject(
            self, create_user_client, _db_transaction, scripted_firebase_adapter, owner_state):
        _, owner = await seed_identity(_db_transaction,
                                       issuer=TEST_ISSUER,
                                       subject=f"provider-account-owner-{owner_state}",
                                       identity_state=owner_state,
                                       provider=IdentityProvider.google)
        # Read back rather than reconstructed: `seed_identity` derives `provider_uid` itself, and a
        # second derivation here would silently stop colliding the day the helper changes.
        assert owner.provider_uid is not None
        scripted_firebase_adapter.script(
            entries=(ProviderDataEntry("google.com", owner.provider_uid),))
        subject = f"provider-account-claimant-{owner_state}"
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _prepare_and_complete(create_user_client, subject)

        # 403, and this code rather than `account_unavailable`: the same status, a different
        # remediation. The caller's Firebase account is already someone's; support, not retry.
        assert completion.status_code == 403, completion.text
        assert completion.json() == {"code": "operation_not_allowed"}

        # Nothing partial survived the conflict: no user row, no identity row for the claimant.
        assert await _count(_db_transaction, _USERS) == users_before
        async with _db_transaction() as session:
            claimant_rows = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == subject))).all()
        assert claimant_rows == []

        challenge, events = await _challenge_and_events(_db_transaction, handle)
        # §02 step 13: a rejection at or after the provider read consumes. A retry needs a fresh
        # prepare -- and will earn the same answer.
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject_hash is None
        assert len(events) == 1
        assert events[0].operation is AuthOperation.create_user
        assert events[0].result is AuthEventResult.provider_account_already_linked

        await _assert_step_10s_global_invariants(_db_transaction)


# ---------------------------------------------------------------------------
# 37-10 Task 3: D-09's real half.
#
# Everything above substitutes the provider seam. This does not, and that is the entire point:
# every scripted `entries=()` above encodes an *assumption* about what the real Firebase Admin SDK
# returns for an anonymous user, and an assumption the whole classifier rests on is exactly the
# kind that fails silently in production -- green tests, 503s for real callers, and nothing in the
# suite that disagrees.
#
# So this case substitutes nothing. A real anonymous Firebase user, minted through
# `accounts:signUp`; the real JWT verifier resolving a real Firebase ID token against real JWKS;
# the real `FirebaseAdminLookup` making a real `getUser` against a real project; and then the same
# row set §02 step 10 names, in the same real PostgreSQL.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module")
async def anonymous_client(_app_lifespan, anonymous_firebase_credential):
    """A client carrying a REAL anonymous Firebase ID token, verified by the REAL verifier.

    Note what it does **not** take: `stub_verifier`. Every other case in this file swaps the
    verifier so an arbitrary subject is expressible without minting an account; this one has a
    genuine account, so the ephemeral-RSA verifier would reject its genuine token. The real
    verifier, the real JWKS fetch and the real issuer/audience checks are all part of what this
    case is here to exercise.
    """
    id_token, _ = anonymous_firebase_credential
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {id_token}"
        yield client


@pytest.mark.asyncio(loop_scope="module")
class TestTheRealAnonymousCompletion:
    """D-09's real half: nothing substituted, end to end, against the live project.

    Skips rather than fails without an Admin credential -- see `anonymous_firebase_credential`.
    Running it creates a permanent anonymous user in the shared project with no cleanup path
    (T-37-50, accepted).
    """

    async def test_a_genuinely_anonymous_user_completes_through_the_real_admin_sdk(
            self, anonymous_client, _db_transaction, _app_lifespan, _app_config,
            anonymous_firebase_credential):
        _, local_id = anonymous_firebase_credential
        adapter = _app_lifespan.state.firebase_adapter
        # The guard that keeps this case honest. `scripted_firebase_adapter` is deliberately not
        # requested, but "deliberately not requested" is invisible in a diff and one careless
        # fixture argument would turn the phase's only unsubstituted proof into another scripted
        # one that agrees with itself.
        assert isinstance(adapter, FirebaseAdminLookup)
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _prepare_and_complete(anonymous_client)

        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": "anonymous"}
        assert await _count(_db_transaction, _USERS) == users_before + 1

        identity, user = await _identity_and_user(_db_transaction, local_id,
                                                  issuer=_app_config.jwt.issuer)
        assert identity.issuer == _app_config.jwt.issuer
        assert identity.identity_state is IdentityState.active
        assert identity.provider is IdentityProvider.anonymous
        # NULL, not a sentinel: the row stays outside the provider-account reservation.
        assert identity.provider_uid is None
        assert user.registered_at is None
        assert user.display_name is None

        async with _db_transaction() as session:
            tokens = (await session.exec(
                select(StorePurchaseToken)
                .where(col(StorePurchaseToken.user_id) == user.id))).all()
        assert len(tokens) == 2
        assert {token.provider for token in tokens} == set(PurchaseProvider)
        assert len({token.identity_value for token in tokens}) == 2

        challenge, events = await _challenge_and_events(_db_transaction, handle)
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject_hash is None
        assert len(events) == 1
        assert events[0].operation is AuthOperation.create_user
        assert events[0].result is AuthEventResult.succeeded

        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_the_real_sdk_returns_empty_provider_data_for_an_anonymous_user(
            self, _app_lifespan, _app_config, anonymous_firebase_credential):
        """**The assertion this whole plan exists to make.**

        No substituted adapter can make it, because a substituted adapter is where the assumption
        lives. §02 step 9's classifier answers `anonymous` to an EMPTY providerData and to nothing
        else -- so if the real SDK returned, say, a single entry with `providerId: "anonymous"`, or
        `None` instead of an empty sequence, every anonymous completion in production would take
        the classifier's reject arm and return 403 while this suite stayed green.

        It is a separate case from the completion above on purpose: the completion asserts the
        *consequence*, and consequences can be right for the wrong reason. This asserts the shape.
        """
        adapter = _app_lifespan.state.firebase_adapter
        assert isinstance(adapter, FirebaseAdminLookup)
        _, local_id = anonymous_firebase_credential

        result = await adapter.get_user_provider_data(_app_config.jwt.issuer, local_id)

        assert result.outcome is ProviderDataOutcome.ok
        assert result.entries == ()
        # The same response's address fields, which §02 step 10's copy rule reads. An anonymous
        # user has neither, so the rule yields NULL -- and it yields it from real values here
        # rather than from scripted ones.
        assert result.email is None
        assert result.email_verified is False
