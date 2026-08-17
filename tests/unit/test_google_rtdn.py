"""`POST /webhooks/google-play/rtdn`: Pub/Sub OIDC authentication, package and redelivery checks,
the trigger-only message body, and the durability gate on the acknowledgement."""

import base64
import json
import time

import pytest

from nativespeaker.api.auth.google_rtdn import (
    RTDN_ACCEPTED,
    RTDN_INTERNAL_FAILURE,
    RTDN_PATH,
    RTDN_UNAUTHENTICATED,
    OidcClaims,
    PlayRtdnConfig,
    PubSubOidcVerifier,
    RtdnAuthenticationError,
    RtdnContractError,
    RtdnLedger,
    RtdnRejectionReason,
    authenticate_rtdn_push,
    authoritative_subscription_state,
    decode_push_body,
    ingest_rtdn_push,
    mutation_inputs,
    play_rtdn_config,
    pubsub_push_credential,
    validate_and_dedupe,
)
from tests.unit.conftest import PUBLIC_KEY_PEM, make_token

PACKAGE = "com.example.nativespeaker"
PRODUCT = "com.example.nativespeaker.gold"
AUDIENCE = "https://api.example.com/webhooks/google-play/rtdn"
SERVICE_ACCOUNT = "play-rtdn-push@example-project.iam.gserviceaccount.com"
GOOGLE_ISSUER = "https://accounts.google.com"

CONFIG = PlayRtdnConfig(package_name=PACKAGE,
                        pubsub_audience=AUDIENCE,
                        pubsub_service_account_email=SERVICE_ACCOUNT,
                        product_ids=frozenset({PRODUCT}))


def oidc_token(*, aud: str = AUDIENCE,
               iss: str = GOOGLE_ISSUER,
               email: str = SERVICE_ACCOUNT,
               email_verified: bool = True,
               exp: float | None = None) -> str:
    return make_token(sub="1234567890", aud=aud, iss=iss, exp=exp,
                      email_verified=email_verified,
                      extra_claims={"email": email})


def verifier(*, audience: str = AUDIENCE, email: str = SERVICE_ACCOUNT) -> PubSubOidcVerifier:
    return PubSubOidcVerifier(audience=audience,
                              service_account_email=email,
                              key_resolver=lambda token: PUBLIC_KEY_PEM)


def push_body(*, message_id: str = "9876543210",
              package: str = PACKAGE,
              product: str = PRODUCT,
              purchase_token: str = "play-purchase-token") -> dict:
    payload = {"version": "1.0", "packageName": package,
               "eventTimeMillis": "1735689600000",
               "subscriptionNotification": {"version": "1.0", "notificationType": 4,
                                            "purchaseToken": purchase_token,
                                            "subscriptionId": product}}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"message": {"messageId": message_id, "data": encoded}, "subscription": "projects/x/y"}


class TestPubSubOidcCredential:

    def test_the_credential_is_a_bearer_service_account_token_not_a_firebase_id_token(self):
        # [utest->req~restore-google-rtdn-pubsub-oidc-token~1]
        token = oidc_token()
        assert pubsub_push_credential([f"Bearer {token}"]) == token
        # It is never handed to a Firebase ID token verifier: that is a different token class.
        with pytest.raises(RtdnContractError):
            pubsub_push_credential([f"Bearer {token}"], firebase_verifier=object())

    def test_a_missing_or_malformed_authorization_field_authenticates_nothing(self):
        # [utest->req~restore-google-rtdn-pubsub-oidc-token~1]
        for header in ([], ["Basic abc"], ["Bearer"], ["Bearer ", "Bearer x"]):
            with pytest.raises(RtdnAuthenticationError) as refused:
                pubsub_push_credential(header)
            assert refused.value.reason is RtdnRejectionReason.missing_token

    def test_the_route_is_the_registered_rtdn_path(self):
        # [utest->req~restore-google-rtdn-pubsub-oidc-token~1]
        assert RTDN_PATH == "/webhooks/google-play/rtdn"


class TestTokenSignatureIssuerExpiryAudience:

    def test_a_google_signed_token_for_the_exact_audience_verifies(self):
        # [utest->req~restore-google-verify-token-signature-audience~1]
        claims = verifier().verify(oidc_token())
        assert isinstance(claims, OidcClaims)
        assert claims.audience == AUDIENCE
        assert claims.issuer == GOOGLE_ISSUER

    def test_a_wrong_audience_is_refused(self):
        # [utest->req~restore-google-verify-token-signature-audience~1]
        with pytest.raises(RtdnAuthenticationError) as refused:
            verifier().verify(oidc_token(aud="https://api.example.com/other"))
        assert refused.value.reason is RtdnRejectionReason.audience_mismatch

    def test_a_wrong_issuer_is_refused(self):
        # [utest->req~restore-google-verify-token-signature-audience~1]
        with pytest.raises(RtdnAuthenticationError) as refused:
            verifier().verify(oidc_token(iss="https://securetoken.google.com/test-project"))
        assert refused.value.reason is RtdnRejectionReason.issuer_mismatch

    def test_an_expired_token_is_refused(self):
        # [utest->req~restore-google-verify-token-signature-audience~1]
        with pytest.raises(RtdnAuthenticationError) as refused:
            verifier().verify(oidc_token(exp=time.time() - 3600))
        assert refused.value.reason is RtdnRejectionReason.expired

    def test_an_unverifiable_signature_is_refused(self):
        # [utest->req~restore-google-verify-token-signature-audience~1]
        token = oidc_token()
        tampered = token[:-6] + ("a" * 6 if not token.endswith("a" * 6) else "b" * 6)
        with pytest.raises(RtdnAuthenticationError):
            verifier().verify(tampered)


