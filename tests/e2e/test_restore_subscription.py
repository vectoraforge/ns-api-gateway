"""The same-account restore of both stores, end to end through the real router and a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.errors import ProofRejected
from nativespeaker.api.tables.grants import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import IdentityProvider
from nativespeaker.api.tables.purchases import (
    PurchaseProvider,
    StorePurchase,
    StorePurchaseToken,
    Subscription,
    SubscriptionStatus,
)

from .conftest import (
    GOOGLE_PRODUCT_ID,
    play_subscription_body,
    seed_identity,
    seed_subscription,
)

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-restore-subscription-subject"

# A second account, which the attribution-mismatch case binds the carried token to.
OTHER_SUBJECT = "another-account-that-bought-the-subscription"

# One obviously synthetic attribution token, recorded against that second account.
OTHER_ACCOUNTS_TOKEN = "a-synthetic-token-recorded-against-another-account"

# The artifact the client presents; the seam is scripted, so its content is never parsed here.
RESTORE_PROOF = "a-signed-transaction-the-scripted-seam-accepts"

# The tier the migration seeds for a paid subscription, which the proof's product maps to.
PAID_TIER_ID = "paid"

# The same body as bytes, so the gate refusal is compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'

# The one body every rejected proof of both stores answers with, compared as raw response bytes.
PROOF_REJECTED_BODY = b'{"code":"proof_rejected"}'

# The one body both refusals of the restore's own 404 family answer with, on the same terms.
RESTORE_NOT_FOUND_BODY = b'{"code":"restore_not_found"}'

# The three Apple arms the library refuses on: the chain, the application and the environment.
APPLE_REJECTION_STAGES = ("VERIFICATION_FAILURE", "INVALID_APP_IDENTIFIER", "INVALID_ENVIRONMENT")

# A month out, so the written term is unambiguously open at the instant every case runs.
TERM_REMAINING = timedelta(days=30)

# An hour back, because `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
PURCHASED_AGO = timedelta(hours=1)


@pytest_asyncio.fixture(loop_scope="module")
async def restore_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


def _proof(external_id: str, *, status: SubscriptionStatus = SubscriptionStatus.active,
           grace_period_expires_at: datetime | None = None,
           attribution_token: str | None = None) -> RestoredSubscription:
    """What the Apple check reports for this case, in the value type the seam returns."""
    now = datetime.now(UTC)
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=external_id,
                                product_id="com.nativespeaker.subscription.monthly",
                                tier_id=PAID_TIER_ID,
                                attribution_token=attribution_token,
                                status=status,
                                purchased_at=now - PURCHASED_AGO,
                                expires_at=now + TERM_REMAINING,
                                grace_period_expires_at=grace_period_expires_at)


async def _restore(client, subject: str = SUBJECT, **body):
    """Present one restore proof; `body` replaces the default two fields wholesale."""
    payload = body or {"provider": "apple", "restore_proof": RESTORE_PROOF}
    return await client.post("/auth/restore-subscription", json=payload, headers=_auth(subject))


async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())


def _play_proof(purchase_token: str) -> RestoredSubscription:
    """What the Play read reports for this case; only the provider and the id differ from Apple's."""
    now = datetime.now(UTC)
    return RestoredSubscription(provider=PurchaseProvider.google_play,
                                external_id=purchase_token,
                                product_id=GOOGLE_PRODUCT_ID,
                                tier_id=PAID_TIER_ID,
                                attribution_token=None,
                                status=SubscriptionStatus.active,
                                purchased_at=now - PURCHASED_AGO,
                                expires_at=now + TERM_REMAINING,
                                grace_period_expires_at=None)


async def _row_counts(factory, user_id) -> tuple[int, int]:
    """The grant and usage row counts for `user_id`: the two kinds a restore writes."""
    grants = await _grants_of(factory, user_id)
    ids = [grant.id for grant in grants]
    async with factory() as session:
        usage = (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id).in_(ids or [uuid4()])))).all()
        return len(grants), len(usage)


async def _four_counts(factory, user_id, external_id) -> tuple[int, int, int, int]:
    """The four kinds a restore can write: the caller's grants and usage, the row and its purchase."""
    grants, usage = await _row_counts(factory, user_id)
    async with factory() as session:
        subscriptions = (await session.exec(
            select(Subscription).where(col(Subscription.external_id) == external_id))).all()
        purchases = (await session.exec(
            select(StorePurchase).where(col(StorePurchase.external_id) == external_id))).all()
    return grants, usage, len(subscriptions), len(purchases)


