"""Both restore proofs: the Apple transaction minted against a throwaway chain, and the Play read.
The store call's place in the request is measured here too: it runs before the session's first statement.
Untested by construction: only whether the two stores' live artifacts match their declared shapes."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from appstoreserverlibrary.signed_data_verifier import VerificationStatus
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth.google_play import GRACE_STATE, PlayDeveloperSubscriptions
from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.crud.violations import UNIQUE_VIOLATION, is_unique_violation
from nativespeaker.api.errors import (
    InternalError,
    PurchaseProofRejected,
    RestoreSubscriptionNotEntitled,
    Unavailable,
    UnmappedStoreProduct,
)
from nativespeaker.api.schemas.auth import LinkedIdentity
from nativespeaker.api.services.restore import RestoreService
from nativespeaker.api.tables import (
    AccessGrantSource,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    PurchaseProvider,
    SubscriptionStatus,
)
from nativespeaker.api.tables.users import User
from unit.test_app_store_notifications import (
    APPLE_ROOT_G3,
    ATTRIBUTION_TOKEN,
    ORIGINAL_TRANSACTION_ID,
    PRODUCT_ID,
    TIER_ID,
    _build_chain,
    _Chain,
    _milliseconds,
    _mint,
    _notifications,
)
from unit.test_app_store_notifications import (
    _transaction as _wall_clock_transaction,
)
from unit.test_google_play_notifications import (
    ATTRIBUTION_TOKEN as PLAY_ATTRIBUTION_TOKEN,
)
from unit.test_google_play_notifications import (
    PRODUCT_ID as PLAY_PRODUCT_ID,
)
from unit.test_google_play_notifications import (
    PURCHASE_TOKEN,
    PURCHASED_AT,
    UNEXPIRED,
    _answering,
    _FakeCredential,
    _StaleCredential,
    _subscription_body,
)
from unit.test_google_play_notifications import (
    TIER_ID as PLAY_TIER_ID,
)

# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)

# The application name the dependency passes in production; the Apple check never reads it.
PACKAGE_NAME = "com.nativespeaker.app"

GONE_STAGE = "play_token_gone"
TOKEN_UNUSABLE_STAGE = "play_restore_token_unusable"
READ_STAGE = "play_restore_read"
UNCONFIGURED_STAGE = "play_restore_unconfigured"
PACKAGE_STAGE = "play_restore_package_unusable"
TRANSPORT_STAGE = "play_restore_transport"
UNPARSEABLE_STAGE = "play_restore_unparseable"

# The fixed part of the read path, which every caller-supplied value must be measured against.
PLAY_TOKENS_PATH = f"/androidpublisher/v3/applications/{PACKAGE_NAME}/purchases/subscriptionsv2/tokens/"

DEFERRED_KEY_VIOLATION = "23503"


class _Orig(Exception):
    """The DBAPI exception SQLAlchemy wraps, carrying the one attribute the writer reads."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


@pytest.fixture(scope="module")
def chain() -> _Chain:
    """One throwaway chain for the whole module: three key generations and three signings."""
    return _build_chain()


def _proof_through(chain: _Chain, transaction: dict, *,
                   evaluated_at: datetime = EVALUATED_AT) -> RestoredSubscription:
    """One restore check on the real seam, with the arguments the service passes in production."""
    return _notifications(chain).verify_transaction(_mint(chain, transaction), evaluated_at)


def _transaction(**fields) -> dict:
    """The Apple payload dated against `EVALUATED_AT`, which is what makes the claim above true.
    The imported helper dates itself from the wall clock, so every case here must pin the instant."""
    return _wall_clock_transaction(now=EVALUATED_AT, **fields)


def _dated(offset: timedelta) -> dict:
    """A transaction whose term ends `offset` from the captured instant, and nothing else changed."""
    return _transaction() | {"expiresDate": _milliseconds(EVALUATED_AT + offset)}


class TestTheRealChainVerifiesTheRestoreProof:
    """The library's chain walk, both OID checks, the ES256 rule and the signature check all run here."""

    def test_a_transaction_minted_by_the_chain_verifies_and_names_its_subscription(self, chain):
        restored = _proof_through(chain, _transaction())

        assert isinstance(restored, RestoredSubscription)
        assert restored.provider is PurchaseProvider.apple
        assert restored.external_id == ORIGINAL_TRANSACTION_ID
        assert restored.product_id == PRODUCT_ID
        assert restored.tier_id == TIER_ID
        assert restored.attribution_token == ATTRIBUTION_TOKEN
        assert restored.purchased_at == EVALUATED_AT
        assert restored.expires_at == EVALUATED_AT + timedelta(days=30)

    def test_the_vendored_apple_root_refuses_the_same_proof_control(self, chain):
        """The control that makes the case above non-vacuous: the real root does not sign this chain."""
        assert APPLE_ROOT_G3.is_file(), f"{APPLE_ROOT_G3} is the pinned root and must be tracked"
        notifications = _notifications(chain, root_certificates=[APPLE_ROOT_G3.read_bytes()])

        with pytest.raises(PurchaseProofRejected) as refusal:
            notifications.verify_transaction(_mint(chain, _transaction()), EVALUATED_AT)

        assert refusal.value.stage == "VERIFICATION_FAILURE"

    def test_an_unconfigured_deployment_answers_unavailable_and_never_decodes(self, chain):
        """No verifier is an operator state, not a refusal the caller earned, so it is a 503."""
        from nativespeaker.api.auth.app_store import AppStoreNotifications

        with pytest.raises(Unavailable) as refusal:
            AppStoreNotifications(verifier=None, products={}).verify_transaction(
                _mint(chain, _transaction()), EVALUATED_AT)

        assert refusal.value.stage == "app_store_verify"


