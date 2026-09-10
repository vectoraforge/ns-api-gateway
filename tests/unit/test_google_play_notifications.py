"""The Google state map, the arms that answer without writing, and the push-token claim pins.
A throwaway keypair mints the push tokens and an `httpx.MockTransport` answers the Play read.
Untested by construction: only whether Google's live tokens and answers match Google's own shapes."""
import ast
import asyncio
import base64
import inspect
import json
import typing
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import google.auth.exceptions
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

from nativespeaker.api.app.dependencies import verify_google_play_notification
from nativespeaker.api.app.lifespan import build_google_push_verifier
from nativespeaker.api.auth.google_play import (
    GOOGLE_ISSUER,
    GOOGLE_JWKS_URL,
    PLAY_CREDENTIAL_REBUILD_INTERVAL_SECONDS,
    PLAY_HTTP_TIMEOUT_SECONDS,
    RESTORE_UNCONFIGURED_STAGE,
    RESTORE_UNPARSEABLE_STAGE,
    CappedRefreshRequest,
    PlayDeveloperSubscriptions,
    PubSubPushTokens,
    developer_notification_from,
    instant_from_millis,
)
from nativespeaker.api.auth.jwt_verifier import (
    DECODE_OPTIONS,
    BoundedReason,
    JWTVerifier,
    TokenVerifier,
)
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.config import GooglePlayConfig
from nativespeaker.api.errors import InternalError, NotificationRejected, Unavailable
from nativespeaker.api.schemas.webhooks import PUBSUB_DATA_LIMIT, PubSubPushRequest
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus
from unit.conftest import PRIVATE_KEY_PEM, make_token
from unit.test_jwks_offload import CountedJwksTransport, install_counted_transport, jwks_body

_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src/nativespeaker/api"
PLAY_MODULE = _SOURCE_ROOT / "auth/google_play.py"
VERIFIER_MODULE = _SOURCE_ROOT / "auth/jwt_verifier.py"

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


class _StaleCredential:
    """ADC whose refresh is refused: the ordinary GCP failure, and not an `httpx` one."""

    valid = False
    token = None

    def refresh(self, request):
        raise google.auth.exceptions.RefreshError("the metadata server refused")


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


def _never_reached(_request: httpx.Request) -> httpx.Response:
    """A Play transport for the cases that must refuse before the network is touched."""
    raise AssertionError("this case must not reach Play at all")


_UNSET = object()


def _play_reader(handler, *, products: dict[str, str] | None = None,
                 credential=_UNSET, build=None,
                 rebuild_interval_seconds: float = PLAY_CREDENTIAL_REBUILD_INTERVAL_SECONDS,
                 ) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and a captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential() if credential is _UNSET else credential,
        build=build,
        rebuild_interval_seconds=rebuild_interval_seconds,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        products={PRODUCT_ID: TIER_ID} if products is None else products)


async def _read_through(reader: PlayDeveloperSubscriptions) -> VerifiedNotification | None:
    """One read on this reader, with the arguments the dependency passes in production."""
    return await reader.read(package_name=PACKAGE_NAME, purchase_token=PURCHASE_TOKEN,
                             event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                             signed_at=SIGNED_AT, evaluated_at=EVALUATED_AT)


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


class TestThePlayReadReportsTheNotificationValueType:
    """Every field of the value type the whole RTDN ingestion is derived from, read at once.
    The status alone leaves the other eleven free to be dropped, and one of them is load-bearing."""

    async def test_the_read_carries_every_field_the_ingestion_derives_from(self):
        notification = await _read("SUBSCRIPTION_STATE_ACTIVE", expiry=UNEXPIRED)

        assert notification.provider is PurchaseProvider.google_play
        assert notification.notification_uuid == NOTIFICATION_KEY
        assert notification.event_type == EVENT_TYPE
        assert notification.signed_at == SIGNED_AT
        assert notification.external_id == PURCHASE_TOKEN
        assert notification.transaction_id == ORDER_ID
        assert notification.product_id == PRODUCT_ID
        assert notification.tier_id == TIER_ID
        assert notification.attribution_token == ATTRIBUTION_TOKEN
        assert notification.status is SubscriptionStatus.active
        assert notification.purchased_at == PURCHASED_AT
        assert notification.expires_at == UNEXPIRED
        assert notification.grace_period_expires_at is None


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


class _RefusingTokens:
    """A push token that does not verify, which is what makes the ordering below observable."""

    async def verify(self, bearer: str) -> None:
        raise NotificationRejected(stage="bad_signature")


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


async def _verify(body: PubSubPushRequest, *, credential=PUSH_CREDENTIAL,
                  evaluated_at: datetime = EVALUATED_AT, **stub):
    """Run the real dependency over a stubbed request, with every argument the route resolves.
    `evaluated_at` is passed explicitly: left to its default it is the `Depends` object itself."""
    return await verify_google_play_notification(_stub_request(**stub), body, credential,
                                                 evaluated_at)


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


