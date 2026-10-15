from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"

    service_api_key: SecretStr | None = None

    express_api_base_url: str = "http://127.0.0.1:3000"
    express_service_token: SecretStr | None = None
    express_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    moderation_policy_version: str = "2026-10-15"
    moderation_flag_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    moderation_block_confidence_threshold: float = Field(default=0.95, ge=0, le=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_moderation_thresholds(self) -> "Settings":
        if self.moderation_block_confidence_threshold < self.moderation_flag_confidence_threshold:
            raise ValueError(
                "MODERATION_BLOCK_CONFIDENCE_THRESHOLD must be greater than or equal "
                "to MODERATION_FLAG_CONFIDENCE_THRESHOLD"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