class TestTheStatusComesFromTheTransactionAlone:
    """A bare transaction carries no `data.status`, so the three reachable words are derived here."""

    def test_a_revoked_transaction_reports_revoked(self, chain):
        revoked = _transaction(revocation_date=_milliseconds(EVALUATED_AT - timedelta(days=1)))

        assert _proof_through(chain, revoked).status is SubscriptionStatus.revoked

    def test_a_term_ending_after_the_captured_instant_reports_active(self, chain):
        assert _proof_through(chain, _dated(timedelta(days=10))).status is SubscriptionStatus.active

    def test_a_term_ending_before_the_captured_instant_reports_expired(self, chain):
        assert _proof_through(chain, _dated(-timedelta(days=1))).status is SubscriptionStatus.expired

    def test_revocation_wins_over_a_term_that_has_not_ended(self, chain):
        """The order is the rule: a refunded subscription inside its paid term is still revoked."""
        revoked = _dated(timedelta(days=10)) | {
            "revocationDate": _milliseconds(EVALUATED_AT - timedelta(days=1))}

        assert _proof_through(chain, revoked).status is SubscriptionStatus.revoked

    def test_grace_period_is_unreachable_from_a_proof_that_carries_no_renewal_payload(self, chain):
        """Pitfall 5: an Apple restore can report three of the five words, and never the other two."""
        reachable = {_proof_through(chain, transaction).status
                     for transaction in (_transaction(),
                                         _dated(-timedelta(days=1)),
                                         _transaction(revocation_date=_milliseconds(EVALUATED_AT)))}

        assert reachable == {SubscriptionStatus.active, SubscriptionStatus.expired,
                             SubscriptionStatus.revoked}


class TestAProofThatDoesNotVerifyIsRefusedWithoutNamingItself:
    """T-45-04: the refusal's `stage` is one of the library's own eight names and carries no payload."""

    def test_an_unmapped_apple_product_is_the_operator_error_and_not_a_refusal(self, chain):
        unmapped = _transaction() | {"productId": "com.example.not-in-the-configured-map"}

        with pytest.raises(UnmappedStoreProduct):
            _proof_through(chain, unmapped)

    def test_a_field_of_the_wrong_type_is_refused_rather_than_reaching_the_generic_500(self, chain):
        """WR-17: the library structures the transaction outside its own guard, so a cattrs error
        escaped this seam; a proof that will never structure is this caller's refusal to earn."""
        with pytest.raises(PurchaseProofRejected) as refusal:
            _proof_through(chain, {**_transaction(), "expiresDate": "nope"})

        assert refusal.value.stage == "payload_unstructurable"

    def test_the_three_arms_are_three_distinct_names_from_the_closed_set(self, chain):
        """`VerificationStatus.name` is a fixed set of strings, which is what makes it a safe label."""
        short_chain = _mint(chain, _transaction(), x5c=chain.x5c[:2])
        stages = []
        for proof in (short_chain,
                      _mint(chain, _transaction(bundle_id="com.example.someone-else")),
                      _mint(chain, _transaction(environment="Production"))):
            with pytest.raises(PurchaseProofRejected) as refusal:
                _notifications(chain).verify_transaction(proof, EVALUATED_AT)
            stages.append(refusal.value.stage)

        assert set(stages) <= {status.name for status in VerificationStatus}
        assert len(set(stages)) == 3

    def test_no_stage_and_no_message_carries_any_part_of_the_proof(self, chain):
        proof = _mint(chain, _transaction(bundle_id="com.example.someone-else"))

        with pytest.raises(PurchaseProofRejected) as refusal:
            _notifications(chain).verify_transaction(proof, EVALUATED_AT)

        for segment in proof.split("."):
            assert segment not in refusal.value.stage
            assert segment not in str(refusal.value)


def _play_reader(handler, *, products: dict[str, str] | None = None,
                 credential=None) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and this module's captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential() if credential is None else credential,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        products={PLAY_PRODUCT_ID: PLAY_TIER_ID} if products is None else products)


async def _restore_through(reader: PlayDeveloperSubscriptions) -> RestoredSubscription:
    """One restore read on this reader, with the arguments the service passes in production."""
    return await reader.read_for_restore(package_name=PACKAGE_NAME,
                                         purchase_token=PURCHASE_TOKEN,
                                         evaluated_at=EVALUATED_AT)


async def _play_restore(state: str, *, expiry: datetime | None = UNEXPIRED) -> RestoredSubscription:
    """Read one subscription in this state through the real class, and return the value type."""
    return await _restore_through(_play_reader(_answering(_subscription_body(state, expiry=expiry))))


class TestThePlayReadReportsTheRestoreValueType:
    """The purchase token is the only handle this subscription has, so it is the external id."""

    async def test_a_live_subscription_is_reported_in_the_restore_value_type(self):
        restored = await _play_restore("SUBSCRIPTION_STATE_ACTIVE")

        assert isinstance(restored, RestoredSubscription)
        assert restored.provider is PurchaseProvider.google_play
        assert restored.external_id == PURCHASE_TOKEN
        assert restored.product_id == PLAY_PRODUCT_ID
        assert restored.tier_id == PLAY_TIER_ID
        assert restored.attribution_token == PLAY_ATTRIBUTION_TOKEN
        assert restored.status is SubscriptionStatus.active
        assert restored.purchased_at == PURCHASED_AT
        assert restored.expires_at == UNEXPIRED

    async def test_the_status_comes_from_the_state_map_the_webhook_already_uses(self):
        """`_status_for` is reused, so both entry points read one state map and never two."""
        restored = await _play_restore("SUBSCRIPTION_STATE_ON_HOLD")

        assert restored.status is SubscriptionStatus.billing_retry

    async def test_a_subscription_in_grace_carries_the_line_items_expiry_as_its_window(self):
        restored = await _play_restore(GRACE_STATE)

        assert restored.status is SubscriptionStatus.grace_period
        assert restored.grace_period_expires_at == UNEXPIRED
        assert restored.grace_period_expires_at == restored.expires_at

    async def test_a_subscription_outside_grace_carries_no_window_control(self):
        """The control that makes the case above non-vacuous: the field is not always the expiry."""
        assert (await _play_restore("SUBSCRIPTION_STATE_ACTIVE")).grace_period_expires_at is None


def _capturing_reader() -> tuple[list[httpx.Request], PlayDeveloperSubscriptions]:
    """A reader that records every request it sends, so a case reads the URL httpx built."""
    sent: list[httpx.Request] = []
    answer = _answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE"))

    def _record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return answer(request)

    return sent, _play_reader(_record)


