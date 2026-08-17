"""The schema-specific invariants of the schema reference: the facts the declarative schema
enforces by construction, and the write-side guards that keep code from proposing a row it
forbids.

Structural expectations are transcribed from the specification, not read back out of either the
migration or the reference copy of the DDL.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Column, ForeignKey, MetaData, Table, Uuid

from nativespeaker.api.auth.audit import (
    AttemptPhase,
    AuditAlreadyWrittenError,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    AuthResultCounter,
    terminal_event,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    DELETE_PERMITTED_ROLES,
    IDENTITY_ROW_DELETERS,
    PAIRING_ENFORCEMENT_MECHANISMS,
    IdentityError,
    IdentityState,
    NativeClaimPlatform,
    assert_no_identity_delete,
    create_account,
    may_delete_identity_rows,
    resolve_owner,
    retire,
    transition_identity_state,
)
from nativespeaker.api.auth.invariants import (
    ENUM_TYPED_FIELDS,
    AttributionSource,
    AttributionTokens,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    GrantCreator,
    InvariantError,
    ProviderAccount,
    ProviderAccountAlreadyLinkedError,
    ProviderAccountGates,
    ProviderAccountReservations,
    StoreProvider,
    assert_attribution_source,
    assert_grant_columns_entitlement_only,
    assert_owner_agreement,
    provider_uid_reserved,
)
from nativespeaker.api.auth.movement import movement_audit_details
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.profile import (
    AccountClass,
    OrphanUserError,
    ProfileError,
    assert_hard_delete_allowed,
)
from nativespeaker.api.auth.schema_invariants import (
    FORBIDDEN_ANTI_ABUSE_COLUMNS,
    FREE_CREDIT_GRANT_SOURCES,
    NEVER_WRITTEN_COLUMNS,
    AntiAbuseEvidence,
    AttributionOutcome,
    LookupOutcome,
    anti_abuse_evidence,
    assert_anti_abuse_pairing,
    assert_classification_pairing,
    assert_enum_typed,
    assert_free_credit_creator,
    assert_grant_source_never_rewritten,
    assert_native_claim_written_before_grant,
    assert_no_client_asserted_attribution,
    assert_no_never_written_column,
    assert_no_raw_device_material,
    assert_registered_conversion,
    assert_tokens_minted_at_creation,
    assert_tokens_survive_upgrade,
    assert_upgrade_revalidates_under_lock,
    attribute_purchase,
    classification_write_set,
    is_free_credit_source,
    requires_anti_abuse_row,
)
from unit.test_schema_auth_events import ISSUER, NOW, FakeSession, RecordingSink, actor
from unit.test_schema_ddl import MIGRATION, Schema, declarative_section, parse

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(scope="module")
def applied() -> Schema:
    return parse(declarative_section(MIGRATION.read_text()))


def constraints_of(applied: Schema, table: str) -> str:
    return " ".join(applied.tables[table].constraints)


# --- 01. Who owns what --------------------------------------------------------------------------

# The business data that always belongs to an internal `core.users.id`, and the column that
# carries that ownership.
USER_OWNED = {
    "core.chats": "user_id",
    "core.subscriptions": "user_id",
    "core.store_purchase_tokens": "user_id",
    "core.access_grants": "user_id",
    "core.manual_grant_issuances": "user_id",
}


# [utest->req~schema-invariant-01~1]
def test_business_data_belongs_to_users_id_and_usage_to_the_grant(applied: Schema):
    for table, column in USER_OWNED.items():
        assert "REFERENCES core.users (id)" in applied.tables[table].columns[column], table
    # Store purchases are attributed to a user by the same key.
    assert "REFERENCES core.users (id)" in \
        applied.tables["core.store_purchases"].columns["purchase_user_id"]
    # Messages hang off the chat, so they inherit its single owner rather than naming their own.
    assert not [name for name, definition in applied.tables["core.messages"].columns.items()
                if "REFERENCES core.users" in definition]
    # Monthly usage counters belong to the grant, never to the user.
    usage = applied.tables["core.user_monthly_usage"]
    assert usage.columns["grant_id"] == \
        "UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE"
    assert "user_id" not in usage.columns


# [utest->req~schema-invariant-01~1]
def test_a_usage_table_owned_by_the_user_is_an_ownership_violation():
    from nativespeaker.api.auth.ownership import (
        assert_ownership_keys,
        ownership_violations,
    )
    metadata = MetaData(schema="core")
    Table("users", metadata, Column("id", Uuid, primary_key=True))
    Table("access_grants", metadata,
          Column("id", Uuid, primary_key=True),
          Column("user_id", Uuid, ForeignKey("core.users.id")))
    Table("user_monthly_usage", metadata,
          Column("grant_id", Uuid, ForeignKey("core.access_grants.id"), primary_key=True))
    assert ownership_violations(metadata) == []
    assert_ownership_keys(metadata)
    # The same usage table owned by the user instead of its grant is refused.
    wrong = MetaData(schema="core")
    Table("users", wrong, Column("id", Uuid, primary_key=True))
    Table("user_monthly_usage", wrong,
          Column("user_id", Uuid, ForeignKey("core.users.id"), primary_key=True))
    assert ownership_violations(wrong)


# --- 02. The creators of a free-credit grant, and the fixed `source` -----------------------------

# [utest->req~schema-invariant-02~1]
def test_only_the_two_claims_create_the_two_free_credit_sources():
    assert set(FREE_CREDIT_GRANT_SOURCES) == {AccessGrantSource.anonymous_device_grant,
                                              AccessGrantSource.registered_account_grant}
    assert_free_credit_creator(GrantCreator.claim_anonymous_grant,
                               AccessGrantSource.anonymous_device_grant)
    assert_free_credit_creator(GrantCreator.claim_registered_grant,
                               AccessGrantSource.registered_account_grant)
    # Neither claim may create the other's source.
    with pytest.raises(InvariantError):
        assert_free_credit_creator(GrantCreator.claim_anonymous_grant,
                                   AccessGrantSource.registered_account_grant)
    with pytest.raises(InvariantError):
        assert_free_credit_creator(GrantCreator.claim_registered_grant,
                                   AccessGrantSource.anonymous_device_grant)
    # `subscription` and `manual` are not free-credit sources at all.
    for source in (AccessGrantSource.subscription, AccessGrantSource.manual):
        assert is_free_credit_source(source) is False
        with pytest.raises(InvariantError):
            assert_free_credit_creator(GrantCreator.purchase_ingestion, source)


# [utest->req~schema-invariant-02~1]
def test_the_conversion_supersedes_and_inserts_rather_than_rewriting_a_source(applied: Schema):
    transaction = object()
    assert_registered_conversion(superseded_source=AccessGrantSource.anonymous_device_grant,
                                 created_source=AccessGrantSource.registered_account_grant,
                                 superseded_transaction=transaction,
                                 created_transaction=transaction)
    # Both rows commit together, not across two transactions.
    with pytest.raises(InvariantError):
        assert_registered_conversion(superseded_source=AccessGrantSource.anonymous_device_grant,
                                     created_source=AccessGrantSource.registered_account_grant,
                                     superseded_transaction=transaction,
                                     created_transaction=object())
    # And a grant's own source is never rewritten into the other one.
    assert_grant_source_never_rewritten(AccessGrantSource.anonymous_device_grant,
                                        AccessGrantSource.anonymous_device_grant)
    with pytest.raises(InvariantError):
        assert_grant_source_never_rewritten(AccessGrantSource.anonymous_device_grant,
                                            AccessGrantSource.registered_account_grant)
    # The schema bounds each user to one committed grant per free source for life.
    index = applied.indexes["ix_access_grants_one_free_grant_per_user_source"]
    assert "core.access_grants (user_id, source)" in index
    assert "WHERE source IN ('anonymous_device_grant', 'registered_account_grant')" in index


# --- 03. Authorization-relevant categorical fields are enums ------------------------------------

# [utest->req~schema-invariant-03~1]
def test_authorization_relevant_fields_are_schema_typed_enums(applied: Schema):
    assert applied.tables["core.external_identities"].columns["provider"] == \
        "core.identity_provider NOT NULL"
    assert applied.tables["core.access_grants"].columns["source"] == \
        "core.access_grant_source NOT NULL"
    assert applied.tables["core.access_grants"].columns["status"] == \
        "core.access_grant_status NOT NULL DEFAULT 'active'"
    assert applied.tables["audit.auth_events"].columns["actor_provider"] == \
        "core.identity_provider"
    # None of them is TEXT.
    for table, column in (("core.external_identities", "provider"),
                          ("core.access_grants", "source"),
                          ("core.access_grants", "status"),
                          ("audit.auth_events", "actor_provider")):
        assert "TEXT" not in applied.tables[table].columns[column]


# [utest->req~schema-invariant-03~1]
def test_a_free_text_value_never_reaches_a_categorical_field():
    # All four authorization-relevant categorical fields the requirement names are policed.
    assert {"core.external_identities.provider",
            "core.access_grants.source",
            "core.access_grants.status",
            "audit.auth_events.actor_provider"} <= set(ENUM_TYPED_FIELDS)
    assert_enum_typed("core.external_identities.provider", IdentityProvider.google)
    assert_enum_typed("core.access_grants.status", AccessGrantStatus.active)
    assert_enum_typed("audit.auth_events.actor_provider", None)
    with pytest.raises(InvariantError):
        assert_enum_typed("core.external_identities.provider", "google")
    with pytest.raises(InvariantError):
        assert_enum_typed("core.access_grants.source", "anonymous_device_grant")
    with pytest.raises(InvariantError):
        assert_enum_typed("core.access_grants.status", "active")
    with pytest.raises(InvariantError):
        assert_enum_typed("core.users.display_name", "not a categorical field")


# --- 04. The provider / `registered_at` pairing -------------------------------------------------

# [utest->req~schema-invariant-04~1]
def test_registered_at_is_set_exactly_when_the_stored_provider_is_registered():
    now = NOW
    for provider in (IdentityProvider.google, IdentityProvider.apple):
        assert_classification_pairing(provider, now)
        with pytest.raises(ProfileError):
            assert_classification_pairing(provider, None)
    assert_classification_pairing(IdentityProvider.anonymous, None)
    with pytest.raises(ProfileError):
        assert_classification_pairing(IdentityProvider.anonymous, now)
    # There is no third classification state for authorization, grant class, or audit.
    assert {member.value for member in AccountClass} == {"anonymous", "registered"}


# [utest->req~schema-invariant-04~1]
def test_the_classification_and_any_email_copy_commit_in_one_transaction():
    transaction = object()
    written = classification_write_set(LookupOutcome.classified,
                                       provider=IdentityProvider.google,
                                       registered_at=NOW,
                                       email="user@example.com",
                                       transaction=transaction,
                                       identity_transaction=transaction,
                                       user_transaction=transaction)
    assert written == {"core.external_identities.provider",
                       "core.users.registered_at",
                       "core.users.email"}
    # With no eligible address, the other two still commit together.
    assert classification_write_set(LookupOutcome.classified,
                                    provider=IdentityProvider.anonymous,
                                    registered_at=None,
                                    transaction=transaction,
                                    identity_transaction=transaction,
                                    user_transaction=transaction) == {
        "core.external_identities.provider", "core.users.registered_at"}
    # Two transactions are not one transaction.
    with pytest.raises(InvariantError):
        classification_write_set(LookupOutcome.classified,
                                 provider=IdentityProvider.google,
                                 registered_at=NOW,
                                 transaction=transaction,
                                 identity_transaction=object(),
                                 user_transaction=transaction)


# [utest->req~schema-invariant-04~1]
def test_a_failed_or_indeterminate_lookup_commits_nothing_across_tables():
    transaction = object()
    for outcome in (LookupOutcome.failed, LookupOutcome.indeterminate):
        assert classification_write_set(outcome,
                                        provider=IdentityProvider.google,
                                        registered_at=NOW,
                                        email="user@example.com",
                                        transaction=transaction,
                                        identity_transaction=transaction,
                                        user_transaction=transaction) == frozenset()


# [utest->req~schema-invariant-04~1]
def test_the_upgrade_transaction_locks_and_revalidates_before_it_classifies():
    assert_upgrade_revalidates_under_lock(
        locked=("core.external_identities", "core.users"), revalidated=True)
    with pytest.raises(InvariantError):
        assert_upgrade_revalidates_under_lock(
            locked=("core.users", "core.external_identities"), revalidated=True)
    with pytest.raises(InvariantError):
        assert_upgrade_revalidates_under_lock(
            locked=("core.external_identities", "core.users"), revalidated=False)


# [utest->req~schema-invariant-04~1]
def test_no_cross_table_constraint_trigger_enforces_the_pairing():
    """The transaction is the whole of the enforcement: the applied schema declares no trigger
    for it, and no enforcement mechanism is registered beside the code."""
    assert PAIRING_ENFORCEMENT_MECHANISMS == frozenset()
    schema_sql = declarative_section(MIGRATION.read_text())
    assert "CREATE TRIGGER" not in schema_sql.upper()


# --- 05. One provider account, at most one user, ever -------------------------------------------

# [utest->req~schema-invariant-05~1]
def test_one_provider_account_binds_to_at_most_one_user_ever(applied: Schema):
    reservations = ProviderAccountReservations()
    first, second = uuid4(), uuid4()
    reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                      provider=IdentityProvider.google, provider_uid="g-1", user_id=first)
    # A second internal user may never take that provider account.
    with pytest.raises(ProviderAccountAlreadyLinkedError):
        reservations.bind(operation=AuthOperation.upgrade_anonymous_to_registered, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=second)
    assert reservations.holder(ISSUER, IdentityProvider.google, "g-1") == first
    # The index spans `active` and `historical` rows, so administrative retirement frees nothing.
    reservations.retire(issuer=ISSUER, provider=IdentityProvider.google, provider_uid="g-1")
    assert reservations.is_historical(ISSUER, IdentityProvider.google, "g-1") is True
    with pytest.raises(ProviderAccountAlreadyLinkedError):
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=second)
    # It is a partial unique index over the rows where `provider_uid IS NOT NULL`, and it has no
    # `identity_state` predicate that could let a retired row out of it.
    index = applied.indexes["ix_external_identities_provider_account"]
    assert "ON core.external_identities (issuer, provider, provider_uid)" in index
    assert index.endswith("WHERE provider_uid IS NOT NULL")
    assert "identity_state" not in index


# [utest->req~schema-invariant-05~1]
def test_anonymous_rows_fall_outside_the_reservation_index():
    # An anonymous row's `provider_uid` is `NULL`, so the index does not constrain it at all...
    assert provider_uid_reserved(IdentityProvider.anonymous, None) is False
    for provider in (IdentityProvider.google, IdentityProvider.apple):
        assert provider_uid_reserved(provider, "uid-1") is True
        assert provider_uid_reserved(provider, None) is False
    # ...so any number of anonymous rows may be bound under one issuer without conflict.
    reservations = ProviderAccountReservations()
    for _ in range(3):
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.anonymous, provider_uid=None,
                          user_id=uuid4())


# --- 06. Identity rows are immortal -------------------------------------------------------------

# [utest->req~schema-invariant-06~1]
def test_neither_the_identity_row_nor_its_user_row_is_ever_hard_deleted(applied: Schema):
    # No path and no role deletes an identity row.
    assert IDENTITY_ROW_DELETERS == frozenset()
    assert DELETE_PERMITTED_ROLES == frozenset()
    for role in ("api", "cleanup", "migrator", "postgres"):
        assert may_delete_identity_rows(role) is False
    with pytest.raises(IdentityError):
        assert_no_identity_delete("cleanup")
    # The linked `core.users` row is not hard-deleted either, while an identity row exists.
    assert_hard_delete_allowed(has_external_identity=False)
    with pytest.raises(ProfileError):
        assert_hard_delete_allowed(has_external_identity=True)
    # The declarative backstop: the identity row's `user_id` foreign key restricts the delete.
    assert applied.tables["core.external_identities"].columns["user_id"] == \
        "UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT"


# [utest->req~schema-invariant-06~1]
def test_the_historical_tombstone_is_the_only_end_state():
    from unit.test_external_identities import google_row

    row = google_row()
    retired = retire(row)
    # Retirement is a state transition on the existing row, not a removal and not a reassignment.
    assert retired.identity_state is IdentityState.historical
    assert (retired.id, retired.user_id) == (row.id, row.user_id)
    # There is no way out of `historical`, and no transition to a removed row.
    with pytest.raises(IdentityError):
        transition_identity_state(IdentityState.historical, IdentityState.active,
                                  administrative=True)
    assert transition_identity_state(IdentityState.active, IdentityState.historical,
                                     administrative=True) is IdentityState.historical


# --- 07. The user row and its identity row are created together ---------------------------------

# [utest->req~schema-invariant-07~1]
def test_the_creating_transaction_is_the_whole_of_the_enforcement(applied: Schema):
    from unit.test_external_identities import anon_row

    transaction = object()
    user_id = uuid4()
    created = create_account(user_id=user_id, identity=anon_row(user_id=user_id),
                             user_transaction=transaction, identity_transaction=transaction)
    assert created.transaction is transaction
    # Two transactions are not one transaction.
    with pytest.raises(IdentityError):
        create_account(user_id=user_id, identity=anon_row(user_id=user_id),
                       user_transaction=transaction, identity_transaction=object())
    # Nothing else backs the pairing: no constraint, trigger, deferrable key or healer.
    assert PAIRING_ENFORCEMENT_MECHANISMS == frozenset()
    ddl = declarative_section(MIGRATION.read_text()).upper()
    assert "CREATE TRIGGER" not in ddl
    # Because identity rows are never deleted, creation is the only point that can break it.
    assert applied.tables["core.external_identities"].columns["user_id"] == \
        "UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT"


# [utest->req~schema-invariant-07~1]
def test_a_user_row_without_an_identity_row_fails_closed_and_is_never_repaired():
    from unit.test_external_identities import anon_row

    user_id = uuid4()
    assert resolve_owner(anon_row(user_id=user_id), user_id=user_id) == user_id
    with pytest.raises(OrphanUserError):
        resolve_owner(None, user_id=user_id)


# --- 08 and 09. The entitlement-only grant row and its anti-abuse row ---------------------------

# [utest->req~schema-invariant-08~2]
def test_the_grant_row_carries_entitlement_state_only(applied: Schema):
    grants = applied.tables["core.access_grants"]
    for column in grants.columns:
        assert not any(word in column for word in ("device", "idp_account", "attest", "token")), \
            column
    assert_grant_columns_entitlement_only(grants.columns)
    with pytest.raises(InvariantError):
        assert_grant_columns_entitlement_only([*grants.columns, "device_check_state"])


# [utest->req~schema-invariant-08~2]
def test_every_free_credit_grant_has_one_anti_abuse_row_of_its_own_source(applied: Schema):
    for source in (AccessGrantSource.anonymous_device_grant,
                   AccessGrantSource.registered_account_grant):
        assert requires_anti_abuse_row(source) is True
        assert_anti_abuse_pairing(source, source)
        with pytest.raises(InvariantError):
            assert_anti_abuse_pairing(source, None)
    # The anti-abuse row records its grant's own source, not the other free source.
    with pytest.raises(InvariantError):
        assert_anti_abuse_pairing(AccessGrantSource.anonymous_device_grant,
                                  AccessGrantSource.registered_account_grant)
    # A subscription or manual grant must not have one at all.
    for source in (AccessGrantSource.subscription, AccessGrantSource.manual):
        assert requires_anti_abuse_row(source) is False
        assert_anti_abuse_pairing(source, None)
        with pytest.raises(InvariantError):
            assert_anti_abuse_pairing(source, source)
    # The schema binds the pair by source and restricts the anti-abuse row to the two sources.
    anti_abuse = constraints_of(applied, "core.access_grants_anti_abuse")
    assert "CHECK (grant_source IN ('anonymous_device_grant', 'registered_account_grant'))" \
        in anti_abuse
    assert "FOREIGN KEY (grant_id, grant_source) REFERENCES core.access_grants (id, source)" \
        in anti_abuse
    assert applied.tables["core.access_grants_anti_abuse"].columns["grant_id"] == "UUID PRIMARY KEY"


# [utest->req~schema-invariant-09~1]
def test_the_two_anti_abuse_evidence_shapes():
    # Native anonymous device grants carry per-device device-check state through
    # `native_claim_provider`...
    assert anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant,
                               native_claim_provider=NativeClaimPlatform.ios_devicecheck) \
        is AntiAbuseEvidence.native_device_check
    # ...web anonymous device grants carry the resolved provider account hash and its version...
    assert anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant,
                               idp_account_hash=b"h", idp_account_hash_key_version=1) \
        is AntiAbuseEvidence.idp_account
    # ...and registered account grants carry IDP-account evidence with no native provider.
    assert anti_abuse_evidence(grant_source=AccessGrantSource.registered_account_grant,
                               idp_account_hash=b"h", idp_account_hash_key_version=1) \
        is AntiAbuseEvidence.idp_account
    with pytest.raises(InvariantError):
        anti_abuse_evidence(grant_source=AccessGrantSource.registered_account_grant,
                            native_claim_provider=NativeClaimPlatform.android_play_integrity,
                            idp_account_hash=b"h", idp_account_hash_key_version=1)
    # Neither shape, both shapes, or a hash without its key version are all refused.
    with pytest.raises(InvariantError):
        anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant)
    with pytest.raises(InvariantError):
        anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant,
                            native_claim_provider=NativeClaimPlatform.ios_devicecheck,
                            idp_account_hash=b"h", idp_account_hash_key_version=1)
    with pytest.raises(InvariantError):
        anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant,
                            idp_account_hash=b"h")
    # A subscription grant has no anti-abuse row to shape.
    with pytest.raises(InvariantError):
        anti_abuse_evidence(grant_source=AccessGrantSource.subscription)


# [utest->req~schema-invariant-09~1]
def test_native_claimed_state_is_written_before_the_grant_in_the_same_attempt():
    assert_native_claim_written_before_grant(native_claim_written=True, same_attempt=True)
    with pytest.raises(InvariantError):
        assert_native_claim_written_before_grant(native_claim_written=False, same_attempt=True)
    with pytest.raises(InvariantError):
        assert_native_claim_written_before_grant(native_claim_written=True, same_attempt=False)


# [utest->req~schema-invariant-08~2]
# [utest->req~schema-invariant-09~1]
def test_no_raw_device_material_or_provider_uid_is_stored_outside_the_identity_tables(
        applied: Schema):
    for name, table in applied.tables.items():
        if name in ("core.external_identities", "core.provider_accounts"):
            continue
        assert_no_raw_device_material(table.columns)
    # Raw provider account identifiers live only in the identity tables.
    assert "provider_uid" in applied.tables["core.external_identities"].columns
    assert "provider_uid" in applied.tables["core.provider_accounts"].columns
    # And the guard really refuses what it names.
    for column in ("devicecheck_token", "device_principal_hash", "stable_device_principal_hash",
                   "play_integrity_token", "bot_check_token", "device_check_hash"):
        assert column in FORBIDDEN_ANTI_ABUSE_COLUMNS
        with pytest.raises(InvariantError):
            assert_no_raw_device_material(["grant_id", column])


# --- 10. The composite key, the per-source CHECK, and the two gates -----------------------------

# [utest->req~schema-invariant-10~1]
def test_the_anti_abuse_row_is_bound_to_its_grant_and_cascades(applied: Schema):
    anti_abuse = constraints_of(applied, "core.access_grants_anti_abuse")
    assert "FOREIGN KEY (grant_id, grant_source) REFERENCES core.access_grants (id, source) " \
        "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED" in anti_abuse
    # The grant side carries the matching composite unique key the reference needs.
    assert "UNIQUE (id, source)" in constraints_of(applied, "core.access_grants")


# [utest->req~schema-invariant-10~1]
def test_each_provider_account_consumes_each_gate_once_and_the_kinds_are_distinct_rows(
        applied: Schema):
    consumptions = applied.tables["core.provider_account_gate_consumptions"]
    assert "PRIMARY KEY (provider_account_id, consumption_kind)" in consumptions.constraints
    account = ProviderAccount(IdentityProvider.google, "google-uid-1")
    gates = ProviderAccountGates()
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid4(),
                  idp_account_hash=b"hash", hash_key_version=1)
    # The two consumption kinds are distinct rows: consuming one leaves the other open.
    gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid4())
    # A registered-gate conflict surfaces as `idp_account_already_claimed` under the
    # client-visible `account_already_claimed` class...
    with pytest.raises(GateAlreadyConsumedError) as registered:
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid4())
    assert registered.value.result is AuthEventResult.idp_account_already_claimed
    assert str(registered.value.client_class) == "account_already_claimed"
    # ...and a web-gate conflict as `device_grant_exhausted`.
    with pytest.raises(GateAlreadyConsumedError) as web:
        gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid4())
    assert str(web.value.client_class) == "device_grant_exhausted"
    # `idp_account_hash` is a lookup and audit alias, not part of what enforces the gate.
    assert gates.alias(account, GateConsumptionKind.registered_account_grant) == (b"hash", 1)
    assert gates.alias(account, GateConsumptionKind.web_anonymous_gate) is None


# --- 11. One owner for an active subscription-backed grant and its subscription -----------------

# [utest->req~schema-invariant-11~1]
def test_owner_agreement_is_a_deferrable_composite_foreign_key(applied: Schema):
    grants = applied.tables["core.access_grants"]
    assert "FOREIGN KEY (active_subscription_grant_subscription_id, " \
        "active_subscription_grant_user_id) REFERENCES core.subscriptions (id, user_id) " \
        "DEFERRABLE INITIALLY DEFERRED" in constraints_of(applied, "core.access_grants")
    # The generated columns are NULL for non-subscription and non-active rows, so MATCH SIMPLE
    # skips them.
    assert "CASE WHEN source = 'subscription' AND status = 'active' THEN subscription_id END" \
        in " ".join(grants.columns["active_subscription_grant_subscription_id"].split())
    assert "CASE WHEN source = 'subscription' AND status = 'active' THEN user_id END" \
        in " ".join(grants.columns["active_subscription_grant_user_id"].split())
    assert "UNIQUE (id, user_id)" in constraints_of(applied, "core.subscriptions")
    # And the read-side check the locked paths make against the same condition.
    owner = uuid4()
    assert_owner_agreement(grant_user_id=owner, subscription_user_id=owner)
    with pytest.raises(InvariantError):
        assert_owner_agreement(grant_user_id=owner, subscription_user_id=uuid4())


# --- 12. One audit row per movement attempt -----------------------------------------------------

# [utest->req~schema-invariant-12~1]
async def test_a_movement_attempt_is_one_row_and_no_second_durable_record(applied: Schema):
    sink = RecordingSink()
    writer = AuthAuditWriter(sink=sink, counter=AuthResultCounter(),
                             session_factory=FakeSession, clock=lambda: NOW)
    attempt = AuthAttempt("POST", "/auth/restore-subscription")
    details = movement_audit_details(_restore_context())
    event = terminal_event(AttemptPhase.business,
                           AuthEventResult.restore_subscription_not_entitled,
                           operation=AuthOperation.restore_subscription,
                           actor=actor(IdentityProvider.google), details=details)
    await writer.write_standalone(attempt, event)
    assert len(sink.rows) == 1
    # A second row for the same attempt is refused outright.
    with pytest.raises(AuditAlreadyWrittenError):
        await writer.write_standalone(attempt, event)
    # The movement context lives in that row's `details`, and no table carries a second
    # durable attempt record or an audit cross-reference column.
    assert sink.rows[0]["details"]["mutation"]["movement_classification"]
    for name, table in applied.tables.items():
        if name == "audit.auth_events":
            continue
        for column, definition in table.columns.items():
            assert "auth_events" not in definition, (name, column)
            assert "auth_event" not in column, (name, column)


def _restore_context():
    from nativespeaker.api.auth.movement import MovementClassification, restore_movement_context

    return restore_movement_context(
        result=AuthEventResult.restore_subscription_not_entitled,
        occurred_at=NOW,
        destination_user_id=uuid4(),
        destination_external_identity_id=uuid4(),
        classification=MovementClassification.same_account,
        subscription_id=uuid4(),
        proof_fingerprints=("sha256:abc",),
        store_state_verification="verified_active")


# --- 13. The retained column nothing writes -----------------------------------------------------

# [utest->req~schema-invariant-13~1]
def test_the_cross_account_transfer_month_is_retained_but_never_written(applied: Schema):
    assert applied.tables["core.subscriptions"].columns[
        "last_cross_account_transfer_month"] == "DATE"
    assert NEVER_WRITTEN_COLUMNS == {"core.subscriptions.last_cross_account_transfer_month"}
    assert_no_never_written_column("core.subscriptions", ["user_id", "status"])
    with pytest.raises(InvariantError):
        assert_no_never_written_column("core.subscriptions",
                                       ["status", "last_cross_account_transfer_month"])
    # No write path in the source names the column at all — only the guard that forbids it.
    for path in SRC.rglob("*.py"):
        if path.name == "schema_invariants.py":
            continue
        assert "last_cross_account_transfer_month" not in path.read_text(), path


# --- 15. Purchase attribution -------------------------------------------------------------------

# [utest->req~schema-invariant-15~1]
def test_attribution_comes_from_the_store_echoed_token_or_the_restore_carve_out():
    owner, destination = uuid4(), uuid4()
    tokens = AttributionTokens()
    tokens.mint(owner, StoreProvider.apple, "token-1")
    # Ingestion resolves the owning user by matching the store-echoed token alone.
    assert tokens.owner_of(StoreProvider.apple, "token-1") == owner
    outcome, rows = attribute_purchase(token_owner_id=owner)
    assert outcome is AttributionOutcome.token_binding
    assert rows["subscription_user_id"] == owner and rows["purchase_user_id"] == owner
    # Restore's insert-once creation is the one carve-out.
    outcome, rows = attribute_purchase(token_owner_id=None,
                                       restoring_destination_user_id=destination)
    assert outcome is AttributionOutcome.restore_insert_once
    assert rows["purchase_user_id"] == destination
    # A token that resolves to no binding creates unclaimed, unattributed rows and nothing else.
    outcome, rows = attribute_purchase(token_owner_id=None)
    assert outcome is AttributionOutcome.unclaimed
    assert rows == {"subscription_user_id": None, "purchase_user_id": None,
                    "access_grant_id": None, "user_monthly_usage_grant_id": None}
    assert tokens.owner_of(StoreProvider.apple, "unknown-token") is None


# [utest->req~schema-invariant-15~1]
def test_attribution_is_never_taken_from_the_request_identity_or_an_identity_kind(
        applied: Schema):
    assert_no_client_asserted_attribution({"provider": "apple", "identity_value": "token-1"})
    for field in ("authenticated_user_id", "client_user_id", "identity_kind", "is_anonymous"):
        with pytest.raises(InvariantError):
            assert_no_client_asserted_attribution({field: "x"})
    for source in (AttributionSource.request_authenticated_identity,
                   AttributionSource.client_asserted_identity):
        with pytest.raises(InvariantError):
            assert_attribution_source(source)
    assert_attribution_source(AttributionSource.store_echoed_token)
    # The binding the store token resolves through carries no identity-kind dimension.
    tokens_table = applied.tables["core.store_purchase_tokens"]
    assert set(tokens_table.columns) == {"user_id", "provider", "identity_value", "created_at"}
    assert "UNIQUE (provider, identity_value)" in tokens_table.constraints
    # An unresolved token leaves both canonical rows unowned, so both columns are nullable.
    assert applied.tables["core.subscriptions"].columns["user_id"] == \
        "UUID REFERENCES core.users (id)"
    assert applied.tables["core.store_purchases"].columns["purchase_user_id"] == \
        "UUID REFERENCES core.users (id)"


# --- 16. The attribution tokens minted once at user creation ------------------------------------

# [utest->req~schema-invariant-16~1]
def test_tokens_are_minted_once_at_creation_and_survive_the_in_place_upgrade(applied: Schema):
    user_id = uuid4()
    tokens = AttributionTokens()
    assert_tokens_minted_at_creation(AuthOperation.create_user)
    for operation in (AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.claim_registered_grant, AuthOperation.restore_subscription):
        with pytest.raises(InvariantError):
            assert_tokens_minted_at_creation(operation)
    tokens.mint(user_id, StoreProvider.apple, "apple-token")
    tokens.mint(user_id, StoreProvider.google_play, "play-token")
    before = {str(provider): tokens.token_for(user_id, provider) or ""
              for provider in StoreProvider}
    # A second mint for the same user and store is refused: minting happens once.
    with pytest.raises(InvariantError):
        tokens.mint(user_id, StoreProvider.apple, "apple-token-2")
    # The in-place upgrade regenerates, moves or retires nothing.
    after = {str(provider): tokens.token_for(user_id, provider) or ""
             for provider in StoreProvider}
    assert_tokens_survive_upgrade(before, after)
    with pytest.raises(InvariantError):
        assert_tokens_survive_upgrade(before, {**after, "apple": "regenerated"})
    # The schema keeps one row per user and store for the life of the user.
    assert "UNIQUE (user_id, provider)" in \
        applied.tables["core.store_purchase_tokens"].constraints
