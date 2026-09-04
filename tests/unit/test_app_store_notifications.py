"""The Apple chain walk, both OID checks, the ES256 rule and the signature check, all run for real here.
A throwaway root, intermediate and leaf mint the payloads, and the vendored Apple root refuses them.
Untested by construction: only whether Apple's live notifications match Apple's own declared shapes."""
import ast
import time
from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as pyjwt
import pytest
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from nativespeaker.api.auth.app_store import (
    AppStoreNotifications,
    StoreNotificationVerifier,
    VerifiedNotification,
)
from nativespeaker.api.errors import NotificationRejected, Unavailable
from nativespeaker.api.tables import PurchaseProvider

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The vendored root the control case uses; it is public reference data, not a secret.
APPLE_ROOT_G3 = _REPO_ROOT / "config/certs/AppleRootCA-G3.cer"

SERVICE_MODULE = _REPO_ROOT / "src/nativespeaker/api/services/subscriptions.py"

# Required on the leaf, checked by the library on the verified chain's first certificate.
LEAF_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")

# Required on the intermediate, checked on the verified chain's second certificate.
INTERMEDIATE_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")

# A DER NULL: only the OID's presence is checked, never the value carried under it.
DER_NULL = b"\x05\x00"

BUNDLE_ID = "com.example.nativespeaker"
APP_APPLE_ID = 1234567890
PRODUCT_ID = "com.example.nativespeaker.subscription.monthly"
ORIGINAL_TRANSACTION_ID = "2000000000000001"
TRANSACTION_ID = "2000000000000002"
ATTRIBUTION_TOKEN = "8f4d1a2e-0000-4000-8000-000000000001"


def _milliseconds(moment: datetime) -> int:
    """Apple's stamps are UNIX milliseconds as an int, so every fixture date is minted as one."""
    return int(moment.timestamp() * 1000)


@dataclass(frozen=True)
class _Chain:
    """One throwaway root, intermediate and leaf, with the leaf key that signs every payload."""

    leaf_key: ec.EllipticCurvePrivateKey
    certificates: tuple[x509.Certificate, x509.Certificate, x509.Certificate]

    @property
    def root_der(self) -> bytes:
        return self.certificates[2].public_bytes(Encoding.DER)

    @property
    def x5c(self) -> list[str]:
        """Leaf, intermediate, root -- the order and the length the library insists on."""
        return [b64encode(cert.public_bytes(Encoding.DER)).decode() for cert in self.certificates]


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _sign(builder: x509.CertificateBuilder, key: ec.EllipticCurvePrivateKey,
          *, valid_from: datetime, valid_to: datetime) -> x509.Certificate:
    return (builder.serial_number(x509.random_serial_number())
            .not_valid_before(valid_from)
            .not_valid_after(valid_to)
            .sign(key, hashes.SHA256()))


