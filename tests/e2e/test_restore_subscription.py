"""The same-account restore of both stores, end to end through the real router and a real database."""
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.app.dependencies import get_evaluated_at
from nativespeaker.api.auth.google_play import GRACE_STATE, RESTORE_TOKEN_GONE_STAGE
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
    GOOGLE_PACKAGE_NAME,
    GOOGLE_PRODUCT_ID,
    LogSpy,
    play_subscription_body,
    seed_grant,
    seed_identity,
    seed_subscription,
    spy_on,
)

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-restore-subscription-subject"

# A second account, which the attribution-mismatch case binds the carried token to.
OTHER_SUBJECT = "another-account-that-bought-the-subscription"

# One obviously synthetic attribution token, recorded against that second account.
OTHER_ACCOUNTS_TOKEN = "a-synthetic-token-recorded-against-another-account"

# The artifact the client presents; the seam is scripted, so its content is never parsed here.
RESTORE_PROOF = "a-signed-transaction-the-scripted-seam-accepts"

# The schema's own bound on the store name, restated here so the boundary is pinned in one place.
MAX_PROVIDER_LENGTH = 32

# The schema's own bound on the artifact, restated here so the boundary is pinned in one place.
MAX_PROOF_LENGTH = 8192

# The tier the migration seeds for a paid subscription, which the proof's product maps to.
PAID_TIER_ID = "paid"

# The same body as bytes, so the gate refusal is compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'

# The one body every rejected proof of both stores answers with, compared as raw response bytes.
PROOF_REJECTED_BODY = b'{"code":"proof_rejected"}'

# The one body both refusals of the restore's own 404 family answer with, on the same terms.
RESTORE_NOT_FOUND_BODY = b'{"code":"restore_not_found"}'

# The body D-10's cap answers with, on the same terms: read as bytes, never parsed.
TRANSFER_REJECTED_BODY = b'{"code":"restore_transfer_rejected"}'

# The three Apple arms the library refuses on: the chain, the application and the environment.
# They reach the route as one exception class and one body, so the stage each carries is asserted
# in the log below -- without that the three are one arm run three times.
APPLE_REJECTION_STAGES = ("VERIFICATION_FAILURE", "INVALID_APP_IDENTIFIER", "INVALID_ENVIRONMENT")

# The stage the Play seam's own classifier attaches to a gone token, which is the fourth cause.
PLAY_REJECTION_STAGE = RESTORE_TOKEN_GONE_STAGE

# The one record a refused proof leaves, written by the handler at the level `ProofRejected` declares.
_HANDLER_LOGGER = "nativespeaker.api.app.error_handlers.logger"

# A month out, so the written term is unambiguously open at the instant every case runs.
TERM_REMAINING = timedelta(days=30)

# An hour back, because `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
PURCHASED_AGO = timedelta(hours=1)

# A term that ended half an hour ago: past, and still after `PURCHASED_AGO`, which the CHECK compares it to.
TERM_ENDED_AGO = timedelta(minutes=30)


@pytest_asyncio.fixture(loop_scope="module")
async def restore_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def refusal_records(monkeypatch) -> LogSpy:
    """Every WARNING record the handler writes, which is the level a refused proof is recorded at."""
    return spy_on(monkeypatch, (_HANDLER_LOGGER,), ("warning",))


@pytest.fixture
def pinned_evaluation_instant(_app_lifespan):
    """The instant this request captures, pinned so a seam reading the clock a second time records
    a value that differs from it: SHARED-INVARIANTS binds every time-dependent value to the one
    captured evaluation time, and only a pinned instant makes a second reading observable."""
    instant = datetime.now(UTC).replace(microsecond=424242)
    _app_lifespan.dependency_overrides[get_evaluated_at] = lambda: instant
    try:
        yield instant
    finally:
        _app_lifespan.dependency_overrides.pop(get_evaluated_at)


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


def _proof(external_id: str, *, status: SubscriptionStatus = SubscriptionStatus.active,
           grace_period_expires_at: datetime | None = None,
           attribution_token: str | None = None,
           expires_at: datetime | None = None) -> RestoredSubscription:
    """What the Apple check reports for this case, in the value type the seam returns."""
    now = datetime.now(UTC)
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=external_id,
                                product_id="com.nativespeaker.subscription.monthly",
                                tier_id=PAID_TIER_ID,
                                attribution_token=attribution_token,
                                status=status,
                                purchased_at=now - PURCHASED_AGO,
                                # A term a case names replaces the open one every other case wants.
                                expires_at=(now + TERM_REMAINING if expires_at is None
                                            else expires_at),
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


