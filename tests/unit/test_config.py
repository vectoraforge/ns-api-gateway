import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from nativespeaker.api.app.lifespan import build_app_store_verifier
from nativespeaker.api.config import (
    AppConfig,
    AppStoreConfig,
    EnvironmentConfig,
    ModelConfig,
    ResilienceConfig,
    StoreEnvironment,
)

# Removed for these cases: the nested delimiter makes pytest-dotenv's CONFIG_DIR ambiguous.
_DOTENV_KEYS = ["CONFIG_DIR"]

# The repository's tracked configuration file -- the one the application actually starts against.
TRACKED_CONFIG = Path(__file__).resolve().parents[2] / "config" / "config.yaml"

# Synthetic values for the blocks that live in .env, so these cases ignore a developer's environment.
_ENV_SECRETS = {
    "DB_HOST": "localhost", "DB_PORT": "5432", "DB_USER": "u",
    "DB_PASSWORD": "p", "DB_NAME": "d",
    "JWT_PROJECT_ID": "test-project", "JWT_API_KEY": "test-api-key",
}


# The repository root, so a path the application resolves against its own cwd resolves here too.
REPOSITORY_ROOT = TRACKED_CONFIG.parents[1]

# The three variables a deployer supplies; the fourth field defaults to the committed root certificate.
_APP_STORE_ENV = {"APP_STORE_BUNDLE_ID": "com.nativespeaker.app",
                  "APP_STORE_APP_APPLE_ID": "6001234567",
                  "APP_STORE_ENVIRONMENT": "production"}

# The library's two other environment values, as literals: importing its enum would make the cases below
# follow a library change instead of catching it.
VERIFICATION_SKIPPING_ENVIRONMENTS = ("Xcode", "LocalTesting")


def load_tracked_config(env: dict[str, str]) -> AppConfig:
    """Load the tracked configuration file under a replaced environment, as the application does at boot."""
    tmp_dir = tempfile.mkdtemp()
    try:
        Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
        Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
        Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

        with patch.dict(os.environ, {**_ENV_SECRETS, **env}, clear=True):
            # See below: _env_file is invisible to ty's synthesised __init__.
            loaded = EnvironmentConfig(config_dir=Path(tmp_dir),
                                       _env_file=None)  # ty: ignore[unknown-argument]
        assert loaded.app_config is not None
        return loaded.app_config
    finally:
        shutil.rmtree(tmp_dir)


def test_model_config_defaults():
    config = ModelConfig()
    assert config.name == "gpt-4o-mini"
    assert config.temperature == 0.3
    assert config.max_tokens == 1000


def test_resilence_config_defaults():
    config = ResilienceConfig()
    assert config.queue_size == 25
    assert config.timeout_seconds == 30.0


def test_model_config_invalid_temperature():
    with pytest.raises(ValidationError):
        ModelConfig(temperature=2.5)


def test_main_config_loads_yaml_and_content():
    yaml_content = """
log_level: INFO
model:
  name: "gpt-4"
  temperature: 0.5
db:
  host: localhost
  port: 5432
  user: test-user
  password: test-password
  name: test-db
jwt:
  project_id: test-project
  api_key: test-api-key
"""
    prompt_content = "Analyze {lang} phrase: {phrase}"
    examples_content = """
en:
  - "Example 1"
"""

    tmp_dir = tempfile.mkdtemp()
    try:
        Path(tmp_dir, "config.yaml").write_text(yaml_content)
        Path(tmp_dir, "prompt.txt").write_text(prompt_content)
        Path(tmp_dir, "examples.yaml").write_text(examples_content)

        env_clean = {k: v for k, v in os.environ.items() if k not in _DOTENV_KEYS}
        with patch.dict(os.environ, env_clean, clear=True):
            # _env_file is on BaseSettings.__init__, but ty sees only the synthesised one.
            config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                       _env_file=None)  # ty: ignore[unknown-argument]
            assert config.app_config is not None
            assert config.app_config.model.name == "gpt-4"
            assert config.app_config.model.temperature == 0.5
            assert config.app_config.prompt == prompt_content
            assert config.app_config.examples["en"] == ["Example 1"]
    finally:
        shutil.rmtree(tmp_dir)


def test_main_config_missing_file():
    env_clean = {k: v for k, v in os.environ.items() if k not in _DOTENV_KEYS}
    with patch.dict(os.environ, env_clean, clear=True):
        with pytest.raises(FileNotFoundError):
            # See above: _env_file is invisible to ty's synthesised __init__.
            EnvironmentConfig(config_dir=Path("/nonexistent/"),
                              _env_file=None)  # ty: ignore[unknown-argument]


