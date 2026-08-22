import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.config import (
    AppConfig,
    EnvironmentConfig,
    FirebaseConfig,
    ModelConfig,
    ResilienceConfig,
)

# pytest-dotenv loads .env which sets CONFIG_DIR.
# With env_nested_delimiter="_", pydantic-settings can misinterpret env vars.
# Remove these env vars for MainConfig tests.
_DOTENV_KEYS = ["CONFIG_DIR"]

# The repository's tracked configuration file -- the one the application actually starts against.
TRACKED_CONFIG = Path(__file__).resolve().parents[2] / "config" / "config.yaml"

# Synthetic values for the two blocks that live in the gitignored .env rather than the YAML, so the
# cases below load the tracked file without depending on a developer's environment.
_ENV_SECRETS = {
    "DB_HOST": "localhost", "DB_PORT": "5432", "DB_USER": "u",
    "DB_PASSWORD": "p", "DB_NAME": "d",
    "JWT_PROJECT_ID": "test-project", "JWT_API_KEY": "test-api-key",
}

# A locally-generated 32-byte key as base64 text -- the encoding pinned by this phase's checkpoint.
# Not the committed development key: nothing here should break when that one is rotated.
_TEST_HMAC_KEY = base64.b64encode(bytes(range(32))).decode()
_HMAC_YAML = f'hmac:\n  active_version: 1\n  keys:\n    1: "{_TEST_HMAC_KEY}"\n'


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
""" + _HMAC_YAML
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
            # _env_file is declared on BaseSettings.__init__, but ty sees only the
            # __init__ synthesised from the model fields.
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
    """D-16: the model no longer describes subscription plans or Apple receipt verification."""

    def test_apple_config_class_is_gone(self):
        import nativespeaker.api.config as config_module
        assert not hasattr(config_module, "AppleConfig")

    def test_app_config_declares_no_apple_or_quota_field(self):
        assert "apple" not in AppConfig.model_fields
        assert "quotas" not in AppConfig.model_fields

    def test_tracked_config_yaml_loads(self):
        """The file the application actually starts against still validates.

        `AppConfig(**yaml_data, ...)` splats the YAML into a settings model, so this loads the
        tracked file rather than a hand-written copy -- a block left behind in `config/config.yaml`
        after the fields were removed would fail here and nowhere else.
        """
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
        """`extra='forbid'` is what makes the removal real: a leftover key raises, never coasts.

        This is the honest failure mode, not something to work around with `extra='ignore'` -- a
        silently-ignored `quotas:` block would read as configured allowance that nothing enforces.

        `hmac` is supplied so the only thing wrong with this construction is the stale block. Let
        it fall back on the required-field error and the case would pass without `extra='forbid'`
        ever being consulted.
        """
        with pytest.raises(ValidationError, match="quotas"):
            AppConfig(quotas={"free": 10},  # ty: ignore[unknown-argument]
                      hmac={"active_version": 1, "keys": {1: _TEST_HMAC_KEY}},
                      prompt="p",
                      examples={"en": ["Example 1"]})


class TestHmacConfigSurface:
    """FOUND-05 / D-20 / D-22: the `hmac:` block is declared on the model and required at load."""

    def test_app_config_declares_hmac(self):
        assert "hmac" in AppConfig.model_fields

    def test_a_config_file_with_no_hmac_block_fails_to_load(self):
        """D-22 at the boundary that matters: the process never starts without the key it needs
        to write. The abort happens inside `EnvironmentConfig()`, before the lifespan runs."""
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text("log_level: INFO\nchats_limit: 50\n")
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            with patch.dict(os.environ, _ENV_SECRETS, clear=True):
                with pytest.raises(ValidationError, match="hmac"):
                    EnvironmentConfig(config_dir=Path(tmp_dir),
                                      _env_file=None)  # ty: ignore[unknown-argument]
        finally:
            shutil.rmtree(tmp_dir)

    def test_the_tracked_config_yaml_carries_a_usable_active_key(self):
        """The committed development key is real material, not a REPLACE-ME placeholder: it
        decodes, it is long enough, and it derives a 32-byte digest for the BYTEA column."""
        tmp_dir = tempfile.mkdtemp()
        try:
            Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
            Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
            Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')

            with patch.dict(os.environ, _ENV_SECRETS, clear=True):
                config = EnvironmentConfig(config_dir=Path(tmp_dir),
                                           _env_file=None)  # ty: ignore[unknown-argument]
                assert config.app_config is not None
                ring = HmacKeyring(config.app_config.hmac)
                assert ring.active_version == config.app_config.hmac.active_version
                assert len(ring.actor_subject_hash("https://issuer.example", "subject")) == 32
        finally:
            shutil.rmtree(tmp_dir)


# A structurally-valid service account with no real key material: the private key is a literal
# placeholder, so nothing here is a credential even though it parses like one.
_FAKE_SERVICE_ACCOUNT = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "0123456789abcdef0123456789abcdef01234567",
    "private_key": "-----BEGIN PRIVATE KEY-----\nPLACEHOLDER\n-----END PRIVATE KEY-----\n",
    "client_email": "svc@test-project.iam.gserviceaccount.com",
    "client_id": "123456789012345678901",
    "token_uri": "https://oauth2.googleapis.com/token",
})

# Not JSON, and shaped like the real thing -- so a test asserting it is absent from an error
# message is asserting the thing that would actually leak.
_MALFORMED_CREDENTIAL = "-----BEGIN PRIVATE KEY-----WOULD-LEAK-----END PRIVATE KEY-----"


def _load_against_tracked_yaml(**env: str) -> EnvironmentConfig:
    """Load the tracked `config/config.yaml` under a controlled environment.

    The tracked file rather than a hand-written copy: Pitfall 7 is about what that specific file
    declares, and a local copy would not notice a `firebase:` block appearing in it.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        Path(tmp_dir, "config.yaml").write_text(TRACKED_CONFIG.read_text())
        Path(tmp_dir, "prompt.txt").write_text("Analyze {lang} phrase: {phrase}")
        Path(tmp_dir, "examples.yaml").write_text('en:\n  - "Example 1"\n')
        with patch.dict(os.environ, {**_ENV_SECRETS, **env}, clear=True):
            # See above: _env_file is invisible to ty's synthesised __init__.
            return EnvironmentConfig(config_dir=Path(tmp_dir),
                                     _env_file=None)  # ty: ignore[unknown-argument]
    finally:
        shutil.rmtree(tmp_dir)


