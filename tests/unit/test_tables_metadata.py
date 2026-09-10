"""WR-33. The one rule the `tables` package holds: the migration owns indexes and delete actions.
A field that declares either states a second version of the schema, and `SQLModel.metadata` is
mirrored by nothing -- a `create_all` bootstrap would build a database the inventory suite fails on.
"""
from uuid import uuid7

import sqlalchemy
from sqlalchemy import UniqueConstraint
from sqlalchemy import inspect as sa_inspect
from sqlmodel import SQLModel

import nativespeaker.api.tables
from nativespeaker.api.tables.grants import AccessGrant, AccessTier, UserMonthlyUsage

TABLES = SQLModel.metadata.tables

_ENTITLEMENT_TABLES = (AccessTier, AccessGrant, UserMonthlyUsage)

_MAPPED_TABLES = tuple(sorted(
    (exported for exported in vars(nativespeaker.api.tables).values()
     if isinstance(exported, type) and issubclass(exported, SQLModel)
     and getattr(exported, "__table__", None) is not None),
    key=lambda model: model.__name__))

def _mints_a_uuid_key(model) -> bool:
    """Selected on the mapped column, never on the annotation."""
    columns = list(model.__table__.primary_key.columns)
    return (len(columns) == 1 and columns[0].name == "id"
            and isinstance(columns[0].type, sqlalchemy.Uuid))


_UUID_KEYED_TABLES = tuple(model for model in _MAPPED_TABLES if _mints_a_uuid_key(model))


class TestTheMetadataDeclaresNoIndex:
    """`ix_chats_user_id` in the migration compiles from this metadata as `ix_core_chats_user_id`,
    so one `index=True` is enough to make the two schemas disagree by a name."""

    def test_no_mapped_table_declares_one(self):
        declared = {name: sorted(index.name or "" for index in table.indexes)
                    for name, table in TABLES.items() if table.indexes}

        assert declared == {}


class TestTheMetadataDeclaresNoUniquenessRule:
    """WR-41. `Field(unique=True)` files a `UniqueConstraint` and no `Index`, so the case above
    walked past three of them; the migration is the only place a uniqueness rule is stated."""

    def test_no_mapped_table_declares_one(self):
        declared = sorted(f"{name}.{column.name}"
                          for name, table in TABLES.items()
                          for constraint in table.constraints
                          if isinstance(constraint, UniqueConstraint)
                          for column in constraint.columns)

        assert declared == []

    def test_the_constraints_are_there_to_walk_control(self):
        """The control: a walk that saw no constraint at all would pass the case above."""
        assert any(table.constraints for table in TABLES.values())


class TestTheMetadataDeclaresNoDeleteAction:
    """The four cascades `00-schema.md` enumerates are the migration's; a partial mirror of them
    reads as if this package decided them."""

    def test_no_foreign_key_declares_one(self):
        declared = sorted(f"{name}.{key.parent.name}"
                          for name, table in TABLES.items()
                          for key in table.foreign_keys if key.ondelete)

        assert declared == []


class TestTheEntitlementTablesHoldNoSecondClock:
    """WR-16. `AccessGrant.starts_at` is half the shared effective-grant predicate, so a wall-clock
    factory gives a forgotten value a different instant from the one `ends_at` and `monthly_period`
    were derived from -- an active grant outside its own term, with no error to catch it."""

    def test_no_timestamp_field_mints_its_own_value(self):
        minted = sorted(f"{model.__name__}.{name}"
                        for model in _ENTITLEMENT_TABLES
                        for name, field in model.model_fields.items()
                        if field.default_factory is not None and "datetime" in str(field.annotation))

        assert minted == []

    def test_the_grant_id_factory_is_still_there_control(self):
        """The control: the RNG is not the clock, and `crud` reads `activated.id` before the flush."""
        assert AccessGrant.model_fields["id"].default_factory is uuid7


class TestEveryUuidPrimaryKeyMintsItsOwnValue:
    """WR-20: `Chat.id` alone declared no factory, and `table=True` skips validation, so the
    omission was a NULL sent to the primary key -- sqlstate 23502, which `is_unique_violation`
    reads as False, so every writer re-raised it as an opaque 500 instead of as a race."""

    def test_no_uuid_keyed_table_leaves_its_id_unminted(self):
        unminted = sorted(model.__name__ for model in _UUID_KEYED_TABLES
                          if model.model_fields["id"].default_factory is not uuid7)

        assert unminted == []

    def test_the_walk_sees_the_tables_control(self):
        """The control: an empty walk would pass the case above without reading a field, and three
        names would leave six of the nine unprotected -- which is how WR-124 stayed invisible."""
        assert {model.__name__ for model in _UUID_KEYED_TABLES} == {
            "AccessGrant", "AuthChallenge", "Chat", "ExternalIdentity", "Message",
            "StorePurchase", "Subscription", "SubscriptionEvent", "User",
        }


class TestTheOnlyRelationshipIsTheOneAQueryEagerLoads:
    """WR-42. A lazy load inside an `AsyncSession` raises `MissingGreenlet` rather than returning a
    row, so a mapped relationship is readable only where a query eager-loads it."""

    def test_the_package_declares_exactly_the_relationship_the_chat_read_selectin_loads(self):
        declared = {f"{model.__name__}.{name}"
                    for model in _MAPPED_TABLES
                    for name in sa_inspect(model).relationships.keys()}

        assert declared == {"Chat.messages"}


class TestTheWalkFires:
    """The control: an empty metadata would pass both cases above without reading anything."""

    def test_the_mapped_tables_are_there_to_walk(self):
        assert "core.chats" in TABLES
        assert "core.messages" in TABLES

    def test_the_foreign_keys_are_there_to_walk(self):
        assert [key.parent.name for key in TABLES["core.messages"].foreign_keys] == ["chat_id"]