class TestTheTokenIsCheckedBeforeTheBodyIsParsed:
    """A forged body must never be decoded, so the refusal comes from the token and nothing else."""

    async def test_an_unverifiable_token_refuses_before_the_body_is_decoded(self, play_logs):
        body = PubSubPushRequest(message={"messageId": "2280000000000003",
                                          "data": "this is not base64 at all!!"})

        with pytest.raises(NotificationRejected) as refusal:
            await _verify(body, tokens=_RefusingTokens())

        assert refusal.value.stage == "bad_signature"
        assert play_logs.records("error") == []


class TestTheEmptyBodyAndTheBreachedBoundAreRecordedApart:
    """WR-01: an attributes-only push is a shape Pub/Sub permits, so recording it at ERROR under
    the bound's name pages an operator for a routine console publish. Both still answer `None`."""

    def test_an_attributes_only_body_is_recorded_at_info_naming_no_bound(self, play_logs):
        assert developer_notification_from("") is None

        assert play_logs.records("info") == [("google_play_message_without_data", {})]
        assert play_logs.records("error") == []

    def test_a_body_past_the_bound_is_still_recorded_at_error_with_its_length(self, play_logs):
        assert developer_notification_from("a" * (PUBSUB_DATA_LIMIT + 1)) is None

        assert play_logs.records("error") == [("google_play_message_out_of_range",
                                               {"length": PUBSUB_DATA_LIMIT + 1})]
        assert play_logs.records("info") == []


class TestAnEventTimeThatNamesNoInstant:
    """WR-21: `eventTimeMillis` is an unbounded int, and `datetime.fromtimestamp` raises past year
    9999. The escape was a 500, which is the one answer that makes Pub/Sub redeliver this same
    body until retention expires -- the loop `developer_notification_from` exists to stop."""

    OUT_OF_RANGE = (10 ** 18, -10 ** 18)

    @pytest.mark.parametrize("millis", OUT_OF_RANGE, ids=["far-future", "far-past"])
    def test_the_conversion_answers_none_naming_no_value(self, millis, play_logs):
        assert instant_from_millis(millis) is None
        assert play_logs.records("error") == [("google_play_event_time_out_of_range", {})]

    def test_an_ordinary_stamp_still_converts_control(self, play_logs):
        """The control: a conversion that answered `None` unconditionally would pass the case above."""
        assert instant_from_millis(EVENT_TIME_MILLIS) == datetime(2026, 5, 28, 20, 26, 40, tzinfo=UTC)
        assert play_logs.records("error") == []

    @pytest.mark.parametrize("millis", OUT_OF_RANGE, ids=["far-future", "far-past"])
    async def test_the_delivery_still_reaches_play_carrying_no_signed_at(self, millis, play_logs):
        """The token is usable even when the stamp is not, so the read happens and the push is acked."""
        play = _RecordingPlay()

        assert await _verify(_push(_rtdn(eventTimeMillis=millis, **SUBSCRIPTION_BODY)),
                             play=play) is None

        assert play.calls[0]["signed_at"] is None
        assert play.calls[0]["notification_uuid"] == f"google_play:{PURCHASE_TOKEN}:{millis}:4"


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

    async def test_a_body_google_adds_later_names_itself_in_the_log(self, play_logs):
        """WR-13: the line exists for the unseen body, so an empty `bodies` is the one useless case."""
        assert await _verify(_push(_rtdn(subscriptionRefundNotification={"version": "1.0"}))) is None

        assert play_logs.records("info")[0][1]["bodies"] == ["subscriptionRefundNotification"]

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

    async def test_an_empty_configured_package_refuses_a_delivery_that_names_none_either(self):
        """WR-02: `GOOGLE_PLAY_PACKAGE_NAME=` parses to `""`, which an equality alone reads as a match."""
        with pytest.raises(NotificationRejected) as refusal:
            await _verify(_push(_rtdn(packageName="", **SUBSCRIPTION_BODY)), package_name="")

        assert refusal.value.stage == "package_name_mismatch"

    async def test_the_configured_package_reaches_the_play_read_with_this_token(self):
        play = _RecordingPlay()

        assert await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), play=play) is None
        assert len(play.calls) == 1
        assert play.calls[0]["package_name"] == PACKAGE_NAME
        assert play.calls[0]["purchase_token"] == PURCHASE_TOKEN
        assert play.calls[0]["notification_uuid"] == f"google_play:{PURCHASE_TOKEN}:{EVENT_TIME_MILLIS}:4"


