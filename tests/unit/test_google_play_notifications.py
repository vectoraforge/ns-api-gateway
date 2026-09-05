"""The Google state map, the arms that answer without writing, and the push-token claim pins.
A throwaway keypair mints the push tokens and an `httpx.MockTransport` answers the Play read.
Untested by construction: only whether Google's live tokens and answers match Google's own shapes."""
import ast
import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from nativespeaker.api.app.dependencies import verify_google_play_notification
from nativespeaker.api.auth.google_play import (
    PlayDeveloperSubscriptions,
    developer_notification_from,
)
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.config import GooglePlayConfig
from nativespeaker.api.errors import InternalError, NotificationRejected
from nativespeaker.api.schemas.webhooks import PubSubPushRequest
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus

PLAY_MODULE = Path(__file__).resolve().parents[2] / "src/nativespeaker/api/auth/google_play.py"

PACKAGE_NAME = "com.example.nativespeaker"
PRODUCT_ID = "com.example.nativespeaker.subscription.monthly"
TIER_ID = "paid"
PURCHASE_TOKEN = "opaque-play-purchase-token"
ORDER_ID = "GPA.0000-0000-0000-00000"
ATTRIBUTION_TOKEN = "8f4d1a2e-0000-4000-8000-000000000002"
EVENT_TYPE = "4"
NOTIFICATION_KEY = f"google_play:{PURCHASE_TOKEN}:1780000000000:{EVENT_TYPE}"

# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)
PURCHASED_AT = EVALUATED_AT - timedelta(days=30)
SIGNED_AT = EVALUATED_AT - timedelta(minutes=1)
UNEXPIRED = EVALUATED_AT + timedelta(days=10)
LAPSED = EVALUATED_AT - timedelta(days=1)

# Google's `SubscriptionState` enum, all nine values verbatim.
PUBLISHED_STATES = (
    "SUBSCRIPTION_STATE_UNSPECIFIED",
    "SUBSCRIPTION_STATE_PENDING",
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_PAUSED",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_ON_HOLD",
    "SUBSCRIPTION_STATE_CANCELED",
    "SUBSCRIPTION_STATE_EXPIRED",
    "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED",
)

# A tenth value this build has never seen, which is the arm that must not be entitled.
UNKNOWN_STATE = "SUBSCRIPTION_STATE_SOMETHING_GOOGLE_SHIPS_LATER"


class _FakeCredential:
    """ADC as the Play read uses it: already valid, so a refresh here is a failure, not a fixture."""

    valid = True
    token = "play-access-token"

    def refresh(self, request):
        raise AssertionError("a valid credential must not be refreshed")


def _subscription_body(state: str, *, expiry: datetime | None = None,
                       product_id: str | None = PRODUCT_ID) -> dict:
    """One `subscriptionsv2.get` answer in Google's own field names."""
    line_item: dict = {"productId": product_id}
    if expiry is not None:
        line_item["expiryTime"] = expiry.isoformat()
    return {"subscriptionState": state,
            "startTime": PURCHASED_AT.isoformat(),
            "latestOrderId": ORDER_ID,
            "lineItems": [line_item],
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": ATTRIBUTION_TOKEN}}


def _answering(body: dict, status_code: int = 200):
    """A Play transport that answers every read with this one status and body."""
    return lambda _request: httpx.Response(status_code, json=body)


def _play_reader(handler, *, products: dict[str, str] | None = None) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and a captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        products={PRODUCT_ID: TIER_ID} if products is None else products,
        evaluated_at_source=lambda: EVALUATED_AT)


async def _read_through(reader: PlayDeveloperSubscriptions) -> VerifiedNotification | None:
    """One read on this reader, with the arguments the dependency passes in production."""
    return await reader.read(package_name=PACKAGE_NAME, purchase_token=PURCHASE_TOKEN,
                             event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                             signed_at=SIGNED_AT)