async def _close_term(factory, grant_id, *, mark: AccessGrantStatus) -> None:
    """Put the grant's term in the past under the mark the webhook has got round to writing."""
    async with factory() as session:
        grant = (await session.exec(
            select(AccessGrant).where(col(AccessGrant.id) == grant_id))).one()
        grant.ends_at = datetime.now(UTC) - TERM_ENDED_AGO
        grant.status = mark
        session.add(grant)
        await session.commit()


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
            self, restore_client, _db_transaction, scripted_app_store_notifications,
            pinned_evaluation_instant):
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
        # The proof and the instant it was checked at: the check is made with the request's one
        # captured instant, so a call site reading the clock again records a different value here.
        assert scripted_app_store_notifications.restore_calls == [(RESTORE_PROOF,
                                                                  pinned_evaluation_instant)]

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
class TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach:
    """CR-02, CR-25: the term is read from whatever decided the status -- the grant the row's own
    webhook wrote where one records it, and the client's proof where nothing else does."""

    async def test_a_stored_grace_row_and_an_apple_proof_attaches_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """An Apple proof carries no grace window, so a grace row with no grant recording one
        has no term to attach from either source."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-grace-row-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID, status="grace_period")
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        # The grant count is what carries the truth the report names: the term is the only end this
        # path could write, so a grant attached here would carry a NULL end -- paid access no store
        # event can ever end. The caller holds none before, so the count is the whole claim.
        assert await _four_counts(_db_transaction, user.id, external_id) == before

    async def test_an_active_proof_carrying_no_expiry_attaches_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The same absent term on the other arm: an active proof may carry no expiry either."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-no-expiry-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(
            replace(_proof(external_id), expires_at=None))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _four_counts(_db_transaction, user.id, external_id) == before

    async def test_a_stale_proof_against_an_active_row_attaches_nothing_and_frees_no_slot(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The account's one slot is held by a live grant, and a dead term may not take it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        await seed_grant(_db_transaction, user_id=user.id)
        external_id = f"e2e-stale-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        before = await _account_snapshot(_db_transaction, user.id)
        scripted_app_store_notifications.script_restore(
            _proof(external_id, expires_at=datetime.now(UTC) - TERM_ENDED_AGO))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _account_snapshot(_db_transaction, user.id) == before

    async def test_a_term_ending_at_the_captured_instant_is_not_open(
            self, restore_client, _db_transaction, scripted_app_store_notifications,
            pinned_evaluation_instant):
        """The closed side of the boundary at the instant itself: the predicate is `<=`, so a term
        ending exactly when the request was evaluated is over. Only a pinned instant names that
        equality, because a live clock never lands on it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-boundary-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(
            _proof(external_id, expires_at=pinned_evaluation_instant))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _four_counts(_db_transaction, user.id, external_id) == before

    async def test_an_open_term_still_attaches_the_grant_control(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The control: the three refusals above must not pass because the write path stopped."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-open-term-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        proof = _proof(external_id)
        scripted_app_store_notifications.script_restore(proof)

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        grants = await _grants_of(_db_transaction, user.id)
        assert [grant.status for grant in grants] == [AccessGrantStatus.active]
        assert grants[0].ends_at == proof.expires_at

    async def test_a_stored_grace_row_and_a_play_proof_carrying_its_window_still_attaches(
            self, restore_client, _db_transaction, real_google_play_seam):
        """The second control, on the other store: Play reports the grace window this row needs."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        purchase_token = f"e2e-play-grace-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=purchase_token, user_id=user.id,
                                provider=PurchaseProvider.google_play, tier_id=PAID_TIER_ID,
                                status="grace_period")
        window_ends = datetime.now(UTC) + TERM_REMAINING
        real_google_play_seam.body = play_subscription_body(
            subscriptionState=GRACE_STATE,
            lineItems=[{"productId": GOOGLE_PRODUCT_ID, "expiryTime": window_ends.isoformat()}])

        answered = await _restore(restore_client, provider="google_play",
                                  restore_proof=purchase_token)

        assert answered.status_code == 200, answered.text
        grants = await _grants_of(_db_transaction, user.id)
        assert [grant.status for grant in grants] == [AccessGrantStatus.active]
        assert grants[0].ends_at == window_ends

    @pytest.mark.parametrize(("mark", "carried"),
                             [(AccessGrantStatus.active, 4), (AccessGrantStatus.expired, 0)])
    async def test_a_closed_recorded_term_never_outranks_a_current_proof_under_either_mark(
            self, restore_client, _db_transaction, scripted_app_store_notifications, mark, carried):
        """CR-01: the recorded term answers only while it is open. Between a term ending and the
        store's renewal notification arriving the grant still reads active with a closed term, and
        the subscriber must not be refused for the mark a webhook has not written yet."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-closed-recorded-term-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))
        assert (await _restore(restore_client)).status_code == 200
        first = (await _grants_of(_db_transaction, user.id))[0]
        await _spend(_db_transaction, first.id, 4)
        await _close_term(_db_transaction, first.id, mark=mark)

        renewed = _proof(external_id)
        scripted_app_store_notifications.script_restore(renewed)
        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        assert answered.json()["entitlement"]["tier_id"] == PAID_TIER_ID
        live = [grant for grant in await _grants_of(_db_transaction, user.id)
                if grant.status is AccessGrantStatus.active]
        assert [grant.ends_at for grant in live] == [renewed.expires_at]
        # The still-active row is superseded, so this month's count follows it to the new term;
        # a row a webhook already expired is outside the locked set and carries nothing.
        assert (await _usage_of(_db_transaction, live[0].id)).monthly_used == carried

    async def test_a_dead_proof_refuses_where_nothing_records_the_term_and_replays_where_one_does(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """One dead proof, both answers, the recorded term the only difference: a proof's own
        expiry is not an entitlement input, so it refuses where nothing else records a term and
        replays where the account's own live grant records one."""
        # `10-restore-subscription.md:65` confirms entitlement "under locked state (statuses
        # exactly `active` and `grace_period` ...)" and names no proof date, and an Apple original
        # transaction states the first term's expiry for a subscription now on its tenth -- so the
        # dead proof below is a currently-subscribed caller, and `:77`(a) makes the repeat
        # "idempotent success (no owner change, grant keeps its id, usage row stays on the same
        # `grant_id` ...)": the same writes-nothing guarantee the refusal carries, under the other
        # status code. CR-02 survives as the first half; CR-25 is the second.
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        unrecorded = f"e2e-dead-unrecorded-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=unrecorded, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(
            _proof(unrecorded, expires_at=datetime.now(UTC) - TERM_ENDED_AGO))

        refused = await _restore(restore_client)

        # Nothing recorded this subscription's term, so the proof was the only source of one and
        # a dead one attaches nothing: the account is left holding no grant at all.
        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _row_counts(_db_transaction, user.id) == (0, 0)

        recorded = f"e2e-dead-repeat-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=recorded, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(recorded))
        assert (await _restore(restore_client)).status_code == 200
        granted = (await _grants_of(_db_transaction, user.id))[0]
        await _spend(_db_transaction, granted.id, 9)
        before = await _account_snapshot(_db_transaction, user.id)

        # The same dead proof, now against the subscription whose own live grant records the term.
        scripted_app_store_notifications.script_restore(
            _proof(recorded, expires_at=datetime.now(UTC) - TERM_ENDED_AGO))
        replayed = await _restore(restore_client)

        # The slot the grant holds is neither taken nor refreshed: no new row, no new term, and
        # the counter still carries what the account spent under the grant it already had.
        assert replayed.status_code == 200, replayed.text
        assert await _account_snapshot(_db_transaction, user.id) == before
        assert [grant.id for grant in await _grants_of(_db_transaction, user.id)] == [granted.id]
        assert (await _usage_of(_db_transaction, granted.id)).monthly_used == 9


@pytest.mark.asyncio(loop_scope="module")
class TestTheTwoRefusalsOfTheRestoreNotFoundFamily:
    """T-45-05: three causes, one body. The adoption case above is the control for every setup."""

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

    async def test_the_three_arms_of_the_family_answer_the_same_bytes(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The third arm joins the family, so the surface still tells no caller which check refused."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        other, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=OTHER_SUBJECT,
                                       provider=IdentityProvider.google)
        unentitled = f"e2e-arm-unentitled-{uuid4()}"
        no_term = f"e2e-arm-no-term-{uuid4()}"
        mismatched = f"e2e-arm-mismatch-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=unentitled, user_id=None,
                                tier_id=PAID_TIER_ID, status="expired")
        # Entitled, so this arm reaches the term check: an Apple proof carries no grace window.
        await seed_subscription(_db_transaction, external_id=no_term, user_id=None,
                                tier_id=PAID_TIER_ID, status="grace_period")
        await seed_subscription(_db_transaction, external_id=mismatched, user_id=None,
                                tier_id=PAID_TIER_ID)
        await _bind_token(_db_transaction, user_id=other.id, identity_value=OTHER_ACCOUNTS_TOKEN)

        answered = []
        for proof in (_proof(unentitled),
                      _proof(no_term),
                      _proof(mismatched, attribution_token=OTHER_ACCOUNTS_TOKEN)):
            scripted_app_store_notifications.script_restore(proof)
            answered.append(await _restore(restore_client))

        # Raw bytes and not parsed JSON: a more helpful field on one body fails here.
        arms = [(answer.status_code, answer.content) for answer in answered]
        assert arms[0] == arms[1] == arms[2]
        assert arms[0] == (404, RESTORE_NOT_FOUND_BODY)
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

    async def test_a_store_name_at_the_bound_still_reaches_the_gates_own_refusal(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The control: a bound one character too low would refuse this name before the gate."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="z" * MAX_PROVIDER_LENGTH,
                                 restore_proof=RESTORE_PROOF)

        assert refused.status_code == 403
        assert refused.text == REFUSED_BODY

    async def test_a_store_name_past_the_bound_is_the_frameworks_own_refusal(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """WR-02: the refusal log names this value, so the framework bounds it before the handler."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="z" * (MAX_PROVIDER_LENGTH + 1),
                                 restore_proof=RESTORE_PROOF)

        assert refused.status_code == 422
        assert scripted_app_store_notifications.restore_calls == []

    async def test_a_proof_at_the_bound_still_reaches_the_store_check(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The control: a bound one character too low would refuse a legitimate artifact."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        scripted_app_store_notifications.script_restore(
            ProofRejected(stage="VERIFICATION_FAILURE"))

        refused = await _restore(restore_client, provider="apple",
                                 restore_proof="z" * MAX_PROOF_LENGTH)

        assert refused.status_code == 403
        assert refused.content == PROOF_REJECTED_BODY
        assert len(scripted_app_store_notifications.restore_calls) == 1

    async def test_a_proof_past_the_bound_is_refused_before_any_store_call(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """WR-02: an unbounded artifact reaches Apple's decoder, so the bound refuses it first."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        scripted_app_store_notifications.script_restore(
            ProofRejected(stage="VERIFICATION_FAILURE"))

        refused = await _restore(restore_client, provider="apple",
                                 restore_proof="z" * (MAX_PROOF_LENGTH + 1))

        assert refused.status_code == 422
        assert scripted_app_store_notifications.restore_calls == []