class TestTheEntitlementDecisionUsesTheInstantTheRequestCaptured:
    """WR-27: the adapter read a clock of its own, so it decided at a different instant from the
    grant writer, and a term crossing between the two commits a grant outside its own term."""

    @pytest.mark.parametrize(("evaluated_at", "expected"), [
        (UNEXPIRED - timedelta(days=1), SubscriptionStatus.active),
        (UNEXPIRED + timedelta(days=1), SubscriptionStatus.expired),
    ], ids=["inside-the-term", "past-the-term"])
    async def test_a_canceled_term_is_judged_against_the_instant_passed_in(self, evaluated_at,
                                                                          expected):
        """The one state whose answer depends on a date, read on both sides of its own expiry."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_CANCELED",
                                                            expiry=UNEXPIRED)))

        notification = await reader.read(package_name=PACKAGE_NAME,
                                         purchase_token=PURCHASE_TOKEN, event_type=EVENT_TYPE,
                                         notification_uuid=NOTIFICATION_KEY, signed_at=SIGNED_AT,
                                         evaluated_at=evaluated_at)

        assert notification.status is expected

    def test_the_class_holds_no_clock_of_its_own_to_fall_back_to(self):
        """Read off the signature: a surviving source would let a later edit silently use it again.
        `rebuild_interval_seconds` is a monotonic floor and names no date a term can be read from."""
        parameters = set(inspect.signature(PlayDeveloperSubscriptions.__init__).parameters)
        assert parameters == {"self", "credential", "build", "rebuild_interval_seconds",
                              "client", "products"}

    async def test_the_dependency_forwards_the_solver_resolved_instant_to_the_read(self):
        """The other half: the instant reaches the adapter through the dependency, not by hand."""
        play = _RecordingPlay()

        await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), play=play, evaluated_at=LAPSED)

        assert play.calls[0]["evaluated_at"] == LAPSED


class TestBothEntryPointsGuardTheValueTheyPutInThePath:
    """WR-26: `read` reached the same `_get` as `read_for_restore` with neither of its guards."""

    @pytest.mark.parametrize("purchase_token", ["", ".", "..", "..."])
    async def test_a_token_that_names_no_path_segment_is_never_sent(self, purchase_token,
                                                                    play_logs):
        """`quote` leaves a dot unescaped and httpx removes a dot segment, so these address
        another Play URL. The answer is the acknowledged `None`, and no request is made."""
        def _never(_request):
            raise AssertionError("an unusable purchase token must not reach Play")

        reader = _play_reader(_never)

        assert await reader.read(package_name=PACKAGE_NAME, purchase_token=purchase_token,
                                 event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                                 signed_at=SIGNED_AT, evaluated_at=EVALUATED_AT) is None
        assert play_logs.records("error") == [("google_play_unusable_purchase_token", {})]

    @pytest.mark.parametrize("package_name", ["", ".", "..", "..."])
    async def test_a_package_name_that_names_no_path_segment_is_refused_and_never_acknowledged(
            self, package_name, play_logs):
        """WR-25: only the token half was hoisted into `read`. A dot-only application name is a
        deployment fault, and acknowledging it drops every RTDN Pub/Sub will ever send."""
        def _never(_request):
            raise AssertionError("an unusable package name must not reach Play")

        reader = _play_reader(_never)

        with pytest.raises(InternalError):
            await reader.read(package_name=package_name, purchase_token=PURCHASE_TOKEN,
                              event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                              signed_at=SIGNED_AT, evaluated_at=EVALUATED_AT)

        assert play_logs.records("error") == [("google_play_unusable_package_name", {})]

    async def test_a_real_token_still_reaches_play(self, play_logs):
        """The control: a guard that refused everything would pass every case above."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)))

        assert await _read_through(reader) is not None
        assert play_logs.records("error") == []