def _build_chain(*, leaf_valid_to: datetime | None = None) -> _Chain:
    """Three EC P-256 keys and three SHA-256 certificates, carrying the two OIDs the library checks."""
    now = datetime.now(UTC)
    # Opened well back, so a case that expires the leaf still leaves a window `not_before` precedes.
    valid_from, valid_to = now - timedelta(days=200), now + timedelta(days=365)
    root_key, intermediate_key, leaf_key = (ec.generate_private_key(ec.SECP256R1())
                                            for _ in range(3))

    root = _sign(x509.CertificateBuilder()
                 .subject_name(_name("throwaway root")).issuer_name(_name("throwaway root"))
                 .public_key(root_key.public_key())
                 .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                 .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                              key_encipherment=False, data_encipherment=False,
                                              key_agreement=False, key_cert_sign=True,
                                              crl_sign=True, encipher_only=False,
                                              decipher_only=False), critical=True)
                 .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()),
                                critical=False),
                 root_key, valid_from=valid_from, valid_to=valid_to)

    intermediate = _sign(x509.CertificateBuilder()
                         .subject_name(_name("throwaway intermediate")).issuer_name(root.subject)
                         .public_key(intermediate_key.public_key())
                         .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                         .add_extension(x509.KeyUsage(digital_signature=False,
                                                      content_commitment=False,
                                                      key_encipherment=False,
                                                      data_encipherment=False, key_agreement=False,
                                                      key_cert_sign=True, crl_sign=True,
                                                      encipher_only=False, decipher_only=False),
                                        critical=True)
                         .add_extension(x509.SubjectKeyIdentifier.from_public_key(
                             intermediate_key.public_key()), critical=False)
                         .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                             root_key.public_key()), critical=False)
                         .add_extension(x509.UnrecognizedExtension(INTERMEDIATE_OID, DER_NULL),
                                        critical=False),
                         root_key, valid_from=valid_from, valid_to=valid_to)

    leaf = _sign(x509.CertificateBuilder()
                 .subject_name(_name("throwaway leaf")).issuer_name(intermediate.subject)
                 .public_key(leaf_key.public_key())
                 .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                 .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                              key_encipherment=False, data_encipherment=False,
                                              key_agreement=False, key_cert_sign=False,
                                              crl_sign=False, encipher_only=False,
                                              decipher_only=False), critical=True)
                 .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
                                critical=False)
                 .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                     intermediate_key.public_key()), critical=False)
                 .add_extension(x509.UnrecognizedExtension(LEAF_OID, DER_NULL), critical=False),
                 intermediate_key,
                 valid_from=valid_from,
                 valid_to=leaf_valid_to if leaf_valid_to is not None else valid_to)

    return _Chain(leaf_key=leaf_key, certificates=(leaf, intermediate, root))


@pytest.fixture(scope="module")
def chain() -> _Chain:
    """One throwaway chain for the whole module: three key generations and three signings."""
    return _build_chain()


def _mint(chain: _Chain, payload: dict, *,
          key: ec.EllipticCurvePrivateKey | None = None,
          x5c: list[str] | None = None) -> str:
    """One ES256 JWS carrying the three-certificate `x5c` header the library walks."""
    return pyjwt.encode(payload, key if key is not None else chain.leaf_key,
                        algorithm="ES256",
                        headers={"x5c": chain.x5c if x5c is None else x5c})


def _transaction(*, bundle_id: str = BUNDLE_ID, environment: str = "Sandbox",
                 revocation_date: int | None = None, expires_in: timedelta = timedelta(days=30),
                 ) -> dict:
    """The nested transaction payload, verified on its own bundle id and environment."""
    now = datetime.now(UTC)
    return {"bundleId": bundle_id,
            "environment": environment,
            "originalTransactionId": ORIGINAL_TRANSACTION_ID,
            "transactionId": TRANSACTION_ID,
            "productId": PRODUCT_ID,
            "appAccountToken": ATTRIBUTION_TOKEN,
            "purchaseDate": _milliseconds(now),
            "expiresDate": _milliseconds(now + expires_in),
            "revocationDate": revocation_date}


def _renewal(*, environment: str = "Sandbox", in_billing_retry: bool = True,
             grace_period_in: timedelta = timedelta(days=16)) -> dict:
    """The nested renewal payload: the only source of the grace period and the retry flag."""
    return {"environment": environment,
            "originalTransactionId": ORIGINAL_TRANSACTION_ID,
            "productId": PRODUCT_ID,
            "isInBillingRetryPeriod": in_billing_retry,
            "gracePeriodExpiresDate": _milliseconds(datetime.now(UTC) + grace_period_in)}


