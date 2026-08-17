"""`core.access_tiers`: the configured tier catalogue, its sizing invariant, and the rows it
becomes in PostgreSQL.

The structural expectations are transcribed from the specification, not read back out of the
migration.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.database.tiers import AccessTiersDB
from nativespeaker.api.models.users import AccessTier
from nativespeaker.api.quota.tiers import (
    AccessTierEntry,
    TierClass,
    TierConfigError,
    allowance_of,
    anonymous_floor,
    assert_no_per_user_credit_override,
    assert_tier_sizing,
    tier_rows,
)

_DOTENV_KEYS = ["CONFIG_DIR"]


def entry(credits: int, tier_class: TierClass) -> AccessTierEntry:
    return AccessTierEntry(monthly_credits=credits, tier_class=tier_class)


def catalogue(**tiers: AccessTierEntry) -> dict[str, AccessTierEntry]:
    return dict(tiers)


WELL_SIZED = catalogue(anonymous=entry(10, TierClass.anonymous),
                       free=entry(10, TierClass.registered),
                       gold=entry(200, TierClass.registered))


# --- The stable tier identifier ----------------------------------------------------------------

# [utest->req~schema-access-tiers-id-stable-identifier~1]
def test_tier_id_is_the_stable_identifier_grants_point_at():
    """`id` is the primary key of `core.access_tiers`, and grants reference tiers by it."""
    tiers = SQLModel.metadata.tables["core.access_tiers"]
    assert [column.name for column in tiers.primary_key.columns] == ["id"]
    grants = SQLModel.metadata.tables["core.access_grants"]
    targets = {str(key.target_fullname) for key in grants.foreign_keys}
    assert "core.access_tiers.id" in targets


# [utest->req~schema-access-tiers-id-stable-identifier~1]
def test_a_credit_change_keeps_the_tier_id():
    """Re-pricing a tier changes its credits under the same id; it does not mint a new id."""
    before = {row.id: row.monthly_credits for row in tier_rows(WELL_SIZED)}
    repriced = dict(WELL_SIZED, gold=entry(300, TierClass.registered))
    after = {row.id: row.monthly_credits for row in tier_rows(repriced)}
    assert set(after) == set(before)
    assert after["gold"] == 300


# --- The configured monthly allowance ----------------------------------------------------------

# [utest->req~schema-access-tiers-monthly-credits-allowance~1]
def test_monthly_credits_is_the_configured_allowance():
    assert allowance_of(WELL_SIZED, "gold") == 200
    assert allowance_of(WELL_SIZED, "anonymous") == 10
    with pytest.raises(TierConfigError):
        allowance_of(WELL_SIZED, "unconfigured")


# --- The tier-sizing invariant -----------------------------------------------------------------

# [utest->req~schema-access-tiers-registered-ge-anonymous~1]
def test_every_registered_tier_sits_at_or_above_the_anonymous_tier():
    assert anonymous_floor(WELL_SIZED) == 10
    assert_tier_sizing(WELL_SIZED)  # equal is allowed: the rule is non-strict
    with pytest.raises(TierConfigError):
        assert_tier_sizing(catalogue(anonymous=entry(10, TierClass.anonymous),
                                     free=entry(9, TierClass.registered)))


# [utest->req~schema-access-tiers-registered-ge-anonymous~1]
def test_a_paid_tier_below_the_anonymous_tier_is_rejected_too():
    """The rule covers every tier a converting user could land on, paid ones included."""
    with pytest.raises(TierConfigError):
        assert_tier_sizing(catalogue(anonymous=entry(50, TierClass.anonymous),
                                     free=entry(50, TierClass.registered),
                                     silver=entry(20, TierClass.registered)))


# [utest->req~schema-access-tiers-sizing-invariant-enforced~1]
def test_configuration_load_rejects_a_violating_catalogue():
    """Configuration load is one of the places tier credit values are set, so it refuses the
    catalogue outright rather than starting the service on it."""
    yaml_content = """
log_level: INFO
db:
  host: localhost
  port: 5432
  user: test-user
  password: test-password
  name: test-db
jwt:
  project_id: test-project
  api_key: test-api-key
auth:
  subject_hash_key: test-subject-hash-key
apple:
  bundle_id: com.example.test
  certs_dir: /tmp/certs
  product_id_to_plan:
    com.example.test.gold: gold
quotas:
  free: 10
access_tiers:
  anonymous:
    tier_class: anonymous
    monthly_credits: 10
  free:
    tier_class: registered
    monthly_credits: 5