class TestTheLineItemCountIsMadeVisible:
    """WR-05: both the tier and the term of the grant are read off one element of a list Google
    documents no ordering for, so a count other than one is a guess and never a silent choice."""

    @pytest.mark.parametrize("line_items", [
        [],
        [{"productId": PRODUCT_ID, "expiryTime": UNEXPIRED.isoformat()},
         {"productId": PRODUCT_ID, "expiryTime": (UNEXPIRED + timedelta(days=30)).isoformat()}],
    ], ids=["none", "two"])
    async def test_a_count_other_than_one_is_refused_before_any_value_type(self, line_items,
                                                                          play_logs):
        reader = _play_reader(_answering({"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
                                          "startTime": PURCHASED_AT.isoformat(),
                                          "lineItems": line_items}))

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert play_logs.records("error") == [("google_play_unexpected_line_item_count",
                                               {"count": len(line_items)})]

    async def test_the_restore_read_refuses_it_as_a_body_it_cannot_read(self, play_logs):
        """WR-35: the second caller of `_product_of` answers the app, so this count is the 503
        every other unreadable 2xx earns there and never the webhook's 500."""
        reader = _play_reader(_answering({"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
                                          "startTime": PURCHASED_AT.isoformat(),
                                          "lineItems": []}))

        with pytest.raises(Unavailable) as refusal:
            await reader.read_for_restore(package_name=PACKAGE_NAME,
                                          purchase_token=PURCHASE_TOKEN,
                                          evaluated_at=EVALUATED_AT)

        assert (refusal.value.stage, refusal.value.status) == (RESTORE_UNPARSEABLE_STAGE, 503)
        assert play_logs.records("error") == [("google_play_unexpected_line_item_count",
                                               {"count": 0})]

    async def test_the_refusal_carries_no_play_value(self, play_logs):
        """The count is ours; the product id and the expiry are Google's and never travel."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED) | {"lineItems": []}))

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert PRODUCT_ID not in str(play_logs.records("error"))
        assert PURCHASE_TOKEN not in str(play_logs.records("error"))

    async def test_exactly_one_line_item_is_read_normally_control(self, play_logs):
        """The control: the guard refuses the ambiguous count alone, never the ordinary purchase."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)))

        notification = await _read_through(reader)

        assert (notification.tier_id, notification.expires_at) == (TIER_ID, UNEXPIRED)
        assert play_logs.records("error") == []


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

    @pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500, 502, 503])
    async def test_every_other_non_2xx_status_names_itself_in_one_error_line(self, status_code,
                                                                             play_logs):
        """WR-03: `InternalError` logs nothing of its own, so the 500 would name no cause at all."""
        reader = _play_reader(_answering({"error": {"status": "UNAVAILABLE"}}, status_code))

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert play_logs.records("error") == [("google_play_read_refused",
                                               {"status_code": status_code})]

    async def test_a_transport_failure_is_redelivered(self):
        def _unreachable(_request):
            raise httpx.ConnectError("the Play endpoint is unreachable")

        with pytest.raises(InternalError):
            await _read_through(_play_reader(_unreachable))

    async def test_a_transport_failure_names_its_class_in_one_error_line(self, play_logs):
        """WR-03. The exception's class name only: its text carries the URL, and the URL is the token."""
        def _unreachable(_request):
            raise httpx.ConnectError("the Play endpoint is unreachable")

        with pytest.raises(InternalError):
            await _read_through(_play_reader(_unreachable))

        assert play_logs.records("error") == [("google_play_read_transport_failed",
                                               {"failure": "ConnectError"})]

    async def test_a_refused_credential_refresh_is_redelivered_too(self, play_logs):
        """WR-11: a `GoogleAuthError` is no `httpx` failure, so the transport arm alone misses it."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE")),
                              credential=_StaleCredential())

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert play_logs.records("error") == [("google_play_read_transport_failed",
                                               {"failure": "RefreshError"})]

    async def test_a_2xx_carrying_no_json_is_redelivered_naming_its_class_alone(self, play_logs):
        """WR-11: an intermediary's HTML page reaches the same read as a `200`."""
        reader = _play_reader(
            lambda _request: httpx.Response(200, text="<html>502 Bad Gateway</html>"))

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert play_logs.records("error") == [("google_play_read_unparseable",
                                               {"failure": "JSONDecodeError"})]

    async def test_a_2xx_this_build_cannot_read_is_redelivered_carrying_no_play_value(self,
                                                                                      play_logs):
        """WR-11: pydantic echoes the rejected input, so only the class name may travel."""
        reader = _play_reader(_answering({"lineItems": [{"productId": PRODUCT_ID}],
                                          "externalAccountIdentifiers": {
                                              "obfuscatedExternalAccountId": ATTRIBUTION_TOKEN}}))

        with pytest.raises(InternalError):
            await _read_through(reader)

        assert play_logs.records("error") == [("google_play_read_unparseable",
                                               {"failure": "ValidationError"})]
        assert ATTRIBUTION_TOKEN not in str(play_logs.records("error"))


