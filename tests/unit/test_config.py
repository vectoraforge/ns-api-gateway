import inspect
import os
import shutil
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

import google.auth
import google.auth.exceptions
import pytest
import yaml
from jwt.exceptions import PyJWTError
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from nativespeaker.api.app.lifespan import (
    _DB_POOL_RECYCLE_SECONDS,
    _play_credential,
    build_app_store_verifier,
    build_db_engine,
    build_jwt_verifier,
)
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.config import (
    AppConfig,
    AppStoreConfig,
    DatabaseConfig,
    EnvironmentConfig,
    JWTConfig,
    ModelConfig,
    ResilienceConfig,
    StoreEnvironment,
)
from nativespeaker.api.logs import setup_logging
from unit.test_jwks_offload import install_counted_transport

# Removed for these cases: the nested delimiter makes pytest-dotenv's CONFIG_DIR ambiguous.
_DOTENV_KEYS = ["CONFIG_DIR"]

# The repository's tracked configuration file -- the one the application actually starts against.
TRACKED_CONFIG = Path(__file__).resolve().parents[2] / "config" / "config.yaml"

# Synthetic values for the blocks that live in .env, so these cases ignore a developer's environment.
_ENV_SECRETS = {
    "DB_HOST": "localhost", "DB_PORT": "5432", "DB_USER": "u",
    "DB_PASSWORD": "p", "DB_NAME": "d",
    "JWT_PROJECT_ID": "test-project", "JWT_API_KEY": "test-api-key",
    "OPENAI_API_KEY": "sk-test-openai-key",
}


# The repository root, so a path the application resolves against its own cwd resolves here too.
REPOSITORY_ROOT = TRACKED_CONFIG.parents[1]

# A URL no case reaches over the network: the transport under `PyJWKClient` is stubbed in every one.
UNUSABLE_JWKS_URL = "https://jwks.example.invalid/keys"

# The three variables a deployer supplies; the fourth field defaults to the committed root certificate.
_APP_STORE_ENV = {"APP_STORE_BUNDLE_ID": "com.nativespeaker.app",
                  "APP_STORE_APP_APPLE_ID": "6001234567",
                  "APP_STORE_ENVIRONMENT": "production"}

# The three variables a deployer supplies for Google; `products` comes from the tracked file, as Apple's does.
_GOOGLE_PLAY_ENV = {"GOOGLE_PLAY_PACKAGE_NAME": "com.nativespeaker.app",
                    "GOOGLE_PLAY_PUSH_AUDIENCE": "https://api.nativespeaker.com/webhooks/google-play/rtdn",
                    "GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL": "rtdn-push@nativespeaker.iam.gserviceaccount.com"}

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
        # Stated rather than inherited: `openai.api_key` is required, and a case that read it from
        # the developer's own environment would pass here and fail in a checkout without one.
        env_clean["OPENAI_API_KEY"] = "sk-test-openai-key"
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


class TestAYamlFileThatIsNotAMappingNamesItself:
    """37.4 WR-04. An empty ConfigMap key is a routine mount failure, and the bare interpreter
    error it used to raise named neither the file nor the problem an operator has to fix."""

    def _load(self, config: str, examples: str):
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(config)
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text(examples)

            with patch.dict(os.environ, _ENV_SECRETS, clear=True):
                # See above: _env_file is invisible to ty's synthesised __init__.
                EnvironmentConfig(config_dir=Path(tmp_dir),
                                  _env_file=None)  # ty: ignore[unknown-argument]
        finally:
            shutil.rmtree(tmp_dir)

    @pytest.mark.parametrize("content", ["", "# every line a comment\n", "- one\n- two\n", "42\n"],
                             ids=["empty", "comments-only", "a-list", "a-scalar"])
    def test_a_config_file_carrying_no_mapping_names_the_file(self, content):
        with pytest.raises(ValidationError, match="config.yaml does not contain a YAML mapping"):
            self._load(config=content, examples='en:\n  - "Example 1"\n')

    def test_an_examples_file_carrying_no_mapping_names_the_file(self):
        """The second read, which reached pydantic as `None` and blamed the `examples` field."""
        with pytest.raises(ValidationError, match="examples.yaml does not contain a YAML mapping"):
            self._load(config="model:\n  name: gpt-4\n", examples="")

    def test_two_well_formed_mappings_still_load_control(self):
        """The control: a loader that rejected everything would pass both cases above."""
        self._load(config="model:\n  name: gpt-4\n", examples='en:\n  - "Example 1"\n')

    @pytest.mark.parametrize("key", ["prompt", "examples"])
    def test_a_key_that_comes_from_a_sibling_file_names_both_files(self, key):
        """WR-04. Both are `AppConfig` fields and `config.yaml` says nothing about where they come
        from, so declaring one there is the obvious mistake -- and it used to crashloop the pod on
        a bare `TypeError` naming neither file."""
        with pytest.raises(ValidationError) as raised:
            self._load(config=f"model:\n  name: gpt-4\n{key}: anything\n",
                       examples='en:\n  - "Example 1"\n')

        message = str(raised.value)
        assert f"config.yaml declares ['{key}']" in message
        assert "prompt.txt" in message and "examples.yaml" in message


