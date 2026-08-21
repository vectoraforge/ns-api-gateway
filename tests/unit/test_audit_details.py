"""FOUND-05: the §4.4 `details` shape and the redaction that runs before every write.

Pure logic -- no database, no application, no writer. `build_details` and `redact` are driven
directly, because both are total functions over their arguments and everything worth asserting
about them is visible without a session.

The redaction cases are parameterized over the **full §4.4 forbidden list**, one row per clause of
the spec sentence, so adding a new secret field to the writer without adding it to the redactor
fails here. Two shapes get their own cases because both are failure modes that look correct in
review:

- a forbidden key **two levels down** -- a top-level-only redactor passes every flat case;
- the **client-IP bucket kind surviving** while a raw address does not -- a redactor that dropped
  anything address-shaped would take the bucket kind with it and quietly empty `context`, and one
  that kept anything address-shaped would turn the audit log into the behavioural-tracking archive
  this plan's prohibition exists to prevent.

`test_audit_writer.py` owns the writer; this module owns the two functions it applies.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from nativespeaker.api.auth.audit import DETAILS_SCHEMA_VERSION, build_details, redact

DETAILS_TOP_LEVEL = ["context", "failure", "mutation", "resolved", "schema_version", "verification"]
SUBOBJECTS = ("context", "verification", "resolved", "mutation", "failure")

# §4.4's redaction sentence, one entry per clause, with the field names a caller would plausibly
# reach for. Every name here must be dropped wherever it appears.
FORBIDDEN_BY_CLAUSE = (
    ("raw JWTs",
     ("raw_jwt", "jwt", "id_token", "raw_token", "access_token", "refresh_token",
      "bearer", "authorization", "credential")),
    ("raw restore_proof",
     ("restore_proof", "raw_proof", "proof")),
    ("purchase tokens",
     ("purchase_token", "purchaseToken", "google_play_purchase_token")),
    ("signed transaction payloads",
     ("signed_payload", "signed_transaction_info", "payload", "signature")),
    ("attestation blobs",
     ("attestation", "attestation_blob", "device_attestation")),
    ("attestation private keys",
     ("attestation_private_key", "private_key")),
    ("raw device identifiers",
     ("device_id", "raw_device_id", "device_fingerprint", "device", "install_id",
      "installation_id", "vendor_id", "idfv", "idfa")),
    ("raw provider responses",
     ("provider_response", "raw_provider_response")),
    ("raw provider account identifiers",
     ("provider_account_id", "provider_account", "provider_uid")),
    ("email addresses",
     ("email", "email_address", "user_email")),
    ("the public challenge_id",
     ("challenge_id", "public_challenge_id", "challenge")),
    ("any other secret material",
     ("secret", "client_secret", "password", "raw_subject", "actor_subject", "subject", "sub")),
    # The prohibition this plan carries: `audit.auth_events` must not become a behavioural-tracking
    # archive, so no raw address and no stable per-client identifier is ever recorded.
    ("the raw client address or any stable per-client identifier",
     ("client_ip", "ip", "ip_address", "client_address", "remote_addr", "peer_address",
      "x_forwarded_for")),
)

FORBIDDEN_KEYS = [(clause, key) for clause, keys in FORBIDDEN_BY_CLAUSE for key in keys]

# Everything a §4.4 subobject legitimately carries. These are the positive control: a redactor that
# simply returned `{}` would pass every drop case above and fail every one of these.
PRESERVED_KEYS = (
    # context
    "route", "method", "operation", "attempt_id", "client_ip_bucket_kind", "mode_signal_followup",
    # verification -- `families_checked`, not `proof_families_checked`; see the over-redaction case
    "families_checked", "verifier_error_code", "adapter_attempts", "budgets_consulted",
    # resolved -- the non-secret challenge row id, next to the public handle that is dropped
    "user_id", "external_identity_id", "challenge_row_id", "grant_id", "store_purchase_id",
    "actor_provider",
    # mutation / failure
    "state_before", "state_after", "stage", "reason", "retryable",
)


class TestTheSixKeyShape:
    """The table CHECKs each of the six keys independently, so the shape is not advisory."""

    def test_an_empty_call_returns_exactly_the_six_keys(self):
        assert sorted(build_details()) == DETAILS_TOP_LEVEL

    def test_the_schema_version_is_a_number_and_is_the_module_constant(self):
        assert build_details()["schema_version"] == DETAILS_SCHEMA_VERSION
        assert isinstance(build_details()["schema_version"], int)

    @pytest.mark.parametrize("key", SUBOBJECTS)
    def test_every_subobject_is_present_and_empty_when_unused(self, key):
        assert build_details()[key] == {}

    @pytest.mark.parametrize("supplied", SUBOBJECTS)
    def test_supplying_one_subobject_still_yields_all_six(self, supplied):
        details = build_details(**{supplied: {"marker": 1}})
        assert sorted(details) == DETAILS_TOP_LEVEL
        assert details[supplied] == {"marker": 1}
        assert all(details[other] == {} for other in SUBOBJECTS if other != supplied)

    @pytest.mark.parametrize("key", SUBOBJECTS)
    def test_every_subobject_is_a_dict_even_when_unused(self, key):
        assert isinstance(build_details()[key], dict)

    def test_a_seventh_top_level_key_is_rejected_rather_than_passed_through(self):
        """The parameters are keyword-only and named, so an invented key is a TypeError at the
        call site -- not a row PostgreSQL rejects at insert time on the other side of a request."""
        with pytest.raises(TypeError):
            build_details(context={}, telemetry={})  # ty: ignore[unknown-argument]

    def test_the_builder_copies_rather_than_aliasing_the_callers_mapping(self):
        """A caller that reuses its scratch dict must not be able to rewrite a built row."""
        scratch = {"route": "/auth/sync"}
        details = build_details(context=scratch)
        scratch["route"] = "/auth/create-user"
        assert details["context"] == {"route": "/auth/sync"}

    def test_values_a_json_column_cannot_hold_are_coerced(self):
        """`attempt_id` is a UUID and `evaluated_at` is a datetime. Left raw, the insert fails at
        the driver -- and the writer's failure rule would swallow it, making a lost audit row the
        quiet outcome."""
        details = build_details(context={"attempt_id": UUID(int=7),
                                         "evaluated_at": datetime(2026, 8, 21, tzinfo=UTC)})
        assert details["context"]["attempt_id"] == "00000000-0000-0000-0000-000000000007"
        assert details["context"]["evaluated_at"].startswith("2026-08-21T00:00:00")


class TestRedactionDropsTheFullForbiddenList:
    """§4.4: `audit.auth_events` is not a proof archive."""

    @pytest.mark.parametrize(("clause", "key"), FORBIDDEN_KEYS,
                             ids=[f"{key}" for _clause, key in FORBIDDEN_KEYS])
    def test_a_forbidden_key_is_dropped_at_the_top_level(self, clause, key):
        assert redact({key: "s3cret", "route": "/auth/sync"}) == {"route": "/auth/sync"}, clause

    @pytest.mark.parametrize(("clause", "key"), FORBIDDEN_KEYS,
                             ids=[f"{key}" for _clause, key in FORBIDDEN_KEYS])
    def test_a_forbidden_key_is_dropped_two_levels_deep(self, clause, key):
        """A top-level-only redactor passes every flat case and leaks every real one: `details` is
        a tree, and secrets arrive inside `verification` and `failure`, not beside them."""
        payload = {"verification": {"adapter": {key: "s3cret", "attempts": 3}}}
        assert redact(payload) == {"verification": {"adapter": {"attempts": 3}}}, clause

    @pytest.mark.parametrize(("clause", "key"), FORBIDDEN_KEYS,
                             ids=[f"{key}" for _clause, key in FORBIDDEN_KEYS])
    def test_a_forbidden_key_is_dropped_inside_a_list_of_objects(self, clause, key):
        """`verification` carries per-attempt records; a list is the obvious way to write them."""
        payload = {"verification": {"attempts": [{"n": 1}, {key: "s3cret", "n": 2}]}}
        assert redact(payload) == {"verification": {"attempts": [{"n": 1}, {"n": 2}]}}, clause

    def test_the_key_name_is_dropped_not_masked(self):
        """A `"raw_token": "[REDACTED]"` entry still tells a reader the field was present, and the
        name is sometimes the disclosure on its own."""
        assert "raw_token" not in str(redact({"raw_token": "eyJhbGciOiJSUzI1NiJ9"}))

    def test_matching_is_case_insensitive(self):
        assert redact({"Authorization": "Bearer x", "PurchaseToken": "y"}) == {}

    def test_a_forbidden_key_is_dropped_however_deep_it_is(self):
        payload = {"a": {"b": {"c": {"d": {"raw_token": "x", "keep": 1}}}}}
        assert redact(payload) == {"a": {"b": {"c": {"d": {"keep": 1}}}}}


class TestRedactionKeepsWhatTheRowMustReconstruct:
    """The positive control. A redactor that returned `{}` would satisfy every case above."""

    @pytest.mark.parametrize("key", PRESERVED_KEYS)
    def test_a_legitimate_field_survives(self, key):
        assert redact({key: "value"}) == {key: "value"}

    @pytest.mark.parametrize("key", PRESERVED_KEYS)
    def test_a_legitimate_field_survives_two_levels_deep(self, key):
        assert redact({"resolved": {"inner": {key: "value"}}}) == \
               {"resolved": {"inner": {key: "value"}}}

    def test_the_non_secret_challenge_row_id_survives_while_the_public_handle_does_not(self):
        """§4.2: correlation uses `core.auth_challenges.id`. The public `challenge_id` is a secret
        capability handle and never appears in a row, in `details`, in a log, or in error text."""
        payload = {"resolved": {"challenge_row_id": "0198f0d2-0000-7000-8000-000000000001",
                                "challenge_id": "Zm9vYmFyYmF6cXV4"}}
        assert redact(payload) == \
               {"resolved": {"challenge_row_id": "0198f0d2-0000-7000-8000-000000000001"}}

    def test_the_client_ip_bucket_kind_survives_while_a_raw_address_does_not(self):
        """The prohibition, as one assertion: the kind is what §4.4 asks for, and the address is
        what would make the audit log a behavioural-tracking archive."""
        payload = {"context": {"client_ip_bucket_kind": "ipv4",
                               "client_ip": "203.0.113.7",
                               "client_address": "203.0.113.7",
                               "remote_addr": "203.0.113.7"}}
        assert redact(payload) == {"context": {"client_ip_bucket_kind": "ipv4"}}

    @pytest.mark.parametrize("key", ("proof_families_checked", "signature_algorithm",
                                     "payload_bytes", "device_id_present"))
    def test_metadata_named_after_a_secret_is_dropped_with_it(self, key):
        """Deliberate over-redaction, pinned here so it is discoverable.

        The match is on the artifact's *name*, so it cannot tell `restore_proof` from
        `proof_families_checked` -- the metadata §4.4 asks `verification` to carry. It drops both,
        because under-redaction is a durable leak and over-redaction is not. The consequence is a
        naming convention: a later phase recording metadata *about* a secret must not name the
        field after the secret. `families_checked` survives; `proof_families_checked` does not.
        """
        assert redact({key: "value"}) == {}
        assert redact({"families_checked": "value"}) == {"families_checked": "value"}

    def test_the_actor_provider_survives_while_a_raw_provider_account_does_not(self):
        """§4.2: the stored provider is the sole classifier and is not a secret; the provider's
        raw account identifier is."""
        payload = {"resolved": {"actor_provider": "google", "provider_uid": "104729...",
                                "provider_account_id": "104729..."}}
        assert redact(payload) == {"resolved": {"actor_provider": "google"}}


class TestRedactionNeverMutatesItsArgument:
    """A caller that logs or asserts against the object it built must still see what it built."""

    def test_the_top_level_input_is_unchanged(self):
        payload = {"raw_token": "x", "route": "/auth/sync"}
        redact(payload)
        assert payload == {"raw_token": "x", "route": "/auth/sync"}

    def test_a_nested_input_is_unchanged(self):
        payload = {"a": {"raw_token": "x", "ok": 1}}
        redact(payload)
        assert payload == {"a": {"raw_token": "x", "ok": 1}}

    def test_the_returned_object_is_a_different_object_at_every_level(self):
        payload = {"a": {"b": {"keep": 1}}}
        result = redact(payload)
        assert result == payload
        assert result is not payload
        assert result["a"] is not payload["a"]
        assert result["a"]["b"] is not payload["a"]["b"]

    def test_a_nested_list_is_copied_rather_than_shared(self):
        payload = {"a": [{"keep": 1}]}
        result = redact(payload)
        result["a"][0]["keep"] = 2
        assert payload == {"a": [{"keep": 1}]}


class TestABarrierRejectionsDetails:
    """The object the barrier hands the writer, as §4.4 and §8.2 shape it."""

    def rejection(self, reason: str = "missing_token") -> dict:
        return build_details(
            context={"route": "/auth/sync", "method": "POST", "operation": "sync",
                     "attempt_id": UUID(int=3), "client_ip_bucket_kind": "ipv4"},
            failure={"stage": "barrier", "reason": reason, "retryable": True})

    def test_it_carries_the_six_keys(self):
        assert sorted(self.rejection()) == DETAILS_TOP_LEVEL

    def test_the_bounded_reason_lives_under_failure(self):
        assert self.rejection()["failure"]["reason"] == "missing_token"

    @pytest.mark.parametrize("key", ("context", "verification", "resolved", "mutation"))
    def test_the_bounded_reason_lives_nowhere_else(self, key):
        """The bounded reason is telemetry, not context. One home means one place to look and one
        place a later phase can widen."""
        assert "missing_token" not in str(self.rejection()[key])

    def test_the_three_untouched_subobjects_are_empty(self):
        """A barrier rejection verified nothing, resolved nothing, and changed nothing."""
        details = self.rejection()
        assert (details["verification"], details["resolved"], details["mutation"]) == ({}, {}, {})

    def test_it_survives_redaction_unchanged(self):
        """Nothing the barrier records is forbidden -- which is the point of recording the bucket
        kind and the route template rather than the address and the request path."""
        details = self.rejection()
        assert redact(details) == details
