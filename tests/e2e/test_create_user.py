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
