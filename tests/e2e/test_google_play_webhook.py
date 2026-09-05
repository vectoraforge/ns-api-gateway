"""The Google Play callback, end to end through the real seam classes against a real database.
The push token is signed for real against the fake JWKS key, and the Play read is scripted at the transport."""
import ast
import base64
import inspect
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlmodel import col, select
from unit.conftest import make_token
from unit.test_google_play_notifications import FOREIGN_PRIVATE_KEY_PEM
from unit.test_jwks_offload import KNOWN_KID

from e2e.conftest import (
    GOOGLE_PACKAGE_NAME,
    GOOGLE_PRODUCT_ID,
    GOOGLE_PUSH_AUDIENCE,
    GOOGLE_PUSH_ISSUER,
    GOOGLE_PUSH_SERVICE_ACCOUNT,
    play_subscription_body,
)
from nativespeaker.api.app.dependencies import verify_google_play_notification
from nativespeaker.api.auth import google_play
from nativespeaker.api.auth.jwt_verifier import BoundedReason
from nativespeaker.api.errors import AttributionConflict, InternalError, UnmappedStoreProduct
from nativespeaker.api.tables import (
    PurchaseProvider,
    StorePurchase,
    StorePurchaseToken,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    User,
)

pytestmark = pytest.mark.e2e

PATH = "/webhooks/google-play/rtdn"

# The tier the migration seeds for a paid subscription, and the one the scripted product maps to.
PAID_TIER_ID = "paid"

# The one body every refusal answers, compared by equality so a richer field fails here.
REJECTED = {"code": "auth_required"}

# The same body as raw bytes, so the refusals are compared on the wire and not after parsing.
REJECTED_BODY = b'{"code":"auth_required"}'

# The 503 an incomplete configuration answers, and the 500 every failed read shares.
UNAVAILABLE = {"code": "verification_temporarily_unavailable"}
INTERNAL = {"code": "internal_error"}

# One RTDN instant and one notification type, so the composite replay key is known to the case.
EVENT_TIME_MILLIS = 1789000000000
SUBSCRIPTION_PURCHASED = 4

# The Pub/Sub subscription name every push body carries, which this route never reads.
PUSH_SUBSCRIPTION = "projects/nativespeaker-test/subscriptions/rtdn-push"

# A push minted for another service account, another issuer's push, and another deployment's app.
OTHER_SERVICE_ACCOUNT = "someone-else@another-project.iam.gserviceaccount.com"
OTHER_ISSUER = "https://accounts.example.com"
OTHER_AUDIENCE = "https://api.example.com/webhooks/somewhere-else"
FOREIGN_PACKAGE_NAME = "com.example.another-app"

# The Play product the configured map has no line for.
UNMAPPED_PRODUCT_ID = "nativespeaker.subscription.unmapped"

# One obviously synthetic attribution token, and a second that disagrees with it.
ATTRIBUTION_TOKEN = "a-synthetic-google-attribution-token"
OTHER_ATTRIBUTION_TOKEN = "a-different-synthetic-google-attribution-token"

# The Google purchase token, which D-10 persists as `external_id` and which no log may carry.
PURCHASE_TOKEN = "a-synthetic-google-purchase-token"


