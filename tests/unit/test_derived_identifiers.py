"""The HMAC families behind `actor_subject_hash`, `preauth_subject_hash` and `idp_account_hash`."""

import hashlib
import hmac
import unicodedata
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.derived_identifiers import (
    DERIVED_IDENTIFIERS,
    DOMAIN_LABELS,
    IDP_ACCOUNT_HASH_AUTHORITATIVE,
    DerivationError,
    DerivationFamily,
    DerivationSpec,
    HmacKey,
    IdpAccountAliasIndex,
    IdpInputSource,
    KeyFamily,
    KeyRing,
    UniquenessAnchor,
    actor_subject_hash,
    actor_subject_preimage,
    assert_derivation_matches,
    assert_idp_input_source,
    assert_key_source,
    assert_no_key_material_column,
    assert_persisted_key_version,
    assert_rotation_persists_no_preimages,
    assert_uniqueness_anchor,
    canonical_provider_account_id,
    confirm_registered_binding,
    idp_account_hash,
    idp_account_preimage,
    preauth_subject_hash,
    preauth_subject_matches,
    registered_grant_canonical_provider_account_id,
    rotation_mints_no_grant,
    web_gate_canonical_provider_account_id,
)
from nativespeaker.api.auth.external_identities import (
    BindingDivergenceError,
    ExternalIdentityRow,
    ProviderClassificationError,
)
from nativespeaker.api.auth.invariants import (
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.operations import IdentityProvider

ISSUER = "https://securetoken.google.com/test-project"

KEY_V1 = HmacKey(version=1, secret=b"k" * 32)
KEY_V2 = HmacKey(version=2, secret=b"j" * 32)


def actor_ring(*, retired: tuple[HmacKey, ...] = (), current: HmacKey = KEY_V1) -> KeyRing:
    return KeyRing(KeyFamily.k_actor_subject, current=current, retired=retired)


def idp_ring(*, retired: tuple[HmacKey, ...] = (), current: HmacKey = KEY_V1) -> KeyRing:
    return KeyRing(KeyFamily.k_idp_account, current=current, retired=retired)


def google_row(uid: str = "g-1", *, subject: str = "sub-1") -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER, subject=subject,
                               provider=IdentityProvider.google, provider_uid=uid)


def anonymous_row() -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER, subject="sub-anon",
                               provider=IdentityProvider.anonymous)


def google_entries(uid: str = "g-1") -> list[dict[str, str]]:
    return [{"provider_id": "google.com", "uid": uid}]


# --- Construction ------------------------------------------------------------------------------