class TestAnUnconfiguredCredentialIsNeverAcknowledged:
    """WR-82: the arm for a pod whose ADC read answered `None`. Returning instead of raising
    acknowledges every RTDN, and Pub/Sub redelivers nothing it has already acknowledged."""

    async def test_the_read_refuses_before_any_play_call(self):
        with pytest.raises(Unavailable) as refusal:
            await _read_through(_play_reader(_never_reached, credential=None))

        assert refusal.value.stage == "play_subscriptions_read"

    async def test_a_configured_credential_still_reaches_play_control(self):
        """The control on the sentinel: the default must still stand a credential in, or every
        other case in this file would be measuring this refusal instead of its own arm."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)))

        assert await _read_through(reader) is not None


class _RecordingCredentialBuild:
    """The ADC read as a double: it counts its calls and answers whatever the case last set."""

    def __init__(self, credential=None) -> None:
        self.credential = credential
        self.calls = 0

    def __call__(self):
        """One rebuild attempt, which answers `None` for as long as the environment does."""
        self.calls += 1
        return self.credential


class TestACredentialBootCouldNotReadIsRebuiltRatherThanCachedForThePodsLife:
    """WR-51: a metadata-server blip at boot answered 503 for every later delivery and every
    later google_play restore, with both probes green and nothing recovering without a restart."""

    def _live_reader(self, **kwargs) -> PlayDeveloperSubscriptions:
        """A reader whose transport answers one ordinary active subscription."""
        return _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                          expiry=UNEXPIRED)), **kwargs)

    async def test_the_next_restore_read_rebuilds_the_credential_boot_could_not_read(self):
        build = _RecordingCredentialBuild(_FakeCredential())
        reader = self._live_reader(credential=None, build=build)

        restored = await reader.read_for_restore(package_name=PACKAGE_NAME,
                                                 purchase_token=PURCHASE_TOKEN,
                                                 evaluated_at=EVALUATED_AT)

        assert (restored.tier_id, build.calls) == (TIER_ID, 1)

    async def test_the_rebuilt_credential_serves_the_webhook_read_and_is_read_once(self):
        build = _RecordingCredentialBuild(_FakeCredential())
        reader = self._live_reader(credential=None, build=build)

        assert await _read_through(reader) is not None
        assert await _read_through(reader) is not None
        assert build.calls == 1, "one rebuild serving both deliveries"

    async def test_an_environment_supplying_none_again_is_the_503_it_was(self):
        """The control: recovery is a retry, never a read no credential ever signed."""
        reader = _play_reader(_never_reached, credential=None,
                              build=_RecordingCredentialBuild())

        with pytest.raises(Unavailable) as refusal:
            await reader.read_for_restore(package_name=PACKAGE_NAME,
                                          purchase_token=PURCHASE_TOKEN,
                                          evaluated_at=EVALUATED_AT)

        assert refusal.value.stage == RESTORE_UNCONFIGURED_STAGE

    async def test_a_rebuild_that_answered_none_is_not_retried_within_the_interval(self):
        """The rate floor: nothing else records that a rebuild was just attempted and failed."""
        build = _RecordingCredentialBuild()
        reader = _play_reader(_never_reached, credential=None, build=build)

        for _ in range(5):
            with pytest.raises(Unavailable):
                await _read_through(reader)

        assert build.calls == 1, "the first delivery's attempt, and none of the four behind it"

    async def test_one_burst_of_callers_shares_a_single_rebuild(self):
        """The lock: with the floor at zero it is the only thing parting eight concurrent callers."""
        build = _RecordingCredentialBuild(_FakeCredential())
        reader = self._live_reader(credential=None, build=build, rebuild_interval_seconds=0.0)

        await asyncio.gather(*(_read_through(reader) for _ in range(8)))

        assert build.calls == 1, "one rebuild for the burst, and not one per caller"

    async def test_the_interval_elapsing_still_recovers_the_route(self):
        """The floor delays the retry and never cancels it, as the push verifier's does."""
        build = _RecordingCredentialBuild()
        reader = self._live_reader(credential=None, build=build, rebuild_interval_seconds=0.0)

        with pytest.raises(Unavailable):
            await _read_through(reader)
        build.credential = _FakeCredential()

        assert await _read_through(reader) is not None
        assert build.calls == 2, "the refused attempt, then the one that recovered the route"

    async def test_a_pod_wired_without_a_builder_keeps_the_answer_boot_gave_it(self):
        """The control on the seam: an absent builder is the old behaviour exactly."""
        reader = _play_reader(_never_reached, credential=None)

        with pytest.raises(Unavailable):
            await _read_through(reader)


class _RecordingSession:
    """A `requests` session that answers 200 and records the timeout each call asked for."""

    def __init__(self) -> None:
        self.timeouts: list[float | None] = []

    def request(self, method, url, data=None, headers=None, timeout=None, **kwargs):
        """Google's transport calls this one method; only the timeout is read back."""
        self.timeouts.append(timeout)
        return SimpleNamespace(status_code=200, headers={}, content=b"{}")

    def close(self) -> None:
        """`Request.__del__` closes its session, so the double owes one."""


class _RefreshingCredential:
    """ADC that is stale once, recording the transport the read handed its refresh."""

    token = "play-access-token"

    def __init__(self) -> None:
        self.valid = False
        self.transports: list[object] = []

    def refresh(self, request):
        """Succeed, keeping the transport so the case can measure what it was given."""
        self.transports.append(request)
        self.valid = True


class TestTheCredentialRefreshIsCapped:
    """WR-01: `Request.__call__` defaults to 120 s and `jwt_grant` passes no timeout of its own,
    so an uncapped refresh holds one thread of the pool `get_identity` shares, retried."""

    def test_a_refresh_call_naming_no_timeout_is_sent_with_the_modules_cap(self):
        """The transport's own behaviour, not its signature: the cap reaches `session.request`."""
        session = _RecordingSession()

        CappedRefreshRequest(session=session)("https://oauth2.googleapis.com/token", "POST")

        assert session.timeouts == [PLAY_HTTP_TIMEOUT_SECONDS]

    def test_a_caller_that_names_its_own_timeout_still_wins(self):
        """The cap is a default and never an override: google-auth may pass a shorter one."""
        session = _RecordingSession()

        CappedRefreshRequest(session=session)("https://oauth2.googleapis.com/token", "POST",
                                              None, None, 1.5)

        assert session.timeouts == [1.5]

    async def test_the_read_refreshes_a_stale_credential_through_the_capped_transport(self):
        """The wiring: a bare `Request()` here would carry google-auth's 120 s instead."""
        credential = _RefreshingCredential()
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)),
                              credential=credential)

        assert await _read_through(reader) is not None
        assert [type(one) for one in credential.transports] == [CappedRefreshRequest]