class TestPushServiceAccountEmail:

    def test_only_the_dedicated_push_service_account_is_accepted(self):
        # [utest->req~restore-google-verify-service-account-email~1]
        assert verifier().verify(oidc_token()).email == SERVICE_ACCOUNT
        with pytest.raises(RtdnAuthenticationError) as refused:
            verifier().verify(oidc_token(email="other-sa@example-project.iam.gserviceaccount.com"))
        assert refused.value.reason is RtdnRejectionReason.service_account_mismatch

    def test_email_verified_is_required(self):
        # [utest->req~restore-google-verify-service-account-email~1]
        with pytest.raises(RtdnAuthenticationError) as refused:
            verifier().verify(oidc_token(email_verified=False))
        assert refused.value.reason is RtdnRejectionReason.email_unverified


class TestAuthenticationFailureIs401:

    async def test_any_authentication_failure_answers_401_with_no_ingestion(self):
        # [utest->req~restore-google-auth-failure-401~1]
        for authorization in ([], ["Bearer " + oidc_token(aud="https://elsewhere")],
                              ["Bearer " + oidc_token(email="intruder@example.com")],
                              ["Bearer " + oidc_token(email_verified=False)]):
            ledger = RtdnLedger()
            status = await ingest_rtdn_push(push_body(), authorization,
                                            config=CONFIG, verifier=verifier(),
                                            already_applied=_never_applied,
                                            fetch=_unreachable_fetch,
                                            apply=_unreachable_apply,
                                            commit=_unreachable_commit,
                                            ledger=ledger)
            assert status == RTDN_UNAUTHENTICATED
            assert ledger.steps == []

    def test_business_logic_never_runs_before_authentication(self):
        # [utest->req~restore-google-auth-failure-401~1]
        ledger = RtdnLedger()
        ledger.record("apply")
        with pytest.raises(RtdnContractError):
            authenticate_rtdn_push([f"Bearer {oidc_token()}"], verifier=verifier(), ledger=ledger)


class TestPackageAndDedupe:

    def test_the_expected_package_and_subscription_are_validated(self):
        # [utest->req~restore-google-validate-package-and-dedupe~1]
        ledger = RtdnLedger()
        message = decode_push_body(push_body())
        assert validate_and_dedupe(message, config=CONFIG, already_applied=False,
                                   ledger=ledger) == "9876543210"
        for wrong in (push_body(package="com.attacker.app"),
                      push_body(product="com.attacker.app.gold")):
            with pytest.raises(RtdnAuthenticationError):
                validate_and_dedupe(decode_push_body(wrong), config=CONFIG,
                                    already_applied=False, ledger=RtdnLedger())

    def test_redelivery_repeats_no_side_effect(self):
        # [utest->req~restore-google-validate-package-and-dedupe~1]
        ledger = RtdnLedger()
        message = decode_push_body(push_body())
        assert validate_and_dedupe(message, config=CONFIG, already_applied=True,
                                   ledger=ledger) is None
        assert ledger.steps == []

    async def test_a_redelivered_message_is_acknowledged_without_applying_anything(self):
        # [utest->req~restore-google-validate-package-and-dedupe~1]
        applied: list[str] = []

        async def seen(message_id: str) -> bool:
            return message_id == "9876543210"

        async def apply(notification_uuid: str, state) -> None:
            applied.append(notification_uuid)

        status = await ingest_rtdn_push(push_body(), [f"Bearer {oidc_token()}"],
                                        config=CONFIG, verifier=verifier(),
                                        already_applied=seen,
                                        fetch=_unreachable_fetch,
                                        apply=apply,
                                        commit=_unreachable_commit)
        assert status == RTDN_ACCEPTED
        assert applied == []