class TestConstruction:

    # [utest->req~proof-actor-subject-hash-hmac-sha256~1]
    # [utest->req~proof-family-actor-subject-hash~1]
    def test_actor_subject_hash_is_the_specified_hmac_sha256_family(self):
        value = actor_subject_hash(ISSUER, "sub-1", actor_ring())
        expected = hmac.new(KEY_V1.secret,
                            f"actor-subject:v1:{ISSUER}:sub-1".encode(),
                            hashlib.sha256).digest()
        assert value.digest == expected
        assert len(value.digest) == 32
        assert value.family is DerivationFamily.actor_subject_hash

    # [utest->req~proof-actor-subject-hash-hmac-sha256~1]
    def test_a_different_key_or_subject_gives_a_different_digest(self):
        base = actor_subject_hash(ISSUER, "sub-1", actor_ring()).digest
        assert actor_subject_hash(ISSUER, "sub-2", actor_ring()).digest != base
        assert actor_subject_hash(ISSUER, "sub-1", actor_ring(current=KEY_V2)).digest != base

    # [utest->req~proof-idp-account-hash-hmac-sha256~1]
    # [utest->req~proof-family-idp-account-hash~1]
    def test_idp_account_hash_is_the_specified_hmac_sha256_family(self):
        value = idp_account_hash(IdentityProvider.google, "g-1", idp_ring())
        expected = hmac.new(KEY_V1.secret, b"idp-account:v1:google:g-1", hashlib.sha256).digest()
        assert value.digest == expected
        assert value.key_version == 1

    # `provider` is `google` or `apple` and never `anonymous`.
    # [utest->req~proof-family-idp-account-hash~1]
    def test_anonymous_is_never_the_provider_component(self):
        with pytest.raises(DerivationError):
            idp_account_preimage(IdentityProvider.anonymous, "whatever")

    # [utest->req~proof-actor-subject-hash-hmac-sha256~1]
    # [utest->req~proof-idp-account-hash-hmac-sha256~1]
    def test_each_family_derives_under_its_own_key(self):
        with pytest.raises(DerivationError):
            actor_subject_hash(ISSUER, "sub-1", idp_ring())
        with pytest.raises(DerivationError):
            idp_account_hash(IdentityProvider.google, "g-1", actor_ring())

    # [utest->req~proof-preauth-subject-hash-derivation~1]
    # [utest->req~proof-family-preauth-subject-hash~1]
    def test_preauth_subject_hash_is_the_actor_family_unchanged(self):
        ring = actor_ring()
        preauth = preauth_subject_hash(ISSUER, "sub-1", ring)
        assert preauth.digest == actor_subject_hash(ISSUER, "sub-1", ring).digest
        assert preauth.family is DerivationFamily.preauth_subject_hash

    # The stored row holds a keyed verifier and never the subject itself: the subject is not
    # recoverable from the digest, and completion recomputes rather than reads it back.
    # [utest->req~proof-preauth-subject-hash-derivation~1]
    # [utest->req~proof-family-preauth-subject-hash~1]
    def test_the_row_holds_a_verifier_recomputed_at_completion(self):
        ring = actor_ring()
        stored = preauth_subject_hash(ISSUER, "sub-1", ring).digest
        assert b"sub-1" not in stored
        assert preauth_subject_matches(stored, ISSUER, "sub-1", ring) is True
        assert preauth_subject_matches(stored, ISSUER, "sub-2", ring) is False


class TestDomainSeparation:

    # [utest->req~proof-hmac-domain-separation~1]
    def test_every_preimage_opens_with_its_families_label(self):
        assert actor_subject_preimage(ISSUER, "x").startswith(
            DOMAIN_LABELS[KeyFamily.k_actor_subject])
        assert idp_account_preimage(IdentityProvider.google, "x").startswith(
            DOMAIN_LABELS[KeyFamily.k_idp_account])

    # The same underlying value under the same key never collides across the two families.
    # [utest->req~proof-hmac-domain-separation~1]
    def test_the_families_never_collide_on_the_same_value(self):
        shared = HmacKey(version=1, secret=b"s" * 32)
        actor = actor_subject_hash("google", "g-1",
                                   KeyRing(KeyFamily.k_actor_subject, current=shared))
        idp = idp_account_hash(IdentityProvider.google, "g-1",
                               KeyRing(KeyFamily.k_idp_account, current=shared))
        assert actor.digest != idp.digest


class TestCanonicalization:

    # An input the adapter normalizes hashes the same as its already-canonical form.
    # [utest->req~proof-hmac-input-canonicalization~1]
    def test_the_adapter_canonicalizes_before_the_hash(self):
        decomposed = unicodedata.normalize("NFD", "josé")
        composed = unicodedata.normalize("NFC", "josé")
        assert decomposed != composed
        ring = actor_ring()
        assert actor_subject_hash(ISSUER, decomposed, ring).digest == \
            actor_subject_hash(ISSUER, composed, ring).digest
        assert actor_subject_hash(ISSUER, "  sub-1  ", ring).digest == \
            actor_subject_hash(ISSUER, "sub-1", ring).digest

    # [utest->req~proof-hmac-input-canonicalization~1]
    def test_an_uncanonicalizable_input_derives_nothing(self):
        for bad in ("", "   ", "a:b", "a\nb"):
            with pytest.raises(DerivationError):
                actor_subject_hash(ISSUER, bad, actor_ring())

    # The canonicalization is the provider-specific adapter's; a provider with no adapter has no
    # canonical form and derives nothing.
    # [utest->req~proof-hmac-input-canonicalization~1]
    def test_the_provider_specific_adapter_is_required(self):
        assert canonical_provider_account_id(IdentityProvider.google, " g-1 ") == "g-1"
        assert canonical_provider_account_id(IdentityProvider.apple, "a-1") == "a-1"
        with pytest.raises(DerivationError):
            canonical_provider_account_id(IdentityProvider.anonymous, "x")