class TestAZoneLessStampIsClassifiedRatherThanRaised:
    """WR-20: a stamp carrying no offset parses into a naive `datetime` and then raises `TypeError`
    inside `_status_for`, past both read paths' `except ValueError` arms and onto the generic 500.
    Declared `AwareDatetime`, it is the parse failure both paths already answer for."""

    ZONE_LESS = "2026-07-01T00:00:00"

    def _reader(self, **overrides) -> PlayDeveloperSubscriptions:
        return _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_CANCELED",
                                                          expiry=UNEXPIRED) | overrides))

    @pytest.mark.parametrize("overrides", [
        {"lineItems": [{"productId": PRODUCT_ID, "expiryTime": ZONE_LESS}]},
        {"startTime": ZONE_LESS},
    ], ids=["expiry", "start"])
    async def test_the_webhook_read_redelivers_it_like_any_other_unreadable_body(self, overrides,
                                                                                 play_logs):
        with pytest.raises(InternalError):
            await _read_through(self._reader(**overrides))

        assert play_logs.records("error") == [("google_play_read_unparseable",
                                               {"failure": "ValidationError"})]

    async def test_the_restore_read_answers_its_own_refusal_rather_than_a_type_error(self):
        reader = self._reader(lineItems=[{"productId": PRODUCT_ID, "expiryTime": self.ZONE_LESS}])

        with pytest.raises(Unavailable) as refusal:
            await reader.read_for_restore(package_name=PACKAGE_NAME,
                                          purchase_token=PURCHASE_TOKEN,
                                          evaluated_at=EVALUATED_AT)

        assert refusal.value.stage == RESTORE_UNPARSEABLE_STAGE

    async def test_the_same_term_carrying_an_offset_is_read_normally_control(self, play_logs):
        """The control: the offset is the whole requirement, and a canceled term still resolves."""
        notification = await _read_through(self._reader())

        assert (notification.status, notification.expires_at) == (SubscriptionStatus.active,
                                                                  UNEXPIRED)
        assert play_logs.records("error") == []


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


# The two deployer values the push token is pinned to, and the key id this suite's JWKS serves.
PUSH_AUDIENCE = "https://api.example.com/webhooks/google-play/rtdn"
PUSH_SERVICE_ACCOUNT = "rtdn-push@example-project.iam.gserviceaccount.com"
PUSH_KID = "google-push-key-1"

# The push identity Google mints these tokens for, which is a numeric service-account subject.
PUSH_SUBJECT = "116000000000000000000"

# A second keypair no JWKS document serves, so a token signed with it fails on the signature alone.
_foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FOREIGN_PRIVATE_KEY_PEM = _foreign_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption())


def _play_config(**overrides) -> GooglePlayConfig:
    """This deployment's Play settings, with whichever value the case under way replaces."""
    values = {"package_name": PACKAGE_NAME, "push_audience": PUSH_AUDIENCE,
              "push_service_account_email": PUSH_SERVICE_ACCOUNT,
              "products": {PRODUCT_ID: TIER_ID}}
    return GooglePlayConfig(**(values | overrides))


def _push_token(*, aud: str = PUSH_AUDIENCE, iss: str = GOOGLE_ISSUER,
                email: str = PUSH_SERVICE_ACCOUNT, email_verified: bool = True,
                private_key: bytes = PRIVATE_KEY_PEM) -> str:
    """One Google-shaped Pub/Sub push token: the five required claims plus Google's own two."""
    return make_token(PUSH_SUBJECT, aud=aud, iss=iss, email_verified=email_verified,
                      extra_claims={"email": email}, private_key=private_key,
                      headers={"kid": PUSH_KID})


def _require_list() -> list[str]:
    """The claims `jwt.decode` is told to require: the verifier's own value, never a copy of it."""
    required = DECODE_OPTIONS.get("require")
    assert isinstance(required, list), "the verifier declares no `require` list at all"
    assert any(keyword.arg == "options" and isinstance(keyword.value, ast.Name)
               and keyword.value.id == "DECODE_OPTIONS"
               for node in ast.walk(ast.parse(VERIFIER_MODULE.read_text()))
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "decode"
               for keyword in node.keywords), \
        "the verifier's `jwt.decode` call is not the one carrying DECODE_OPTIONS"
    return required


SPEC_REASONS = frozenset({"missing_token", "malformed", "duplicate_authorization",
                          "bad_signature", "issuer_mismatch", "audience_mismatch",
                          "expired", "empty_subject"})

# Each arm of the push-token check, with the bounded reason the refusal carries as its `stage`.
TOKEN_REFUSALS = [
    ({"private_key": FOREIGN_PRIVATE_KEY_PEM}, "bad_signature"),
    ({"email": "someone-else@example-project.iam.gserviceaccount.com"}, "required_claim_mismatch"),
    ({"email_verified": False}, "required_claim_mismatch"),
    ({"aud": "https://api.example.com/webhooks/somewhere-else"}, "audience_mismatch"),
    ({"iss": "https://accounts.example.com"}, "issuer_mismatch"),
]
TOKEN_REFUSAL_IDS = ["signature", "email", "email-verified", "aud", "iss"]

NOT_JSON = b"<html>502 Bad Gateway</html>"


@pytest.fixture
def jwks(monkeypatch) -> CountedJwksTransport:
    """The offload suite's counted transport, serving this suite's one push key."""
    transport = install_counted_transport(monkeypatch)
    transport.body = jwks_body(PUSH_KID)
    return transport