class TestAnAbsentCredentialBlockIsReportedUnderItsOwnName:
    """37.4 WR-05. `default_factory` on a model whose own fields are required raised from inside the
    factory, so a wholly absent block surfaced as leaf names with no path -- five `Field required`
    lines, none of them saying "db". Boot is the one place that message has to be actionable."""

    @pytest.mark.parametrize(("block", "prefix"), [("db", "DB_"), ("jwt", "JWT_")])
    def test_a_wholly_absent_block_names_the_block(self, block, prefix):
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text("model:\n  name: gpt-4\n")
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            without = {key: value for key, value in _ENV_SECRETS.items()
                       if not key.startswith(prefix)}
            with patch.dict(os.environ, without, clear=True):
                with pytest.raises(ValidationError) as failure:
                    # See above: _env_file is invisible to ty's synthesised __init__.
                    EnvironmentConfig(config_dir=Path(tmp_dir),
                                      _env_file=None)  # ty: ignore[unknown-argument]

            assert [error["loc"] for error in failure.value.errors()] == [(block,)]
        finally:
            shutil.rmtree(tmp_dir)

    def test_neither_block_declares_a_factory_that_would_hide_the_path(self):
        """The mechanism, not just the message: a factory reinstated here restores the old error."""
        for block in ("db", "jwt"):
            assert AppConfig.model_fields[block].is_required()


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