class TestDerivationStrength:

    # [utest->req~proof-derivation-matches-entropy-privacy~1]
    def test_every_stored_derived_identifier_is_a_keyed_full_width_digest(self):
        for family in DerivationFamily:
            spec = assert_derivation_matches(family)
            assert spec.keyed and spec.digest_bits == 256 and not spec.reversible
        assert set(DERIVED_IDENTIFIERS) == set(DerivationFamily)

    # A bare digest, a truncation or a reversible encoding does not match the entropy and
    # privacy properties of the value underneath it.
    # [utest->req~proof-derivation-matches-entropy-privacy~1]
    def test_a_weaker_derivation_is_refused(self):
        for spec in (DerivationSpec("SHA-256", keyed=False, digest_bits=256, reversible=False),
                     DerivationSpec("HMAC-SHA-256", keyed=True, digest_bits=64, reversible=False),
                     DerivationSpec("HMAC-SHA-256", keyed=True, digest_bits=256, reversible=True)):
            with pytest.raises(DerivationError):
                assert_derivation_matches(DerivationFamily.actor_subject_hash, spec)


# --- Keys, versions and rotation ---------------------------------------------------------------


class TestKeyVersions:

    # [utest->req~proof-hmac-key-version-recorded~1]
    def test_the_lookup_and_audit_values_carry_their_key_version(self):
        for value in (actor_subject_hash(ISSUER, "sub-1", actor_ring(current=KEY_V2)),
                      idp_account_hash(IdentityProvider.google, "g-1",
                                       idp_ring(current=KEY_V2))):
            assert assert_persisted_key_version(value).key_version == 2

    # `preauth_subject_hash` is the one exception and carries none.
    # [utest->req~proof-hmac-key-version-recorded~1]
    def test_preauth_subject_hash_carries_no_key_version(self):
        preauth = preauth_subject_hash(ISSUER, "sub-1", actor_ring())
        assert preauth.key_version is None
        assert assert_persisted_key_version(preauth) is preauth

    # [utest->req~proof-hmac-key-version-recorded~1]
    def test_a_missing_or_surplus_key_version_is_refused(self):
        digest = actor_subject_hash(ISSUER, "sub-1", actor_ring()).digest
        from nativespeaker.api.auth.derived_identifiers import DerivedValue
        with pytest.raises(DerivationError):
            assert_persisted_key_version(
                DerivedValue(DerivationFamily.idp_account_hash, digest, None))
        with pytest.raises(DerivationError):
            assert_persisted_key_version(
                DerivedValue(DerivationFamily.preauth_subject_hash, digest, 1))


class TestRotationWindow:

    # Old versions stay valid for lookup; new values are written under the current one.
    # [utest->req~proof-hmac-key-rotation-window~1]
    def test_new_values_use_the_current_key_and_old_ones_stay_readable(self):
        ring = actor_ring(current=KEY_V2, retired=(KEY_V1,))
        assert ring.write_key is KEY_V2
        assert actor_subject_hash(ISSUER, "sub-1", ring).key_version == 2
        assert [key.version for key in ring.lookup_keys()] == [2, 1]
        assert ring.key(1) is KEY_V1

    # [utest->req~proof-hmac-key-rotation-window~1]
    def test_a_version_that_was_not_retained_is_not_a_lookup_key(self):
        with pytest.raises(DerivationError):
            actor_ring(current=KEY_V2).key(1)

    # A challenge prepared before a rotation stops verifying after it: no retired key version is
    # kept for `preauth_subject_hash`, so the comparison fails and the completion is rejected as
    # `challenge_identity_mismatch`, which tells the client to prepare a fresh challenge.
    # [utest->req~proof-preauth-hash-current-key-only~1]
    def test_a_challenge_prepared_before_a_rotation_stops_verifying(self):
        before = preauth_subject_hash(ISSUER, "sub-1", actor_ring()).digest
        rotated = actor_ring(current=KEY_V2, retired=(KEY_V1,))
        assert preauth_subject_matches(before, ISSUER, "sub-1", rotated) is False
        assert preauth_subject_matches(before, ISSUER, "sub-1", actor_ring()) is True

    # [utest->req~proof-preauth-hash-current-key-only~1]
    def test_the_rejection_is_challenge_identity_mismatch(self):
        from nativespeaker.api.auth.derived_identifiers import preauth_mismatch
        from nativespeaker.api.auth.taxonomy import ClientErrorClass
        result, client_class = preauth_mismatch()
        assert result is AuthEventResult.challenge_identity_mismatch
        assert client_class is ClientErrorClass.challenge_required

    # [utest->req~proof-no-raw-subjects-for-rotation~1]
    def test_rotation_never_persists_a_raw_subject(self):
        assert_rotation_persists_no_preimages(["actor_subject_hash_key_version"])
        for column in ("subject", "raw_subject", "actor_subject", "preauth_subject"):
            with pytest.raises(DerivationError):
                assert_rotation_persists_no_preimages([column])

    # [utest->req~proof-no-raw-provider-account-ids-for-rotation~1]
    def test_rotation_never_persists_a_raw_provider_account_id(self):
        assert_rotation_persists_no_preimages(["idp_account_hash_key_version"])
        for column in ("provider_account_id", "raw_provider_account_id",
                       "canonical_provider_account_id"):
            with pytest.raises(DerivationError):
                assert_rotation_persists_no_preimages([column])


