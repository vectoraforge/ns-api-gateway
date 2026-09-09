"""WR-33. The one rule the `tables` package holds: the migration owns indexes and delete actions.
A field that declares either states a second version of the schema, and `SQLModel.metadata` is
mirrored by nothing -- a `create_all` bootstrap would build a database the inventory suite fails on.
"""
from sqlmodel import SQLModel

# Imported for the registration alone: a model no module imported is in no metadata.
import nativespeaker.api.tables  # noqa: F401

TABLES = SQLModel.metadata.tables


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


class TestTheWalkFires:
    """The control: an empty metadata would pass both cases above without reading anything."""

    def test_the_mapped_tables_are_there_to_walk(self):
        assert "core.chats" in TABLES
        assert "core.messages" in TABLES

    def test_the_foreign_keys_are_there_to_walk(self):
        assert [key.parent.name for key in TABLES["core.messages"].foreign_keys] == ["chat_id"]