@pytest.fixture
def push_tokens(jwks) -> PubSubPushTokens:
    """The real push-token class over a real `JWTVerifier`, built the way lifespan builds it."""
    return PubSubPushTokens(verifier=build_google_push_verifier(_play_config()))


async def _refused(push_tokens: PubSubPushTokens, token: str) -> NotificationRejected:
    """Verify a token that must be refused, and hand back the refusal it raised."""
    with pytest.raises(NotificationRejected) as refusal:
        await push_tokens.verify(token)
    return refusal.value


class TestThePushTokenCheck:
    """Every arm run against a real verifier over a fake JWKS document, not against a stub."""

    async def test_a_token_carrying_every_pinned_claim_verifies(self, push_tokens):
        assert await push_tokens.verify(_push_token()) is None

    @pytest.mark.parametrize(("overrides", "stage"), TOKEN_REFUSALS, ids=TOKEN_REFUSAL_IDS)
    async def test_each_arm_refuses_with_its_own_stage(self, overrides, stage, push_tokens):
        assert (await _refused(push_tokens, _push_token(**overrides))).stage == stage

    async def test_an_unconfigured_deployment_answers_503_rather_than_admitting_the_push(self):
        """The verifier the builder could not build: the route fails closed, it does not open."""
        with pytest.raises(Unavailable):
            await PubSubPushTokens(verifier=None).verify(_push_token())

    async def test_every_refusal_is_one_class_with_one_body(self, push_tokens):
        refusals = [await _refused(push_tokens, _push_token(**overrides))
                    for overrides, _stage in TOKEN_REFUSALS]

        assert {type(refusal) for refusal in refusals} == {NotificationRejected}
        assert {(refusal.status, refusal.code) for refusal in refusals} == {(401, "auth_required")}
        assert all(set(refusal.log_fields()) == {"stage"} for refusal in refusals)


class TestTheClaimPinsArePostDecodeComparisons:
    """D-09's two properties, which a passing verification case would otherwise hide."""

    def test_bounded_reason_adds_only_a_reason_no_barrier_rejection_can_carry(self):
        """The eight the specs close `invalid_external_jwt` over must all still be there, and the
        only member outside them must be one the barrier cannot reach: it passes no
        `required_claims`, so the `is None` guard returns before the comparison that yields it."""
        assert SPEC_REASONS <= set(BoundedReason)
        assert set(BoundedReason) - SPEC_REASONS == {BoundedReason.required_claim_mismatch}
        assert VERIFIER_MODULE.read_text().count("BoundedReason.required_claim_mismatch") == 1

    def test_email_is_compared_after_decode_rather_than_required(self):
        """In `require`, a Google token shape without `email` would fail like a forgery (P-03)."""
        assert "email" not in _require_list()
        assert _require_list() == ["exp", "iat", "aud", "iss", "sub"]


class TestThePushTokenSeamIsTheAnnotation:
    """WR-24: `TokenVerifier` was declared and named nowhere, while its one consumer took the
    concrete `JWTVerifier`. A seam nothing is typed against catches no wrong-shaped double."""

    def test_the_push_token_class_takes_the_declared_seam(self):
        annotations = inspect.get_annotations(PubSubPushTokens.__init__, eval_str=True)
        assert annotations["verifier"] == TokenVerifier | None

    def test_the_verifier_lifespan_supplies_carries_every_member_it_declares_control(self):
        """The control: a seam the production verifier does not satisfy would be worse than none."""
        assert typing.get_protocol_members(TokenVerifier) <= set(dir(JWTVerifier))


class TestTheJwksWarmUpGuard:
    """F-04: the constructor fetches, so an unguarded second verifier is a pod that will not start."""

    def test_an_unreachable_jwks_endpoint_raises_at_construction(self, jwks):
        """Measured, not assumed: this is the raise the builder's guard exists to catch."""
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")

        with pytest.raises(PyJWKClientConnectionError):
            JWTVerifier(jwks_url=GOOGLE_JWKS_URL, audience=PUSH_AUDIENCE, issuer=GOOGLE_ISSUER)

    def test_the_builder_answers_none_and_lets_the_pod_boot(self, jwks):
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")

        assert build_google_push_verifier(_play_config()) is None

    def test_a_2xx_that_is_not_json_raises_inside_the_guarded_family(self, jwks):
        """WR-04/WR-20: `fetch_data` converts `URLError` and `TimeoutError` alone, so a captive
        portal or proxy error page answering 200 leaves `json.load`'s `JSONDecodeError`, which is a
        `ValueError` and not a `PyJWTError` -- it escaped the guard and took the whole pod down."""
        jwks.body = NOT_JSON

        with pytest.raises(PyJWTError):
            JWTVerifier(jwks_url=GOOGLE_JWKS_URL, audience=PUSH_AUDIENCE, issuer=GOOGLE_ISSUER)

    def test_a_2xx_that_is_not_json_lets_the_pod_boot_too(self, jwks):
        """The whole point: one route's 503 beats a dead `/chats`, which is what the guard promised."""
        jwks.body = NOT_JSON

        assert build_google_push_verifier(_play_config()) is None

    def test_the_wrapped_failure_carries_neither_the_url_nor_the_body(self, jwks):
        """`JSONDecodeError`'s message quotes what it was reading, and PyJWT's embeds the URL."""
        jwks.body = NOT_JSON

        with pytest.raises(PyJWTError) as raised:
            JWTVerifier(jwks_url=GOOGLE_JWKS_URL, audience=PUSH_AUDIENCE, issuer=GOOGLE_ISSUER)

        assert GOOGLE_JWKS_URL not in str(raised.value)
        assert NOT_JSON.decode() not in str(raised.value)

    def test_a_body_that_is_json_but_no_key_set_was_already_covered_control(self, jwks):
        """The control on the wrapper's scope: PyJWT converts this one itself, so the case above
        measures the conversion this constructor adds and not one the library already made."""
        jwks.body = b"[]"

        with pytest.raises(PyJWKClientError) as raised:
            JWTVerifier(jwks_url=GOOGLE_JWKS_URL, audience=PUSH_AUDIENCE, issuer=GOOGLE_ISSUER)

        assert "JWKS warm-up failed" not in str(raised.value)

    @pytest.mark.parametrize("absent", ["push_audience", "push_service_account_email"])
    def test_an_unconfigured_value_answers_none_without_a_fetch(self, absent, jwks):
        assert build_google_push_verifier(_play_config(**{absent: None})) is None
        assert len(jwks) == 0, "an unconfigured deployment must not reach for Google's keys"


