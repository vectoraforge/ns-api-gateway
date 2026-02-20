import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="_"    )


class FileConfig(BaseSettings):
    config_path: str = Field(default="config/config.yaml")
    prompt_path: str = Field(default="config/prompt.txt")
    examples_path: str = Field(default="config/examples.yaml")


class ModelConfig(BaseModel):
    name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1)


class AppConfig(BaseConfig):
    log_level: str = Field(default="INFO")
    pool_size: int = Field(default=5, ge=1)
    model: ModelConfig = Field(default_factory=ModelConfig)


class ContentConfig(BaseModel):
    prompt: str
    examples: dict[str, list[str]]


def load_app_config() -> AppConfig:
    file_config = FileConfig()
    yaml_data = yaml.safe_load(Path(file_config.config_path).read_text())
    return AppConfig(**yaml_data)


def load_content_config() -> ContentConfig:
    file_config = FileConfig()
    prompt = Path(file_config.prompt_path).read_text()
    examples = yaml.safe_load(Path(file_config.examples_path).read_text())
    return ContentConfig(prompt=prompt, examples=examples)
