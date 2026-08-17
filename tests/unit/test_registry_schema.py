"""The record tables beside the grant tables: `core.manual_grant_issuances`,
`core.provider_accounts` and `core.provider_account_gate_consumptions`.

Structural expectations are transcribed from `06-schema-reference.md` by hand, not read back out of
the migration or the reference copy of the DDL.
"""

from typing import Any
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.derived_identifiers import (
    DerivationError,
    HmacKey,
    IdpAccountAliasIndex,
    IdpInputSource,
    KeyFamily,
    KeyRing,
    idp_account_hash,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    ERASURE_RETAINED_ROWS,
    IdentityState,
    erase_account,
)
from nativespeaker.api.auth.invariants import (
    GATE_CONFLICTS,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    InvariantError,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.manual_grants import (
    ManualGrantError,
    assert_excluded_from_anti_abuse,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.registry_schema import (
    GATE_CLAIM_OPERATIONS,
    GATE_ROLE,
    GATE_ROLES_REFUSED,
    LINK_UNIQUENESS_KEY,
    LINK_UNIQUENESS_TABLE,
    MANUAL_ISSUANCE_AUDIT_EVENT_ROWS,
    MANUAL_ISSUANCE_PRIMARY_KEY,
    MANUAL_ISSUANCE_REQUIRED_TEXT,
    MANUAL_ISSUANCE_ROW_DELETERS,
    MANUAL_ISSUANCE_ROW_UPDATERS,
    MANUAL_ISSUANCE_UNIQUE_COLUMNS,
    MANUAL_ISSUANCES_TABLE,
    PROVIDER_ACCOUNT_REASSIGNERS,
    PROVIDER_ACCOUNT_ROW_DELETERS,
    PROVIDER_ACCOUNTS_TABLE,
    PROVIDER_ACCOUNTS_UNIQUE_ON,
    REGISTRY_PROVIDERS,
    STABLE_UID_SOURCE_COLUMN,
    UNRESOLVED_ROW_IS_FRESH_ACCOUNT,
    PrelaunchDisposition,
    RegistryError,
    assert_alias_never_mints_a_row,
    assert_case_issues_once,
    assert_gate_is_no_second_allowance,
    assert_grant_claimed_by_one_case,
    assert_issuance_row_immutable,
    assert_stable_binding_immutable,
    assert_uniqueness_rules_separate,
    canonical_account,
    consumed_grant,
    gate_consumption_row,
    manual_issuance_row,
    prelaunch_disposition,
    resolve_or_create_provider_account,
    resolve_through_retained_version,
)
from unit.test_schema_ddl import MIGRATION, Schema, declarative_section, parse

KEY_V1 = HmacKey(version=1, secret=b"k" * 32)
KEY_V2 = HmacKey(version=2, secret=b"j" * 32)


@pytest.fixture(scope="module")
def applied() -> Schema:
    return parse(declarative_section(MIGRATION.read_text()))


def idp_ring(*, current: HmacKey = KEY_V1, retired: tuple[HmacKey, ...] = ()) -> KeyRing:
    return KeyRing(KeyFamily.k_idp_account, current=current, retired=retired)


def alias_index(ring: KeyRing | None = None,
                gates: ProviderAccountGates | None = None) -> IdpAccountAliasIndex:
    return IdpAccountAliasIndex(gates or ProviderAccountGates(), ring or idp_ring())


GOOGLE = ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1")
APPLE = ProviderAccount(provider=IdentityProvider.apple, provider_uid="g-1")


def manual_grant(*, user_id: UUID, grant_id: UUID | None = None,
                 source: AccessGrantSource = AccessGrantSource.manual) -> dict[str, Any]:
    return {"id": grant_id or uuid7(), "user_id": user_id, "tier_id": "anonymous",
            "source": source, "subscription_id": None}


def one_transaction() -> dict[str, Any]:
    transaction = object()
    return {"transaction": transaction, "grant_transaction": transaction,
            "consumption_transaction": transaction}


# --- `core.manual_grant_issuances` --------------------------------------------------------------

# One row per support case, written in the same transaction as the grant it produced.
# [utest->req~schema-manual-grant-issuances-purpose~1]
def test_the_issuance_row_records_one_case_in_the_grants_own_transaction(applied: Schema):
    user_id = uuid7()
    grant = manual_grant(user_id=user_id)
    transaction = object()
    row = manual_issuance_row(case_id="CASE-1", grant=grant, operator="ops@example.com",
                              reason="ticket NS-42", target_user_id=user_id,
                              transaction=transaction, grant_transaction=transaction)
    assert row == {"case_id": "CASE-1", "grant_id": grant["id"], "user_id": user_id,
                   "operator": "ops@example.com", "reason": "ticket NS-42"}
    # A second transaction is not the grant's transaction.
    with pytest.raises(RegistryError):
        manual_issuance_row(case_id="CASE-1", grant=grant, operator="ops@example.com",
                            reason="ticket NS-42", target_user_id=user_id,
                            transaction=transaction, grant_transaction=object())
    # The table exists with exactly the columns the specification declares.
    issuances = applied.tables[MANUAL_ISSUANCES_TABLE]
    assert set(issuances.columns) == {"case_id", "grant_id", "user_id", "operator", "reason",
                                      "created_at"}


# [utest->req~schema-manual-grant-issuances-case-id-primary-key~1]
def test_case_id_is_the_primary_key_so_a_repeat_issues_nothing(applied: Schema):
    assert MANUAL_ISSUANCE_PRIMARY_KEY == "case_id"
    assert applied.tables[MANUAL_ISSUANCES_TABLE].columns["case_id"] == \
        "TEXT PRIMARY KEY CHECK (case_id <> '')"
    assert_case_issues_once("CASE-2", ["CASE-1"])
    with pytest.raises(RegistryError):
        assert_case_issues_once("CASE-1", ["CASE-1"])


# The procedure itself returns the recorded result rather than issuing a second grant.
# [utest->req~schema-manual-grant-issuances-case-id-primary-key~1]
def test_a_repeated_case_returns_the_recorded_grant():
    from unit.test_manual_grants import run

    first = run()
    again = run(recorded={first.issuance["case_id"]: first})
    assert again.repeated is True
    assert again.grant["id"] == first.grant["id"]
    assert again.issuance == first.issuance


# [utest->req~schema-manual-grant-issuances-grant-id-unique~1]
def test_grant_id_is_unique_so_one_grant_belongs_to_one_case(applied: Schema):
    assert MANUAL_ISSUANCE_UNIQUE_COLUMNS == ("grant_id",)
    assert applied.tables[MANUAL_ISSUANCES_TABLE].columns["grant_id"] == \
        "UUID NOT NULL UNIQUE REFERENCES core.access_grants (id)"
    grant_id = uuid7()
    assert_grant_claimed_by_one_case(grant_id, {"CASE-1": uuid7()})
    with pytest.raises(RegistryError):
        assert_grant_claimed_by_one_case(grant_id, {"CASE-1": grant_id})
    # The recorded grant is always a `manual` grant, so it carries no anti-abuse row and no
    # gate-consumption row: an issuance row naming a free-credit grant is refused.
    user_id = uuid7()
    transaction = object()
    for source in (AccessGrantSource.registered_account_grant,
                   AccessGrantSource.anonymous_device_grant, AccessGrantSource.subscription):
        with pytest.raises(RegistryError):
            manual_issuance_row(case_id="CASE-1",
                                grant=manual_grant(user_id=user_id, source=source),
                                operator="ops", reason="ticket", target_user_id=user_id,
                                transaction=transaction, grant_transaction=transaction)
    # And that `manual` grant really has neither row.
    assert_excluded_from_anti_abuse()
    with pytest.raises(ManualGrantError):
        assert_excluded_from_anti_abuse(gate_consumption_rows=1)
    with pytest.raises(InvariantError):
        assert_excluded_from_anti_abuse(anti_abuse_grant_source=AccessGrantSource.manual)


# [utest->req~schema-manual-grant-issuances-user-id-target-owner~1]
def test_user_id_is_the_target_owner_and_the_grants_own_owner(applied: Schema):
    assert applied.tables[MANUAL_ISSUANCES_TABLE].columns["user_id"] == \
        "UUID NOT NULL REFERENCES core.users (id)"
    user_id = uuid7()
    transaction = object()
    row = manual_issuance_row(case_id="CASE-1", grant=manual_grant(user_id=user_id),
                              operator="ops", reason="ticket", target_user_id=user_id,
                              transaction=transaction, grant_transaction=transaction)
    assert row["user_id"] == user_id
    # A row whose target owner is not the grant's owner is refused.
    with pytest.raises(RegistryError):
        manual_issuance_row(case_id="CASE-1", grant=manual_grant(user_id=uuid7()),
                            operator="ops", reason="ticket", target_user_id=user_id,
                            transaction=transaction, grant_transaction=transaction)


# [utest->req~schema-manual-grant-issuances-operator-reason-required~1]
def test_operator_and_reason_are_required_and_non_empty(applied: Schema):
    assert MANUAL_ISSUANCE_REQUIRED_TEXT == ("case_id", "operator", "reason")
    issuances = applied.tables[MANUAL_ISSUANCES_TABLE]
    assert issuances.columns["operator"] == "TEXT NOT NULL CHECK (operator <> '')"
    assert issuances.columns["reason"] == "TEXT NOT NULL CHECK (reason <> '')"
    user_id = uuid7()
    transaction = object()
    for blank in ("", "   "):
        with pytest.raises(RegistryError):
            manual_issuance_row(case_id="CASE-1", grant=manual_grant(user_id=user_id),
                                operator=blank, reason="ticket", target_user_id=user_id,
                                transaction=transaction, grant_transaction=transaction)
        with pytest.raises(RegistryError):
            manual_issuance_row(case_id="CASE-1", grant=manual_grant(user_id=user_id),
                                operator="ops", reason=blank, target_user_id=user_id,
                                transaction=transaction, grant_transaction=transaction)
        with pytest.raises(RegistryError):
            manual_issuance_row(case_id=blank, grant=manual_grant(user_id=user_id),
                                operator="ops", reason="ticket", target_user_id=user_id,
                                transaction=transaction, grant_transaction=transaction)


# The issuance procedure itself refuses the same shapes: the row contract is the one it writes.
# [utest->req~schema-manual-grant-issuances-operator-reason-required~1]
def test_the_procedure_refuses_a_row_the_table_would_reject():
    from nativespeaker.api.auth.manual_grants import issue_manual_grant
    from unit.test_manual_grants import LOST_ANONYMOUS, NOW, request_for

    def issue(**overrides: Any) -> Any:
        return issue_manual_grant(request_for(**overrides), grant_id=uuid7(),
                                  lost=LOST_ANONYMOUS, live_grant_ids=(), grants=(), now=NOW,
                                  transaction=object(), claim_would_have_succeeded=True)

    issued = issue()
    assert issued.issuance["operator"] and issued.issuance["reason"]
    for blank in ({"reason": "   "}, {"operator": ""}, {"case_id": " "}):
        with pytest.raises(ManualGrantError):
            issue(**blank)


# [utest->req~schema-manual-grant-issuances-rows-immutable~1]
def test_issuance_rows_are_never_updated_or_deleted_and_write_no_audit_row():
    assert MANUAL_ISSUANCE_ROW_UPDATERS == frozenset()
    assert MANUAL_ISSUANCE_ROW_DELETERS == frozenset()
    assert MANUAL_ISSUANCE_AUDIT_EVENT_ROWS == 0
    assert_issuance_row_immutable()
    with pytest.raises(RegistryError):
        assert_issuance_row_immutable(updated=("reason",))
    with pytest.raises(RegistryError):
        assert_issuance_row_immutable(deleted=True)
    # `audit.auth_events` covers the audited attempt path only, so an operator issuance has no row
    # there and this table is the durable record instead.
    with pytest.raises(RegistryError):
        assert_issuance_row_immutable(audit_rows=1)


# --- `core.provider_accounts` and its gate consumptions -----------------------------------------

# [utest->req~schema-provider-accounts-registry-definition~1]
def test_the_registry_binds_one_stable_uid_per_provider_to_one_canonical_row(applied: Schema):
    assert PROVIDER_ACCOUNTS_UNIQUE_ON == ("provider", "provider_uid")
    assert REGISTRY_PROVIDERS == {IdentityProvider.google, IdentityProvider.apple}
    assert STABLE_UID_SOURCE_COLUMN == "core.external_identities.provider_uid"
    accounts = applied.tables[PROVIDER_ACCOUNTS_TABLE]
    assert "UNIQUE (provider, provider_uid)" in accounts.constraints
    assert accounts.columns["provider"] == \
        "core.identity_provider NOT NULL CHECK (provider IN ('google', 'apple'))"
    assert accounts.columns["provider_uid"] == "TEXT NOT NULL CHECK (provider_uid <> '')"
    # The provider is a component of the key, so the Google and Apple namespaces are separate: the
    # same stable UID string under two providers is two accounts.
    assert canonical_account(IdentityProvider.google, "g-1") != \
        canonical_account(IdentityProvider.apple, "g-1")
    # Anonymous is no provider account, and an empty UID is no identifier.
    with pytest.raises(RegistryError):
        canonical_account(IdentityProvider.anonymous, "g-1")
    with pytest.raises(RegistryError):
        canonical_account(IdentityProvider.google, "  ")


# [utest->req~schema-provider-accounts-registry-definition~1]
def test_one_consumption_row_per_account_and_kind_recording_the_grant_it_produced(
        applied: Schema):
    consumptions = applied.tables["core.provider_account_gate_consumptions"]
    assert "PRIMARY KEY (provider_account_id, consumption_kind)" in consumptions.constraints
    assert consumptions.columns["grant_id"] == \
        "UUID NOT NULL REFERENCES core.access_grants (id)"
    assert applied.enums["core.gate_consumption_kind"] == ("web_anonymous_gate",
                                                           "registered_account_grant")
    # `web_anonymous_gate` is the web anonymous claim's gate; `registered_account_grant` is the
    # registered claim's.
    assert GATE_CLAIM_OPERATIONS == {
        GateConsumptionKind.web_anonymous_gate: AuthOperation.claim_anonymous_grant,
        GateConsumptionKind.registered_account_grant: AuthOperation.claim_registered_grant,
    }
    grant_id = uuid7()
    row = gate_consumption_row(GOOGLE, GateConsumptionKind.web_anonymous_gate, grant_id)
    assert row == {"provider_account_id": GOOGLE,
                   "consumption_kind": GateConsumptionKind.web_anonymous_gate,
                   "grant_id": grant_id}
    # The consumption records the grant it produced, so a repeat claim is matched to its grant.
    gates = ProviderAccountGates()
    assert consumed_grant(gates, GOOGLE, GateConsumptionKind.web_anonymous_gate) is None
    gates.consume(GOOGLE, GateConsumptionKind.web_anonymous_gate, grant_id)
    assert consumed_grant(gates, GOOGLE, GateConsumptionKind.web_anonymous_gate) == grant_id
    # A row for the other namespace's account is a different row.
    assert consumed_grant(gates, APPLE, GateConsumptionKind.web_anonymous_gate) is None


# [utest->req~schema-provider-accounts-uid-immutable-historical~1]
def test_the_registry_row_is_immutable_and_resolved_or_created_in_one_transaction():
    assert PROVIDER_ACCOUNT_ROW_DELETERS == frozenset()
    assert PROVIDER_ACCOUNT_REASSIGNERS == frozenset()
    index = alias_index()
    resolved = resolve_or_create_provider_account(
        index, GOOGLE, source=IdpInputSource.stored_identity_binding, **one_transaction())
    assert resolved == GOOGLE
    assert index.accounts == (GOOGLE,)
    # A second claim for the same stable UID resolves to the very same row rather than creating one.
    again = resolve_or_create_provider_account(
        index, ProviderAccount(provider=IdentityProvider.google, provider_uid="g-1"),
        source=IdpInputSource.stored_identity_binding, **one_transaction())
    assert again == resolved
    assert index.accounts == (GOOGLE,)
    # The provider binding and the stable UID are immutable.
    assert_stable_binding_immutable(GOOGLE, GOOGLE)
    with pytest.raises(RegistryError):
        assert_stable_binding_immutable(GOOGLE, APPLE)
    with pytest.raises(RegistryError):
        assert_stable_binding_immutable(
            GOOGLE, ProviderAccount(provider=IdentityProvider.google, provider_uid="g-2"))
    # The resolve-or-create shares the grant's and the consumption's transaction.
    transactions = one_transaction()
    with pytest.raises(RegistryError):
        resolve_or_create_provider_account(index, GOOGLE,
                                          source=IdpInputSource.stored_identity_binding,
                                          transaction=transactions["transaction"],
                                          grant_transaction=object(),
                                          consumption_transaction=transactions["transaction"])
    with pytest.raises(RegistryError):
        resolve_or_create_provider_account(index, GOOGLE,
                                          source=IdpInputSource.stored_identity_binding,
                                          transaction=transactions["transaction"],
                                          grant_transaction=transactions["transaction"],
                                          consumption_transaction=object())


# [utest->req~schema-provider-accounts-uid-source-backend-verified~1]
def test_the_stable_uid_comes_only_from_a_backend_verified_source():
    index = alias_index()
    # The stored identity binding, and the mandatory Firebase Admin `providerData` read the web
    # gate validates, are the two permitted sources.
    for source in (IdpInputSource.stored_identity_binding,
                   IdpInputSource.web_gate_validated_provider_data_entry):
        resolve_or_create_provider_account(index, GOOGLE, source=source, **one_transaction())
    # A client field, a gateway header, a token claim, or a profile field never supplies it.
    for source in (IdpInputSource.client_input, IdpInputSource.request_header,
                   IdpInputSource.token_claim, IdpInputSource.sign_in_provider_claim,
                   IdpInputSource.email, IdpInputSource.display_name):
        with pytest.raises(DerivationError):
            resolve_or_create_provider_account(index, GOOGLE, source=source, **one_transaction())


# [utest->req~schema-provider-accounts-gate-conflict-results~1]
def test_each_gates_conflict_has_its_own_audited_result_and_client_class():
    # The registered gate's conflict is audited `idp_account_already_claimed` and surfaced as
    # `account_already_claimed`; the web gate's is `anti_abuse_already_claimed` and
    # `device_grant_exhausted`. They are different rejections, not one shared one.
    registered = GATE_CONFLICTS[GateConsumptionKind.registered_account_grant]
    web = GATE_CONFLICTS[GateConsumptionKind.web_anonymous_gate]
    assert registered[0] is AuthEventResult.idp_account_already_claimed
    assert str(registered[1]) == "account_already_claimed"
    assert web[0] is AuthEventResult.anti_abuse_already_claimed
    assert str(web[1]) == "device_grant_exhausted"
    for kind, (result, client_class) in ((GateConsumptionKind.registered_account_grant, registered),
                                        (GateConsumptionKind.web_anonymous_gate, web)):
        gates = ProviderAccountGates()
        gates.consume(GOOGLE, kind, uuid7(), idp_account_hash=b"v1", hash_key_version=1)
        # A repeat presenting a different hash version is still a conflict: the key is the stable
        # UID, so "already consumed" does not depend on which version was presented.
        with pytest.raises(GateAlreadyConsumedError) as conflict:
            gates.consume(GOOGLE, kind, uuid7(), idp_account_hash=b"v2", hash_key_version=2)
        assert conflict.value.result is result
        assert conflict.value.client_class is client_class


# [utest->req~schema-provider-accounts-gates-are-abuse-brakes~1]
def test_an_open_gate_is_an_abuse_brake_and_never_a_second_user_allowance():
    assert GATE_ROLE == "per_key_abuse_brake"
    assert "independent_user_allowance" in GATE_ROLES_REFUSED
    # A user who has committed no free grant is unconstrained by the open gates.
    assert_gate_is_no_second_allowance(
        open_gates=(GateConsumptionKind.web_anonymous_gate,), committed_free_sources=())
    # A user who already holds one free grant is refused a second, even though the other
    # endpoint's gate for the same provider account is untouched.
    with pytest.raises(RegistryError):
        assert_gate_is_no_second_allowance(
            open_gates=(GateConsumptionKind.registered_account_grant,),
            committed_free_sources=(AccessGrantSource.anonymous_device_grant,))
    with pytest.raises(RegistryError):
        assert_gate_is_no_second_allowance(
            open_gates=(GateConsumptionKind.web_anonymous_gate,),
            committed_free_sources=(AccessGrantSource.registered_account_grant,))
    # The two kinds really are distinct rows on the brake side: one account may spend one of each.
    gates = ProviderAccountGates()
    gates.consume(GOOGLE, GateConsumptionKind.web_anonymous_gate, uuid7())
    gates.consume(GOOGLE, GateConsumptionKind.registered_account_grant, uuid7())


# [utest->req~schema-provider-accounts-hash-non-authoritative-alias~1]
def test_the_hash_is_a_lookup_alias_that_never_mints_a_second_canonical_row():
    rotated = idp_ring(current=KEY_V2, retired=(KEY_V1,))
    index = alias_index(rotated)
    index.register(GOOGLE)
    # Several key versions map to the same stable account, and a lookup through any retained
    # version resolves to the same canonical row.
    current = idp_account_hash(IdentityProvider.google, "g-1", rotated).digest
    old = idp_account_hash(IdentityProvider.google, "g-1", idp_ring(current=KEY_V1)).digest
    assert current != old
    assert resolve_through_retained_version(index, current) == GOOGLE
    assert resolve_through_retained_version(index, old) == GOOGLE
    assert resolve_through_retained_version(index, b"not-an-alias" * 4) is None
    # A resolve with no current-version hash at all still finds the one row: the registry is keyed
    # on the stable UID, so no second canonical row is created for an account that already has one.
    assert assert_alias_never_mints_a_row(index, GOOGLE, current_version_hash=None) == GOOGLE
    assert index.accounts == (GOOGLE,)
    assert assert_alias_never_mints_a_row(index, GOOGLE, current_version_hash=old) == GOOGLE
    assert index.accounts == (GOOGLE,)
    # A genuinely new account does get its own row, under the other provider's namespace.
    assert assert_alias_never_mints_a_row(index, APPLE, current_version_hash=None) == APPLE
    assert set(index.accounts) == {GOOGLE, APPLE}


# [utest->req~schema-provider-accounts-prelaunch-migration~1]
def test_prelaunch_migration_backfills_or_fails_closed_but_invents_no_fresh_account():
    assert UNRESOLVED_ROW_IS_FRESH_ACCOUNT is False
    # Backfill the stable UID wherever it is available.
    assert prelaunch_disposition(stable_uid="g-1") is PrelaunchDisposition.backfilled
    # An unresolved hash-only row is discarded, or the migration fails closed — never treated as a
    # fresh account, which would hand that provider account a second free grant.
    assert prelaunch_disposition(stable_uid=None) is PrelaunchDisposition.discarded
    assert prelaunch_disposition(stable_uid=None, discard_unresolved=False) \
        is PrelaunchDisposition.failed_closed
    assert prelaunch_disposition(stable_uid="   ") is PrelaunchDisposition.discarded
    assert PrelaunchDisposition.backfilled not in {
        prelaunch_disposition(stable_uid=None),
        prelaunch_disposition(stable_uid=None, discard_unresolved=False)}


# [utest->req~schema-provider-accounts-survives-erasure~1]
def test_erasure_keeps_the_registry_rows_so_the_gate_stays_closed():
    from nativespeaker.api.auth.external_identities import mark_free_grant_consumed
    from unit.test_external_identities import NOW, google_row

    assert "core.provider_accounts" in ERASURE_RETAINED_ROWS
    assert "core.provider_account_gate_consumptions" in ERASURE_RETAINED_ROWS
    transaction = object()
    row = mark_free_grant_consumed(google_row(), now=NOW,
                                   grant_transaction=transaction, marker_transaction=transaction)
    gates = ProviderAccountGates()
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid=row.provider_uid or "")
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    tombstone, scrubbed = erase_account(row, profile={"email": "a@b.c", "display_name": "A"})
    # The PII is gone and the identity row survives as a tombstone...
    assert scrubbed == {"email": None, "display_name": None}
    assert tombstone.identity_state is IdentityState.historical
    # ...and the erased provider account may not claim a free grant again.
    with pytest.raises(GateAlreadyConsumedError):
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    assert consumed_grant(gates, account, GateConsumptionKind.registered_account_grant) is not None


# [utest->req~schema-provider-accounts-link-uniqueness-separate~1]
def test_the_link_reservation_and_the_gate_uniqueness_are_two_separate_rules(applied: Schema):
    from nativespeaker.api.auth.invariants import (
        ProviderAccountAlreadyLinkedError,
        ProviderAccountReservations,
    )

    assert_uniqueness_rules_separate()
    assert LINK_UNIQUENESS_TABLE == "core.external_identities"
    assert LINK_UNIQUENESS_KEY == ("issuer", "provider", "provider_uid")
    # Two different keys on two different tables.
    assert "ix_external_identities_provider_account" in applied.indexes
    assert "PRIMARY KEY (provider_account_id, consumption_kind)" in \
        applied.tables["core.provider_account_gate_consumptions"].constraints
    # A consumed gate does not attach anything, and an already-attached provider account is
    # rejected on attachment rather than silently moved to the second user.
    reservations = ProviderAccountReservations()
    first, second = uuid7(), uuid7()
    reservations.bind(operation=AuthOperation.create_user, issuer="iss",
                      provider=IdentityProvider.google, provider_uid="g-1", user_id=first)
    with pytest.raises(ProviderAccountAlreadyLinkedError):
        reservations.bind(operation=AuthOperation.upgrade_anonymous_to_registered, issuer="iss",
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=second)
    assert reservations.holder("iss", IdentityProvider.google, "g-1") == first
    # Spending the gate is a separate act with a separate result class.
    gates = ProviderAccountGates()
    gates.consume(GOOGLE, GateConsumptionKind.registered_account_grant, uuid7())
    assert reservations.holder("iss", IdentityProvider.google, "g-1") == first
    assert GATE_CONFLICTS[GateConsumptionKind.registered_account_grant][0] is not \
        ProviderAccountAlreadyLinkedError.result
