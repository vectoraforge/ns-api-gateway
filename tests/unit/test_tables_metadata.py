"""WR-33. The one rule the `tables` package holds: the migration owns indexes and delete actions.
A field that declares either states a second version of the schema, and `SQLModel.metadata` is
mirrored by nothing -- a `create_all` bootstrap would build a database the inventory suite fails on.
"""
from uuid import uuid7

from sqlmodel import SQLModel

# Imported for the registration alone: a model no module imported is in no metadata.
import nativespeaker.api.tables  # noqa: F401
from nativespeaker.api.tables.grants import AccessGrant, AccessTier, UserMonthlyUsage

TABLES = SQLModel.metadata.tables

_ENTITLEMENT_TABLES = (AccessTier, AccessGrant, UserMonthlyUsage)


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


class TestTheWalkFires:
    """The control: an empty metadata would pass both cases above without reading anything."""

    def test_the_mapped_tables_are_there_to_walk(self):
        assert "core.chats" in TABLES
        assert "core.messages" in TABLES

    def test_the_foreign_keys_are_there_to_walk(self):
        assert [key.parent.name for key in TABLES["core.messages"].foreign_keys] == ["chat_id"]
