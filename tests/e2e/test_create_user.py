"""An unlinked caller goes from no account to an account, unstubbed but for the verifier and the adapter."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.firebase import FirebaseAdminLookup, _verified_email
from nativespeaker.api.errors import NotLinked
from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.grants import AccessGrant, UserMonthlyUsage
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.purchases import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.tables.users import User

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

_GRANTS = select(func.count()).select_from(AccessGrant)
_MONTHLY_USAGE = select(func.count()).select_from(UserMonthlyUsage)
_USERS_CARRYING_A_NAME = (select(func.count()).select_from(User)
                          .where(col(User.display_name).is_not(None)))


async def _assert_step_10s_global_invariants(factory) -> None:
    """Two rules hold after every completion here: no entitlement is minted anywhere, display_name stays NULL."""
    assert await _count(factory, _GRANTS) == 0
    assert await _count(factory, _MONTHLY_USAGE) == 0
    assert await _count(factory, _USERS_CARRYING_A_NAME) == 0


@pytest.mark.asyncio(loop_scope="module")
class TestTheAnonymousHappyPath:
    """One unlinked caller, one issued challenge, one completion, and the exact row set that must result."""

    async def test_an_unlinked_caller_creates_an_anonymous_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None))

        users_before = await _count(_db_transaction, select(func.count()).select_from(User))

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth())

        assert issued.status_code == 200
        # The key set is asserted rather than two known keys, since a third field would pass the weaker check.
        assert set(issued.json()) == {"challenge_id", "expires_at"}
        assert issued.headers["cache-control"] == "no-store"
        handle = issued.json()["challenge_id"]

        assert await _count(_db_transaction, select(func.count()).select_from(User)) == users_before
        assert scripted_firebase_adapter.calls == []

        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth())

        assert completion.status_code == 200
        assert completion.json() == {"identity_provider": "anonymous"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]

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
            assert user.display_name is None
            # NULL for anonymous, non-NULL for google/apple -- no third state.
            assert user.registered_at is None
            # The scripted result carried no address, so step 10's copy rule yields NULL.
            assert user.email is None

        async with _db_transaction() as session:
            tokens = (await session.exec(
                select(StorePurchaseToken)
                .where(col(StorePurchaseToken.user_id) == identity.user_id))).all()
        assert {token.provider for token in tokens} == set(PurchaseProvider)
        assert len({token.identity_value for token in tokens}) == 2

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

        async with _db_transaction() as session:
            challenge = (await session.exec(
                select(AuthChallenge)
                .where(col(AuthChallenge.challenge_id) == handle))).one()
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject is None

        await _assert_step_10s_global_invariants(_db_transaction)


@pytest.mark.asyncio(loop_scope="module")
class TestTheChallengeEndpoint:
    """The split path: one caller asks the challenge route for a handle, then spends it at completion."""

    async def test_a_handle_from_the_challenge_route_completes_an_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        subject = "challenge-endpoint-anonymous"
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None))
        users_before = await _count(_db_transaction, select(func.count()).select_from(User))

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth(subject))

        assert issued.status_code == 200, issued.text
        # The key set is asserted rather than two known keys, since a third field would pass the weaker check.
        assert set(issued.json()) == {"challenge_id", "expires_at"}
        assert issued.headers["cache-control"] == "no-store"
        handle = issued.json()["challenge_id"]

        assert await _count(_db_transaction, select(func.count()).select_from(User)) == users_before
        assert scripted_firebase_adapter.calls == []

        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth(subject))

        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": "anonymous"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, subject)]
        assert await _count(_db_transaction,
                            select(func.count()).select_from(User)) == users_before + 1

    async def test_an_operation_this_route_will_not_issue_for_is_rejected(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """A valid enum member whose phase is unbuilt rejects exactly as an unknown string would."""
        challenges_before = await _count(_db_transaction, _CHALLENGES)

        response = await create_user_client.post("/auth/challenge",
                                                 json={"operation": "sync"},
                                                 headers=_auth("challenge-endpoint-sync"))

        assert response.status_code == 400
        assert response.json() == {"code": "invalid_request"}
        assert await _count(_db_transaction, _CHALLENGES) == challenges_before
        assert scripted_firebase_adapter.calls == []


@pytest.mark.asyncio(loop_scope="module")
class TestCompletionRejectsAnAlreadyLinkedCaller:
    """A caller who already has an account is refused at completion.

    Issuance does not pre-check the linkage, so the refusal costs a challenge row and one provider lookup.
    """

    async def test_an_active_linked_identity_is_rejected_at_completion(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        subject = "already-linked-completion"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)
        # A uid of its own, so the reservation index cannot be what answers: the re-resolution is.
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=f"g-uid-{subject}"))

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth(subject))

        assert issued.status_code == 200, issued.text
        assert set(issued.json()) == {"challenge_id", "expires_at"}

        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": issued.json()["challenge_id"]},
                                                   headers=_auth(subject))

        assert completion.status_code == 409, completion.text
        assert completion.json() == {"code": "identity_already_linked"}

    async def test_the_rejection_mints_no_second_account_and_spends_the_challenge(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """Nothing is created, and nothing of the attempt survives but the spent challenge."""
        subject = "already-linked-mints-nothing"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=f"g-uid-{subject}"))
        users_before = await _count(_db_transaction, _USERS)

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth(subject))
        handle = issued.json()["challenge_id"]
        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth(subject))

        assert completion.status_code == 409

        assert await _count(_db_transaction, _USERS) == users_before
        async with _db_transaction() as session:
            rows = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == subject))).all()
        assert len(rows) == 1

        challenge = await _challenge_for(_db_transaction, handle)
        assert challenge.consumed_at is not None

        await _assert_step_10s_global_invariants(_db_transaction)


@pytest.mark.asyncio(loop_scope="module")
class TestIssuanceStillServesAnUnlinkedCaller:
    """The route the handle now comes from must not have narrowed the path it serves."""

    async def test_an_unlinked_caller_still_gets_the_two_field_body(self, create_user_client,
                                                                    _db_transaction):
        response = await create_user_client.post("/auth/challenge",
                                                 json={"operation": "create_user"},
                                                 headers=_auth("still-unlinked"))

        assert response.status_code == 200
        assert set(response.json()) == {"challenge_id", "expires_at"}

    async def test_two_issuances_produce_two_distinct_challenges(self, create_user_client,
                                                                 _db_transaction):
        """Issuance never reuses a row: reusing one would hand two attempts the same single-use capability."""
        headers = _auth("issues-twice")

        first = await create_user_client.post("/auth/challenge",
                                              json={"operation": "create_user"}, headers=headers)
        second = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"}, headers=headers)

        assert first.status_code == second.status_code == 200
        assert first.json()["challenge_id"] != second.json()["challenge_id"]


_USERS = select(func.count()).select_from(User)


@pytest.mark.asyncio(loop_scope="module")
class TestCompletionRejectionsOnTheWire:
    """Two rejections from opposite sides of the consumption boundary: the earliest, and the latest before it."""

    async def test_an_unknown_handle_is_challenge_required(
            self, create_user_client, _db_transaction):
        users_before = await _count(_db_transaction, _USERS)

        response = await create_user_client.post("/auth/create-user",
                                                 json={"challenge_id": "no-such-handle"},
                                                 headers=_auth("e2e-unknown-handle"))

        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert await _count(_db_transaction, _USERS) == users_before
        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_a_password_entry_is_operation_not_allowed_and_consumes_the_challenge(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """One unrecognized entry is an unclassifiable account: terminal operation_not_allowed, persisting nothing."""
        subject = "e2e-password-shape"
        # The rejection a password-provider account takes at classification.
        scripted_firebase_adapter.script(NotLinked(stage="provider_classification",
                                                   cause="invalid-shape"))
        users_before = await _count(_db_transaction, _USERS)

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth(subject))
        handle = issued.json()["challenge_id"]

        completion = await create_user_client.post("/auth/create-user",
                                                   json={"challenge_id": handle},
                                                   headers=_auth(subject))

        assert completion.status_code == 403
        assert completion.json() == {"code": "operation_not_allowed"}
        assert set(completion.json()) == {"code"}
        assert await _count(_db_transaction, _USERS) == users_before

        async with _db_transaction() as session:
            challenge = (await session.exec(
                select(AuthChallenge)
                .where(col(AuthChallenge.challenge_id) == handle))).one()
        # Every rejection at or after the Admin lookup consumes the challenge.
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject is None

        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_the_same_handle_replayed_after_a_rejection_mints_nothing(
            self, create_user_client, _db_transaction, scripted_firebase_adapter):
        """No idempotent replay: the second attempt is told to obtain a fresh challenge, not the first's outcome."""
        subject = "e2e-replayed-handle"
        # The rejection a password-provider account takes at classification.
        scripted_firebase_adapter.script(NotLinked(stage="provider_classification",
                                                   cause="invalid-shape"))
        users_before = await _count(_db_transaction, _USERS)

        issued = await create_user_client.post("/auth/challenge",
                                               json={"operation": "create_user"},
                                               headers=_auth(subject))
        handle = issued.json()["challenge_id"]
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
    """One token gets two different answers: the auth routes admit an unlinked identity and no other does."""

    async def test_one_unlinked_token_is_admitted_at_the_auth_routes_and_refused_at_examples(
            self, create_user_client, _db_transaction):
        headers = _auth("e2e-create01-unlinked")

        admitted = await create_user_client.post("/auth/challenge",
                                                 json={"operation": "create_user"},
                                                 headers=headers)
        refused = await create_user_client.get("/examples?lang=en", headers=headers)

        assert admitted.status_code == 200
        assert set(admitted.json()) == {"challenge_id", "expires_at"}
        # 403 and this class, not auth_required: the token is fine, the identity is not admissible here.
        assert refused.status_code == 403
        assert refused.json() == {"code": "preauth_identity_not_allowed"}