class TestThePlayRequestUrlIsConfinedToOneResource:
    """T-45-06-01: the caller's own token names one path segment of the intended resource, and no other."""

    async def test_a_token_carrying_path_traversal_names_one_segment_and_no_other_path(self):
        sent, reader = _capturing_reader()

        await reader.read_for_restore(package_name=PACKAGE_NAME,
                                      purchase_token="a/../../../../v3/applications/evil/edits",
                                      evaluated_at=EVALUATED_AT)

        # The wire form, because `url.path` percent-decodes and would hide the escaping this asserts.
        path = sent[0].url.raw_path.decode()
        assert path.startswith(PLAY_TOKENS_PATH)
        assert "evil" not in path.split("/")

    async def test_a_token_carrying_a_query_string_leaves_the_query_empty(self):
        sent, reader = _capturing_reader()

        await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token="x?alt=media",
                                      evaluated_at=EVALUATED_AT)

        assert sent[0].url.query == b""

    async def test_a_package_name_carrying_a_separator_is_escaped_too(self):
        """The guard cannot be escaped from either side, so both interpolated values are escaped."""
        sent, reader = _capturing_reader()

        await reader.read_for_restore(package_name=f"{PACKAGE_NAME}/evil",
                                      purchase_token=PURCHASE_TOKEN, evaluated_at=EVALUATED_AT)

        path = sent[0].url.raw_path.decode()
        assert "/" not in path.split("/applications/")[1].split("/purchases")[0]

    async def test_an_ordinary_token_reaches_the_expected_path_control(self):
        """The control: without it the three cases above would pass a read that called Play no more."""
        sent, reader = _capturing_reader()

        restored = await reader.read_for_restore(package_name=PACKAGE_NAME,
                                                 purchase_token=PURCHASE_TOKEN,
                                                 evaluated_at=EVALUATED_AT)

        assert sent[0].url.raw_path.decode() == PLAY_TOKENS_PATH + PURCHASE_TOKEN
        assert isinstance(restored, RestoredSubscription)
        # The escaping is the URL's alone: the persisted external id stays the token Google gave.
        assert restored.external_id == PURCHASE_TOKEN

    @pytest.mark.parametrize("token", [".", "..", "...."])
    async def test_a_dot_only_token_is_refused_and_reaches_no_transport(self, token):
        """`quote` leaves a dot unescaped and the client deletes a dot segment, so dots name nothing."""
        sent, reader = _capturing_reader()

        with pytest.raises(PurchaseProofRejected) as refusal:
            await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token=token,
                                          evaluated_at=EVALUATED_AT)

        assert refusal.value.stage == GONE_STAGE
        assert sent == []

    async def test_a_dot_only_package_name_is_an_operator_state_and_reaches_no_transport(self):
        """The application name is operator configuration, so dots alone are a 503 and not a refusal."""
        sent, reader = _capturing_reader()

        with pytest.raises(Unavailable) as refusal:
            await reader.read_for_restore(package_name="..", purchase_token=PURCHASE_TOKEN,
                                          evaluated_at=EVALUATED_AT)

        assert refusal.value.stage == PACKAGE_STAGE
        assert sent == []

    async def test_a_token_carrying_dots_among_other_characters_is_still_read_control(self):
        """The control: a real Play token carries dots, so only a token of dots alone is refused."""
        sent, reader = _capturing_reader()

        restored = await reader.read_for_restore(package_name=PACKAGE_NAME,
                                                 purchase_token="a.b..c", evaluated_at=EVALUATED_AT)

        assert sent[0].url.raw_path.decode() == PLAY_TOKENS_PATH + "a.b..c"
        assert restored.external_id == "a.b..c"


class TestThePlayAnswerIsClassifiedBeforeItIsParsed:
    """D-05: a gone token is a rejected proof, as is a token Play cannot read; every other
    failure is a 503 the app retries."""

    @pytest.mark.parametrize("status_code", [404, 410])
    async def test_a_gone_purchase_token_is_a_rejected_proof(self, status_code):
        reader = _play_reader(_answering({"error": {"status": "NOT_FOUND"}}, status_code))

        with pytest.raises(PurchaseProofRejected) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == GONE_STAGE
        assert refusal.value.status == 403

    async def test_a_token_play_cannot_read_is_a_rejected_proof(self):
        """WR-36: Play answers 400 for a token that does not parse and for one naming another
        application. No later attempt changes either, so `verification_temporarily_unavailable`
        would ask a well-behaved client to retry a proof that can never verify."""
        reader = _play_reader(_answering({"error": {"status": "INVALID_ARGUMENT"}}, 400))

        with pytest.raises(PurchaseProofRejected) as refusal:
            await _restore_through(reader)

        assert (refusal.value.stage, refusal.value.status) == (TOKEN_UNUSABLE_STAGE, 403)
        assert refusal.value.stage != GONE_STAGE

    @pytest.mark.parametrize("status_code,cause", [(401, "refused"),
                                                   (403, "refused"), (429, "refused"),
                                                   (500, "failed"), (502, "failed"),
                                                   (503, "failed")])
    async def test_every_other_non_2xx_status_is_temporarily_unavailable(self, status_code, cause):
        reader = _play_reader(_answering({"error": {"status": "UNAVAILABLE"}}, status_code))

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == READ_STAGE
        assert refusal.value.status == 503
        assert refusal.value.log_fields() == {"stage": READ_STAGE, "cause": cause}

    async def test_a_transport_failure_is_temporarily_unavailable(self):
        def _unreachable(_request):
            raise httpx.ConnectError("the Play endpoint is unreachable")

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(_play_reader(_unreachable))

        assert refusal.value.stage == TRANSPORT_STAGE

    async def test_a_refused_credential_refresh_is_temporarily_unavailable(self):
        """WR-11: a `GoogleAuthError` is no `httpx` failure, so the transport arm alone misses it."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)),
                              credential=_StaleCredential())

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == TRANSPORT_STAGE

    async def test_a_2xx_carrying_no_json_is_temporarily_unavailable(self):
        """WR-11: an intermediary's HTML page reaches this read as a `200` the app must retry."""
        reader = _play_reader(lambda _request: httpx.Response(200, text="<html>502</html>"))

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == UNPARSEABLE_STAGE

    async def test_a_2xx_this_build_cannot_read_carries_no_play_value_into_its_refusal(self):
        """WR-11: pydantic echoes the rejected input, so the cause is dropped and not chained."""
        reader = _play_reader(_answering({"lineItems": [{"productId": PLAY_PRODUCT_ID}]}))

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == UNPARSEABLE_STAGE
        assert refusal.value.__cause__ is None

    async def test_an_absent_credential_is_unavailable_and_reaches_no_transport(self):
        """No credential is an operator state, not a refusal the caller earned, so it is a 503."""
        def _never(request):
            raise AssertionError(f"an unconfigured deployment reached {request.url}")

        reader = PlayDeveloperSubscriptions(
            credential=None,
            client=httpx.AsyncClient(transport=httpx.MockTransport(_never)),
            products={})

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == UNCONFIGURED_STAGE

    async def test_an_unmapped_play_product_is_the_operator_error_and_not_a_503(self):
        """Pitfall 1: this class is an `InternalError`, so a caught base class would hide it here."""
        reader = _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE",
                                                            expiry=UNEXPIRED)),
                              products={"another.product.entirely": PLAY_TIER_ID})

        with pytest.raises(UnmappedStoreProduct) as failure:
            await _restore_through(reader)

        assert failure.value.status == 500
        assert not isinstance(failure.value, Unavailable)


