"""The `core.users` model at its target shape; that the shape matches the applied schema is an e2e claim."""
import ast
from pathlib import Path

from nativespeaker.api import tables
from nativespeaker.api.tables import User

# The same seven names tests/schema/test_inventory.py asserts against the live crud.
EXPECTED_FIELDS = {
    "id", "email", "display_name", "registered_at", "active", "created_at", "updated_at",
}

# Absent by design: the verified pair, the display name and the allowance all live elsewhere now.
ABSENT_FIELDS = ("jwt_sub", "name", "subscription_plan")

# Symbols that left with tables/subscriptions.py and tables.users.UsageMonthly, and stayed gone.
# `Subscription`, `SubscriptionEvent` and the two status names came back in 43-01, against the v2.0
# migration and in tables/purchases.py; the plan names below are the v1 layer and have no crud table.
REMOVED_SYMBOLS = frozenset({
    "SubscriptionPlan", "SubscriptionPlanType",
    "SubscriptionProvider", "SubscriptionProviderType", "UsageMonthly",
})

# Exempted by name rather than by weakening the backstop, so every other such symbol still trips it.
ALLOWED_MODEL_SYMBOLS = frozenset({"Subscription", "SubscriptionEvent", "SubscriptionStatus",
                                   "UserMonthlyUsage"})

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _imported_names(path: Path) -> set[str]:
    """Every name a module imports, read from its AST, so a SQL string naming a dropped table is not a hit."""
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
        """NULL unless a verified address was copied, so NOT NULL would reject rows the crud accepts."""
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
    """The v1 model layer no longer describes subscription plans or monthly usage."""

    def test_barrel_exports_no_removed_symbol(self):
        assert REMOVED_SYMBOLS.isdisjoint(tables.__all__)
        suspect = [
            name for name in tables.__all__
            if ("Subscription" in name or "Usage" in name) and name not in ALLOWED_MODEL_SYMBOLS
        ]
        assert not suspect, f"barrel exports a removed-layer symbol: {suspect}"

    def test_barrel_all_matches_its_namespace(self):
        """`__all__` is written by hand and listed first, so it can drift from what is imported."""
        for name in tables.__all__:
            assert hasattr(tables, name), f"tables.__all__ names {name}, which it does not export"

    def test_subscriptions_module_does_not_exist(self):
        assert not (_REPO_ROOT / "src/nativespeaker/api/tables/subscriptions.py").exists()

    def test_no_module_imports_a_removed_symbol(self):
        """A stale import is an ImportError at collection time for the whole package, not a latent nuisance."""
        offenders = {}
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")) + \
                    sorted((_REPO_ROOT / "tests").rglob("*.py")):
            imported = _imported_names(path)
            hits = sorted((imported & REMOVED_SYMBOLS)
                          | {n for n in imported if n.endswith("tables.subscriptions")})
            if hits:
                offenders[str(path.relative_to(_REPO_ROOT))] = hits
        assert not offenders, f"stale model imports: {offenders}"