def _envelope(chain: _Chain, *, notification_type: str = "SUBSCRIBED",
              notification_uuid: str = "8f0f0f00-0000-4000-8000-00000000000a",
              bundle_id: str = BUNDLE_ID, environment: str = "Sandbox",
              app_apple_id: int = APP_APPLE_ID,
              transaction: dict | None = None, renewal: dict | None = None,
              signed_date: int | None = None) -> dict:
    """The minimum envelope the library accepts, plus whichever nested payloads a case wants."""
    data = {"environment": environment, "appAppleId": app_apple_id, "bundleId": bundle_id}
    if transaction is not None:
        data["signedTransactionInfo"] = _mint(chain, transaction)
    if renewal is not None:
        data["signedRenewalInfo"] = _mint(chain, renewal)
    return {"notificationType": notification_type,
            "notificationUUID": notification_uuid,
            "version": "2.0",
            "signedDate": _milliseconds(datetime.now(UTC)) if signed_date is None else signed_date,
            "data": data}


def _notifications(chain: _Chain, *, root_certificates: list[bytes] | None = None,
                   environment: Environment = Environment.SANDBOX,
                   bundle_id: str = BUNDLE_ID,
                   app_apple_id: int | None = APP_APPLE_ID) -> AppStoreNotifications:
    """The real seam over a real verifier; only the configured root changes for the control."""
    verifier = SignedDataVerifier(
        root_certificates=[chain.root_der] if root_certificates is None else root_certificates,
        enable_online_checks=False,
        environment=environment,
        bundle_id=bundle_id,
        app_apple_id=app_apple_id)
    return AppStoreNotifications(verifier=verifier)


def _full(chain: _Chain, **overrides) -> str:
    """One minted envelope carrying both nested payloads, which is the ordinary subscription case."""
    return _mint(chain, _envelope(chain, transaction=_transaction(), renewal=_renewal(),
                                  **overrides))


class TestTheRealChainVerifies:
    """The library's chain walk, OID checks, ES256 rule and signature check all run in these cases."""

    def test_a_payload_minted_by_the_chain_verifies_against_its_own_root(self, chain):
        verified = _notifications(chain).verify(_full(chain))

        assert isinstance(verified, VerifiedNotification)
        assert verified.provider is PurchaseProvider.apple
        assert verified.notification_uuid == "8f0f0f00-0000-4000-8000-00000000000a"
        assert verified.event_type == "SUBSCRIBED"

    def test_the_vendored_apple_root_refuses_the_same_payload_control(self, chain):
        """The control that makes the case above non-vacuous: the real root does not sign this chain."""
        assert APPLE_ROOT_G3.is_file(), f"{APPLE_ROOT_G3} is the pinned root and must be tracked"
        notifications = _notifications(chain, root_certificates=[APPLE_ROOT_G3.read_bytes()])

        with pytest.raises(NotificationRejected) as refusal:
            notifications.verify(_full(chain))

        assert refusal.value.stage == "VERIFICATION_FAILURE"

    def test_the_seam_satisfies_the_protocol_declared_beside_it(self, chain):
        """Phase 44's own class must satisfy this same Protocol, so it is asserted rather than assumed."""
        seam: StoreNotificationVerifier = _notifications(chain)
        assert isinstance(seam.verify(_full(chain)), VerifiedNotification)


