"""The Apple restore proof, minted for real against a throwaway chain and refused by the real root.
The store call's place in the request is measured here too: it runs before the session's first statement.
Untested by construction: only whether Apple's live signed transactions match Apple's declared shapes."""
from datetime import UTC, datetime, timedelta

import pytest
from appstoreserverlibrary.signed_data_verifier import VerificationStatus

from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.errors import (
    ProofRejected,
    RestoreProviderUnknown,
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

# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)

# The application name the dependency passes in production; the Apple check never reads it.
PACKAGE_NAME = "com.nativespeaker.app"


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


def _service(session: _CountingSession, store: _ScriptedAppStore) -> RestoreService:
    return RestoreService(db=session, evaluated_at=EVALUATED_AT,
                          app_store=store, package_name=PACKAGE_NAME)


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

    async def test_a_store_the_deployment_does_not_serve_runs_no_statement_at_all(self):
        """The gate refusal writes nothing, so an interrupted refusal leaves every row unchanged."""
        session = _CountingSession()
        store = _ScriptedAppStore(session, _restored())

        with pytest.raises(RestoreProviderUnknown):
            await _service(session, store).restore(identity=_caller(),
                                                   provider=PurchaseProvider.google_play,
                                                   restore_proof="a-purchase-token")

        assert session.statements == 0
        assert store.statements_at_call is None

    async def test_a_proof_that_does_not_verify_runs_no_statement_either(self):
        session = _CountingSession()
        store = _ScriptedAppStore(session, ProofRejected(stage="VERIFICATION_FAILURE"))

        with pytest.raises(ProofRejected):
            await _service(session, store).restore(identity=_caller(),
                                                   provider=PurchaseProvider.apple,
                                                   restore_proof="a-forged-transaction")

        assert session.statements == 0
        assert store.statements_at_call == 0

    async def test_the_counting_session_really_counts_control(self):
        """The control: a recorder that never incremented would pass the two zero cases above."""
        session = _CountingSession()

        with pytest.raises(_Stop):
            await session.exec("any statement")

        assert session.statements == 1