async def _subscription_row(factory, external_id) -> Subscription:
    """The canonical row for one lifecycle key, read back on a session of its own."""
    async with factory() as session:
        return (await session.exec(
            select(Subscription).where(col(Subscription.external_id) == external_id))).one()


async def _bind_token(factory, *, user_id, identity_value) -> None:
    """Bind one Apple attribution token to an account, which is what `resolve_user` then reads."""
    async with factory() as session:
        session.add(StorePurchaseToken(user_id=user_id,
                                       provider=PurchaseProvider.apple,
                                       identity_value=identity_value,
                                       created_at=datetime.now(UTC)))
        await session.commit()


async def _usage_of(factory, grant_id) -> UserMonthlyUsage:
    async with factory() as session:
        return (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))).one()


async def _spend(factory, grant_id, used: int) -> None:
    """Charge the grant's counter, so a reset by a repeat restore is visible rather than invisible."""
    async with factory() as session:
        usage = (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))).one()
        usage.monthly_used = used
        session.add(usage)
        await session.commit()


@pytest.mark.asyncio(loop_scope="module")
class TestTheSameAccountAppleRestore:
    """The one path this slice serves: the caller's account already owns the subscription named."""

    async def test_a_verified_proof_attaches_the_paid_grant_and_the_body_reports_it(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["entitlement"]["type"] == "subscription"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == PAID_TIER_ID
        assert body["identity_provider"] == "google"
        assert answered.headers["Cache-Control"] == "no-store"

    async def test_the_one_grant_it_wrote_is_the_subscription_grant_and_its_usage_row(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        subscription_id = await seed_subscription(_db_transaction, external_id=external_id,
                                                  user_id=user.id, tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        assert (await _restore(restore_client)).status_code == 200

        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 1
        assert grants[0].source is AccessGrantSource.subscription
        assert grants[0].status is AccessGrantStatus.active
        assert grants[0].subscription_id == subscription_id
        assert (await _usage_of(_db_transaction, grants[0].id)).monthly_used == 0

    async def test_a_repeat_restore_writes_no_new_row_and_resets_no_counter(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """D-07: the same term and tier is a replay, so the paid month's counter survives it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        proof = _proof(external_id)
        scripted_app_store_notifications.script_restore(proof)
        assert (await _restore(restore_client)).status_code == 200
        first = (await _grants_of(_db_transaction, user.id))[0]
        await _spend(_db_transaction, first.id, 7)

        # The identical proof a second time: the same term, so the writer answers `replayed`.
        scripted_app_store_notifications.script_restore(proof)
        repeated = await _restore(restore_client)

        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["entitlement"]["monthly_used"] == 7
        grants = await _grants_of(_db_transaction, user.id)
        assert [grant.id for grant in grants] == [first.id]
        assert (await _usage_of(_db_transaction, first.id)).monthly_used == 7


@pytest.mark.asyncio(loop_scope="module")
class TestTheAdoptionBranches:
    """The two branches that first write an owner: a row nobody owns, and no row at all."""

    async def test_an_unowned_subscription_becomes_the_callers_and_carries_its_grant(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-adopt-{uuid4()}"
        subscription_id = await seed_subscription(_db_transaction, external_id=external_id,
                                                  user_id=None, tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        seeded = (await _subscription_row(_db_transaction, external_id)).updated_at

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        adopted = await _subscription_row(_db_transaction, external_id)
        assert adopted.user_id == user.id
        # The control for the same-account case below: an owner update really does move this clock.
        assert adopted.updated_at != seeded
        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 1
        assert grants[0].status is AccessGrantStatus.active
        assert grants[0].source is AccessGrantSource.subscription
        assert grants[0].subscription_id == subscription_id
        assert (await _usage_of(_db_transaction, grants[0].id)).monthly_used == 0

    async def test_a_proof_with_no_row_at_all_creates_it_at_the_proofs_own_state_and_tier(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """D-06: canonical state belongs to the webhooks, so the created row says what the proof says."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-create-{uuid4()}"
        # Grace, not active: a hard-coded status on the create path would pass an `active` case.
        scripted_app_store_notifications.script_restore(
            _proof(external_id, status=SubscriptionStatus.grace_period,
                   grace_period_expires_at=datetime.now(UTC) + TERM_REMAINING))

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        created = await _subscription_row(_db_transaction, external_id)
        assert created.status is SubscriptionStatus.grace_period
        assert created.tier_id == PAID_TIER_ID
        assert created.user_id == user.id
        grants = await _grants_of(_db_transaction, user.id)
        assert [grant.subscription_id for grant in grants] == [created.id]


@pytest.mark.asyncio(loop_scope="module")
class TestTheTwoRefusalsOfTheRestoreNotFoundFamily:
    """T-45-05: two causes, one body. The adoption case above is the control for both setups."""

    async def test_a_subscription_outside_the_entitled_set_writes_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """D-06: the stored row's own status decides, and the proof never rewrites it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-unentitled-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=None,
                                tier_id=PAID_TIER_ID, status="expired")
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _four_counts(_db_transaction, user.id, external_id) == before

    async def test_a_token_recorded_against_another_account_answers_the_same_body(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The setup of the adoption case exactly, plus one binding: the token is the only difference."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        other, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=OTHER_SUBJECT,
                                       provider=IdentityProvider.google)
        external_id = f"e2e-mismatch-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=None,
                                tier_id=PAID_TIER_ID)
        await _bind_token(_db_transaction, user_id=other.id, identity_value=OTHER_ACCOUNTS_TOKEN)
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(
            _proof(external_id, attribution_token=OTHER_ACCOUNTS_TOKEN))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _four_counts(_db_transaction, user.id, external_id) == before

    async def test_the_two_refusals_answer_bodies_equal_to_each_other(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """One body for two causes, compared to each other rather than each to a literal."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        other, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=OTHER_SUBJECT,
                                       provider=IdentityProvider.google)
        unentitled = f"e2e-pair-unentitled-{uuid4()}"
        mismatched = f"e2e-pair-mismatch-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=unentitled, user_id=None,
                                tier_id=PAID_TIER_ID, status="expired")
        await seed_subscription(_db_transaction, external_id=mismatched, user_id=None,
                                tier_id=PAID_TIER_ID)
        await _bind_token(_db_transaction, user_id=other.id, identity_value=OTHER_ACCOUNTS_TOKEN)

        scripted_app_store_notifications.script_restore(_proof(unentitled))
        first = await _restore(restore_client)
        scripted_app_store_notifications.script_restore(
            _proof(mismatched, attribution_token=OTHER_ACCOUNTS_TOKEN))
        second = await _restore(restore_client)

        assert [first.status_code, second.status_code] == [404, 404]
        # Byte-equal, so a body naming which of the two checks refused fails here.
        assert first.content == second.content
        assert await _row_counts(_db_transaction, user.id) == (0, 0)


@pytest.mark.asyncio(loop_scope="module")
class TestTheSameAccountBranchRunsNoOwnerUpdate:
    """RESEARCH Q2: a no-op update would make "zero rows means a lost race" untrue for this branch."""

    async def test_the_row_the_caller_already_owns_is_not_written_at_all(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-same-account-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        seeded = (await _subscription_row(_db_transaction, external_id)).updated_at
        scripted_app_store_notifications.script_restore(_proof(external_id))

        assert (await _restore(restore_client)).status_code == 200

        # `updated_at` is what the owner update writes, so an unmoved clock is a statement not run.
        settled = await _subscription_row(_db_transaction, external_id)
        assert settled.updated_at == seeded
        assert settled.user_id == user.id


@pytest.mark.asyncio(loop_scope="module")
class TestTheSurfaceGateIsTheStoreNameAndTheProof:
    """RESTORE-02, D-01, D-02: a caller naming no store this deployment serves is refused here."""

    async def test_a_store_the_server_does_not_serve_is_refused_before_any_proof_check(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="web", restore_proof=RESTORE_PROOF)

        assert refused.status_code == 403
        # Compared as bytes, so a more helpful field on this body fails here.
        assert refused.text == REFUSED_BODY
        assert scripted_app_store_notifications.restore_calls == []

    async def test_an_empty_store_name_is_the_frameworks_own_refusal(
            self, restore_client, _db_transaction):
        """D-01: both fields are required and non-empty, so an empty one never reaches the handler."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="", restore_proof=RESTORE_PROOF)

        assert refused.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
class TestTheSameAccountGooglePlayRestore:
    """The second store on the same path: the purchase token is both the proof and the external id."""

    async def test_a_live_purchase_token_attaches_the_paid_grant_and_the_body_reports_it(
            self, restore_client, _db_transaction, scripted_play_subscriptions):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        purchase_token = f"e2e-play-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=purchase_token, user_id=user.id,
                                provider=PurchaseProvider.google_play, tier_id=PAID_TIER_ID)
        scripted_play_subscriptions.script_restore(_play_proof(purchase_token))

        answered = await _restore(restore_client, provider="google_play",
                                  restore_proof=purchase_token)

        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["entitlement"]["type"] == "subscription"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == PAID_TIER_ID
        assert answered.headers["Cache-Control"] == "no-store"
        # The proof itself is the token the read was made with, and the package name is the config's.
        assert [call["purchase_token"] for call in
                scripted_play_subscriptions.restore_calls] == [purchase_token]

    async def test_the_one_grant_it_wrote_is_the_subscription_grant_and_its_usage_row(
            self, restore_client, _db_transaction, scripted_play_subscriptions):
        """Both stores reach one write path, so the Play branch writes exactly what Apple's does."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        purchase_token = f"e2e-play-restore-{uuid4()}"
        subscription_id = await seed_subscription(_db_transaction, external_id=purchase_token,
                                                  user_id=user.id,
                                                  provider=PurchaseProvider.google_play,
                                                  tier_id=PAID_TIER_ID)
        scripted_play_subscriptions.script_restore(_play_proof(purchase_token))

        assert (await _restore(restore_client, provider="google_play",
                               restore_proof=purchase_token)).status_code == 200

        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 1
        assert grants[0].source is AccessGrantSource.subscription
        assert grants[0].status is AccessGrantStatus.active
        assert grants[0].subscription_id == subscription_id
        assert (await _usage_of(_db_transaction, grants[0].id)).monthly_used == 0


@pytest.mark.asyncio(loop_scope="module")
class TestEveryRejectedProofOfBothStoresAnswersOneBody:
    """T-45-05: one status and one body for four causes, so the refusal is no enumeration oracle."""

    async def test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications,
            real_google_play_seam):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        before = await _row_counts(_db_transaction, user.id)

        answers = []
        for stage in APPLE_REJECTION_STAGES:
            scripted_app_store_notifications.script_restore(ProofRejected(stage=stage))
            answers.append(await _restore(restore_client))
        # Google's own word that this token is gone, read through the real class and its classifier.
        real_google_play_seam.status_code = 404
        answers.append(await _restore(restore_client, provider="google_play",
                                      restore_proof="a-token-google-reports-as-gone"))

        assert [answer.status_code for answer in answers] == [403, 403, 403, 403]
        # Compared as one set of raw bodies, so an arm that says more than the others fails here.
        assert {answer.content for answer in answers} == {PROOF_REJECTED_BODY}
        assert await _row_counts(_db_transaction, user.id) == before

    async def test_a_gone_token_reached_play_and_wrote_nothing(
            self, restore_client, _db_transaction, real_google_play_seam):
        """The control: the case above would also pass if the Play read had never been made."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        real_google_play_seam.status_code = 410

        refused = await _restore(restore_client, provider="google_play",
                                 restore_proof="another-token-google-reports-as-gone")

        assert refused.status_code == 403
        assert refused.content == PROOF_REJECTED_BODY
        assert len(real_google_play_seam.requests) == 1
        assert await _row_counts(_db_transaction, user.id) == (0, 0)


@pytest.mark.asyncio(loop_scope="module")
class TestThePlayFailuresThatAreNotRefusals:
    """D-05 and Pitfall 1: an operator state is a 503, and an operator error is a 500, never one code."""

    async def test_an_unconfigured_credential_is_temporarily_unavailable(
            self, restore_client, _db_transaction, unconfigured_google_play):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)

        answered = await _restore(restore_client, provider="google_play",
                                  restore_proof="a-token-no-credential-can-read")

        assert answered.status_code == 503
        assert answered.json()["code"] == "verification_temporarily_unavailable"
        assert await _row_counts(_db_transaction, user.id) == (0, 0)

    async def test_an_unmapped_play_product_is_an_internal_error_and_never_a_503(
            self, restore_client, _db_transaction, real_google_play_seam):
        """Pitfall 1 seen from the client's end: a product with no tier is the operator's to fix."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        real_google_play_seam.body = play_subscription_body(
            lineItems=[{"productId": "com.example.a.product.with.no.tier",
                        "expiryTime": (datetime.now(UTC) + TERM_REMAINING).isoformat()}])

        answered = await _restore(restore_client, provider="google_play",
                                  restore_proof="a-token-naming-an-unmapped-product")

        assert answered.status_code == 500
        assert answered.json()["code"] == "internal_error"
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
