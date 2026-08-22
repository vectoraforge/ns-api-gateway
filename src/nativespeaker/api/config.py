import json
import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nativespeaker.api.auth.keys import HmacConfig

LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})


class BaseConfig(BaseSettings):
    # `hide_input_in_errors` is T-35-08-02: pydantic renders the pre-coercion input in
    # `input_value=...`, and a nested model's error is rendered under the *outer* model's config,
    # so `HmacConfig` setting the flag on itself is not enough -- an invalid `hmac:` block reaching
    # validation through `AppConfig` would print the raw base64 key. The field path and the message
    # still identify what was wrong; only the offending value is withheld. Every secret this
    # project loads (`db.password`, the HMAC keys) travels through this tree.
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


class FirebaseConfig(BaseModel):
    """The Firebase service-account credential, and nothing else (37 D-08).

    Populated from the gitignored `.env` and nowhere else. `BaseConfig` sets
    `env_nested_delimiter="_"` with `env_nested_max_split=1`, so
    `FIREBASE_SERVICE_ACCOUNT_JSON` reaches `firebase.service_account_json` by the same rule that
    carries `JWT_PROJECT_ID` to `jwt.project_id`.

    **Never add a `firebase:` block to `config/config.yaml`.** That file is tracked in git, and it
    is authoritative for anything it declares -- `AppConfig(**yaml_data, ...)` puts it in
    `init_settings`, which pydantic-settings ranks above `env_settings`. A block added there to
    document the shape would make the `.env` value permanently unreachable *and* commit real key
    material. `.env.example` is where the shape is documented.

    Two states, decided here rather than left to a raise site:

    * **Absent** is supported. The service boots, `service_account_json` is `None`, and
      `credential_dict()` returns `None`; prepare mode, the mode-signal partition, the classifier
      and every substituted-adapter test run unaffected, while a real completion fails closed at
      the adapter's selection arm as `verification_temporarily_unavailable` (503). Refusing to
      boot without a credential would block all of that for a credential most paths never touch.
    * **Present but unparseable** fails at configuration load, and the service does not start.
      The parse happens once, here, so a malformed credential is a boot-time failure rather than a
      surprise 503 on the first completion long after deploy.

    Extra keys are ignored deliberately: `.env` already carries `FIREBASE_API_KEY` and
    `FIREBASE_TEST_*` for the e2e sign-in fixture, and the nesting rule routes all of them here.
    Rejecting them would take the e2e suite down.
    """
    service_account_json: SecretStr | None = Field(
        default=None,
        description="The whole service-account JSON on one line, from the gitignored .env")

    _credential: dict | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _parse_credential(self):
        if self.service_account_json is None:
            return self
        try:
            parsed = json.loads(self.service_account_json.get_secret_value())
        except json.JSONDecodeError:
            # `from None` drops the JSONDecodeError, whose `doc` attribute holds the credential
            # verbatim. The message names the field and nothing else; `BaseConfig` sets
            # `hide_input_in_errors=True` for pydantic's own rendering, and this hand-written path
            # must not undo it (T-37-09).
            raise ValueError("service_account_json is not valid JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("service_account_json is not a JSON object")
        self._credential = parsed
        return self

    def credential_dict(self) -> dict | None:
        """The parsed credential for `credentials.Certificate`, or `None` when unconfigured.

        Total over both supported states on purpose: the adapter's selection arm branches on the
        `None` rather than catching an exception. A fresh copy each call, so a caller editing the
        result cannot rewrite the process-wide credential.
        """
        return None if self._credential is None else dict(self._credential)


# `AppleConfig` is deleted with the subscription model layer (D-16). It mapped Apple product ids
# onto `core.subscription_plan`, an enum the v2.0 schema dropped, and pointed the receipt verifier
# at its certificate directory -- and the lifespan no longer builds that verifier. Phase 43 writes
# `/webhooks/app-store` and whatever configuration it needs from scratch.


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
    # Defaulted, not required: the credential is absent today and every non-completion path in
    # phase 37 must stay runnable without it. See `FirebaseConfig` for the absent/malformed split
    # and for why no `firebase:` block may ever appear in `config/config.yaml`.
    firebase: FirebaseConfig = Field(default_factory=FirebaseConfig)
    # Required, with no default: D-22 fails closed on the active key, so a deployment with no
    # `hmac:` block never starts rather than starting and failing every audit insert. Unlike the
    # blocks above it takes no `default_factory` -- there is no safe key to default to.
    hmac: HmacConfig
    # No `quotas` mapping: v2.0 resolves a caller's allowance from `core.access_tiers.monthly_credits`
    # through the grant Phase 36 wires, not from a per-plan table in this file.

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