async def _read(state: str, *, expiry: datetime | None = None) -> VerifiedNotification:
    """Read one subscription in this state through the real class, and return the value type."""
    return await _read_through(_play_reader(_answering(_subscription_body(state, expiry=expiry))))


class TestTheStateMap:
    """Nine published states and one unknown state, each with the status it must produce."""

    @pytest.mark.parametrize(("state", "expiry", "expected"), [
        ("SUBSCRIPTION_STATE_ACTIVE", UNEXPIRED, SubscriptionStatus.active),
        ("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", UNEXPIRED, SubscriptionStatus.grace_period),
        # On hold is Play's billing retry: the paid term ended and Google is still charging.
        ("SUBSCRIPTION_STATE_ON_HOLD", LAPSED, SubscriptionStatus.billing_retry),
        # This project's enum carries no paused word, and the auto-resume arrives as a fresh active.
        ("SUBSCRIPTION_STATE_PAUSED", UNEXPIRED, SubscriptionStatus.expired),
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        ("SUBSCRIPTION_STATE_CANCELED", UNEXPIRED, SubscriptionStatus.active),
        ("SUBSCRIPTION_STATE_CANCELED", LAPSED, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_CANCELED", EVALUATED_AT, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_CANCELED", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_EXPIRED", LAPSED, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_PENDING", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_UNSPECIFIED", UNEXPIRED, SubscriptionStatus.expired),
        (UNKNOWN_STATE, UNEXPIRED, SubscriptionStatus.expired),
    ])
    async def test_each_state_produces_its_status(self, state, expiry, expected):
        assert (await _read(state, expiry=expiry)).status is expected

    async def test_a_state_this_build_has_never_seen_is_not_entitled(self):
        """The fall-through, stated on its own: an unlisted value never grants."""
        notification = await _read(UNKNOWN_STATE, expiry=UNEXPIRED)

        assert notification.status is SubscriptionStatus.expired
        assert notification.provider is PurchaseProvider.google_play

    @pytest.mark.parametrize("state", [*PUBLISHED_STATES, UNKNOWN_STATE])
    async def test_no_state_produces_revoked(self, state):
        """`revoked` is unreachable here: `subscriptionsv2` exposes no citable revocation signal."""
        assert (await _read(state, expiry=UNEXPIRED)).status is not SubscriptionStatus.revoked


class TestTheGraceWindowGoogleDoesNotName:
    """Google carries no grace field, so in grace the line item's own expiry ends the window."""

    async def test_a_grace_period_subscription_carries_the_end_of_its_window(self):
        notification = await _read("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", expiry=UNEXPIRED)

        assert notification.status is SubscriptionStatus.grace_period
        assert notification.grace_period_expires_at == UNEXPIRED
        assert notification.grace_period_expires_at == notification.expires_at
        assert notification.expires_at is not None

    @pytest.mark.parametrize("state", [state for state in PUBLISHED_STATES
                                       if state != "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"])
    async def test_every_other_state_carries_no_grace_window(self, state):
        assert (await _read(state, expiry=UNEXPIRED)).grace_period_expires_at is None


# The RTDN envelope every case below shares, and the one body that leads to a Play read.
EVENT_TIME_MILLIS = 1780000000000
SUBSCRIPTION_BODY = {"subscriptionNotification": {"version": "1.0", "notificationType": 4,
                                                  "purchaseToken": PURCHASE_TOKEN}}

# The four bodies Google ships that are not subscription notifications.
OTHER_BODIES = ("testNotification", "oneTimeProductNotification", "voidedPurchaseNotification",
                "pendingRefundReviewNotification")


class _RecordingLogger:
    """Records one call per level, with no dependency on structlog's configuration state."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, dict]] = []

    def at(self, level: str):
        return lambda event, **fields: self.entries.append((level, event, fields))

    def records(self, level: str) -> list[tuple[str, dict]]:
        return [(event, fields) for recorded, event, fields in self.entries if recorded == level]


@pytest.fixture
def play_logs(monkeypatch) -> _RecordingLogger:
    """A spy, not `capture_logs`: the module-level logger caches its binding at import."""
    spy = _RecordingLogger()
    for level in ("error", "info"):
        monkeypatch.setattr(f"nativespeaker.api.auth.google_play.logger.{level}", spy.at(level))
    return spy


class _AcceptingTokens:
    """A push token that already verified, so a body case below is never also a token case."""

    async def verify(self, bearer: str) -> None:
        return None


class _UncallablePlay:
    """A Play seam that fails its case if reached, which is what "makes no Play call" means here."""

    async def read(self, **_fields):
        raise AssertionError("this arm must answer before any Play call is made")


class _RecordingPlay:
    """A Play seam that records what it was asked for and answers with a prepared value."""

    def __init__(self, answer: VerifiedNotification | None = None) -> None:
        self.calls: list[dict] = []
        self._answer = answer

    async def read(self, **fields):
        self.calls.append(fields)
        return self._answer


PUSH_CREDENTIAL = HTTPAuthorizationCredentials(scheme="Bearer", credentials="push.token.value")


def _rtdn(**bodies) -> dict:
    """One decoded RTDN: the envelope every delivery carries, plus whichever body this case sends."""
    return {"version": "1.0", "packageName": PACKAGE_NAME,
            "eventTimeMillis": EVENT_TIME_MILLIS, **bodies}


def _push(payload: dict) -> PubSubPushRequest:
    """One Cloud Pub/Sub push body carrying this RTDN as base64 text."""
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return PubSubPushRequest(message={"messageId": "2280000000000001", "data": data})


def _stub_request(*, play=None, tokens=None, package_name: str | None = PACKAGE_NAME):
    """The three `app.state` members the dependency reads, and nothing else."""
    state = SimpleNamespace(
        google_push_tokens=_AcceptingTokens() if tokens is None else tokens,
        play_subscriptions=_UncallablePlay() if play is None else play,
        config=SimpleNamespace(google_play=GooglePlayConfig(package_name=package_name)))
    return SimpleNamespace(app=SimpleNamespace(state=state))


async def _verify(body: PubSubPushRequest, *, credential=PUSH_CREDENTIAL, **stub):
    """Run the real dependency over a stubbed request, which is what the route resolves."""
    return await verify_google_play_notification(_stub_request(**stub), body, credential)


def _names_read_inside_functions() -> set[str]:
    """Every attribute name and string literal the module's functions and methods mention."""
    used: set[str] = set()
    for node in ast.walk(ast.parse(PLAY_MODULE.read_text())):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Attribute):
                used.add(inner.attr)
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                used.add(inner.value)
    return used


