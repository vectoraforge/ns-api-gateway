import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from nativespeaker.api.config import EnvironmentConfig, ModelConfig, ResilienceConfig

# pytest-dotenv loads .env which sets CONFIG_DIR.
# With env_nested_delimiter="_", pydantic-settings can misinterpret env vars.
# Remove these env vars for MainConfig tests.
_DOTENV_KEYS = ["CONFIG_DIR"]


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
apple:
  bundle_id: com.example.test
  certs_dir: /tmp/certs
  product_id_to_plan:
    com.example.test.gold: gold
quotas:
  free: 10
  silver: 50
  gold: 200
  platinum: 1000
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
