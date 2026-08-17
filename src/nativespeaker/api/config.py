import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nativespeaker.api.auth.audit import InvalidJwtAlertPolicy
from nativespeaker.api.models import SubscriptionPlan
from nativespeaker.api.quota.tiers import AccessTierEntry, assert_tier_sizing
from nativespeaker.api.ratelimit.config import GatewayRateLimitsConfig, RateLimitsConfig
from nativespeaker.api.ratelimit.providers import ProviderDampingConfig

LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="_",
                                      env_nested_max_split=1)


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
        """The accepted issuer, derived from the one configured Firebase project rather than
        configured separately: the project, the issuer and the audience the backend pins are one
        value, which is also the value the gateway's JWT filter is configured against."""
        # [impl->req~sessions-gateway-backend-same-project-pin~1]
        return  f"https://securetoken.google.com/{self.project_id}"


class AuthConfig(BaseModel):
    """The shared auth barrier's own configuration."""
    # Actor subject material is stored only as its derived HMAC hash, keyed by a server-side
    # secret and stamped with the version of the key that produced it.
    # [impl->req~shared-auth-events-actor-subject-hash~1]
    subject_hash_key: SecretStr = Field(
        description="HMAC key for derived subject identifiers")
    subject_hash_key_version: int = Field(default=1, ge=1,
                                          description="Version of the subject hash key in use")

    # The threshold for the required operational alert on a sustained rise in
    # `invalid_external_jwt` rejections is deployment configuration: an absolute count of
    # rejections per window, or a fraction of the authenticated traffic in that window.
    # [impl->req~sessions-invalid-external-jwt-metric-alert~1]
    invalid_external_jwt_alert: InvalidJwtAlertPolicy = Field(
        default_factory=lambda: InvalidJwtAlertPolicy(threshold_fraction=0.25),
        description="Sustained-rise alert threshold for invalid external JWT rejections")


class AppleConfig(BaseModel):
    environment: str = Field(default="sandbox", description="Apple environment: sandbox or production")
    bundle_id: str = Field(description="App bundle identifier")
    app_apple_id: int | None = Field(default=None, description="Numeric Apple ID (required for production)")
    enable_online_checks: bool = Field(default=True, description="Enable OCSP certificate checks")
    certs_dir: str = Field(..., description="Directory containing Apple root CA certificates")
    product_id_to_plan: dict[str, SubscriptionPlan] = Field(
        description="Maps Apple product IDs to SubscriptionPlan values")


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
    auth: AuthConfig = Field(default_factory=AuthConfig)
    apple: AppleConfig = Field(default_factory=AppleConfig)
    quotas: dict[SubscriptionPlan, int]

    # The configured access tiers, keyed by the stable tier id grants and subscriptions point
    # at. This is the catalogue startup writes into `core.access_tiers`.
    access_tiers: dict[str, AccessTierEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_tier_sizing(self):
        """A catalogue whose registered tiers are sized below the anonymous tier is rejected at
        configuration load: the service refuses to start rather than running in a state the
        conversion carryover rule does not support."""
        # [impl->req~schema-access-tiers-sizing-invariant-enforced~1]
        # [impl->req~schema-access-tiers-registered-ge-anonymous~1]
        assert_tier_sizing(self.access_tiers)
        return self

    # Every rate limit and admission control is exposed here: no endpoint hard-codes its limit
    # string, storage URI, key function, cost, strategy, enabled state, or failure behaviour.
    # [impl->req~ratelimit-all-limits-in-config-no-hardcoding~1]
    # [impl->req~ratelimit-config-must-include-at-least~1]
    rate_limits: RateLimitsConfig
    gateway_rate_limits: GatewayRateLimitsConfig | None = None

    # The adapters' configured backend-to-provider damping limits: connect and per-attempt
    # timeouts, total budgets, attempt caps, retry budgets and coalesced-result freshness.
    # [impl->req~ratelimit-adapter-damping-limits-configured~1]
    provider_damping: ProviderDampingConfig | None = None

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
    raw_config: dict | None = None

    @model_validator(mode="after")
    def load_config(self):
        config_path = self.config_dir / self.config_filename
        prompt_path = self.config_dir / self.prompt_filename
        examples_path = self.config_dir / self.examples_filename
        yaml_data = yaml.safe_load(config_path.read_text())
        self.raw_config = yaml_data
        self.app_config = AppConfig(**yaml_data,
                                    prompt=prompt_path.read_text(),
                                    examples=yaml.safe_load(examples_path.read_text()))
        return self


class ConfigFileLocation(BaseConfig):
    """Where the application configuration file lives, resolved the same way
    `EnvironmentConfig` resolves it."""
    config_dir: Path = Field(default=Path("config/"))
    config_filename: str = Field(default="config.yaml")

    @property
    def path(self) -> Path:
        return self.config_dir / self.config_filename


def raw_config_file() -> dict:
    """The application configuration file as written, read without validating it.

    Route registration has to know which store integrations a deployment configured before the
    validated configuration exists, so it reads the file directly. A missing or unreadable file
    yields no configured integration, which registers no store route — the fail-closed answer.
    """
    try:
        loaded = yaml.safe_load(ConfigFileLocation().path.read_text())
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
