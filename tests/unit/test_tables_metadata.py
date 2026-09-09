"""WR-33. The one rule the `tables` package holds: the migration owns indexes and delete actions.
A field that declares either states a second version of the schema, and `SQLModel.metadata` is
mirrored by nothing -- a `create_all` bootstrap would build a database the inventory suite fails on.
"""
from uuid import UUID, uuid7

from sqlmodel import SQLModel

# Imported for the registration alone: a model no module imported is in no metadata.
import nativespeaker.api.tables
from nativespeaker.api.tables.grants import AccessGrant, AccessTier, UserMonthlyUsage

TABLES = SQLModel.metadata.tables

_ENTITLEMENT_TABLES = (AccessTier, AccessGrant, UserMonthlyUsage)

# Every mapped model the package exports, read off the package namespace rather than restated,
# so a table added later is walked without this file being edited.
_MAPPED_TABLES = tuple(sorted(
    (exported for exported in vars(nativespeaker.api.tables).values()
     if isinstance(exported, type) and issubclass(exported, SQLModel)
     and getattr(exported, "__table__", None) is not None),
    key=lambda model: model.__name__))

_UUID_KEYED_TABLES = tuple(model for model in _MAPPED_TABLES
                           if "id" in model.model_fields
                           and model.model_fields["id"].annotation is UUID)


class TestTheMetadataDeclaresNoIndex:
    """`ix_chats_user_id` in the migration compiles from this metadata as `ix_core_chats_user_id`,
    so one `index=True` is enough to make the two schemas disagree by a name."""

    def test_no_mapped_table_declares_one(self):
        declared = {name: sorted(index.name or "" for index in table.indexes)
                    for name, table in TABLES.items() if table.indexes}

        assert declared == {}


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
    """WR-20: `Chat.id` alone declared no factory. `table=True` skips validation, so the omission
    was not a `ValidationError` but a NULL sent to the primary key -- sqlstate 23502, which
    `is_unique_violation` reads as False, so every writer re-raised it as an opaque 500 rather
    than as the race the arm was written for. `AccessTier.id` is out of the walk by annotation:
    its key is the seeded tier name, not a minted id."""

    def test_no_uuid_keyed_table_leaves_its_id_unminted(self):
        unminted = sorted(model.__name__ for model in _UUID_KEYED_TABLES
                          if model.model_fields["id"].default_factory is not uuid7)

        assert unminted == []

    def test_the_walk_sees_the_tables_control(self):
        """The control: an empty walk would pass the case above without reading a field."""
        assert {model.__name__ for model in _UUID_KEYED_TABLES} >= {"Chat", "Message", "User"}


class TestTheWalkFires:
    """The control: an empty metadata would pass both cases above without reading anything."""

    def test_the_mapped_tables_are_there_to_walk(self):
        assert "core.chats" in TABLES
        assert "core.messages" in TABLES

    def test_the_foreign_keys_are_there_to_walk(self):
        assert [key.parent.name for key in TABLES["core.messages"].foreign_keys] == ["chat_id"]