class TestThePlayRefusalNamesNoPartOfTheToken:
    """T-45-04: on this path the external id is the purchase token, so no label may carry it."""

    @pytest.mark.parametrize(("status_code", "refusal_type"),
                             [(404, PurchaseProofRejected), (500, Unavailable)])
    async def test_neither_the_stage_nor_the_message_nor_the_log_fields_carry_it(
            self, status_code, refusal_type):
        reader = _play_reader(_answering({"error": {"status": "NOT_FOUND"}}, status_code))

        with pytest.raises(refusal_type) as refusal:
            await _restore_through(reader)

        assert PURCHASE_TOKEN not in refusal.value.stage
        assert PURCHASE_TOKEN not in str(refusal.value)
        assert PURCHASE_TOKEN not in str(refusal.value.log_fields())


class _Stop(Exception):
    """Raised by the counting session at its first statement, so the case ends where it measures."""


class _CountingSession:
    """A session stand-in on `_RacedSession`'s shape, counting statements instead of racing them."""

    def __init__(self) -> None:
        self.statements = 0

    async def exec(self, *args, **kwargs):
        self.statements += 1
        raise _Stop

    async def commit(self, *args, **kwargs):
        raise AssertionError("a case that stops at the first statement must not commit")

    async def rollback(self, *args, **kwargs):
        raise AssertionError("a case that stops at the first statement must not roll back")


class _ScriptedAppStore:
    """The Apple check as a fake, recording the session's statement count at the moment it ran."""

    def __init__(self, session: _CountingSession, answer) -> None:
        self._session = session
        self._answer = answer
        self.statements_at_call: int | None = None

    def verify_transaction(self, signed_transaction: str, evaluated_at: datetime):
        self.statements_at_call = self._session.statements
        if isinstance(self._answer, BaseException):
            raise self._answer
        return self._answer


class _ScriptedPlay:
    """The Play read as a fake, recording the session's statement count at the moment it ran."""

    def __init__(self, session: _CountingSession, answer) -> None:
        self._session = session
        self._answer = answer
        self.statements_at_call: int | None = None

    async def read_for_restore(self, *, package_name: str, purchase_token: str,
                               evaluated_at):
        self.statements_at_call = self._session.statements
        if isinstance(self._answer, BaseException):
            raise self._answer
        return self._answer


def _restored() -> RestoredSubscription:
    """What a verified Apple proof reports, in the value type the service consumes."""
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=ORIGINAL_TRANSACTION_ID,
                                product_id=PRODUCT_ID,
                                tier_id=TIER_ID,
                                attribution_token=ATTRIBUTION_TOKEN,
                                status=SubscriptionStatus.active,
                                purchased_at=EVALUATED_AT - timedelta(days=1),
                                expires_at=EVALUATED_AT + timedelta(days=30),
                                grace_period_expires_at=None)


def _play_restored() -> RestoredSubscription:
    """What the Play read reports, in the same value type: only the provider and the id differ."""
    return RestoredSubscription(provider=PurchaseProvider.google_play,
                                external_id=PURCHASE_TOKEN,
                                product_id=PLAY_PRODUCT_ID,
                                tier_id=PLAY_TIER_ID,
                                attribution_token=PLAY_ATTRIBUTION_TOKEN,
                                status=SubscriptionStatus.active,
                                purchased_at=EVALUATED_AT - timedelta(days=1),
                                expires_at=EVALUATED_AT + timedelta(days=30),
                                grace_period_expires_at=None)


def _service(session: _CountingSession, store: _ScriptedAppStore,
             play: _ScriptedPlay | None = None) -> RestoreService:
    return RestoreService(db=session, evaluated_at=EVALUATED_AT, app_store=store,
                          play=_ScriptedPlay(session, _play_restored()) if play is None else play,
                          package_name=PACKAGE_NAME)


ISSUER = "https://issuer.test"
SUBJECT = "restore-ordering-subject"


def _caller() -> LinkedIdentity:
    """The shape the barrier hands the handler: `resolve` sets the two rows together or neither,
    so a user standing beside `identity=None` stands in for a state production cannot produce."""
    user = User()
    return LinkedIdentity(issuer=ISSUER, subject=SUBJECT, user=user,
                          identity=ExternalIdentity(user_id=user.id, issuer=ISSUER,
                                                    subject=SUBJECT,
                                                    provider=IdentityProvider.google,
                                                    provider_uid="google-account-restore",
                                                    identity_state=IdentityState.active))