class TestFirebaseConfigSurface:
    """D-08: the service-account credential has exactly one home, the gitignored `.env`."""

    def test_app_config_declares_firebase(self):
        assert "firebase" in AppConfig.model_fields

    def test_the_field_is_defaulted_not_required(self):
        """The credential is genuinely absent today, and every non-completion path in the phase
        must stay runnable without it -- prepare mode, the mode-signal partition, the classifier,
        and every substituted-adapter test."""
        assert not AppConfig.model_fields["firebase"].is_required()

    def test_the_credential_is_typed_as_a_secret(self):
        annotation = FirebaseConfig.model_fields["service_account_json"].annotation
        assert annotation == (SecretStr | None)


class TestFirebaseCredentialAbsent:
    """Absent is a supported state: the service boots and completions fail closed downstream."""

    def test_config_loads_with_the_variable_unset(self):
        config = _load_against_tracked_yaml()
        assert config.app_config is not None
        assert config.app_config.firebase.service_account_json is None

    def test_credential_dict_is_none_rather_than_raising(self):
        """The adapter's selection arm branches on this; it must not have to catch an exception."""
        config = _load_against_tracked_yaml()
        assert config.app_config is not None
        assert config.app_config.firebase.credential_dict() is None

    def test_the_e2e_firebase_variables_do_not_collide_with_the_new_block(self):
        """`.env` already carries FIREBASE_API_KEY / FIREBASE_TEST_* for the e2e sign-in fixture.

        `env_nested_delimiter="_"` routes all of them at `firebase.*`, so the new block must
        tolerate them rather than reject the load and take the whole e2e suite down with it.
        """
        config = _load_against_tracked_yaml(FIREBASE_API_KEY="k",
                                            FIREBASE_TEST_EMAIL="e@example.com",
                                            FIREBASE_TEST_PASSWORD="p")
        assert config.app_config is not None
        assert config.app_config.firebase.service_account_json is None