class TestEveryLoggingFieldReachesTheLoggingSetup:
    """WR-03: `json_log_path` outlived the `FileHandler` branch that read it. `extra='forbid'`
    accepted it from `config.yaml` and from `JSON_LOG_PATH`, so an operator who set it got console
    lines, no JSON file, and no error saying so -- the silent stand-in this codebase refuses."""

    def test_no_logging_field_is_declared_that_setup_logging_cannot_take(self):
        declared = {name for name in AppConfig.model_fields if "log" in name}
        accepted = set(inspect.signature(setup_logging).parameters)

        # The control: an empty left side would pass this on any signature at all.
        assert declared
        assert declared <= accepted, declared - accepted

    def test_the_removed_field_is_now_refused_rather_than_ignored(self):
        with pytest.raises(ValidationError, match="json_log_path"):
            AppConfig(json_log_path="/var/log/app.json",  # ty: ignore[unknown-argument]
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


class TestTheIdentityToolkitKeyIsOptionalAndSecret:
    """WR-07. Only the e2e harness reads it, so a deployment must boot without it and never print it."""

    def _config_without_the_key(self) -> AppConfig:
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            without = {key: value for key, value in _ENV_SECRETS.items() if key != "JWT_API_KEY"}
            with patch.dict(os.environ, without, clear=True):
                loaded = EnvironmentConfig(config_dir=Path(tmp_dir),
                                           _env_file=None)  # ty: ignore[unknown-argument]
                assert loaded.app_config is not None
                return loaded.app_config
        finally:
            shutil.rmtree(tmp_dir)

    def test_a_deployment_carrying_no_key_still_boots(self):
        assert self._config_without_the_key().jwt.api_key is None

    def test_the_key_never_renders_in_a_dump_or_a_repr(self):
        """`hide_input_in_errors` covers a validation error; a dump and a repr are the other two channels."""
        # The copied directory its siblings all use: reading the live `config/` would make what
        # this asserts depend on whatever a developer has there, and skips the `is not None` guard.
        jwt = load_tracked_config({}).jwt

        assert jwt.api_key is not None
        assert jwt.api_key.get_secret_value() == "test-api-key"
        assert "test-api-key" not in repr(jwt)
        assert "test-api-key" not in str(jwt.model_dump())


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


class TestTheProviderKeyIsADeclaredSetting:
    """WR-04. `init_chat_model` read OPENAI_API_KEY from the ambient environment, so the seventh
    boot-blocking credential failed as a library `OpenAIError` naming no setting of this service --
    and both chart lists documented it as optional."""

    def test_an_absent_key_is_a_validation_error_naming_this_blocks_field(self):
        without = {key: value for key, value in _ENV_SECRETS.items() if key != "OPENAI_API_KEY"}
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            with patch.dict(os.environ, without, clear=True):
                with pytest.raises(ValidationError, match="openai"):
                    EnvironmentConfig(config_dir=Path(tmp_dir),
                                      _env_file=None)  # ty: ignore[unknown-argument]
        finally:
            shutil.rmtree(tmp_dir)

    def test_the_key_loads_and_never_renders_in_a_dump_or_a_repr(self):
        """The control, and the secrecy the other six credentials already have."""
        openai = load_tracked_config({}).openai

        assert openai.api_key.get_secret_value() == "sk-test-openai-key"
        assert "sk-test-openai-key" not in repr(openai)
        assert "sk-test-openai-key" not in str(openai.model_dump())


class TestThePoolChecksAConnectionBeforeHandingItOut:
    """WR-05. A pod is long-lived and almost idle, so a pooled connection outlives the far end's
    idle timeout. Undetected, the next request raises out of the CRUD layer as an opaque 500 --
    and on a chat route, after the credit is already spent."""

    def _engine(self):
        # No connection is opened by construction, so this reads the pool the lifespan would build.
        return build_db_engine(DatabaseConfig(host="db.internal", port=5432, user="u",
                                              password="p", name="n"))  # ty: ignore[invalid-argument-type]

    def test_a_connection_is_pinged_before_it_is_reused(self):
        assert self._engine().pool._pre_ping is True

    def test_a_connection_is_retired_before_the_far_end_drops_it(self):
        assert self._engine().pool._recycle == _DB_POOL_RECYCLE_SECONDS
        assert 0 < _DB_POOL_RECYCLE_SECONDS <= 3600

    def test_the_pool_still_has_no_overflow_control(self):
        """The control: a builder that ignored its arguments would pass both cases above."""
        assert (self._engine().pool.size(), self._engine().pool._max_overflow) == (5, 0)


class TestTheLoggingLevelIsAPerDeploymentLever:
    """WR-02. `config.yaml` is init_settings, so a `log_level` declared there outranked LOG_LEVEL
    in every environment: the chart's `env` escape hatch rendered faithfully and did nothing."""

    def test_the_environment_raises_the_level(self):
        assert load_tracked_config({"LOG_LEVEL": "DEBUG"}).log_level == "DEBUG"

    def test_an_unset_variable_still_leaves_the_default(self):
        """The control: a case that read DEBUG from anywhere would pass the one above regardless."""
        assert load_tracked_config({}).log_level == "INFO"

    def test_the_tracked_file_declares_no_key_that_outranks_a_deployment_lever(self):
        declared = yaml.safe_load(TRACKED_CONFIG.read_text())

        assert "log_level" not in declared


class TestNoTrackedYamlCarriesKeyMaterial:
    """The tracked configuration is a public file: a credential pasted into it would be committed."""

    def test_no_tracked_yaml_under_config_carries_service_account_material(self):
        files = list(TRACKED_CONFIG.parent.rglob("*.y*ml"))
        # The control every other walking guard here carries: an empty walk is a pass, so a
        # renamed `config/` would turn the one committed-credential scan green having read nothing.
        assert files, f"no tracked YAML found under {TRACKED_CONFIG.parent}: the scan checked nothing"
        for path in files:
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


class TestTheThreeGooglePlayVariablesLandOnTheConfig:
    """A5, D-16, D-18. The Apple class above, executed for the block whose section name is two words."""

    # A variable that does not land leaves its field at None, so the seam reads unconfigured and the route
    # answers 503 in every environment with nothing written anywhere. That costs a deployment to find.
    def test_every_google_play_variable_lands_on_the_nested_model(self):
        """A5 falsified: `env_nested_max_split=1` was read from the source; the split is executed here."""
        play = load_tracked_config(_GOOGLE_PLAY_ENV).google_play

        assert play.package_name == "com.nativespeaker.app"
        assert play.push_audience == "https://api.nativespeaker.com/webhooks/google-play/rtdn"
        assert play.push_service_account_email == "rtdn-push@nativespeaker.iam.gserviceaccount.com"

    def test_the_tracked_product_map_merges_with_the_environment_nesting(self):
        """D-16, D-18: the partial `google_play:` block coexists with GOOGLE_PLAY_*, as `app_store:` does."""
        play = load_tracked_config(_GOOGLE_PLAY_ENV).google_play

        assert play.products
        assert set(play.products.values()) <= {"anonymous", "registered", "paid"}
        assert play.package_name == "com.nativespeaker.app"

    # `google` already names five things here: the Firebase sign-in provider, the Firebase Admin
    # credential, the Pub/Sub push identity, the Play Developer API and the purchase provider. A field
    # of that name beside `google_play` would take the first split of every GOOGLE_PLAY_* variable.
    def test_the_model_declares_no_sibling_field_that_would_make_a_variable_ambiguous(self):
        """The `appstore` / `app_store` case, for the prefix this project already gives five meanings."""
        assert "google" not in AppConfig.model_fields
        assert "google_play" in AppConfig.model_fields


class TestTheDefaultRootCertificateIsTheCommittedAppleRoot:
    """D-10, WR-08. The vendored root is found wherever `config_dir` puts the config tree, not
    wherever the process was started: as two independent notions, CONFIG_DIR moved config.yaml and
    left the certificate behind, and the webhook then 503'd for the life of the deployment."""

    def _loaded(self, config_dir: Path, env: dict[str, str] | None = None) -> AppStoreConfig:
        with patch.dict(os.environ, {**_ENV_SECRETS, **(env or {})}, clear=True):
            loaded = EnvironmentConfig(config_dir=config_dir,
                                       _env_file=None)  # ty: ignore[unknown-argument]
        assert loaded.app_config is not None
        return loaded.app_config.app_store

    def _config_tree_without_the_certs(self) -> str:
        tmp_dir = tempfile.mkdtemp()
        for name in ("config.yaml", "prompt.txt", "examples.yaml"):
            Path(tmp_dir, name).write_text((TRACKED_CONFIG.parent / name).read_text())
        return tmp_dir

    def test_the_shipped_tree_resolves_to_the_committed_file(self):
        store = self._loaded(TRACKED_CONFIG.parent)

        assert Path(store.root_certificate_path).read_bytes()
        assert build_app_store_verifier(self._complete(store)) is not None

    def test_a_moved_config_dir_moves_the_certificate_with_it(self):
        """The defect: this used to resolve under the process working directory regardless."""
        tmp_dir = self._config_tree_without_the_certs()
        try:
            store = self._loaded(Path(tmp_dir))
            assert store.root_certificate_path == str(Path(tmp_dir, "certs", "AppleRootCA-G3.cer"))
        finally:
            shutil.rmtree(tmp_dir)

    def test_an_explicitly_configured_path_still_outranks_the_derived_one(self):
        """The derived value is filled after construction, so it must not shadow the variable."""
        tmp_dir = self._config_tree_without_the_certs()
        try:
            store = self._loaded(Path(tmp_dir),
                                 {"APP_STORE_ROOT_CERTIFICATE_PATH": "/etc/ns/apple.cer"})
            assert store.root_certificate_path == "/etc/ns/apple.cer"
        finally:
            shutil.rmtree(tmp_dir)

    def test_the_bare_model_carries_no_working_directory_relative_default(self):
        assert AppStoreConfig().root_certificate_path is None

    def _complete(self, store: AppStoreConfig) -> AppStoreConfig:
        """The resolved path on an otherwise complete Production configuration."""
        return AppStoreConfig(bundle_id="com.nativespeaker.app",
                              environment=StoreEnvironment.production,
                              app_apple_id=6001234567,
                              root_certificate_path=store.root_certificate_path)


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

    @pytest.mark.parametrize("content", [b"", b"not a certificate at all", b"-----BEGIN CERT"],
                             ids=["truncated", "arbitrary-bytes", "the-pem-form"])
    def test_a_root_that_is_not_a_der_certificate_yields_no_verifier(self, content):
        """37.4 WR-06. The library parses its root lazily, so an unchecked one built a verifier that
        answered 401 to every genuine Apple notification -- a rejection reading as Apple forging."""
        tmp_dir = tempfile.mkdtemp()
        try:
            root = Path(tmp_dir, "AppleRootCA-G3.cer")
            root.write_bytes(content)
            assert build_app_store_verifier(self._store(root_certificate_path=str(root))) is None
        finally:
            shutil.rmtree(tmp_dir)

    def test_an_unopenable_root_yields_no_verifier_rather_than_raising(self):
        """A projected secret carrying the wrong mode is present, and `is_file()` says so."""
        tmp_dir = tempfile.mkdtemp()
        try:
            root = Path(tmp_dir, "AppleRootCA-G3.cer")
            root.write_bytes((REPOSITORY_ROOT / "config/certs/AppleRootCA-G3.cer").read_bytes())
            root.chmod(0o000)
            if os.access(root, os.R_OK):  # pragma: no cover - the root user reads it regardless
                pytest.skip("running as a user that ignores file modes")
            assert build_app_store_verifier(self._store(root_certificate_path=str(root))) is None
        finally:
            shutil.rmtree(tmp_dir)


class TestEveryAdcFailureCostsOneRouteAndNotTheBoot:
    """37.4 WR-08. `google.auth.default()` raises `RefreshError` and `TransportError` too, when the
    GCE metadata server answers but answers badly -- a routine transient at pod start. Catching only
    `DefaultCredentialsError` let those out of `lifespan` and crashlooped the pod."""

    @pytest.mark.parametrize("failure", ["DefaultCredentialsError", "RefreshError",
                                         "TransportError", "MutualTLSChannelError"])
    def test_the_credential_reader_answers_none_for_any_of_them(self, monkeypatch, failure):
        def raising(*_args, **_kwargs):
            raise getattr(google.auth.exceptions, failure)(f"{failure} in this test")

        monkeypatch.setattr(google.auth, "default", raising)
        assert _play_credential() is None

    def test_a_supplied_credential_is_returned_control(self, monkeypatch):
        """The control: a reader that answered None unconditionally would pass every case above."""
        supplied = object()
        monkeypatch.setattr(google.auth, "default", lambda *a, **k: (supplied, "a-project"))
        assert _play_credential() is supplied


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


class TestTheDsnSurvivesAPasswordCarryingUrlDelimiters:
    """WR-01. An f-string DSN re-partitioned on `@ / : ? #`, sending the credential to another host."""

    @pytest.mark.parametrize("password", ["p@ss/w0rd", "a:b@c", "pw?x#y", "pass word", "sim.ple"])
    def test_every_component_round_trips(self, password):
        config = DatabaseConfig(host="db.internal", port=5432, user="postgres",
                                password=password, name="ns")  # ty: ignore[invalid-argument-type]

        parsed = make_url(config.url)

        assert (parsed.host, parsed.port, parsed.username, parsed.database) == (
            "db.internal", 5432, "postgres", "ns")
        assert parsed.password == password

    def test_a_user_carrying_a_delimiter_round_trips_too(self):
        config = DatabaseConfig(host="db.internal", port=5432, user="ns@tenant",
                                password="p", name="ns")  # ty: ignore[invalid-argument-type]

        assert make_url(config.url).username == "ns@tenant"


class TestTheComposeDatabaseIsNotPublishedToTheWholeNetwork:
    """WR-05. `"5432:5432"` binds every interface, leaving the `.env` password as the only barrier."""

    def test_every_published_port_names_the_loopback_address(self):
        compose = yaml.safe_load((REPOSITORY_ROOT / "docker-compose.yml").read_text())
        published = [str(port) for service in compose["services"].values()
                     for port in service.get("ports", [])]

        # The control: an empty list would pass the loop below without checking anything.
        assert published
        for port in published:
            assert port.startswith("127.0.0.1:"), f"{port} publishes on every interface"


class TestTheIdentityBarrierVerifierFailsFastAndNamesItsEndpoint:
    """WR-02. `JWTVerifier.__init__` fetches, and the one caller that must not degrade is the one
    whose failure takes the whole pod down -- so its diagnostic has to name the endpoint that refused."""

    @staticmethod
    def _jwt_config() -> JWTConfig:
        return JWTConfig(project_id="test-project", jwks_url=UNUSABLE_JWKS_URL)

    def test_an_unreachable_endpoint_raises_a_runtime_error_naming_the_url(self, monkeypatch):
        transport = install_counted_transport(monkeypatch)
        transport.error = urllib.error.URLError("the JWKS endpoint is unreachable")

        with pytest.raises(RuntimeError) as raised:
            build_jwt_verifier(self._jwt_config())

        # The whole point of the guard: the bare `PyJWKClientError` names no URL at all.
        assert UNUSABLE_JWKS_URL in str(raised.value)
        assert not isinstance(raised.value, PyJWTError)

    def test_a_2xx_that_is_not_json_is_named_the_same_way(self, monkeypatch):
        """The wrapped family too, not just the one PyJWT converts itself: a proxy error page
        answering 200 leaves a `JSONDecodeError` that the constructor turns into a `PyJWKClientError`."""
        transport = install_counted_transport(monkeypatch)
        transport.body = b"<html>502 Bad Gateway</html>"

        with pytest.raises(RuntimeError) as raised:
            build_jwt_verifier(self._jwt_config())

        assert UNUSABLE_JWKS_URL in str(raised.value)

    def test_a_usable_endpoint_builds_the_verifier(self, monkeypatch):
        """The control: a builder that raised unconditionally would pass both cases above."""
        install_counted_transport(monkeypatch)

        assert isinstance(build_jwt_verifier(self._jwt_config()), JWTVerifier)
