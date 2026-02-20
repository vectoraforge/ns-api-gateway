import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import AppConfig, ModelConfig, ContentConfig, load_app_config, load_content_config


class TestModelConfig:
    def test_model_config_defaults(self):
        config = ModelConfig()
        assert config.name == "gpt-4o-mini"
        assert config.temperature == 0.3
        assert config.max_tokens == 1000

    def test_temperature_validation_range(self):
        with pytest.raises(ValidationError):
            ModelConfig(temperature=2.5)

    def test_temperature_negative_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(temperature=-0.1)


class TestAppConfig:
    def test_app_config_from_env_and_yaml(self):
        yaml_content = """
model:
  name: "gpt-4"
  temperature: 0.5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            with patch.dict(os.environ, {"CONFIG_PATH": config_path}, clear=False):
                config = load_app_config()
                assert config.model.name == "gpt-4"
                assert config.model.temperature == 0.5
        finally:
            os.unlink(config_path)


    def test_pool_size_minimum(self):
        yaml_content = """
api_key: "test-key"
pool_size: 0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            with patch.dict(os.environ, {"CONFIG_PATH": config_path}, clear=False):
                with pytest.raises(ValidationError) as exc_info:
                    load_app_config()
                assert "pool_size" in str(exc_info.value)
        finally:
            os.unlink(config_path)


class TestContentConfig:
    def test_load_content_config(self):
        prompt_content = "Analyze {lang} phrase: {phrase}"
        examples_content = """
en:
  - "Example 1"
es:
  - "Ejemplo 1"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as pf, \
             tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as ef:
            pf.write(prompt_content)
            ef.write(examples_content)
            prompt_path = pf.name
            examples_path = ef.name

        try:
            with patch.dict(os.environ, {
                "PROMPT_PATH": prompt_path,
                "EXAMPLES_PATH": examples_path,
            }, clear=False):
                content = load_content_config()
                assert content.prompt == prompt_content
                assert content.examples["en"] == ["Example 1"]
                assert content.examples["es"] == ["Ejemplo 1"]
        finally:
            os.unlink(prompt_path)
            os.unlink(examples_path)


class TestLoadAppConfig:
    def test_load_app_config_missing_file(self):
        with patch.dict(os.environ, {"CONFIG_PATH": "/nonexistent/path.yaml"}, clear=False):
            with pytest.raises(FileNotFoundError):
                load_app_config()