@pytest_asyncio.fixture(loop_scope="module")
async def webhook_client(_app_lifespan):
    """A client over the real started app that sends the push token as its own Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _push_token(**overrides) -> str:
    """One RS256 OIDC token in the shape Cloud Pub/Sub sends, signed by the fake JWKS key."""
    fields = {"sub": "111111111111111111111",
              "aud": GOOGLE_PUSH_AUDIENCE,
              "iss": GOOGLE_PUSH_ISSUER,
              "extra_claims": {"email": GOOGLE_PUSH_SERVICE_ACCOUNT},
              "headers": {"kid": KNOWN_KID}}
    return make_token(**(fields | overrides))


def _pushed(data: str) -> dict:
    """One Pub/Sub push envelope around whatever `data` a case wants delivered."""
    return {"message": {"messageId": f"message-{uuid4()}", "data": data},
            "subscription": PUSH_SUBSCRIPTION}


def _encoded(notification: dict) -> str:
    """One `DeveloperNotification` as the base64 Google publishes it in `message.data`."""
    return base64.b64encode(json.dumps(notification).encode()).decode()


def _push_body(purchase_token: str, *, package_name: str = GOOGLE_PACKAGE_NAME,
               event_time_millis: int = EVENT_TIME_MILLIS) -> dict:
    """One Pub/Sub push body whose `data` is the base64 `DeveloperNotification` Google publishes."""
    return _pushed(_encoded({"version": "1.0",
                             "packageName": package_name,
                             "eventTimeMillis": str(event_time_millis),
                             "subscriptionNotification": {
                                 "version": "1.0",
                                 "notificationType": SUBSCRIPTION_PURCHASED,
                                 "purchaseToken": purchase_token}}))


def _undecodable_push_body() -> dict:
    """D-04: a verified push whose `message.data` is not decodable base64 and never will be."""
    return _pushed("this-is-not-base64-$$$$")


def _refund_review_push_body() -> dict:
    """D-05: a verified push carrying the one body a closed three-member list would let through."""
    return _pushed(_encoded({"version": "1.0",
                             "packageName": GOOGLE_PACKAGE_NAME,
                             "eventTimeMillis": str(EVENT_TIME_MILLIS),
                             "pendingRefundReviewNotification": {}}))


def _replay_key(purchase_token: str) -> str:
    """The composite key the Google path derives from the RTDN itself, spelled out here."""
    return f"google_play:{purchase_token}:{EVENT_TIME_MILLIS}:{SUBSCRIPTION_PURCHASED}"


async def _subscriptions_of(factory, external_id: str) -> list[Subscription]:
    """Every canonical row for one lifecycle key; the unique index allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(Subscription).where(col(Subscription.external_id) == external_id))).all())


async def _events_of(factory, notification_uuid: str) -> list[SubscriptionEvent]:
    """Every event row carrying one notification key; the UNIQUE column allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(SubscriptionEvent)
            .where(col(SubscriptionEvent.notification_uuid) == notification_uuid))).all())


async def _purchases_of(factory, external_id: str) -> list[StorePurchase]:
    """Every purchase row for one lifecycle key; the UNIQUE constraint allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(StorePurchase).where(col(StorePurchase.external_id) == external_id))).all())


async def _counts(factory) -> tuple[int, ...]:
    """Row counts of the three tables one delivery writes, so a case naming no key can say "nothing"."""
    counted = []
    async with factory() as session:
        for model in (Subscription, StorePurchase, SubscriptionEvent):
            counted.append((await session.exec(select(func.count()).select_from(model))).one())
    return tuple(counted)


async def _seed_store_token(factory, value: str) -> None:
    """One user holding one Google store token, so a delivery carrying it resolves a real owner."""
    async with factory() as session:
        user = User()
        session.add(user)
        await session.flush()
        session.add(StorePurchaseToken(user_id=user.id, provider=PurchaseProvider.google_play,
                                       identity_value=value, created_at=datetime.now(UTC)))
        await session.commit()


# Each way this route refuses, as the push it refuses and the stage that refusal logs.
# A `None` token means no Authorization header at all, which is its own arm.
REFUSALS = (
    (None, GOOGLE_PACKAGE_NAME, "push_credential_absent"),
    ({"private_key": FOREIGN_PRIVATE_KEY_PEM}, GOOGLE_PACKAGE_NAME, "bad_signature"),
    ({"extra_claims": {"email": OTHER_SERVICE_ACCOUNT}}, GOOGLE_PACKAGE_NAME, "bad_signature"),
    ({"email_verified": False}, GOOGLE_PACKAGE_NAME, "bad_signature"),
    ({"aud": OTHER_AUDIENCE}, GOOGLE_PACKAGE_NAME, "audience_mismatch"),
    ({"iss": OTHER_ISSUER}, GOOGLE_PACKAGE_NAME, "issuer_mismatch"),
    ({"exp": time.time() - 3600}, GOOGLE_PACKAGE_NAME, "expired"),
    ({"sub": ""}, GOOGLE_PACKAGE_NAME, "empty_subject"),
    ({}, FOREIGN_PACKAGE_NAME, "package_name_mismatch"),
)
REFUSAL_IDS = ["no-credential", "signature", "email", "email-verified", "aud", "iss",
               "expired", "empty-sub", "package-name"]