class TestKeyStorage:

    # [utest->req~proof-no-raw-keys-in-postgresql~1]
    def test_key_material_comes_from_configuration_not_a_table(self):
        assert assert_key_source("server_configuration") == "server_configuration"
        for source in ("postgresql", "core.hmac_keys", "audit.auth_events"):
            with pytest.raises(DerivationError):
                assert_key_source(source)
        with pytest.raises(DerivationError):
            KeyRing(KeyFamily.k_actor_subject, current=KEY_V1, source="postgresql")

    # [utest->req~proof-no-raw-keys-in-postgresql~1]
    def test_no_application_table_carries_key_material(self):
        assert_no_key_material_column("core.users", ["id", "email"])
        for column in ("hmac_key", "k_idp_account", "attestation_private_key", "private_key"):
            with pytest.raises(DerivationError):
                assert_no_key_material_column("core.access_grants_anti_abuse", [column])


# --- Where the IDP-account inputs come from ----------------------------------------------------


class TestIdpInputs:

    # [utest->req~proof-idp-hmac-inputs-not-from-client~1]
    def test_neither_component_comes_from_client_controlled_material(self):
        for source in (IdpInputSource.stored_identity_binding,
                       IdpInputSource.web_gate_validated_provider_data_entry):
            assert assert_idp_input_source(source) is source
        for source in (IdpInputSource.client_input, IdpInputSource.request_header,
                       IdpInputSource.token_claim, IdpInputSource.sign_in_provider_claim,
                       IdpInputSource.email, IdpInputSource.display_name):
            with pytest.raises(DerivationError):
                assert_idp_input_source(source)

    # [utest->req~proof-registered-grant-canonical-provider-account-id~1]
    def test_the_registered_claim_reads_the_stored_provider_uid(self):
        row = google_row("g-77")
        assert registered_grant_canonical_provider_account_id(row) == "g-77"

    # The operation rejects when the stored value is absent.
    # [utest->req~proof-registered-grant-canonical-provider-account-id~1]
    def test_the_registered_claim_rejects_without_a_stored_provider_uid(self):
        with pytest.raises(DerivationError):
            registered_grant_canonical_provider_account_id(anonymous_row())

    # The mandatory confirmation must match the stored binding, and never rewrites it.
    # [utest->req~proof-registered-grant-canonical-provider-account-id~1]
    def test_the_confirmation_matches_the_stored_binding_without_rewriting_it(self):
        row = google_row("g-1")
        assert confirm_registered_binding(row, google_entries("g-1")) is IdentityProvider.google
        assert (row.provider, row.provider_uid) == (IdentityProvider.google, "g-1")
        with pytest.raises(BindingDivergenceError):
            confirm_registered_binding(row, google_entries("g-2"))
        assert row.provider_uid == "g-1"

    # [utest->req~proof-web-gate-canonical-provider-account-id~1]
    def test_the_web_gate_takes_the_sole_validated_entrys_subject(self):
        account = web_gate_canonical_provider_account_id(google_row("g-9"), google_entries("g-9"))
        assert account.provider is IdentityProvider.google
        assert account.canonical_provider_account_id == "g-9"

    # An invalid shape, a mismatched provider, a mismatched uid or an anonymous claiming identity
    # all deny: the sole entry must equal the stored binding on both components.
    # [utest->req~proof-web-gate-canonical-provider-account-id~1]
    def test_the_web_gate_denies_every_non_matching_shape(self):
        row = google_row("g-9")
        for entries in ([{"provider_id": "apple.com", "uid": "a-9"}],
                        [{"provider_id": "google.com", "uid": "g-8"}],
                        [{"provider_id": "google.com", "uid": "g-9"},
                         {"provider_id": "apple.com", "uid": "a-9"}],
                        []):
            with pytest.raises((DerivationError, ProviderClassificationError)):
                web_gate_canonical_provider_account_id(row, entries)
        with pytest.raises(DerivationError):
            web_gate_canonical_provider_account_id(anonymous_row(), google_entries())