class TestTheValueTypeCarriesThisProjectsFieldNames:
    """D-08: no Apple type crosses the seam, and the two renewal-only fields come from the renewal."""

    @pytest.fixture(scope="class")
    def verified(self, chain) -> VerifiedNotification:
        return _notifications(chain).verify(_full(chain))

    def test_the_transaction_part_is_mapped_by_this_projects_names(self, verified):
        assert verified.external_id == ORIGINAL_TRANSACTION_ID
        assert verified.transaction_id == TRANSACTION_ID
        assert verified.product_id == PRODUCT_ID
        assert verified.attribution_token == ATTRIBUTION_TOKEN

    def test_every_apple_millisecond_stamp_became_an_aware_datetime(self, verified):
        assert verified.purchased_at.tzinfo is not None
        assert verified.expires_at > verified.purchased_at
        # Not revoked: an absent stamp stays absent rather than becoming the epoch.
        assert verified.revoked_at is None

    def test_the_two_renewal_only_fields_come_from_the_renewal_payload(self, verified):
        assert verified.in_billing_retry is True
        assert verified.grace_period_expires_at is not None

    def test_an_envelope_without_a_renewal_payload_carries_neither(self, chain):
        """The transaction payload has no grace period and no retry flag, so both must fail closed."""
        verified = _notifications(chain).verify(
            _mint(chain, _envelope(chain, transaction=_transaction())))

        assert verified.grace_period_expires_at is None
        assert verified.in_billing_retry is False

    def test_an_unrecognised_notification_type_yields_the_raw_string(self, chain):
        """`notificationType` is None for a type this library build does not know; the raw one is not."""
        verified = _notifications(chain).verify(
            _full(chain, notification_type="SOME_FUTURE_TYPE"))

        assert verified.event_type == "SOME_FUTURE_TYPE"

    def test_a_notification_with_no_transaction_part_carries_none_throughout(self, chain):
        verified = _notifications(chain).verify(
            _mint(chain, _envelope(chain, notification_type="TEST")))

        assert verified.event_type == "TEST"
        assert (verified.external_id, verified.transaction_id, verified.product_id) == (
            None, None, None)
        assert verified.in_billing_retry is False


class TestEveryReachableRefusalIsOneClassWithItsOwnStage:
    """T-43-05: one class for every arm, told apart in the log by `stage` and nowhere else."""

    def test_a_foreign_signing_key_is_refused(self, chain):
        """The x5c chain is genuine and the signature is not, which is the forged-payload arm."""
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(
                _mint(chain, _envelope(chain, transaction=_transaction()),
                      key=ec.generate_private_key(ec.SECP256R1())))

        assert refusal.value.stage == "VERIFICATION_FAILURE"

    def test_a_two_certificate_chain_is_refused_on_its_length(self, chain):
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(
                _mint(chain, _envelope(chain), x5c=chain.x5c[:2]))

        assert refusal.value.stage == "INVALID_CHAIN_LENGTH"

    def test_a_wrong_bundle_id_is_refused(self, chain):
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(
                _mint(chain, _envelope(chain, bundle_id="com.example.someone-else")))

        assert refusal.value.stage == "INVALID_APP_IDENTIFIER"

    def test_a_wrong_environment_is_refused(self, chain):
        """A sandbox purchase is free to anyone with a test build, so this arm is a security control."""
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(
                _mint(chain, _envelope(chain, environment="Production")))

        assert refusal.value.stage == "INVALID_ENVIRONMENT"

    def test_a_wrong_app_apple_id_is_refused_in_production(self, chain):
        production = _notifications(chain, environment=Environment.PRODUCTION)

        with pytest.raises(NotificationRejected) as refusal:
            production.verify(_mint(chain, _envelope(chain, environment="Production",
                                                     app_apple_id=APP_APPLE_ID + 1)))

        assert refusal.value.stage == "INVALID_APP_IDENTIFIER"

    def test_every_reachable_stage_is_a_closed_set_name(self, chain):
        """`VerificationStatus.name` is one of eight strings, which is what makes it a safe log label."""
        from appstoreserverlibrary.signed_data_verifier import VerificationStatus

        refusals = []
        for envelope in (_mint(chain, _envelope(chain), x5c=chain.x5c[:2]),
                         _mint(chain, _envelope(chain, bundle_id="com.example.someone-else")),
                         _mint(chain, _envelope(chain, environment="Production"))):
            with pytest.raises(NotificationRejected) as refusal:
                _notifications(chain).verify(envelope)
            refusals.append(refusal.value.stage)

        assert set(refusals) <= {status.name for status in VerificationStatus}
        assert len(set(refusals)) == 3


