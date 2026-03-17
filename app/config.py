import logging
from enum import StrEnum
from pathlib import Path

import yaml
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
        return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
                f"@{self.host}:{self.port}/{self.name}")


class ResilienceConfig(BaseModel):
    pool_size: int = Field(default=5, ge=1)
    queue_size: int = Field(default=25, ge=1)
    queue_retry_after_seconds: int = Field(default=2, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retry_max_attempts: int = Field(default=3, ge=1)
    retry_backoff_base_seconds: float = Field(default=0.5, ge=0)
    retry_backoff_max_seconds: float = Field(default=4.0, ge=0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: int = Field(default=60, ge=1)


class JWTConfig(BaseModel):
    project_id: str
    jwks_url: str = Field(default="https://www.googleapis.com/service_accounts/v1/jwk/"
                                  "securetoken@system.gserviceaccount.com")
    leeway_seconds: int = Field(default=30, ge=0)
    jwks_cache_ttl_seconds: float = Field(default=3600.0, gt=0)

    # Derived from project_id — not in YAML
    audience: str = ""
    issuer: str = ""

    @model_validator(mode="after")
    def derive_audience_and_issuer(self) -> "JWTConfig":
        if not self.audience:
            self.audience = self.project_id
        if not self.issuer:
            self.issuer = f"https://securetoken.google.com/{self.project_id}"
        return self


class ModelConfig(BaseModel):
    name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)


class AppConfig(BaseConfig):
    log_level: LogLevel = Field(default=LogLevel.INFO)  # type: ignore

    model: ModelConfig = Field(default_factory=ModelConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig
    history_max_messages: int = Field(default=50, ge=1)
    messages_max_page_size: int = Field(default=100, ge=1)
    chat_list_limit: int = Field(default=50, ge=1)

    prompt: str
    examples: dict[str, list[str]]


class MainConfig(BaseConfig):
    config_dir: Path = Field(default=Path("config/"))
    config_filename: str = Field(default="config.yaml")
    prompt_filename: str = Field(default="prompt.txt")
    examples_filename: str = Field(default="examples.yaml")

    app_config: AppConfig | None = None

    @model_validator(mode="after")
    def load_config(self):
        config_path = self.config_dir / self.config_filename
        prompt_path = self.config_dir / self.prompt_filename
        examples_path = self.config_dir / self.examples_filename
        yaml_data = yaml.safe_load(config_path.read_text())
        self.app_config = AppConfig(**yaml_data,
                                    prompt=prompt_path.read_text(),
                                    examples=yaml.safe_load(examples_path.read_text()))
        return self