# --- The canonical registry --------------------------------------------------------------------


class TestRegistryUniqueness:

    # [utest->req~proof-firebase-uid-not-uniqueness-anchor~1]
    def test_the_anchor_is_the_stable_provider_uid(self):
        assert assert_uniqueness_anchor(UniquenessAnchor.stable_provider_uid) is \
            UniquenessAnchor.stable_provider_uid
        for anchor in (UniquenessAnchor.firebase_uid, UniquenessAnchor.idp_account_hash):
            with pytest.raises(DerivationError):
                assert_uniqueness_anchor(anchor)

    # Deleting and recreating a Firebase user for the same Google account produces a new Firebase
    # UID while the provider subject stays the same — and the gate stays closed.
    # [utest->req~proof-firebase-uid-not-uniqueness-anchor~1]
    def test_a_recreated_firebase_user_does_not_reopen_the_gate(self):
        index = IdpAccountAliasIndex(ProviderAccountGates(), idp_ring())
        account = ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1")
        index.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        # A second Firebase account, same underlying provider subject.
        with pytest.raises(GateAlreadyConsumedError):
            index.consume(ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1"),
                          GateConsumptionKind.registered_account_grant, uuid7())

    # [utest->req~proof-provider-accounts-registry-uniqueness~1]
    def test_uniqueness_is_enforced_on_the_registry_not_on_the_alias(self):
        assert IDP_ACCOUNT_HASH_AUTHORITATIVE is False
        index = IdpAccountAliasIndex(ProviderAccountGates(), idp_ring())
        account = ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1")
        alias = index.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        assert alias.key_version == 1
        # The two consumption kinds are distinct rows: the same account may hold one of each.
        index.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
        with pytest.raises(GateAlreadyConsumedError):
            index.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())

    # A lookup through any retained version resolves to the same canonical provider-account row,
    # and new writes still use the current version.
    # [utest->req~proof-idp-account-key-rotation-window~2]
    def test_every_retained_version_resolves_to_the_same_row(self):
        rotated = idp_ring(current=KEY_V2, retired=(KEY_V1,))
        index = IdpAccountAliasIndex(ProviderAccountGates(), rotated)
        account = ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1")
        alias = index.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        assert alias.key_version == 2
        old = idp_account_hash(IdentityProvider.google, "g-1", idp_ring(current=KEY_V1)).digest
        assert index.resolve(old) == account
        assert index.resolve(alias.digest) == account

    # The required regression: a claim under the new key version, for an account consumed under
    # the old one, is rejected. Rotating the alias key mints no grant and reopens no gate.
    # [utest->req~proof-idp-rotation-never-mints-grant~1]
    def test_rotating_the_key_never_reopens_a_consumed_gate(self):
        gates = ProviderAccountGates()
        account = ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1")
        before = IdpAccountAliasIndex(gates, idp_ring(current=KEY_V1))
        consumed = before.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        assert consumed.key_version == 1
        after = IdpAccountAliasIndex(gates, idp_ring(current=KEY_V2, retired=(KEY_V1,)))
        after.register(account)
        assert rotation_mints_no_grant(after, account,
                                       GateConsumptionKind.registered_account_grant,
                                       uuid7()) is AuthEventResult.idp_account_already_claimed