class TestTheNestedPayloadsAreVerifiedOnTheirOwn:
    """The envelope's signature says nothing about either nested JWS, so each is verified alone."""

    def test_a_transaction_with_a_wrong_bundle_id_is_refused(self, chain):
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(_mint(chain, _envelope(
                chain, transaction=_transaction(bundle_id="com.example.someone-else"))))

        assert refusal.value.stage == "INVALID_APP_IDENTIFIER"

    def test_a_transaction_from_the_wrong_environment_is_refused(self, chain):
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(_mint(chain, _envelope(
                chain, transaction=_transaction(environment="Production"))))

        assert refusal.value.stage == "INVALID_ENVIRONMENT"

    def test_a_renewal_from_the_wrong_environment_is_refused(self, chain):
        """The renewal carries no bundle id, so the environment is the only check it answers."""
        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(_mint(chain, _envelope(
                chain, transaction=_transaction(), renewal=_renewal(environment="Production"))))

        assert refusal.value.stage == "INVALID_ENVIRONMENT"

    def test_a_nested_payload_signed_by_a_foreign_key_is_refused(self, chain):
        """The envelope verifies; the transaction under it does not, and that is the whole point."""
        foreign = _mint(chain, _transaction(), key=ec.generate_private_key(ec.SECP256R1()))
        envelope = _envelope(chain)
        envelope["data"]["signedTransactionInfo"] = foreign

        with pytest.raises(NotificationRejected) as refusal:
            _notifications(chain).verify(_mint(chain, envelope))

        assert refusal.value.stage == "VERIFICATION_FAILURE"


class TestAnAbsentVerifierFailsClosedOnUse:
    """The unconfigured deployment: the class is on `app.state` in every environment and raises here."""

    def test_it_raises_unavailable_rather_than_returning_anything(self):
        with pytest.raises(Unavailable) as failure:
            AppStoreNotifications(verifier=None).verify("anything at all")

        assert failure.value.status == 503
        assert failure.value.code == "verification_temporarily_unavailable"


class TestTheValidityWindowIsTheClaimedSigningDate:
    """P-09, recorded as measured behaviour: with online checks off, the payload supplies the clock."""

    def test_an_expired_leaf_verifies_against_a_backdated_signing_date(self):
        """The accepted cost of D-09's no-network rule, asserted rather than left as a surprise."""
        expired = _build_chain(leaf_valid_to=datetime.now(UTC) - timedelta(days=30))
        backdated = int((time.time() - 90 * 24 * 3600) * 1000)

        verified = _notifications(expired).verify(
            _mint(expired, _envelope(expired, signed_date=backdated)))

        assert verified.event_type == "SUBSCRIBED"

    def test_the_same_expired_leaf_is_refused_at_a_current_signing_date_control(self):
        """The control: the window is enforced, just against the date the payload claims."""
        expired = _build_chain(leaf_valid_to=datetime.now(UTC) - timedelta(days=30))

        with pytest.raises(NotificationRejected) as refusal:
            _notifications(expired).verify(_mint(expired, _envelope(expired)))

        assert refusal.value.stage == "VERIFICATION_FAILURE"


def _imported_roots(path: Path) -> set[str]:
    """The top-level package of every name the module at `path` imports, read from its AST."""
    tree = ast.parse(path.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
    return roots


class TestTheServiceNamesNothingFromTheAppleLibrary:
    """D-08's boundary: Phase 44's Google class feeds the same service, so no Apple type may cross."""

    def test_the_service_imports_no_apple_store_library_name(self):
        assert "appstoreserverlibrary" not in _imported_roots(SERVICE_MODULE)

    def test_the_walk_finds_the_imports_the_module_does_have_control(self):
        """The control: a walk that quietly returned nothing would pass the case above."""
        roots = _imported_roots(SERVICE_MODULE)
        assert {"nativespeaker", "structlog", "sqlmodel", "datetime"} <= roots

    def test_the_walk_finds_the_apple_library_where_it_is_imported_control(self):
        """The second control: the same walk over the seam does find the name it is looking for."""
        seam = _REPO_ROOT / "src/nativespeaker/api/auth/app_store.py"
        assert "appstoreserverlibrary" in _imported_roots(seam)