class TestAWarmUpFailureIsRetriedRatherThanCachedForThePodsLife:
    """WR-41: a two-second JWKS blip at boot answered 503 for every later delivery, and the
    deliveries Pub/Sub gives up on are the renewals and revocations nothing else reports."""

    async def test_the_next_delivery_rebuilds_the_verifier_boot_could_not_build(self, jwks):
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")
        tokens = PubSubPushTokens(verifier=build_google_push_verifier(_play_config()),
                                  build=lambda: build_google_push_verifier(_play_config()))
        jwks.error = None

        assert await tokens.verify(_push_token()) is None

    async def test_the_rebuilt_verifier_is_kept_rather_than_rebuilt_per_delivery(self, jwks):
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")
        tokens = PubSubPushTokens(verifier=build_google_push_verifier(_play_config()),
                                  build=lambda: build_google_push_verifier(_play_config()))
        jwks.error = None

        await tokens.verify(_push_token())
        await tokens.verify(_push_token())

        assert len(jwks) == 2, "the failed warm-up, then one rebuild serving both deliveries"

    async def test_a_key_set_still_unreachable_is_the_503_it_was(self, jwks):
        """The control: recovery is a retry, never an admission of a token nothing verified."""
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")
        tokens = PubSubPushTokens(verifier=None,
                                  build=lambda: build_google_push_verifier(_play_config()))

        with pytest.raises(Unavailable):
            await tokens.verify(_push_token())

    async def test_an_unconfigured_deployment_rebuilds_without_reaching_for_the_keys(self, jwks):
        """The control: absent settings are not transient, so the rebuild costs no fetch at all."""
        tokens = PubSubPushTokens(verifier=None,
                                  build=lambda: build_google_push_verifier(
                                      _play_config(push_audience=None)))

        with pytest.raises(Unavailable):
            await tokens.verify(_push_token())
        assert len(jwks) == 0


class TestTheRebuildIsSerializedAndFloored:
    """WR-02: the rebuild runs before the bearer is examined at all, on one of the two routes
    outside the gateway's JWT policy, so unguarded one burst pays a blocking fetch per delivery."""

    async def test_one_burst_of_deliveries_shares_a_single_rebuild(self, jwks):
        """Every caller reaches the guard before the first fetch returns, so only the lock parts them."""
        jwks.fetch_delay = 0.02
        tokens = PubSubPushTokens(verifier=None,
                                  build=lambda: build_google_push_verifier(_play_config()))

        await asyncio.gather(*(tokens.verify(_push_token()) for _ in range(8)))

        assert len(jwks) == 1, "one rebuild for the burst, and not one per delivery"

    async def test_a_rebuild_that_failed_is_not_retried_within_the_interval(self, jwks):
        """The rate floor: nothing else records that a rebuild was just attempted and failed."""
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")
        tokens = PubSubPushTokens(verifier=None,
                                  build=lambda: build_google_push_verifier(_play_config()))

        for _ in range(5):
            with pytest.raises(Unavailable):
                await tokens.verify(_push_token())

        assert len(jwks) == 1, "the first delivery's attempt, and none of the four behind it"

    async def test_the_interval_elapsing_still_recovers_the_route(self, jwks):
        """WR-41's intent, kept: the floor delays the retry and never cancels it."""
        jwks.error = urllib.error.URLError("the JWKS endpoint is unreachable")
        tokens = PubSubPushTokens(verifier=None,
                                  build=lambda: build_google_push_verifier(_play_config()),
                                  rebuild_interval_seconds=0.0)

        with pytest.raises(Unavailable):
            await tokens.verify(_push_token())
        jwks.error = None

        assert await tokens.verify(_push_token()) is None
        assert len(jwks) == 2, "the refused attempt, then the one that recovered the route"