class TestTheStoreCallRunsBeforeTheSessionsFirstStatement:
    """SHARED-INVARIANTS: no network call may run with a transaction open, and the first statement opens one."""

    async def test_the_apple_check_ran_while_the_statement_count_was_still_zero(self):
        session = _CountingSession()
        store = _ScriptedAppStore(session, _restored())

        with pytest.raises(_Stop):
            await _service(session, store).restore(identity=_caller(),
                                                   provider=PurchaseProvider.apple,
                                                   restore_proof="a-signed-transaction")

        assert store.statements_at_call == 0
        assert session.statements == 1

    async def test_the_play_read_ran_while_the_statement_count_was_still_zero(self):
        """The second store has the same place in the request, and it is measured the same way."""
        session = _CountingSession()
        store = _ScriptedAppStore(session, _restored())
        play = _ScriptedPlay(session, _play_restored())

        with pytest.raises(_Stop):
            await _service(session, store, play).restore(identity=_caller(),
                                                         provider=PurchaseProvider.google_play,
                                                         restore_proof="a-purchase-token")

        assert play.statements_at_call == 0
        assert session.statements == 1

    async def test_exactly_one_store_is_called_per_request(self):
        """The dispatch names one member, so the other store's check never also runs."""
        session = _CountingSession()
        store = _ScriptedAppStore(session, _restored())
        play = _ScriptedPlay(session, _play_restored())

        with pytest.raises(_Stop):
            await _service(session, store, play).restore(identity=_caller(),
                                                         provider=PurchaseProvider.apple,
                                                         restore_proof="a-signed-transaction")

        assert store.statements_at_call == 0
        assert play.statements_at_call is None

    async def test_a_proof_that_does_not_verify_runs_no_statement_either(self):
        session = _CountingSession()
        store = _ScriptedAppStore(session, PurchaseProofRejected(stage="VERIFICATION_FAILURE"))

        with pytest.raises(PurchaseProofRejected):
            await _service(session, store).restore(identity=_caller(),
                                                   provider=PurchaseProvider.apple,
                                                   restore_proof="a-forged-transaction")

        assert session.statements == 0
        assert store.statements_at_call == 0

    async def test_a_gone_purchase_token_runs_no_statement_either(self):
        """T-45-03: a fabricated token is refused by Google, so nothing is read and nothing written."""
        session = _CountingSession()
        play = _ScriptedPlay(session, PurchaseProofRejected(stage=GONE_STAGE))

        with pytest.raises(PurchaseProofRejected):
            await _service(session, _ScriptedAppStore(session, _restored()), play).restore(
                identity=_caller(), provider=PurchaseProvider.google_play,
                restore_proof="a-fabricated-purchase-token")

        assert session.statements == 0
        assert play.statements_at_call == 0

    async def test_the_counting_session_really_counts_control(self):
        """The control: a recorder that never incremented would pass the two zero cases above."""
        session = _CountingSession()

        with pytest.raises(_Stop):
            await session.exec("any statement")

        assert session.statements == 1


class _InsertOnlyRecorder:
    """The two reads the create branch makes, and a recorder for whichever writer it then calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read_subscription(self, provider, external_id):
        return None

    async def read_purchase(self, provider, external_id):
        return None

    async def lock_grants_of(self, user_ids, *, counted_for):
        self.calls.append("lock_grants_of")
        return []

    async def insert_subscription(self, **fields):
        self.calls.append("insert_subscription")
        raise _Stop

    async def upsert_subscription(self, **fields):
        self.calls.append("upsert_subscription")
        raise _Stop


class _NoAttribution:
    """The purchases read the create branch makes, answering that this proof is attributed to nobody."""

    async def resolve_user(self, provider, token):
        return None


class TestTheCreateBranchNeverOverwritesARowCommittedSinceItsRead:
    """WR-02: the in-place updater re-reads under READ COMMITTED, so it could write over a webhook's status."""

    async def test_the_create_branch_calls_the_insert_only_writer_and_nothing_else(self):
        session = _CountingSession()
        service = _service(session, _ScriptedAppStore(session, _restored()))
        recorder = _InsertOnlyRecorder()
        service.subscriptions_db = recorder
        service.purchases_db = _NoAttribution()

        with pytest.raises(_Stop):
            await service.restore(identity=_caller(), provider=PurchaseProvider.apple,
                                  restore_proof="a-signed-transaction")

        assert recorder.calls == ["lock_grants_of", "insert_subscription"]


class _CommittingSession(_CountingSession):
    """The counting session for the cases that run to the end: it commits rather than refusing to."""

    def __init__(self, refusal: BaseException | None = None) -> None:
        super().__init__()
        self.commits = 0
        self.rollbacks = 0
        self._refusal = refusal

    async def commit(self, *args, **kwargs):
        self.commits += 1
        if self._refusal is not None:
            raise self._refusal

    async def rollback(self, *args, **kwargs):
        self.rollbacks += 1


class _GrantRecorder:
    """The subscriptions crud as a recorder, on the branch that reaches the grant writer directly."""

    def __init__(self, destination, settled_status=SubscriptionStatus.active,
                 settled_tier: str = TIER_ID, *, purchase_recorded: bool = True) -> None:
        self.granted: list[dict] = []
        self.purchases: list[dict] = []
        self._settled_status = settled_status
        self._settled_tier = settled_tier
        self._purchase_recorded = purchase_recorded
        self.destination = destination
        self.reads = 0
        self._stored = SimpleNamespace(id=uuid4(), user_id=destination, tier_id=TIER_ID,
                                       status=SubscriptionStatus.active,
                                       last_cross_account_transfer_month=None)

    async def read_subscription(self, provider, external_id):
        self.reads += 1
        if self.reads > 1:
            self._stored.status = self._settled_status
            self._stored.tier_id = self._settled_tier
        return self._stored

    async def read_purchase(self, provider, external_id):
        if not self._purchase_recorded:
            return None
        return SimpleNamespace(id=uuid4(), resolved_token_value=None)

    async def insert_purchase(self, **fields):
        self.purchases.append(fields)
        return WriteOutcome.applied

    async def lock_grants_of(self, user_ids, *, counted_for):
        return []

    async def write_subscription_grant(self, **fields):
        self.granted.append(fields)
        return WriteOutcome.applied


