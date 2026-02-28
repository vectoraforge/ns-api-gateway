import yaml
from pathlib import Path
from enum import StrEnum
import logging

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="_")


class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    user: str = Field(default="postgres")
    password: SecretStr = Field(default=SecretStr("postgres"))
    name: str = Field(default="nativespeaker")
    pool_size: int = Field(default=5, ge=1)

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.name}"


class ModelConfig(BaseModel):
    name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1)
    pool_size: int = Field(default=5, ge=1)
    queue_size: int = Field(default=25, ge=1)
    queue_retry_after_seconds: int = Field(default=2, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retry_max_attempts: int = Field(default=3, ge=1)
    retry_backoff_base_seconds: float = Field(default=0.5, ge=0)
    retry_backoff_max_seconds: float = Field(default=4.0, ge=0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: int = Field(default=60, ge=1)


class AppConfig(BaseConfig):
    log_level: LogLevel = Field(default=LogLevel.INFO)  # type: ignore

    model: ModelConfig = Field(default_factory=ModelConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    history_max_human_messages: int = Field(default=50, ge=1)
    history_max_assistant_messages: int = Field(default=50, ge=1)
    message_max_chars: int = Field(default=4096, ge=1)
    messages_max_page_size: int = Field(default=100, ge=1)
    readiness_cache_seconds: int = Field(default=60, ge=1)

    prompt: str | None = None
    examples: dict[str, list[str]] = {}


class MainConfig(BaseConfig):
    config_dir: Path = Field(default="config/config.yaml")
    prompt_path: Path = Field(default="config/prompt.txt")
    examples_path: Path = Field(default="config/examples.yaml")

    app: AppConfig | None = None

    @model_validator(mode='after')
    def load_config(self):
        yaml_data = yaml.safe_load(self.config_dir.read_text())
        app_config = AppConfig(_env_prefix='__NONE__', **yaml_data)
        app_config.prompt = self.prompt_path.read_text()
        app_config.examples = yaml.safe_load(self.examples_path.read_text())
        self.app = app_config
        return self
