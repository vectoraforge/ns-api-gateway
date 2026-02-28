import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import MainConfig, ModelConfig


def _write_temp(content: str, suffix: str) -> str:
    handle, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(handle, "w") as file:
        file.write(content)
    return path


def test_model_config_defaults():
    config = ModelConfig()
    assert config.name == "gpt-4o-mini"
    assert config.temperature == 0.3
    assert config.max_tokens == 1000
    assert config.resilience.queue_size == 25
    assert config.resilience.timeout_seconds == 30.0


def test_model_config_invalid_temperature():
    with pytest.raises(ValidationError):
        ModelConfig(temperature=2.5)


def test_main_config_loads_yaml_and_content():
    yaml_content = """
log_level: INFO
model:
  name: "gpt-4"
  temperature: 0.5
"""
    prompt_content = "Analyze {lang} phrase: {phrase}"
    examples_content = """
en:
  - "Example 1"
"""

    config_path = _write_temp(yaml_content, ".yaml")
    prompt_path = _write_temp(prompt_content, ".txt")
    examples_path = _write_temp(examples_content, ".yaml")

    try:
        with patch.dict(
            os.environ,
            {
                "CONFIG_DIR": config_path,
                "PROMPT_PATH": prompt_path,
                "EXAMPLES_PATH": examples_path,
            },
            clear=False,
        ):
            config = MainConfig()
            assert config.app.model.name == "gpt-4"
            assert config.app.model.temperature == 0.5
            assert config.app.prompt == prompt_content
            assert config.app.examples["en"] == ["Example 1"]
    finally:
        os.unlink(config_path)
        os.unlink(prompt_path)
        os.unlink(examples_path)


def test_main_config_missing_file():
    with patch.dict(os.environ, {"CONFIG_DIR": "/nonexistent/path.yaml"}, clear=False):
        with pytest.raises(FileNotFoundError):
            MainConfig()