async def _same_account_restore(purchased_at, settled_status=SubscriptionStatus.active,
                                session: _CommittingSession | None = None,
                                settled_tier: str = TIER_ID, *,
                                purchase_recorded: bool = True,
                                attributed_to_caller: bool = False
                                ) -> tuple[_GrantRecorder, _CommittingSession]:
    """One same-account restore of a proof carrying `purchased_at`, against a canonical row whose
    status and tier under the grant locks are `settled_status` and `settled_tier`."""
    session = _CommittingSession() if session is None else session
    caller = _caller()
    recorder = _GrantRecorder(caller.user.id, settled_status, settled_tier,
                              purchase_recorded=purchase_recorded)
    proof = RestoredSubscription(provider=PurchaseProvider.apple,
                                 external_id=ORIGINAL_TRANSACTION_ID,
                                 product_id=PRODUCT_ID,
                                 tier_id=TIER_ID,
                                 attribution_token=ATTRIBUTION_TOKEN,
                                 status=SubscriptionStatus.active,
                                 purchased_at=purchased_at,
                                 expires_at=EVALUATED_AT + timedelta(days=30),
                                 grace_period_expires_at=None)
    service = _service(session, _ScriptedAppStore(session, proof))
    service.subscriptions_db = recorder
    service.purchases_db = (_AttributedToTheCaller(caller.user.id) if attributed_to_caller
                            else _NoAttribution())

    await service.restore(identity=caller, provider=PurchaseProvider.apple,
                          restore_proof="a-signed-transaction")
    return recorder, session


class _AttributedToTheCaller:
    """The purchases read answering that the store recorded this proof against the caller's own
    account, which is the branch where the deferred key has a binding row to point at."""

    def __init__(self, destination) -> None:
        self._destination = destination

    async def resolve_user(self, provider, token):
        return self._destination


class TestTheFirstRestoreOfAnUnrecordedPurchaseWritesItsRow:
    """WR-67: no purchase row for the pair, so the restore writes `core.store_purchases` itself.
    `resolved_token_value` is one half of a DEFERRABLE INITIALLY DEFERRED pair, so a value set
    where no binding row exists is refused at COMMIT and the client is told only 500."""

    async def test_a_token_that_binds_to_nobody_points_the_deferred_key_at_nothing(self):
        recorder, session = await _same_account_restore(EVALUATED_AT - timedelta(days=1),
                                                        purchase_recorded=False)

        assert session.commits == 1
        written = recorder.purchases[0]
        assert written["purchase_user_id"] is None
        assert written["resolved_token_value"] is None
        assert written["identity_value"] == ATTRIBUTION_TOKEN
        assert written["external_id"] == ORIGINAL_TRANSACTION_ID
        assert written["store_original_transaction_id"] == ORIGINAL_TRANSACTION_ID
        assert written["store_transaction_id"] is None
        assert written["provider"] is PurchaseProvider.apple

    async def test_a_token_that_binds_to_the_caller_names_the_binding_it_has(self):
        """The other half of the pair: a resolved token has a row to point at, so the key is set."""
        recorder, session = await _same_account_restore(EVALUATED_AT - timedelta(days=1),
                                                        purchase_recorded=False,
                                                        attributed_to_caller=True)

        assert session.commits == 1
        written = recorder.purchases[0]
        assert written["purchase_user_id"] == recorder.destination
        assert written["resolved_token_value"] == ATTRIBUTION_TOKEN

    async def test_a_recorded_purchase_is_never_written_twice_control(self):
        """The control: the two cases above are the unrecorded branch and not every restore."""
        recorder, _ = await _same_account_restore(EVALUATED_AT - timedelta(days=1))

        assert recorder.purchases == []


async def _grant_written(purchased_at) -> dict:
    """The fields the restore hands the grant writer for a proof carrying `purchased_at`."""
    recorder, session = await _same_account_restore(purchased_at)

    assert session.commits == 1
    return recorder.granted[0]


@pytest.fixture
def race_warnings(monkeypatch) -> list[tuple[str, dict]]:
    """A spy, not `capture_logs`: the module-level logger caches its binding at import."""
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr("nativespeaker.api.services.restore.logger.warning",
                        lambda event, **kwargs: entries.append((event, kwargs)))
    return entries


@pytest.fixture
def commit_errors(monkeypatch) -> list[tuple[str, dict]]:
    """A spy on the same logger's error level, for the refusals that are not races at all."""
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr("nativespeaker.api.services.restore.logger.error",
                        lambda event, **kwargs: entries.append((event, kwargs)))
    return entries


class TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated:
    """WR-11: COMMIT is the deferred pair's only evaluation, and both of them are FOREIGN KEYs --
    23503, which is the one class `is_unique_violation` exists to re-raise. Read as a lost race,
    a deterministic writer bug was retried forever with nothing in any log line naming it."""

    async def test_a_deferred_foreign_key_at_commit_is_not_read_as_a_race(self, race_warnings,
                                                                          commit_errors):
        """The cause survives: only the `IntegrityError` names the constraint that refused."""
        session = _CommittingSession(IntegrityError("COMMIT", {}, _Orig(DEFERRED_KEY_VIOLATION)))

        with pytest.raises(IntegrityError) as refused:
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert refused.value.orig.sqlstate == DEFERRED_KEY_VIOLATION
        assert (session.commits, session.rollbacks) == (1, 0)
        assert race_warnings == []

    async def test_the_refusal_names_the_code_the_constraint_carried(self, race_warnings,
                                                                      commit_errors):
        """`InternalError.log_level` is None, so before this line the failure was wholly silent."""
        session = _CommittingSession(IntegrityError("COMMIT", {}, _Orig(DEFERRED_KEY_VIOLATION)))

        with pytest.raises(IntegrityError):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert commit_errors == [("restore_commit_refused",
                                  {"sqlstate": DEFERRED_KEY_VIOLATION})]

    async def test_a_violation_carrying_no_readable_code_is_refused_too(self, race_warnings,
                                                                        commit_errors):
        """Fail-closed, exactly as `is_unique_violation` reads it: no code is not a race."""
        session = _CommittingSession(IntegrityError("COMMIT", {}, None))

        with pytest.raises(IntegrityError):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert commit_errors == [("restore_commit_refused", {"sqlstate": None})]
        assert race_warnings == []

    async def test_a_unique_violation_at_commit_is_still_the_lost_race(self, race_warnings,
                                                                       commit_errors):
        """The control on the classification: COMMIT flushes too, so a unique index can refuse a
        write the arms above never reached, and that one code is the race a retry recovers from."""
        session = _CommittingSession(IntegrityError("COMMIT", {}, _Orig(UNIQUE_VIOLATION)))

        with pytest.raises(InternalError):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert (session.commits, session.rollbacks) == (1, 1)
        assert race_warnings == [("restore_grant_race_lost", {"provider": "apple"})]
        assert commit_errors == []

    async def test_a_restore_that_wins_reports_neither_control(self, race_warnings, commit_errors):
        """The control: a line written unconditionally would pass the cases above and page on
        every ordinary restore."""
        recorder, session = await _same_account_restore(EVALUATED_AT - timedelta(days=1))

        assert (len(recorder.granted), session.commits) == (1, 1)
        assert (race_warnings, commit_errors) == ([], [])