class TestTheUndecodableBody:
    """D-04: a payload that can never parse gets one ERROR record and a 200, which ends the loop."""

    @pytest.mark.parametrize("data", [
        "this is not base64 at all!!",
        base64.b64encode(b"{not json").decode(),
        base64.b64encode(b'"a bare string, not the object"').decode(),
        base64.b64encode(json.dumps({"version": "1.0"}).encode()).decode(),
    ], ids=["not-base64", "not-json", "not-an-object", "no-envelope"])
    async def test_the_decode_yields_none_and_records_one_error(self, data, play_logs):
        body = PubSubPushRequest(message={"messageId": "2280000000000002", "data": data})

        assert await _verify(body) is None
        assert len(play_logs.records("error")) == 1
        # Closed-set labels only: a body that failed to parse may still be a forgery carrying secrets.
        assert play_logs.records("error")[0][1] == {}

    def test_the_decoder_itself_answers_none_rather_than_raising(self, play_logs):
        assert developer_notification_from("this is not base64 at all!!") is None


class TestTheBodiesThatAreNotSubscriptions:
    """D-05: decided on the presence of `subscriptionNotification`, never on a list of names."""

    @pytest.mark.parametrize("body_name", OTHER_BODIES)
    async def test_each_body_yields_none_naming_itself_and_makes_no_play_call(self, body_name,
                                                                             play_logs):
        assert await _verify(_push(_rtdn(**{body_name: {"version": "1.0"}}))) is None

        records = play_logs.records("info")
        assert len(records) == 1
        assert body_name in records[0][1]["bodies"]

    async def test_a_body_google_adds_later_answers_here_rather_than_falling_through(self):
        """The arm a three-member allow-list would let through into a Play call with no token."""
        assert await _verify(_push(_rtdn(subscriptionRefundNotification={"version": "1.0"}))) is None

    def test_no_function_in_the_module_names_the_four_other_bodies(self):
        """The presence test, pinned at the source: enumerating the names is the anti-pattern."""
        used = _names_read_inside_functions()

        assert "subscriptionNotification" in used
        assert not (set(OTHER_BODIES) & used)


