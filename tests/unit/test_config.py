import base64
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from nativespeaker.api.auth.hmac_keyring import HmacKeyring
from nativespeaker.api.config import (
    AppConfig,
    EnvironmentConfig,
    ModelConfig,
    ResilienceConfig,
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

# A locally-generated key, not the committed one, so nothing here breaks when that one is rotated.
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
                      hmac={"active_version": 1, "keys": {1: _TEST_HMAC_KEY}},
                      prompt="p",
                      examples={"en": ["Example 1"]})


class TestHmacConfigSurface:
    """The `hmac:` block is declared on the model and required at load."""

    def test_app_config_declares_hmac(self):
        assert "hmac" in AppConfig.model_fields

    def test_a_config_file_with_no_hmac_block_fails_to_load(self):
        """The process never starts without the key it needs to write, and the abort precedes the lifespan."""
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
        """The committed development key is real material, not a placeholder: it decodes and derives 32 bytes."""
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


class TestNoTrackedYamlCarriesKeyMaterial:
    """The tracked configuration is a public file: a credential pasted into it would be committed."""

    def test_no_tracked_yaml_under_config_carries_service_account_material(self):
        for path in TRACKED_CONFIG.parent.rglob("*.y*ml"):
            text = path.read_text()
            assert "private_key" not in text, f"{path} carries key material"
            assert "service_account" not in text, f"{path} carries key material"