class TestTheStatusIsReReadUnderTheGrantLocksBeforeAnythingIsWritten:
    """WR-61: the entitlement decision came from a plain read taken before the locks were taken."""

    @pytest.mark.parametrize("moved", [SubscriptionStatus.revoked,
                                       SubscriptionStatus.expired,
                                       SubscriptionStatus.grace_period])
    async def test_a_status_that_moved_under_the_locks_is_refused_with_nothing_written(self, moved):
        """A webhook owns canonical state; writing an entitled grant against a row it just moved
        reached the deferred entitlement key at COMMIT as an opaque 500, or committed a wrong term."""
        with pytest.raises(RestoreSubscriptionNotEntitled):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), moved)

    async def test_a_status_that_still_agrees_is_written_control(self):
        recorder, session = await _same_account_restore(EVALUATED_AT - timedelta(days=1))

        assert len(recorder.granted) == 1
        assert session.commits == 1


class TestTheTierIsReReadUnderTheGrantLocksAsWell:
    """WR-60: only the status was re-read, so the grant was written at the pre-lock tier."""

    async def test_a_tier_that_moved_under_the_locks_is_refused_with_nothing_written(self):
        """A tier-change webhook committed inside the window was silently reverted: the restore
        superseded the buyer's grants and re-inserted one at the tier its pre-lock read saw."""
        with pytest.raises(RestoreSubscriptionNotEntitled):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1),
                                        settled_tier="another-tier")

    async def test_a_tier_that_still_agrees_is_the_one_written_control(self):
        recorder, session = await _same_account_restore(EVALUATED_AT - timedelta(days=1))

        assert recorder.granted[0]["tier_id"] == TIER_ID
        assert session.commits == 1


class TestTheRestoredGrantNeverBeginsAfterTheInstantThatWroteIt:
    """WR-60: `10-restore-subscription.md:84(3)` requires `starts_at <= now` of the created grant."""

    async def test_a_purchase_date_ahead_of_the_captured_instant_is_capped_at_it(self):
        """Unclamped it wrote a row the shared effective predicate never reads, while that row still
        held `ix_access_grants_one_active_per_user` and refused every free claim behind it."""
        granted = await _grant_written(EVALUATED_AT + timedelta(days=2))

        assert granted["starts_at"] == EVALUATED_AT

    async def test_a_purchase_date_before_it_is_carried_through_control(self):
        """The control: the cap binds one direction only, so a real purchase date is still the start."""
        granted = await _grant_written(EVALUATED_AT - timedelta(days=1))

        assert granted["starts_at"] == EVALUATED_AT - timedelta(days=1)

    async def test_an_absent_purchase_date_is_the_captured_instant_control(self):
        granted = await _grant_written(None)

        assert granted["starts_at"] == EVALUATED_AT


GRACE_WINDOW_ENDS = EVALUATED_AT + timedelta(days=14)


class _GraceRecorder(_GrantRecorder):
    """The canonical row in `grace_period`, and -- where the webhook wrote one -- the grant it
    wrote for that row, answered from the grant locks as `lock_grants_of` answers in production."""

    def __init__(self, destination, ends_at: datetime | None) -> None:
        super().__init__(destination, SubscriptionStatus.grace_period)
        self._stored.status = SubscriptionStatus.grace_period
        self._locked = ([] if ends_at is None
                        else [SimpleNamespace(source=AccessGrantSource.subscription,
                                              subscription_id=self._stored.id,
                                              user_id=destination,
                                              ends_at=ends_at)])

    async def lock_grants_of(self, user_ids, *, counted_for):
        return self._locked


async def _grace_restore(ends_at: datetime | None) -> tuple[_GraceRecorder, _CommittingSession]:
    """One same-account restore of an Apple proof whose paid term has lapsed -- the only proof
    Apple can produce for a subscription it has put in grace -- against a `grace_period` row."""
    session = _CommittingSession()
    caller = _caller()
    recorder = _GraceRecorder(caller.user.id, ends_at)
    proof = RestoredSubscription(provider=PurchaseProvider.apple,
                                 external_id=ORIGINAL_TRANSACTION_ID,
                                 product_id=PRODUCT_ID,
                                 tier_id=TIER_ID,
                                 attribution_token=ATTRIBUTION_TOKEN,
                                 status=SubscriptionStatus.expired,
                                 purchased_at=EVALUATED_AT - timedelta(days=31),
                                 expires_at=EVALUATED_AT - timedelta(days=1),
                                 grace_period_expires_at=None)
    service = _service(session, _ScriptedAppStore(session, proof))
    service.subscriptions_db = recorder
    service.purchases_db = _NoAttribution()

    await service.restore(identity=caller, provider=PurchaseProvider.apple,
                          restore_proof="a-signed-transaction")
    return recorder, session


class TestTheTermIsReadFromWhateverDecidedTheStatus:
    """CR-25: the status came from the canonical row and the window from the client's proof, which
    on Apple can never agree for `grace_period` -- the proof states no grace window at all -- so a
    subscriber the store had put in grace was refused. The row's own webhook wrote both."""

    async def test_a_grace_row_restores_on_the_window_its_own_webhook_wrote(self):
        recorder, session = await _grace_restore(GRACE_WINDOW_ENDS)

        assert session.commits == 1
        assert [granted["ends_at"] for granted in recorder.granted] == [GRACE_WINDOW_ENDS]

    async def test_a_grace_row_with_no_recorded_term_is_still_refused_control(self):
        """The control: the case above passes because the locked grant answered, not because the
        term check was loosened -- with nothing recording the window, nothing entitles anything."""
        with pytest.raises(RestoreSubscriptionNotEntitled):
            await _grace_restore(None)