# The two places on this path that raise the refusal, read as source so a third one arrives here.
_REFUSAL_SOURCES = (inspect.getsource(verify_google_play_notification),
                    inspect.getsource(google_play))

# What a `stage=` that is not a literal leaves behind: the verifier's own bounded reason.
_COMPUTED = "<computed at the raise site>"


def _raised_refusal_stages() -> set[str]:
    """Every `NotificationRejected(stage=...)` the Google path raises, read from its own source."""
    stages = set()
    for source in _REFUSAL_SOURCES:
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "NotificationRejected"):
                continue
            for keyword in node.keywords:
                if keyword.arg == "stage":
                    stages.add(keyword.value.value
                               if isinstance(keyword.value, ast.Constant) else _COMPUTED)
    return stages


# The three modules that write a record on this route: the error handler, the Google seam, the service.
_LOGGERS = ("nativespeaker.api.app.error_handlers.logger",
            "nativespeaker.api.auth.google_play.logger",
            "nativespeaker.api.services.subscriptions.logger")


class _LogSpy:
    """A recording spy on a module's own logger, so "which record, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.entries.append((event, fields))


def _spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> _LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing."""
    spy = _LogSpy()
    for target in targets:
        for level in levels:
            monkeypatch.setattr(f"{target}.{level}", spy.record)
    return spy


@pytest.fixture
def refusal_records(monkeypatch) -> _LogSpy:
    """Every WARNING record the handler writes, which is the level a refusal is recorded at."""
    return _spy_on(monkeypatch, (_LOGGERS[0],), ("warning",))


@pytest.fixture
def error_records(monkeypatch) -> _LogSpy:
    """Every ERROR record any of the three modules writes, and nothing else."""
    return _spy_on(monkeypatch, _LOGGERS, ("error",))


@pytest.fixture
def info_records(monkeypatch) -> _LogSpy:
    """Every INFO record the Google seam or the service writes, and nothing else."""
    return _spy_on(monkeypatch, _LOGGERS[1:], ("info",))


@pytest.fixture
def captured_records(monkeypatch) -> _LogSpy:
    """One list holding every record any of the three modules writes, for the hygiene walk."""
    return _spy_on(monkeypatch, _LOGGERS, ("info", "warning", "error"))