@pytest.mark.asyncio(loop_scope="module")
class TestTheSameAccountGooglePlayRestore:
    """The second store on the same path: the purchase token is both the proof and the external id."""

    async def test_a_live_purchase_token_attaches_the_paid_grant_and_the_body_reports_it(
            self, restore_client, _db_transaction, scripted_google_play,
            pinned_evaluation_instant):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        purchase_token = f"e2e-play-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=purchase_token, user_id=user.id,
                                provider=PurchaseProvider.google_play, tier_id=PAID_TIER_ID)
        scripted_google_play.script_restore(_play_proof(purchase_token))

        answered = await _restore(restore_client, provider="google_play",
                                  restore_proof=purchase_token)

        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["entitlement"]["type"] == "subscription"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == PAID_TIER_ID
        assert answered.headers["Cache-Control"] == "no-store"
        # WR-81: the application name is the configured one, the proof itself is the token the read
        # was made with, and the instant is the request's own. A read made at a freshly-taken clock
        # reading records a value that is not the pinned one, and a read made under any other
        # application name is answered 403 by Google for every paying Android customer.
        assert [(call["package_name"], call["purchase_token"], call["evaluated_at"]) for call in
                scripted_google_play.restore_calls] == [(GOOGLE_PACKAGE_NAME, purchase_token,
                                                         pinned_evaluation_instant)]

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
            real_google_play_seam, refusal_records):
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
        # The distinguishing detail exists, and only in the log: `stage` reaches no response, so
        # without this the four causes are one cause driven four times and the class proves nothing.
        assert [(event, fields["stage"]) for event, fields in refusal_records.entries] == [
            *(("proof_rejected", stage) for stage in APPLE_REJECTION_STAGES),
            ("proof_rejected", PLAY_REJECTION_STAGE)]
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