class TestSubscriptionConfigSurfaceIsGone:
    """The model no longer describes subscription plans or receipt verification."""

    def test_apple_config_class_is_gone(self):
        import nativespeaker.api.config as config_module
        assert not hasattr(config_module, "AppleConfig")

    def test_app_config_declares_no_apple_or_quota_field(self):
        assert "apple" not in AppConfig.model_fields
        assert "quotas" not in AppConfig.model_fields

    def test_tracked_config_yaml_loads(self):
        """Loads the tracked file, so a block left behind after the fields were removed fails here and nowhere else."""
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            with patch.dict(os.environ, _ENV_SECRETS, clear=True):
                config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                           _env_file=None)  # ty: ignore[unknown-argument]
                assert config.app_config is not None
                assert config.app_config.model.name == "gpt-4o-mini"
        finally:
            shutil.rmtree(tmp_dir)

    def test_a_stale_block_fails_loudly(self):
        """`extra='forbid'` makes the removal real: an ignored block would read as allowance nothing enforces."""
        with pytest.raises(ValidationError, match="quotas"):
            AppConfig(quotas={"free": 10},  # ty: ignore[unknown-argument]
                      prompt="p",
                      examples={"en": ["Example 1"]})


class TestFirebaseCredentialSurfaceIsGone:
    """The credential is discovered from the environment now, so the model declares no Firebase key at all."""

    def test_app_config_declares_no_firebase_field(self):
        assert "firebase" not in AppConfig.model_fields

    def test_a_leftover_credential_variable_in_a_developers_env_is_ignored(self):
        """T-37.2-07: an orphaned value must not fail the load -- nothing reads it, and boot still succeeds."""
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            stale = {**_ENV_SECRETS, "FIREBASE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}'}
            with patch.dict(os.environ, stale, clear=True):
                config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                           _env_file=None)  # ty: ignore[unknown-argument]
                assert config.app_config is not None
        finally:
            shutil.rmtree(tmp_dir)


class TestTheTrackedPoolSizeMergesWithTheEnvironmentCredentials:
    """D-16: a partial `db:` block sets the pool size without displacing the credentials that live in .env."""

    def test_the_tracked_pool_size_loads_beside_the_environment_credentials(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            with patch.dict(os.environ, _ENV_SECRETS, clear=True):
                config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                           _env_file=None)  # ty: ignore[unknown-argument]
                assert config.app_config is not None
                db = config.app_config.db

                # The YAML key, and the five credentials the block would have replaced had it not merged.
                assert db.pool_size == 12
                assert (db.host, db.port, db.user, db.name) == ("localhost", 5432, "u", "d")
                assert db.password.get_secret_value() == "p"
        finally:
            shutil.rmtree(tmp_dir)


class TestNoTrackedYamlCarriesKeyMaterial:
    """The tracked configuration is a public file: a credential pasted into it would be committed."""

    def test_no_tracked_yaml_under_config_carries_service_account_material(self):
        for path in TRACKED_CONFIG.parent.rglob("*.y*ml"):
            text = path.read_text()
            assert "private_key" not in text, f"{path} carries key material"
            assert "service_account" not in text, f"{path} carries key material"


class TestTheStoreEnvironmentCannotSkipSignatureVerification:
    """D-11, T-43-04. A security case: two of the library's four environments verify no signature at all."""

    def test_the_member_set_is_exactly_sandbox_and_production(self):
        assert {member.value for member in StoreEnvironment} == {"sandbox", "production"}

    @pytest.mark.parametrize("value", VERIFICATION_SKIPPING_ENVIRONMENTS)
    def test_a_verification_skipping_environment_never_reaches_a_verifier(self, value):
        # These two make the library skip verification, so a free-text field would open this route.
        store = load_tracked_config({**_APP_STORE_ENV, "APP_STORE_ENVIRONMENT": value}).app_store

        assert store.environment is None
        assert build_app_store_verifier(store) is None

    def test_a_named_environment_still_loads(self):
        """The control: a loader that refused everything would pass both cases above."""
        assert load_tracked_config(_APP_STORE_ENV).app_store.environment is StoreEnvironment.production


class TestTheThreeDeployerVariablesLandOnTheConfig:
    """P-13, P-14. The deployer supplies three variables and the tracked file supplies the product map."""

    def test_every_app_store_variable_lands_on_the_nested_model(self):
        store = load_tracked_config(_APP_STORE_ENV).app_store
        assert store.bundle_id == "com.nativespeaker.app"
        assert store.app_apple_id == 6001234567
        assert store.environment is StoreEnvironment.production

    def test_the_tracked_product_map_merges_with_the_environment_nesting(self):
        """D-16, P-13: the partial `app_store:` block coexists with APP_STORE_*, as `db:` does with DB_*."""
        store = load_tracked_config(_APP_STORE_ENV).app_store
        assert store.products
        assert set(store.products.values()) <= {"anonymous", "registered", "paid"}
        assert (store.bundle_id, store.app_apple_id) == ("com.nativespeaker.app", 6001234567)

    def test_the_model_declares_no_sibling_field_that_would_make_a_variable_ambiguous(self):
        """P-14: a field named `appstore` beside `app_store` was measured to stop APP_STORE_APP_APPLE_ID landing."""
        assert "appstore" not in AppConfig.model_fields
        assert "app_store" in AppConfig.model_fields