class _UnownedRecorder(_GrantRecorder):
    """The canonical row no account owns yet, which is the one state that runs the owner claim."""

    def __init__(self, destination, *, claim_wins: bool = True,
                 winner_owner: UUID | None = None) -> None:
        super().__init__(destination)
        self._stored.user_id = None
        self._claim_wins = claim_wins
        self._winner_owner = winner_owner
        self.claims: list[dict] = []

    async def claim_subscription_owner(self, **fields) -> bool:
        self.claims.append(fields)
        self._stored.user_id = fields["destination"] if self._claim_wins else self._winner_owner
        return self._claim_wins


def _adoption_restore(*, claim_wins: bool = True, winner_is_caller: bool = False):
    """One restore of an unowned row, built but not run: the refusing case reads the recorder
    afterwards, which a helper that ran the restore itself could not hand back."""
    session = _CommittingSession()
    caller = _caller()
    recorder = _UnownedRecorder(caller.user.id, claim_wins=claim_wins,
                                winner_owner=caller.user.id if winner_is_caller else uuid4())
    service = _service(session, _ScriptedAppStore(session, _restored()))
    service.subscriptions_db = recorder
    service.purchases_db = _NoAttribution()
    return service, caller, recorder, session


class TestALostAdoptionClaimIsAnsweredAsTheWinnerLeftIt:
    """The claim's row count is the whole answer, and zero rows rolls back and re-reads rather
    than writing a grant against a row another account now owns."""

    async def test_a_claim_the_same_account_already_won_returns_without_raising(self):
        """The winner was another attempt of this same account, so its rows are there to read."""
        service, caller, recorder, session = _adoption_restore(claim_wins=False,
                                                               winner_is_caller=True)

        await service.restore(identity=caller, provider=PurchaseProvider.apple,
                              restore_proof="a-signed-transaction")

        assert (recorder.granted, session.rollbacks, session.commits) == ([], 1, 0)

    async def test_a_claim_another_account_won_is_not_this_accounts_to_restore_from(self):
        """Every other state the winner could have left refuses, and refuses having written nothing."""
        service, caller, recorder, session = _adoption_restore(claim_wins=False)

        with pytest.raises(RestoreSubscriptionNotEntitled):
            await service.restore(identity=caller, provider=PurchaseProvider.apple,
                                  restore_proof="a-signed-transaction")

        assert (recorder.granted, session.rollbacks, session.commits) == ([], 1, 0)

    async def test_a_claim_this_restore_wins_adopts_the_row_control(self):
        """The control: adoption takes the row and spends none of D-10's month cap doing it."""
        service, caller, recorder, session = _adoption_restore()

        await service.restore(identity=caller, provider=PurchaseProvider.apple,
                              restore_proof="a-signed-transaction")

        assert (recorder.claims[0]["owner_read"], recorder.claims[0]["transfer_month"]) == (None,
                                                                                            None)
        assert (len(recorder.granted), session.commits, session.rollbacks) == (1, 1, 0)


class _AddingSession:
    """A session stand-in for the insert-only writer: it records the add and refuses to be read."""

    def __init__(self, violation: BaseException | None = None) -> None:
        self.added: list = []
        self._violation = violation

    async def exec(self, *args, **kwargs):
        raise AssertionError("the insert-only writer must issue no read")

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        if self._violation is not None:
            raise self._violation


def _violation(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT INTO core.subscriptions", {}, _Orig(sqlstate))


async def _insert_through(session: _AddingSession):
    return await SubscriptionsDB(session).insert_subscription(  # ty: ignore[invalid-argument-type]
        provider=PurchaseProvider.apple,
        external_id=ORIGINAL_TRANSACTION_ID,
        user_id=None,
        tier_id=TIER_ID,
        status=SubscriptionStatus.active,
        signed_at=None,
        evaluated_at=EVALUATED_AT)


class TestTheInsertOnlyWriterReadsNothingAndLosesTheRaceCleanly:
    """One INSERT and no read, so a row that appeared since cannot be updated in place by this path."""

    async def test_it_adds_the_row_and_reports_applied(self):
        session = _AddingSession()

        stored, outcome = await _insert_through(session)

        assert session.added == [stored]
        assert (stored.provider, stored.external_id) == (PurchaseProvider.apple,
                                                         ORIGINAL_TRANSACTION_ID)
        assert (stored.user_id, stored.store_signed_at) == (None, None)
        assert outcome is WriteOutcome.applied

    async def test_a_unique_violation_is_reported_as_a_lost_race(self):
        session = _AddingSession(_violation("23505"))

        _, outcome = await _insert_through(session)

        assert outcome is WriteOutcome.lost_race

    async def test_every_other_integrity_failure_propagates(self):
        """A NOT NULL or a foreign key is a broken invariant, and swallowing it would hide it."""
        session = _AddingSession(_violation("23502"))

        with pytest.raises(IntegrityError):
            await _insert_through(session)

    async def test_an_integrity_error_carrying_no_dbapi_exception_propagates(self):
        """WR-08. SQLAlchemy raises this class itself with `orig` unset, and reading `orig.sqlstate`
        raised AttributeError inside the except block, losing the classification and the rollback."""
        session = _AddingSession(IntegrityError("INSERT INTO core.subscriptions", {}, None))

        with pytest.raises(IntegrityError):
            await _insert_through(session)


class TestTheUniqueViolationIsReadFailClosed:
    """WR-08. One classifier for all eight arms, so no writer dereferences an optional attribute."""

    def test_the_arbiters_own_code_is_a_race(self):
        assert is_unique_violation(_violation(UNIQUE_VIOLATION)) is True

    @pytest.mark.parametrize("sqlstate", ["23502", "23503", "23514", ""])
    def test_every_other_code_is_not_a_race(self, sqlstate):
        assert is_unique_violation(_violation(sqlstate)) is False

    def test_an_absent_dbapi_exception_is_not_a_race(self):
        """Fail closed: the caller re-raises rather than reading an unreadable code as a lost race."""
        assert is_unique_violation(IntegrityError("INSERT", {}, None)) is False

    def test_a_dbapi_exception_of_another_driver_is_not_a_race(self):
        """A psycopg-shaped exception carries `pgcode`, so this refuses rather than guessing."""
        assert is_unique_violation(IntegrityError("INSERT", {}, Exception())) is False