class TestThePackageNameCheck:
    """D-18: a delivery naming another application is refused before the network is touched."""

    async def test_a_foreign_package_is_refused_before_any_play_call(self):
        with pytest.raises(NotificationRejected) as refusal:
            await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), package_name="com.example.other")

        assert refusal.value.stage == "package_name_mismatch"

    async def test_an_unconfigured_package_refuses_every_delivery(self):
        with pytest.raises(NotificationRejected):
            await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), package_name=None)

    async def test_the_configured_package_reaches_the_play_read_with_this_token(self):
        play = _RecordingPlay()

        assert await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), play=play) is None
        assert len(play.calls) == 1
        assert play.calls[0]["package_name"] == PACKAGE_NAME
        assert play.calls[0]["purchase_token"] == PURCHASE_TOKEN
        assert play.calls[0]["notification_uuid"] == f"google_play:{PURCHASE_TOKEN}:{EVENT_TIME_MILLIS}:4"


class TestThePlayResponseArms:
    """OQ-5: 404 and 410 are definitive, and every other failure is the redelivery D-20 asks for."""

    @pytest.mark.parametrize("status_code", [404, 410])
    async def test_a_gone_purchase_token_yields_none_and_records_one_error(self, status_code,
                                                                          play_logs):
        reader = _play_reader(_answering({"error": {"status": "NOT_FOUND"}}, status_code))

        assert await _read_through(reader) is None
        assert len(play_logs.records("error")) == 1

    @pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500, 502, 503])
    async def test_every_other_non_2xx_status_is_redelivered(self, status_code):
        reader = _play_reader(_answering({"error": {"status": "UNAVAILABLE"}}, status_code))

        with pytest.raises(InternalError):
            await _read_through(reader)

    async def test_a_transport_failure_is_redelivered(self):
        def _unreachable(_request):
            raise httpx.ConnectError("the Play endpoint is unreachable")

        with pytest.raises(InternalError):
            await _read_through(_play_reader(_unreachable))


class TestTheRefusalsDifferOnlyInStage:
    """The anti-oracle property: one class, one body, and the reason in the log field alone."""

    async def _refusals(self) -> list[NotificationRejected]:
        raised = []
        for kwargs in ({"credential": None}, {"package_name": "com.example.other"}):
            with pytest.raises(NotificationRejected) as refusal:
                await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), **kwargs)
            raised.append(refusal.value)
        return raised

    async def test_every_refusal_is_one_class_with_one_body(self):
        refusals = await self._refusals()

        assert {type(refusal) for refusal in refusals} == {NotificationRejected}
        assert {(refusal.status, refusal.code) for refusal in refusals} == {(401, "auth_required")}

    async def test_the_stage_is_the_only_thing_that_differs(self):
        refusals = await self._refusals()

        assert len({refusal.stage for refusal in refusals}) == len(refusals)
        assert all(set(refusal.log_fields()) == {"stage"} for refusal in refusals)
