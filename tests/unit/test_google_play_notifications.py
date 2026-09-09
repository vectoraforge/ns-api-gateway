"""The Google state map, the arms that answer without writing, and the push-token claim pins.
A throwaway keypair mints the push tokens and an `httpx.MockTransport` answers the Play read.
Untested by construction: only whether Google's live tokens and answers match Google's own shapes."""
import ast
import base64
import inspect
import json
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
from jwt.exceptions import PyJWKClientConnectionError

from nativespeaker.api.app.dependencies import verify_google_play_notification
from nativespeaker.api.app.lifespan import build_google_push_verifier
from nativespeaker.api.auth.google_play import (
    GOOGLE_ISSUER,
    GOOGLE_JWKS_URL,
    PlayDeveloperSubscriptions,
    PubSubPushTokens,
    developer_notification_from,
)
from nativespeaker.api.auth.jwt_verifier import DECODE_OPTIONS, BoundedReason, JWTVerifier
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.config import GooglePlayConfig
from nativespeaker.api.errors import InternalError, NotificationRejected, Unavailable
from nativespeaker.api.schemas.webhooks import PubSubPushRequest
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


def _play_reader(handler, *, products: dict[str, str] | None = None,
                 credential=None) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and a captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential() if credential is None else credential,
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
        """Read off the signature: a surviving source would let a later edit silently use it again."""
        parameters = set(inspect.signature(PlayDeveloperSubscriptions.__init__).parameters)
        assert parameters == {"self", "credential", "client", "products"}


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

    async def test_a_real_token_still_reaches_play(self, play_logs):
        """The control: a guard that refused everything would pass every case above."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)))

        assert await _read_through(reader) is not None
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
    # Verified to be the value the call actually passes, not merely a constant beside it.
    assert any(keyword.arg == "options" and isinstance(keyword.value, ast.Name)
               and keyword.value.id == "DECODE_OPTIONS"
               for node in ast.walk(ast.parse(VERIFIER_MODULE.read_text()))
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "decode"
               for keyword in node.keywords), \
        "the verifier's `jwt.decode` call is not the one carrying DECODE_OPTIONS"
    return required


# Each arm of the push-token check, with the bounded reason the refusal carries as its `stage`.
TOKEN_REFUSALS = [
    ({"private_key": FOREIGN_PRIVATE_KEY_PEM}, "bad_signature"),
    ({"email": "someone-else@example-project.iam.gserviceaccount.com"}, "bad_signature"),
    ({"email_verified": False}, "bad_signature"),
    ({"aud": "https://api.example.com/webhooks/somewhere-else"}, "audience_mismatch"),
    ({"iss": "https://accounts.example.com"}, "issuer_mismatch"),
]
TOKEN_REFUSAL_IDS = ["signature", "email", "email-verified", "aud", "iss"]


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

    def test_bounded_reason_stays_inside_the_closed_set_the_specs_name(self):
        """A member outside those eight would be a refusal word no spec closed over."""
        assert set(BoundedReason) <= {"missing_token", "malformed", "duplicate_authorization",
                                      "bad_signature", "issuer_mismatch", "audience_mismatch",
                                      "expired", "empty_subject"}

    def test_email_is_compared_after_decode_rather_than_required(self):
        """In `require`, a Google token shape without `email` would fail like a forgery (P-03)."""
        assert "email" not in _require_list()
        assert _require_list() == ["exp", "iat", "aud", "iss", "sub"]


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

    @pytest.mark.parametrize("absent", ["push_audience", "push_service_account_email"])
    def test_an_unconfigured_value_answers_none_without_a_fetch(self, absent, jwks):
        assert build_google_push_verifier(_play_config(**{absent: None})) is None
        assert len(jwks) == 0, "an unconfigured deployment must not reach for Google's keys"