class TestTheDefaultRootCertificateIsTheCommittedAppleRoot:
    """D-10. A deployment that configures no certificate still pins Apple's own root."""

    def test_the_default_path_is_the_committed_file(self):
        assert AppStoreConfig().root_certificate_path == "config/certs/AppleRootCA-G3.cer"

    def test_the_default_path_reads_as_bytes(self):
        default = REPOSITORY_ROOT / AppStoreConfig().root_certificate_path
        assert default.read_bytes()


class TestAnIncompleteConfigurationBootsAndHoldsNoVerifier:
    """D-02, P-04. The library raises ValueError from its own constructor, which would kill the pod at boot."""

    def _store(self, **overrides) -> AppStoreConfig:
        """A complete Production configuration, with `overrides` removing whatever a case wants absent."""
        complete = {"bundle_id": "com.nativespeaker.app",
                    "environment": StoreEnvironment.production,
                    "app_apple_id": 6001234567,
                    "root_certificate_path": str(REPOSITORY_ROOT
                                                 / "config/certs/AppleRootCA-G3.cer")}
        return AppStoreConfig(**(complete | overrides))

    def test_production_without_an_app_id_yields_no_verifier_and_does_not_raise(self):
        assert build_app_store_verifier(self._store(app_apple_id=None)) is None

    def test_a_complete_production_configuration_yields_one(self):
        """The control: without it the case above would pass with a builder that always answers None."""
        assert build_app_store_verifier(self._store()) is not None

    def test_an_absent_environment_yields_no_verifier(self):
        assert build_app_store_verifier(self._store(environment=None)) is None

    def test_an_unreadable_root_certificate_yields_no_verifier(self):
        assert build_app_store_verifier(
            self._store(root_certificate_path="/nonexistent/AppleRootCA-G3.cer")) is None


def _uncommented(path: Path) -> dict[str, str]:
    """Every assignment a file ships uncommented, which is what a copied .env carries to boot."""
    pairs = (line.split("=", 1) for line in path.read_text().splitlines()
             if "=" in line and not line.lstrip().startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


class TestAMalformedAppStoreValueCostsTheRouteAndNotTheBoot:
    """CR-04, T-U7T-03. An operator error costs one route its 503, never the pod its boot."""

    def test_the_shipped_placeholders_degrade_to_absent(self):
        store = AppStoreConfig(app_apple_id="...",  # ty: ignore[invalid-argument-type]
                               environment="...")  # ty: ignore[invalid-argument-type]

        assert (store.app_apple_id, store.environment) == (None, None)

    def test_a_degraded_configuration_holds_no_verifier(self):
        """The 503 path: the route fails closed and the rest of the service is untouched."""
        degraded = AppStoreConfig(bundle_id="com.nativespeaker.app",
                                  app_apple_id="...",  # ty: ignore[invalid-argument-type]
                                  environment="...")  # ty: ignore[invalid-argument-type]

        assert build_app_store_verifier(degraded) is None

    def test_a_well_formed_pair_still_parses_and_builds_a_verifier_control(self):
        """The control: a validator that degraded everything would pass both cases above."""
        store = AppStoreConfig(bundle_id="com.nativespeaker.app",
                               app_apple_id="6001234567",  # ty: ignore[invalid-argument-type]
                               environment="production",  # ty: ignore[invalid-argument-type]
                               root_certificate_path=str(REPOSITORY_ROOT
                                                         / "config/certs/AppleRootCA-G3.cer"))

        assert (store.app_apple_id, store.environment) == (6001234567,
                                                           StoreEnvironment.production)
        assert build_app_store_verifier(store) is not None


class TestTheCommittedEnvExampleCannotCrashABoot:
    """CR-04. The shipped placeholders parsed as an int and an enum, so a copied file killed the pod."""

    def test_the_app_store_lines_it_ships_are_constructible(self):
        shipped = _uncommented(REPOSITORY_ROOT / ".env.example")
        fields = {key.removeprefix("APP_STORE_").lower(): value
                  for key, value in shipped.items() if key.startswith("APP_STORE_")}

        assert isinstance(AppStoreConfig(**fields), AppStoreConfig)

    def test_the_reader_finds_the_assignments_that_file_does_ship_control(self):
        """The control: a reader that quietly returned nothing would pass the case above."""
        assert "DB_HOST" in _uncommented(REPOSITORY_ROOT / ".env.example")