class TestFirebaseCredentialPresent:
    """Present and well-formed: parsed once, at configuration time, never per request."""

    def test_the_value_arrives_through_the_nesting_rule(self):
        config = _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_FAKE_SERVICE_ACCOUNT)
        assert config.app_config is not None
        secret = config.app_config.firebase.service_account_json
        assert isinstance(secret, SecretStr)
        assert secret.get_secret_value() == _FAKE_SERVICE_ACCOUNT

    def test_credential_dict_carries_what_certificate_needs(self):
        config = _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_FAKE_SERVICE_ACCOUNT)
        assert config.app_config is not None
        credential = config.app_config.firebase.credential_dict()
        assert credential is not None
        for key in ("project_id", "private_key_id", "client_email"):
            assert key in credential

    def test_the_parse_result_cannot_be_mutated_through_the_accessor(self):
        """A caller editing the returned dict must not rewrite the process-wide credential."""
        config = _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_FAKE_SERVICE_ACCOUNT)
        assert config.app_config is not None
        firebase = config.app_config.firebase
        first = firebase.credential_dict()
        assert first is not None
        first["project_id"] = "hijacked"
        second = firebase.credential_dict()
        assert second is not None
        assert second["project_id"] == "test-project"

    def test_the_secret_is_masked_in_the_models_repr(self):
        config = _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_FAKE_SERVICE_ACCOUNT)
        assert config.app_config is not None
        assert "PLACEHOLDER" not in repr(config.app_config.firebase)


class TestFirebaseCredentialMalformed:
    """Present but unparseable is a boot-time failure -- never a first-completion 503."""

    def test_a_non_json_value_fails_the_load(self):
        with pytest.raises(ValidationError):
            _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_MALFORMED_CREDENTIAL)

    def test_the_failure_names_the_field(self):
        with pytest.raises(ValidationError) as excinfo:
            _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_MALFORMED_CREDENTIAL)
        assert "service_account_json" in str(excinfo.value)

    def test_the_failure_does_not_echo_the_offending_value(self):
        """T-37-09. `hide_input_in_errors=True` covers pydantic's own rendering; the hand-written
        parse must not undo it by putting the text in its own message."""
        with pytest.raises(ValidationError) as excinfo:
            _load_against_tracked_yaml(FIREBASE_SERVICE_ACCOUNT_JSON=_MALFORMED_CREDENTIAL)
        rendered = str(excinfo.value)
        assert "WOULD-LEAK" not in rendered
        assert "BEGIN PRIVATE KEY" not in rendered


class TestTheTrackedYamlNeverShadowsTheCredential:
    """Pitfall 7, as a standing test rather than a reviewer's memory.

    `AppConfig(**yaml_data, ...)` puts the YAML in `init_settings`, which pydantic-settings ranks
    above `env_settings`. A `firebase:` block added to the tracked file to "document the shape"
    would therefore make the `.env` value permanently unreachable AND put real key material in a
    file that is committed. `.env.example` is where the shape is documented.
    """

    def test_the_tracked_config_yaml_declares_no_firebase_key(self):
        data = yaml.safe_load(TRACKED_CONFIG.read_text())
        assert "firebase" not in data

    def test_no_tracked_yaml_under_config_carries_service_account_material(self):
        for path in TRACKED_CONFIG.parent.rglob("*.y*ml"):
            text = path.read_text()
            assert "private_key" not in text, f"{path} carries key material"
            assert "service_account" not in text, f"{path} carries key material"

    def test_the_env_example_documents_the_variable(self):
        env_example = TRACKED_CONFIG.parents[1] / ".env.example"
        assert any(line.startswith("FIREBASE_SERVICE_ACCOUNT_JSON=")
                   for line in env_example.read_text().splitlines())