class TestMessageIsTriggerOnly:

    async def test_state_comes_from_the_authoritative_play_lookup(self):
        # [utest->req~restore-google-message-is-trigger-only~1]
        looked_up: list[tuple[str, str]] = []

        async def fetch(package: str, token: str) -> dict:
            looked_up.append((package, token))
            return {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE"}

        ledger = RtdnLedger()
        state = await authoritative_subscription_state(decode_push_body(push_body()),
                                                       fetch=fetch, config=CONFIG,
                                                       ledger=ledger)
        # The package comes from configuration, never from the message body.
        assert looked_up == [(PACKAGE, "play-purchase-token")]
        assert state["subscriptionState"] == "SUBSCRIPTION_STATE_ACTIVE"
        assert any(step.startswith("lookup:") for step in ledger.steps)

    def test_a_mutation_input_taken_from_the_message_is_refused(self):
        # [utest->req~restore-google-message-is-trigger-only~1]
        state = {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE"}
        assert mutation_inputs(state) == state
        with pytest.raises(RtdnContractError):
            mutation_inputs(state, taken_from_message=["subscriptionId"])

    async def test_a_forged_message_only_triggers_a_truthful_lookup(self):
        # [utest->req~restore-google-message-is-trigger-only~1]
        seen_states: list[dict] = []

        async def fetch(package: str, token: str) -> dict:
            # The store says the subscription is expired, whatever the message claimed.
            return {"subscriptionState": "SUBSCRIPTION_STATE_EXPIRED"}

        async def apply(notification_uuid: str, state) -> None:
            seen_states.append(dict(state))

        status = await ingest_rtdn_push(push_body(), [f"Bearer {oidc_token()}"],
                                        config=CONFIG, verifier=verifier(),
                                        already_applied=_never_applied,
                                        fetch=fetch, apply=apply, commit=_ok_commit)
        assert status == RTDN_ACCEPTED
        assert seen_states == [{"subscriptionState": "SUBSCRIPTION_STATE_EXPIRED"}]


class TestAcknowledgementOnlyAfterDurable:

    async def test_200_only_once_the_state_is_committed(self):
        # [utest->req~restore-google-200-only-after-durable~1]
        ledger = RtdnLedger()
        status = await ingest_rtdn_push(push_body(), [f"Bearer {oidc_token()}"],
                                        config=CONFIG, verifier=verifier(),
                                        already_applied=_never_applied,
                                        fetch=_active_fetch, apply=_ok_apply, commit=_ok_commit,
                                        ledger=ledger)
        assert status == RTDN_ACCEPTED
        assert ledger.committed is True

    async def test_a_failed_commit_answers_5xx_so_pubsub_redelivers(self):
        # [utest->req~restore-google-200-only-after-durable~1]
        async def failing_commit() -> None:
            raise RuntimeError("the transaction could not be made durable")

        ledger = RtdnLedger()
        status = await ingest_rtdn_push(push_body(), [f"Bearer {oidc_token()}"],
                                        config=CONFIG, verifier=verifier(),
                                        already_applied=_never_applied,
                                        fetch=_active_fetch, apply=_ok_apply,
                                        commit=failing_commit, ledger=ledger)
        assert status == RTDN_INTERNAL_FAILURE
        assert ledger.committed is False

    async def test_a_failed_lookup_answers_5xx_rather_than_acknowledging(self):
        # [utest->req~restore-google-200-only-after-durable~1]
        async def failing_fetch(package: str, token: str) -> dict:
            raise TimeoutError("play developer api timed out")

        status = await ingest_rtdn_push(push_body(), [f"Bearer {oidc_token()}"],
                                        config=CONFIG, verifier=verifier(),
                                        already_applied=_never_applied,
                                        fetch=failing_fetch, apply=_unreachable_apply,
                                        commit=_unreachable_commit)
        assert status == RTDN_INTERNAL_FAILURE


class TestConfiguration:

    def test_every_registry_required_key_must_be_configured(self):
        raw = {"google_play": {"package_name": PACKAGE,
                               "pubsub_audience": AUDIENCE,
                               "pubsub_service_account_email": SERVICE_ACCOUNT,
                               "product_id_to_tier": {PRODUCT: "gold"}}}
        assert play_rtdn_config(raw).package_name == PACKAGE
        for missing in ("package_name", "pubsub_audience", "pubsub_service_account_email",
                        "product_id_to_tier"):
            partial = {"google_play": {k: v for k, v in raw["google_play"].items()
                                       if k != missing}}
            with pytest.raises(RtdnContractError):
                play_rtdn_config(partial)


async def _never_applied(message_id: str) -> bool:
    return False


async def _active_fetch(package: str, token: str) -> dict:
    return {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE"}


async def _ok_apply(notification_uuid: str, state) -> None:
    return None


async def _ok_commit() -> None:
    return None


async def _unreachable_fetch(package: str, token: str) -> dict:
    raise AssertionError("no lookup runs on a rejected push")


async def _unreachable_apply(notification_uuid: str, state) -> None:
    raise AssertionError("nothing is applied on a rejected push")


async def _unreachable_commit() -> None:
    raise AssertionError("nothing is committed on a rejected push")
