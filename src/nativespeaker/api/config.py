import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})


class StoreEnvironment(StrEnum):
    """The two App Store environments whose notifications Apple signs."""
    sandbox = "sandbox"
    production = "production"


class BaseConfig(BaseSettings):
    # `hide_input_in_errors` belongs here, not on the nested tables: a nested error renders under the outer config.
    model_config = SettingsConfigDict(env_nested_delimiter="_",
                                      env_nested_max_split=1,
                                      hide_input_in_errors=True)


class DatabaseConfig(BaseModel):
    host: str = Field(description="Database server hostname")
    port: int = Field(description="Database server port")
    user: str = Field(description="Database user")
    password: SecretStr = Field(description="Database password")
    name: str = Field(description="Database name")
    pool_size: int = Field(default=5, ge=1, description="Connection pool size")

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
    project_id: str = Field(description="GCP project ID")
    api_key: str = Field(description="GCP API key")
    jwks_url: str = Field(default="https://www.googleapis.com/service_accounts/v1/jwk/"
                                  "securetoken@system.gserviceaccount.com")
    leeway_seconds: int = Field(default=30, ge=0, description="Expiration timeout")
    jwks_cache_ttl_seconds: float = Field(default=3600.0, gt=0, description="JWKS cache TTL")

    @property
    def issuer(self) -> str:
        return  f"https://securetoken.google.com/{self.project_id}"


class DeviceCheckConfig(BaseModel):
    # All three optional, unlike JWTConfig: an absent credential lets boot proceed and the route fail closed.
    key_id: str | None = Field(default=None, description="Apple DeviceCheck key ID")
    team_id: str | None = Field(default=None, description="Apple developer team ID")
    private_key_path: str | None = Field(default=None, description="Path to the ES256 private key PEM")


class AppStoreConfig(BaseModel):
    """The App Store Server Notifications settings the JWS verifier is built from."""
    # All five optional, like DeviceCheckConfig: an absent value lets boot proceed and the route fail closed.
    bundle_id: str | None = Field(default=None, description="The app's bundle ID")
    app_apple_id: int | None = Field(default=None, description="The app's App Store ID, required in production")
    # No default: a typed member, never free text, because two library values skip signature verification.
    environment: StoreEnvironment | None = Field(default=None, description="The store environment")
    root_certificate_path: str | None = Field(default="config/certs/AppleRootCA-G3.cer",
                                              description="Path to the Apple root CA in DER form")
    products: dict[str, str] = Field(default_factory=dict,
                                     description="Store product ID to core.access_tiers.id")

    # Degrading beats raising: absence is already the fail-closed path this route answers 503 from,
    # and `lifespan` logs the same app_store_configuration_absent warning for it either way.
    @field_validator("app_apple_id", mode="before")
    @classmethod
    def _numeric_or_absent(cls, value):
        """Keep an int or an all-digit string, and read anything else as absent."""
        return value if isinstance(value, int) or (isinstance(value, str)
                                                   and value.isdigit()) else None

    @field_validator("environment", mode="before")
    @classmethod
    def _named_or_absent(cls, value):
        """Keep one of the two named environments, and read anything else as absent."""
        # Membership by value, never a case transform: the library's two verification-skipping
        # environments have to stay unreachable, which is why this field is typed at all.
        return value if value in tuple(StoreEnvironment) else None


class ModelConfig(BaseModel):
    name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1)


class AppConfig(BaseConfig):
    log_level: LogLevel = Field(default=LogLevel.INFO)  # type: ignore
    json_log_path: str | None = Field(default=None, description="Path for JSON log file output")

    model: ModelConfig = Field(default_factory=ModelConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    devicecheck: DeviceCheckConfig = Field(default_factory=DeviceCheckConfig)
    app_store: AppStoreConfig = Field(default_factory=AppStoreConfig)
    chats_limit: int = Field(default=50, ge=1)
    messages_limit: int = Field(default=50, ge=1)

    prompt: str
    examples: dict[str, list[str]]


class EnvironmentConfig(BaseConfig):
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