async def _sync_as(client, subject: str) -> dict:
    """What `/auth/sync` reports for one account, read back through the real route."""
    answered = await client.post("/auth/sync", headers=_auth(subject))
    assert answered.status_code == 200, answered.text
    return answered.json()


def _this_month() -> date:
    """The first day of the current UTC month, which is what a move writes to the row."""
    return datetime.now(UTC).date().replace(day=1)


def _earlier_month() -> date:
    """The first day of the month before this one, which the cap must let through."""
    return (_this_month() - timedelta(days=1)).replace(day=1)


async def _account_snapshot(factory, user_id) -> list[tuple]:
    """Each grant of `user_id` with the fields a move rewrites, and its own usage counter."""
    grants = await _grants_of(factory, user_id)
    return [(grant.id, grant.status, grant.ends_at, grant.tier_id,
             (await _usage_of(factory, grant.id)).monthly_used) for grant in grants]


async def _subscription_snapshot(factory, external_id) -> tuple:
    """The columns of the canonical row a move rewrites, read on a session of its own."""
    row = await _subscription_row(factory, external_id)
    return (row.user_id, row.status, row.last_cross_account_transfer_month,
            row.updated_at, row.restore_bound_user_id)


async def _held_by_the_old_owner(client, factory, notifications, *, external_id,
                                 transfer_month: date | None = None):
    """Seed both accounts and let the old owner restore first, so its grant is one the route wrote."""
    # The old owner is `OTHER_SUBJECT` throughout; the caller under test is always `SUBJECT`.
    old_owner, _ = await seed_identity(factory, issuer=TEST_ISSUER, subject=OTHER_SUBJECT,
                                       provider=IdentityProvider.google)
    caller, _ = await seed_identity(factory, issuer=TEST_ISSUER, subject=SUBJECT,
                                    provider=IdentityProvider.google)
    await seed_subscription(factory, external_id=external_id, user_id=old_owner.id,
                            tier_id=PAID_TIER_ID,
                            last_cross_account_transfer_month=transfer_month)
    # One proof, returned for re-presentation: the store reports one term for one subscription,
    # so the account it moves to is shown the same expiry the old owner was shown.
    proof = _proof(external_id)
    notifications.script_restore(proof)
    answered = await _restore(client, OTHER_SUBJECT)
    assert answered.status_code == 200, answered.text
    return old_owner, caller, proof


