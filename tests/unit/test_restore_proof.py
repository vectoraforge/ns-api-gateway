"""Both restore proofs: the Apple transaction minted against a throwaway chain, and the Play read.
The store call's place in the request is measured here too: it runs before the session's first statement.
Untested by construction: only whether the two stores' live artifacts match their declared shapes."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from appstoreserverlibrary.signed_data_verifier import VerificationStatus

from nativespeaker.api.auth.google_play import GRACE_STATE, PlayDeveloperSubscriptions
from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.errors import (
    ProofRejected,
    Unavailable,
    UnmappedStoreProduct,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services.restore import RestoreService
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus
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
    _transaction,
)
from unit.test_google_play_notifications import (
    ATTRIBUTION_TOKEN as PLAY_ATTRIBUTION_TOKEN,
)
from unit.test_google_play_notifications import (
    PRODUCT_ID as PLAY_PRODUCT_ID,
)
from unit.test_google_play_notifications import (
    PURCHASE_TOKEN,
    UNEXPIRED,
    _answering,
    _FakeCredential,
    _subscription_body,
)
from unit.test_google_play_notifications import (
    TIER_ID as PLAY_TIER_ID,
)

# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)

# The application name the dependency passes in production; the Apple check never reads it.
PACKAGE_NAME = "com.nativespeaker.app"

# The two stages the Play restore read answers with, which are its whole label vocabulary.
GONE_STAGE = "play_token_gone"
READ_STAGE = "play_restore_read"

# The fixed part of the read path, which every caller-supplied value must be measured against.
PLAY_TOKENS_PATH = f"/androidpublisher/v3/applications/{PACKAGE_NAME}/purchases/subscriptionsv2/tokens/"


@pytest.fixture(scope="module")
def chain() -> _Chain:
    """One throwaway chain for the whole module: three key generations and three signings."""
    return _build_chain()


def _proof_through(chain: _Chain, transaction: dict, *,
                   evaluated_at: datetime = EVALUATED_AT) -> RestoredSubscription:
    """One restore check on the real seam, with the arguments the service passes in production."""
    return _notifications(chain).verify_transaction(_mint(chain, transaction), evaluated_at)


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

    def test_the_vendored_apple_root_refuses_the_same_proof_control(self, chain):
        """The control that makes the case above non-vacuous: the real root does not sign this chain."""
        assert APPLE_ROOT_G3.is_file(), f"{APPLE_ROOT_G3} is the pinned root and must be tracked"
        notifications = _notifications(chain, root_certificates=[APPLE_ROOT_G3.read_bytes()])

        with pytest.raises(ProofRejected) as refusal:
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

    def test_the_three_arms_are_three_distinct_names_from_the_closed_set(self, chain):
        """`VerificationStatus.name` is a fixed set of strings, which is what makes it a safe label."""
        short_chain = _mint(chain, _transaction(), x5c=chain.x5c[:2])
        stages = []
        for proof in (short_chain,
                      _mint(chain, _transaction(bundle_id="com.example.someone-else")),
                      _mint(chain, _transaction(environment="Production"))):
            with pytest.raises(ProofRejected) as refusal:
                _notifications(chain).verify_transaction(proof, EVALUATED_AT)
            stages.append(refusal.value.stage)

        assert set(stages) <= {status.name for status in VerificationStatus}
        assert len(set(stages)) == 3

    def test_no_stage_and_no_message_carries_any_part_of_the_proof(self, chain):
        proof = _mint(chain, _transaction(bundle_id="com.example.someone-else"))

        with pytest.raises(ProofRejected) as refusal:
            _notifications(chain).verify_transaction(proof, EVALUATED_AT)

        for segment in proof.split("."):
            assert segment not in refusal.value.stage
            assert segment not in str(refusal.value)


def _play_reader(handler, *, products: dict[str, str] | None = None) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and this module's captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        products={PLAY_PRODUCT_ID: PLAY_TIER_ID} if products is None else products,
        evaluated_at_source=lambda: EVALUATED_AT)


async def _restore_through(reader: PlayDeveloperSubscriptions) -> RestoredSubscription:
    """One restore read on this reader, with the arguments the service passes in production."""
    return await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token=PURCHASE_TOKEN)


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
                                      purchase_token="a/../../../../v3/applications/evil/edits")

        # The wire form, because `url.path` percent-decodes and would hide the escaping this asserts.
        path = sent[0].url.raw_path.decode()
        assert path.startswith(PLAY_TOKENS_PATH)
        assert "evil" not in path.split("/")

    async def test_a_token_carrying_a_query_string_leaves_the_query_empty(self):
        sent, reader = _capturing_reader()

        await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token="x?alt=media")

        assert sent[0].url.query == b""

    async def test_a_package_name_carrying_a_separator_is_escaped_too(self):
        """The guard cannot be escaped from either side, so both interpolated values are escaped."""
        sent, reader = _capturing_reader()

        await reader.read_for_restore(package_name=f"{PACKAGE_NAME}/evil",
                                      purchase_token=PURCHASE_TOKEN)

        path = sent[0].url.raw_path.decode()
        assert "/" not in path.split("/applications/")[1].split("/purchases")[0]

    async def test_an_ordinary_token_reaches_the_expected_path_control(self):
        """The control: without it the three cases above would pass a read that called Play no more."""
        sent, reader = _capturing_reader()

        restored = await reader.read_for_restore(package_name=PACKAGE_NAME,
                                                 purchase_token=PURCHASE_TOKEN)

        assert sent[0].url.raw_path.decode() == PLAY_TOKENS_PATH + PURCHASE_TOKEN
        assert isinstance(restored, RestoredSubscription)
        # The escaping is the URL's alone: the persisted external id stays the token Google gave.
        assert restored.external_id == PURCHASE_TOKEN

    @pytest.mark.parametrize("token", [".", "..", "...."])
    async def test_a_dot_only_token_is_refused_and_reaches_no_transport(self, token):
        """`quote` leaves a dot unescaped and the client deletes a dot segment, so dots name nothing."""
        sent, reader = _capturing_reader()

        with pytest.raises(ProofRejected) as refusal:
            await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token=token)

        assert refusal.value.stage == GONE_STAGE
        assert sent == []

    async def test_a_dot_only_package_name_is_an_operator_state_and_reaches_no_transport(self):
        """The application name is operator configuration, so dots alone are a 503 and not a refusal."""
        sent, reader = _capturing_reader()

        with pytest.raises(Unavailable) as refusal:
            await reader.read_for_restore(package_name="..", purchase_token=PURCHASE_TOKEN)

        assert refusal.value.stage == READ_STAGE
        assert sent == []

    async def test_a_token_carrying_dots_among_other_characters_is_still_read_control(self):
        """The control: a real Play token carries dots, so only a token of dots alone is refused."""
        sent, reader = _capturing_reader()

        restored = await reader.read_for_restore(package_name=PACKAGE_NAME,
                                                 purchase_token="a.b..c")

        assert sent[0].url.raw_path.decode() == PLAY_TOKENS_PATH + "a.b..c"
        assert restored.external_id == "a.b..c"


class TestThePlayAnswerIsClassifiedBeforeItIsParsed:
    """D-05: a gone token is a rejected proof, and every other failure is a 503 the app retries."""

    @pytest.mark.parametrize("status_code", [404, 410])
    async def test_a_gone_purchase_token_is_a_rejected_proof(self, status_code):
        reader = _play_reader(_answering({"error": {"status": "NOT_FOUND"}}, status_code))

        with pytest.raises(ProofRejected) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == GONE_STAGE
        assert refusal.value.status == 403

    @pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500, 502, 503])
    async def test_every_other_non_2xx_status_is_temporarily_unavailable(self, status_code):
        reader = _play_reader(_answering({"error": {"status": "UNAVAILABLE"}}, status_code))

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == READ_STAGE
        assert refusal.value.status == 503

    async def test_a_transport_failure_is_temporarily_unavailable(self):
        def _unreachable(_request):
            raise httpx.ConnectError("the Play endpoint is unreachable")

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(_play_reader(_unreachable))

        assert refusal.value.stage == READ_STAGE

    async def test_an_absent_credential_is_unavailable_and_reaches_no_transport(self):
        """No credential is an operator state, not a refusal the caller earned, so it is a 503."""
        def _never(request):
            raise AssertionError(f"an unconfigured deployment reached {request.url}")

        reader = PlayDeveloperSubscriptions(
            credential=None,
            client=httpx.AsyncClient(transport=httpx.MockTransport(_never)),
            products={},
            evaluated_at_source=lambda: EVALUATED_AT)

        with pytest.raises(Unavailable) as refusal:
            await _restore_through(reader)

        assert refusal.value.stage == READ_STAGE

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
                             [(404, ProofRejected), (500, Unavailable)])
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

    async def read_for_restore(self, *, package_name: str, purchase_token: str):
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


def _caller() -> Identity:
    return Identity(issuer="https://issuer.test", subject="restore-ordering-subject",
                    user=User(), identity=None)


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
        store = _ScriptedAppStore(session, ProofRejected(stage="VERIFICATION_FAILURE"))

        with pytest.raises(ProofRejected):
            await _service(session, store).restore(identity=_caller(),
                                                   provider=PurchaseProvider.apple,
                                                   restore_proof="a-forged-transaction")

        assert session.statements == 0
        assert store.statements_at_call == 0

    async def test_a_gone_purchase_token_runs_no_statement_either(self):
        """T-45-03: a fabricated token is refused by Google, so nothing is read and nothing written."""
        session = _CountingSession()
        play = _ScriptedPlay(session, ProofRejected(stage=GONE_STAGE))

        with pytest.raises(ProofRejected):
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