async def _issue_and_complete(client, subject: str | None = None):
    """One issuance then one completion for subject; subject=None sends no header and keeps the client's own."""
    headers = {} if subject is None else _auth(subject)
    issued = await client.post("/auth/challenge",
                               json={"operation": "create_user"},
                               headers=headers)
    assert issued.status_code == 200, issued.text
    handle = issued.json()["challenge_id"]
    completion = await client.post("/auth/create-user",
                                   json={"challenge_id": handle},
                                   headers=headers)
    return handle, completion


async def _identity_and_user(factory, subject: str,
                             issuer: str = TEST_ISSUER) -> tuple[ExternalIdentity, User]:
    """The single identity row for (issuer, subject) and the user it points at; .one() so a second row fails."""
    async with factory() as session:
        identity = (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                           col(ExternalIdentity.subject) == subject))).one()
        user = (await session.exec(select(User).where(col(User.id) == identity.user_id))).one()
    return identity, user


async def _challenge_for(factory, handle: str):
    """The challenge row for `handle`, read back through the test's own factory."""
    async with factory() as session:
        return (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()


# The two recognized provider ids, each with the uid the classifier must carry through unchanged.
_REGISTERED_SHAPES = [
    pytest.param("google.com", IdentityProvider.google, "g-123", id="google"),
    pytest.param("apple.com", IdentityProvider.apple, "a-456", id="apple"),
]


@pytest.mark.asyncio(loop_scope="module")
class TestTheRegisteredFlow:
    """A caller whose providerData carries one recognized entry; it differs from anonymous in three columns."""

    @pytest.mark.parametrize(("provider_id", "expected", "uid"), _REGISTERED_SHAPES)
    async def test_one_recognized_entry_creates_a_registered_account(
            self, create_user_client, _db_transaction, scripted_firebase_adapter,
            provider_id, expected, uid):
        subject = f"registered-{expected}-subject"
        scripted_firebase_adapter.script(VerifiedProviderIdentity(provider=expected,
                                                                  provider_uid=uid))
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _issue_and_complete(create_user_client, subject)

        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": expected.value}
        # Exactly one provider read per completion; a second would be invisible without this assertion.
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, subject)]
        assert await _count(_db_transaction, _USERS) == users_before + 1

        identity, user = await _identity_and_user(_db_transaction, subject)
        assert identity.identity_state is IdentityState.active
        assert identity.provider is expected
        # The matching entry's uid is the sole source of provider_uid: never a claim, never client input.
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
        # Distinct, because two equal values would be a cross-store correlation key.
        assert len({token.identity_value for token in tokens}) == 2

        challenge = await _challenge_for(_db_transaction, handle)
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject is None

        await _assert_step_10s_global_invariants(_db_transaction)