rate_limits:
  enabled: true
  storage_uri: "memory://"
  strategy: moving-window
  default:
    limit: "120/minute"
    key: "ip"
"""
    tmp_dir = tempfile.mkdtemp()
    try:
        Path(tmp_dir, "config.yaml").write_text(yaml_content)
        Path(tmp_dir, "prompt.txt").write_text("prompt")
        Path(tmp_dir, "examples.yaml").write_text("en:\n  - 'Example'\n")
        env_clean = {k: v for k, v in os.environ.items() if k not in _DOTENV_KEYS}
        with patch.dict(os.environ, env_clean, clear=True):
            with pytest.raises(TierConfigError) as raised:
                # See test_config.py: _env_file is invisible to ty's synthesised __init__.
                EnvironmentConfig(config_dir=Path(tmp_dir),
                                  _env_file=None)  # ty: ignore[unknown-argument]
        assert "anonymous tier" in str(raised.value)
    finally:
        shutil.rmtree(tmp_dir)


# [utest->req~schema-access-tiers-sizing-invariant-enforced~1]
@pytest.mark.asyncio
async def test_the_write_path_rejects_a_violating_catalogue_before_writing_anything():
    """The invariant is enforced wherever tier credit values are set: an edited catalogue that
    breaks it is refused, and no row is touched."""
    session = MagicMock()
    session.exec = AsyncMock()
    violating = catalogue(anonymous=entry(10, TierClass.anonymous),
                          free=entry(0, TierClass.registered))
    with pytest.raises(TierConfigError):
        await AccessTiersDB(cast(AsyncSession, session)).sync(violating)
    session.exec.assert_not_called()


# --- Zero credits ------------------------------------------------------------------------------

# [utest->req~schema-access-tiers-zero-credits-allowed~1]
def test_a_zero_credit_tier_is_legal_and_a_negative_one_is_not():
    zero = catalogue(anonymous=entry(0, TierClass.anonymous),
                     no_access=entry(0, TierClass.registered))
    assert_tier_sizing(zero)
    assert allowance_of(zero, "no_access") == 0
    assert [row.monthly_credits for row in tier_rows(zero)] == [0, 0]
    with pytest.raises(ValidationError):
        AccessTierEntry(monthly_credits=-1, tier_class=TierClass.registered)


# --- Product configuration, not per-user state -------------------------------------------------

# [utest->req~schema-access-tiers-product-configuration~1]
def test_tiers_are_rows_in_postgresql_and_never_per_user_state():
    rows = tier_rows(WELL_SIZED)
    assert all(isinstance(row, AccessTier) for row in rows)
    assert "core.access_tiers" in SQLModel.metadata.tables
    user_columns = set(SQLModel.metadata.tables["core.users"].columns.keys()) | set(
        SQLModel.metadata.tables["core.user_monthly_usage"].columns.keys())
    for column in ("monthly_credits", "credits", "monthly_limit", "quota"):
        assert column not in user_columns


# [utest->req~schema-access-tiers-product-configuration~1]
def test_a_per_user_credit_column_is_refused():
    with pytest.raises(TierConfigError):
        assert_no_per_user_credit_override("core.users", ["id", "monthly_credits"])
    assert_no_per_user_credit_override("core.users", ["id", "email"])


# [utest->req~schema-access-tiers-custom-tiers-as-rows~1]
def test_a_custom_tier_is_one_more_row_not_a_per_user_override():
    custom = dict(WELL_SIZED, enterprise=entry(5000, TierClass.registered))
    ids = [row.id for row in tier_rows(custom)]
    assert ids == sorted(custom)
    assert "enterprise" in ids
    with pytest.raises(TierConfigError):
        assert_no_per_user_credit_override("core.user_monthly_usage", ["grant_id", "credits"])


# [utest->req~schema-access-tiers-custom-tiers-as-rows~1]
@pytest.mark.asyncio
async def test_syncing_the_catalogue_writes_one_row_per_configured_tier():
    session = MagicMock()
    session.exec = AsyncMock()
    custom = dict(WELL_SIZED, enterprise=entry(5000, TierClass.registered))
    written = await AccessTiersDB(cast(AsyncSession, session)).sync(custom)
    assert written == sorted(custom)
    assert session.exec.await_count == len(custom)
    statements = [str(call.args[0].compile()) for call in session.exec.await_args_list]
    assert all("core.access_tiers" in statement for statement in statements)
    # The stable id is the conflict key: an existing tier is repriced in place.
    assert all("ON CONFLICT (id) DO UPDATE" in statement for statement in statements)
