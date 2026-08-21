import base64
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.config import AppConfig, EnvironmentConfig, ModelConfig, ResilienceConfig

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