# The copy rule ANDs a non-empty address with emailVerified; each row below fails at most one of them.
_EMAIL_CASES = [
    pytest.param("verified@example.test", True, "verified@example.test", id="non-empty-and-verified"),
    pytest.param("unverified@example.test", False, None, id="non-empty-but-unverified"),
    pytest.param("", True, None, id="empty-though-verified"),
    pytest.param("   ", True, None, id="whitespace-only-though-verified"),
    pytest.param(None, True, None, id="absent-though-verified"),
]


@pytest.mark.asyncio(loop_scope="module")
class TestStep10sEmailCopyRule:
    """The address that lands in core.users.email, asserted over the wire against the real column."""

    @pytest.mark.parametrize(("email", "email_verified", "persisted"), _EMAIL_CASES)
    async def test_the_address_is_copied_only_when_both_conditions_hold(
            self, create_user_client, _db_transaction, scripted_firebase_adapter,
            email, email_verified, persisted):
        subject = f"email-rule-{email!r}-{email_verified}"
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid="g-email-case",
                                     email=_verified_email(email, email_verified)))

        _, completion = await _issue_and_complete(create_user_client, subject)

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
    """One provider account, one identity, forever -- retiring an identity never frees its provider account."""

    @pytest.mark.parametrize("owner_state", [IdentityState.active, IdentityState.historical],
                             ids=["owner-active", "owner-historical"])
    async def test_a_reserved_provider_account_refuses_a_second_subject(
            self, create_user_client, _db_transaction, scripted_firebase_adapter, owner_state):
        _, owner = await seed_identity(_db_transaction,
                                       issuer=TEST_ISSUER,
                                       subject=f"provider-account-owner-{owner_state}",
                                       identity_state=owner_state,
                                       provider=IdentityProvider.google)
        # Read back rather than rederived: a second derivation would stop colliding the day the helper changes.
        assert owner.provider_uid is not None
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=owner.provider_uid))
        subject = f"provider-account-claimant-{owner_state}"
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _issue_and_complete(create_user_client, subject)

        assert completion.status_code == 409, completion.text
        assert completion.json() == {"code": "identity_already_linked"}

        assert await _count(_db_transaction, _USERS) == users_before
        async with _db_transaction() as session:
            claimant_rows = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == subject))).all()
        assert claimant_rows == []

        challenge = await _challenge_for(_db_transaction, handle)
        # A rejection at or after the provider read consumes, so a retry needs a freshly issued challenge.
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject is None

        await _assert_step_10s_global_invariants(_db_transaction)


@pytest_asyncio.fixture(loop_scope="module")
async def anonymous_client(_app_lifespan, anonymous_firebase_credential):
    """A client with a real anonymous Firebase token, so it must not take stub_verifier, which would reject it."""
    id_token, _ = anonymous_firebase_credential
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {id_token}"
        yield client


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
        users_before = await _count(_db_transaction, _USERS)

        handle, completion = await _issue_and_complete(anonymous_client)

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

        challenge = await _challenge_for(_db_transaction, handle)
        assert challenge.consumed_at is not None
        assert challenge.preauth_subject is None

        await _assert_step_10s_global_invariants(_db_transaction)

    async def test_the_real_sdk_returns_empty_provider_data_for_an_anonymous_user(
            self, _app_lifespan, _app_config, anonymous_firebase_credential):
        """The real SDK returns an EMPTY providerData, the only shape the classifier answers anonymous to."""
        adapter = _app_lifespan.state.firebase_adapter
        assert isinstance(adapter, FirebaseAdminLookup)
        _, local_id = anonymous_firebase_credential

        identity = await adapter.get_user_provider_data(_app_config.jwt.issuer, local_id)

        assert identity.provider is IdentityProvider.anonymous
        assert identity.provider_uid is None
        assert identity.email is None
