"""USER-01: the `core.users` model at the section 2 target shape.

`GET /users/me` is deleted under D-16: it read `user.name`, `user.subscription_plan`, and
`UsageDB`, all three of which the v2.0 schema dropped, so it could not serve unchanged and is
rewritten from scratch in Phase 39. The six cases that exercised it went with it -- see
35-04-SUMMARY.md for the list.

USER-01's identity value object is now `VerifiedClaims`, carrying only the verified (iss, sub).
Its coverage lives beside the verification rules, in test_jwt_security.py::TestVerifiedClaims.

These cases pin the model's *shape*. That the shape matches the schema actually applied to
PostgreSQL is a different claim, and a model can satisfy every case here while still failing the
first real query -- which is exactly what happened before this plan. That claim is proven against
the live database in tests/e2e/test_model_queries.py.
"""
import ast
from pathlib import Path

from nativespeaker.api import models
from nativespeaker.api.models import User

# migrations/20260818_01_initial-release.sql:150-158, in ordinal_position. The same seven names
# tests/schema/test_inventory.py::EXPECTED_USERS_COLUMNS asserts against the live database.
EXPECTED_FIELDS = {
    "id", "email", "display_name", "registered_at", "active", "created_at", "updated_at",
}

# Deliberately absent, each for its own reason: `jwt_sub` because the external subject is never an
# ownership or lookup key in v2.0 -- (issuer, subject) lives only on core.external_identities;
# `name` because the schema renamed it `display_name`; `subscription_plan` because allowance moved
# to core.access_tiers.monthly_credits.
ABSENT_FIELDS = ("jwt_sub", "name", "subscription_plan")

# Symbols that left with models/subscriptions.py and models.users.UsageMonthly.
REMOVED_SYMBOLS = frozenset({
    "Subscription", "SubscriptionEvent", "SubscriptionPlan", "SubscriptionPlanType",
    "SubscriptionProvider", "SubscriptionProviderType", "SubscriptionStatus",
    "SubscriptionStatusType", "UsageMonthly",
})

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _imported_names(path: Path) -> set[str]:
    """Every name a module imports, read from its AST.

    Reading imports rather than grepping text is what keeps this from firing on
    tests/schema/, whose SQL strings name `core.subscription_plan` and `core.usage_monthly`
    precisely in order to assert the database no longer has them.
    """
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


class TestUserModel:
    """The seven v2.0 columns, and nothing else."""

    def test_field_set_is_exactly_the_seven_v2_columns(self):
        assert set(User.model_fields) == EXPECTED_FIELDS

    def test_dropped_columns_are_absent(self):
        for field in ABSENT_FIELDS:
            assert field not in User.model_fields, f"User still declares {field}"
            assert not hasattr(User, field), f"User still exposes {field}"

    def test_email_is_nullable(self):
        """NULLABLE on purpose (00-schema.md:80).

        `email` is copied only from a Firebase Admin record whose `emailVerified` is TRUE and
        stays NULL otherwise, so a NOT NULL constraint or a non-None default would make the model
        reject rows the database accepts.
        """
        assert User(email=None).email is None
        assert User().email is None

    def test_optional_columns_default_to_none(self):
        user = User()
        assert user.display_name is None
        assert user.registered_at is None

    def test_uuid7_id_generated(self):
        user = User()
        assert user.id is not None
        assert user.id.version == 7

    def test_default_active_is_true(self):
        assert User().active is True

    def test_timestamps_are_set(self):
        user = User()
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_maps_core_users(self):
        assert User.__tablename__ == "users"
        assert User.__table_args__ == {"schema": "core"}


class TestSubscriptionModelLayerIsGone:
    """D-16: the model layer no longer describes subscription plans or monthly usage."""

    def test_barrel_exports_no_removed_symbol(self):
        assert REMOVED_SYMBOLS.isdisjoint(models.__all__)
        assert not any("Subscription" in name or "Usage" in name for name in models.__all__)

    def test_barrel_all_matches_its_namespace(self):
        """`__all__` is written by hand and listed first, so it can drift from what is imported."""
        for name in models.__all__:
            assert hasattr(models, name), f"models.__all__ names {name}, which it does not export"

    def test_subscriptions_module_does_not_exist(self):
        assert not (_REPO_ROOT / "src/nativespeaker/api/models/subscriptions.py").exists()

    def test_no_module_imports_a_removed_symbol(self):
        """No module in src/ or tests/ imports one of the deleted model symbols.

        A stale import is not a latent inconvenience here -- it is an ImportError at collection
        time for the whole package, which is how config.py's `SubscriptionPlan` import made the
        model repair and the config removal inseparable.
        """
        offenders = {}
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")) + \
                    sorted((_REPO_ROOT / "tests").rglob("*.py")):
            imported = _imported_names(path)
            hits = sorted((imported & REMOVED_SYMBOLS)
                          | {n for n in imported if n.endswith("models.subscriptions")})
            if hits:
                offenders[str(path.relative_to(_REPO_ROOT))] = hits
        assert not offenders, f"stale model imports: {offenders}"