@pytest.mark.asyncio(loop_scope="module")
class TestTheSubscriptionMovesToTheCaller:
    """D-10's third outcome: the subscription leaves the account holding it and joins the caller's."""

    async def test_the_owner_the_grants_and_the_transfer_month_all_move_together(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        external_id = f"e2e-move-{uuid4()}"
        old_owner, caller, proof = await _held_by_the_old_owner(
            restore_client, _db_transaction, scripted_app_store_notifications,
            external_id=external_id)
        scripted_app_store_notifications.script_restore(proof)

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        assert answered.json()["entitlement"]["type"] == "subscription"
        assert answered.json()["entitlement"]["tier_id"] == PAID_TIER_ID
        moved = await _subscription_row(_db_transaction, external_id)
        assert moved.user_id == caller.id
        assert moved.last_cross_account_transfer_month == _this_month()
        # D-10 replaces this column; nothing on any branch writes it.
        assert moved.restore_bound_user_id is None
        # The old owner loses access at that moment: no grant of theirs is still active.
        assert [grant.status for grant in await _grants_of(_db_transaction, old_owner.id)] == [
            AccessGrantStatus.expired]
        held = await _grants_of(_db_transaction, caller.id)
        assert len(held) == 1
        assert held[0].status is AccessGrantStatus.active
        assert held[0].source is AccessGrantSource.subscription
        assert held[0].subscription_id == moved.id
        assert (await _usage_of(_db_transaction, held[0].id)).monthly_used == 0

    async def test_the_account_it_moved_away_from_reads_no_entitlement_at_all(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """A5 as a measurement: the loss of access is read back through `/auth/sync`, not derived."""
        external_id = f"e2e-moved-from-{uuid4()}"
        _, _, proof = await _held_by_the_old_owner(
            restore_client, _db_transaction, scripted_app_store_notifications,
            external_id=external_id)
        held = await _sync_as(restore_client, OTHER_SUBJECT)
        assert held["entitlement"]["type"] == "subscription"
        scripted_app_store_notifications.script_restore(proof)

        assert (await _restore(restore_client)).status_code == 200

        lost = await _sync_as(restore_client, OTHER_SUBJECT)
        assert lost["entitlement"]["type"] == "none"
        assert lost["entitlement"]["status"] == "none"
        assert lost["entitlement"]["tier_id"] is None

    async def test_a_stored_month_earlier_than_this_one_is_allowed_and_moves(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """The boundary: the cap is an equality on the month, so last month spends nothing."""
        external_id = f"e2e-earlier-month-{uuid4()}"
        _, caller, proof = await _held_by_the_old_owner(
            restore_client, _db_transaction, scripted_app_store_notifications,
            external_id=external_id, transfer_month=_earlier_month())
        scripted_app_store_notifications.script_restore(proof)

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        moved = await _subscription_row(_db_transaction, external_id)
        assert moved.user_id == caller.id
        assert moved.last_cross_account_transfer_month == _this_month()
        assert moved.restore_bound_user_id is None


@pytest.mark.asyncio(loop_scope="module")
class TestTheSecondMoveOfOneMonthIsRefused:
    """T-45-01 and T-45-10: one stolen proof reaches at most two accounts in a UTC month."""

    async def test_a_stored_month_equal_to_this_one_answers_the_conflict_and_writes_nothing(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        external_id = f"e2e-capped-{uuid4()}"
        old_owner, caller, proof = await _held_by_the_old_owner(
            restore_client, _db_transaction, scripted_app_store_notifications,
            external_id=external_id, transfer_month=_this_month())
        before = (await _account_snapshot(_db_transaction, old_owner.id),
                  await _account_snapshot(_db_transaction, caller.id),
                  await _subscription_snapshot(_db_transaction, external_id))
        scripted_app_store_notifications.script_restore(proof)

        refused = await _restore(restore_client)

        assert refused.status_code == 409
        assert refused.content == TRANSFER_REJECTED_BODY
        assert (await _account_snapshot(_db_transaction, old_owner.id),
                await _account_snapshot(_db_transaction, caller.id),
                await _subscription_snapshot(_db_transaction, external_id)) == before
        assert (await _subscription_row(_db_transaction,
                                        external_id)).restore_bound_user_id is None


@pytest.mark.asyncio(loop_scope="module")
class TestTheBranchesThatSpendNoneOfTheCap:
    """D-10: only a move counts, so adoption and a same-account repeat leave the column NULL."""

    async def test_adoption_leaves_the_transfer_month_unwritten(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-adopt-no-month-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=None,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        assert (await _restore(restore_client)).status_code == 200

        adopted = await _subscription_row(_db_transaction, external_id)
        assert adopted.user_id == user.id
        assert adopted.last_cross_account_transfer_month is None
        assert adopted.restore_bound_user_id is None

    async def test_a_same_account_repeat_leaves_the_transfer_month_unwritten(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-repeat-no-month-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        proof = _proof(external_id)
        for _ in range(2):
            scripted_app_store_notifications.script_restore(proof)
            assert (await _restore(restore_client)).status_code == 200

        repeated = await _subscription_row(_db_transaction, external_id)
        assert repeated.last_cross_account_transfer_month is None
        assert repeated.restore_bound_user_id is None