@pytest.mark.asyncio(loop_scope="module")
class TestOneVerifiedPushReachesACommittedRow:
    """The tracer: one signed push, one live Play read, one canonical row, and a 200 after the commit."""

    async def test_a_verified_push_writes_the_subscription_row(
            self, webhook_client, real_google_play_seam, _db_transaction):
        purchase_token = f"purchase-token-{uuid4()}"

        response = await webhook_client.post(PATH, json=_push_body(purchase_token),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        subscriptions = await _subscriptions_of(_db_transaction, purchase_token)
        assert len(subscriptions) == 1
        assert subscriptions[0].provider is PurchaseProvider.google_play
        # D-10: the purchase token is the only handle `subscriptionsv2.get` accepts.
        assert subscriptions[0].external_id == purchase_token
        assert subscriptions[0].status is SubscriptionStatus.active
        assert subscriptions[0].tier_id == PAID_TIER_ID

    async def test_the_delivery_records_exactly_one_event_under_the_composite_key(
            self, webhook_client, real_google_play_seam, _db_transaction):
        """OQ-4: the key is derived from the RTDN, so a redelivery of it repeats the same key."""
        purchase_token = f"purchase-token-{uuid4()}"

        response = await webhook_client.post(PATH, json=_push_body(purchase_token),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        events = await _events_of(_db_transaction, _replay_key(purchase_token))
        assert len(events) == 1
        assert events[0].event_type == str(SUBSCRIPTION_PURCHASED)
        assert events[0].new_tier_id == PAID_TIER_ID

    async def test_the_play_read_asked_for_the_configured_package_and_this_token(
            self, webhook_client, real_google_play_seam, _db_transaction):
        """The control: a scripted transport that was never called would pass every row assertion above."""
        purchase_token = f"purchase-token-{uuid4()}"

        await webhook_client.post(PATH, json=_push_body(purchase_token),
                                  headers={"Authorization": f"Bearer {_push_token()}"})

        assert len(real_google_play_seam.requests) == 1
        asked = str(real_google_play_seam.requests[0].url)
        assert GOOGLE_PACKAGE_NAME in asked and purchase_token in asked
        assert GOOGLE_PRODUCT_ID in json.dumps(real_google_play_seam.body)


@pytest.mark.asyncio(loop_scope="module")
class TestAnIncompleteDeploymentStillRegistersTheRoute:
    """D-14, D-18. The route set is identical in every environment: present and answering 503, never absent."""

    async def test_an_unconfigured_deployment_answers_503(
            self, webhook_client, unconfigured_google_play):
        response = await webhook_client.post(PATH, json=_push_body("a-purchase-token"),
                                             headers={"Authorization": "Bearer a-token"})

        assert response.status_code == 503
        assert response.json() == UNAVAILABLE

    async def test_both_callback_routes_are_registered_while_the_seam_is_unconfigured(
            self, _app_lifespan, webhook_client, unconfigured_google_play):
        response = await webhook_client.post(PATH, json=_push_body("a-purchase-token"),
                                             headers={"Authorization": "Bearer a-token"})

        assert response.status_code == 503
        registered = {route.path for route in _app_lifespan.routes}
        assert {"/webhooks/app-store", PATH} <= registered


@pytest.mark.asyncio(loop_scope="module")
class TestEveryRefusalAnswersTheOneBody:
    """T-44-25: one class, one body, so the answer tells a caller nothing about which check refused it."""

    @pytest.mark.parametrize(("overrides", "package_name", "stage"), REFUSALS, ids=REFUSAL_IDS)
    async def test_each_refusal_answers_the_same_401_body(
            self, webhook_client, real_google_play_seam, refusal_records,
            overrides, package_name, stage):
        headers = ({} if overrides is None
                   else {"Authorization": f"Bearer {_push_token(**overrides)}"})

        response = await webhook_client.post(
            PATH, json=_push_body(PURCHASE_TOKEN, package_name=package_name), headers=headers)

        assert response.status_code == 401
        assert response.json() == REJECTED
        # On the wire, not after parsing: a field added later fails here rather than becoming an oracle.
        assert response.content == REJECTED_BODY
        # The distinguishing detail exists, and it exists only in the log the operator reads.
        assert [(event, fields["stage"]) for event, fields in refusal_records.entries] == [
            ("notification_rejected", stage)]
        assert real_google_play_seam.requests == []

    async def test_every_reachable_arm_is_covered_by_one_parameter(self):
        """The control: a narrowed tuple would leave an arm untested while every case above passed."""
        raised = _raised_refusal_stages()
        # The one computed stage is the verifier's bounded reason, so it stands for all five members.
        assert _COMPUTED in raised
        reachable = (raised - {_COMPUTED}) | {str(reason) for reason in BoundedReason}
        assert {stage for _overrides, _package, stage in REFUSALS} == reachable

    async def test_a_refused_push_writes_nothing(
            self, webhook_client, real_google_play_seam, _db_transaction):
        before = await _counts(_db_transaction)

        response = await webhook_client.post(
            PATH, json=_push_body(PURCHASE_TOKEN),
            headers={"Authorization": f"Bearer {_push_token(iss=OTHER_ISSUER)}"})

        assert response.status_code == 401
        assert await _counts(_db_transaction) == before
        assert await _subscriptions_of(_db_transaction, PURCHASE_TOKEN) == []

    async def test_a_valid_firebase_token_does_not_change_the_refusal(
            self, webhook_client, real_google_play_seam, stub_verifier):
        """This route reads only its own credential: the application's identity gate buys nothing here."""
        firebase_bearer = make_token(sub="a-firebase-subject")
        claims, _reason = stub_verifier.verify(firebase_bearer)
        # The control: a token the application itself would not admit proves nothing about leakage.
        assert claims is not None

        response = await webhook_client.post(PATH, json=_push_body(PURCHASE_TOKEN),
                                             headers={"Authorization": f"Bearer {firebase_bearer}"})

        assert response.status_code == 401
        assert response.content == REJECTED_BODY


@pytest.mark.asyncio(loop_scope="module")
class TestTheTwoArmsThatAnswerWithoutWriting:
    """D-04 and D-05: the payloads a retry can never fix, acknowledged rather than redelivered."""

    async def test_an_undecodable_body_answers_200_and_records_one_error(
            self, webhook_client, real_google_play_seam, _db_transaction, error_records):
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json=_undecodable_push_body(),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        assert [event for event, _fields in error_records.entries] == [
            "google_play_message_undecodable"]
        assert await _counts(_db_transaction) == before
        assert real_google_play_seam.requests == []

    async def test_a_body_this_route_does_not_act_on_answers_200_and_makes_no_play_call(
            self, webhook_client, real_google_play_seam, _db_transaction, info_records):
        """`pendingRefundReviewNotification` is the body D-05 does not name, so a closed list drops it."""
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json=_refund_review_push_body(),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        assert len(info_records.entries) == 1
        event, fields = info_records.entries[0]
        assert event == "google_play_notification_ignored"
        assert fields["bodies"] == ["pendingRefundReviewNotification"]
        assert await _counts(_db_transaction) == before
        # The point of the arm: no purchase token exists in this body to call Play with.
        assert real_google_play_seam.requests == []


# The three failures of the read that each answer the shared 500, which is what makes Pub/Sub redeliver.
PLAY_FAILURES = (
    InternalError(),
    UnmappedStoreProduct(PurchaseProvider.google_play, UNMAPPED_PRODUCT_ID),
    AttributionConflict(PurchaseProvider.google_play, PURCHASE_TOKEN),
)
PLAY_FAILURE_IDS = ["failed-play-call", "unmapped-product", "attribution-conflict"]


@pytest.mark.asyncio(loop_scope="module")
class TestEveryFailedReadAnswersTheShared500:
    """D-20: 500 is the answer that makes Pub/Sub redeliver, and nothing partial is left behind."""

    @pytest.mark.parametrize("failure", PLAY_FAILURES, ids=PLAY_FAILURE_IDS)
    async def test_each_failure_answers_500_and_writes_nothing(
            self, webhook_client, scripted_google_play, _db_transaction, failure):
        scripted_google_play.script(failure)
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json=_push_body(PURCHASE_TOKEN),
                                             headers={"Authorization": "Bearer any-push-token"})

        assert response.status_code == 500
        assert response.json() == INTERNAL
        assert await _counts(_db_transaction) == before
        assert await _subscriptions_of(_db_transaction, PURCHASE_TOKEN) == []
        assert await _events_of(_db_transaction, _replay_key(PURCHASE_TOKEN)) == []

    async def test_the_scripted_read_was_asked_for_this_delivery(
            self, webhook_client, scripted_google_play, _db_transaction):
        """The control: a fake that was never called would pass every "nothing written" assertion."""
        scripted_google_play.script(InternalError())

        await webhook_client.post(PATH, json=_push_body(PURCHASE_TOKEN),
                                  headers={"Authorization": "Bearer any-push-token"})

        assert len(scripted_google_play.calls) == 1
        assert scripted_google_play.calls[0]["purchase_token"] == PURCHASE_TOKEN
        assert scripted_google_play.calls[0]["notification_uuid"] == _replay_key(PURCHASE_TOKEN)


@pytest.mark.asyncio(loop_scope="module")
class TestNoRecordCarriesASensitiveValue:
    """T-44-26: the push token, the envelope, the attribution token and the purchase token reach no record."""

    async def _drive_every_recording_arm(self, client, seam, factory) -> tuple[str, dict]:
        """One delivery per arm that writes a record, all through the real seam; return the push and body."""
        await _seed_store_token(factory, ATTRIBUTION_TOKEN)
        verified = _push_token()
        body = _push_body(PURCHASE_TOKEN)
        headers = {"Authorization": f"Bearer {verified}"}

        # A refused push, then the two bodies that answer 200 having written nothing.
        await client.post(PATH, json=body,
                          headers={"Authorization":
                                   f"Bearer {_push_token(private_key=FOREIGN_PRIVATE_KEY_PEM)}"})
        await client.post(PATH, json=_undecodable_push_body(), headers=headers)
        await client.post(PATH, json=_refund_review_push_body(), headers=headers)

        # A product the configured map has no line for.
        expiry = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        seam.body = play_subscription_body(
            lineItems=[{"productId": UNMAPPED_PRODUCT_ID, "expiryTime": expiry}])
        await client.post(PATH, json=body, headers=headers)

        # Then a delivery whose owner is recorded, and a later one that disagrees with it.
        # The later instant is what makes the second a fresh delivery rather than a replay.
        for offset, attribution in ((0, ATTRIBUTION_TOKEN), (1000, OTHER_ATTRIBUTION_TOKEN)):
            seam.body = play_subscription_body(
                externalAccountIdentifiers={"obfuscatedExternalAccountId": attribution})
            body = _push_body(PURCHASE_TOKEN, event_time_millis=EVENT_TIME_MILLIS + offset)
            await client.post(PATH, json=body, headers=headers)
        return verified, body

    async def test_the_walk_sees_the_records_the_deliveries_produced(
            self, webhook_client, real_google_play_seam, _db_transaction, captured_records):
        """The control: a spy recording nothing would pass the hygiene case below without reading a record."""
        await self._drive_every_recording_arm(
            webhook_client, real_google_play_seam, _db_transaction)

        assert {event for event, _fields in captured_records.entries} == {
            "notification_rejected",
            "google_play_message_undecodable",
            "google_play_notification_ignored",
            "unmapped_store_product",
            "attribution_conflict"}

    async def test_the_conflicting_delivery_left_the_first_owner_as_it_was(
            self, webhook_client, real_google_play_seam, _db_transaction):
        """The second control: without a recorded owner the conflict above never fires."""
        await self._drive_every_recording_arm(
            webhook_client, real_google_play_seam, _db_transaction)

        purchases = await _purchases_of(_db_transaction, PURCHASE_TOKEN)
        assert len(purchases) == 1
        assert purchases[0].resolved_token_value == ATTRIBUTION_TOKEN

    async def test_no_record_carries_a_token_the_envelope_or_the_purchase_token(
            self, webhook_client, real_google_play_seam, _db_transaction, captured_records):
        verified, body = await self._drive_every_recording_arm(
            webhook_client, real_google_play_seam, _db_transaction)

        rendered = repr(captured_records.entries)
        # D-10 persists the purchase token as `external_id`; it must still reach no log line.
        for secret in (verified, body["message"]["data"], PURCHASE_TOKEN,
                       ATTRIBUTION_TOKEN, OTHER_ATTRIBUTION_TOKEN):
            assert secret not in rendered, f"a log record carries {secret!r}"
