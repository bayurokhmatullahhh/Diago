"""Konfigurasi terpusat. Semua nilai dibaca dari environment variables / file .env."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Digital Operator"
    app_version: str = "0.3.0"
    app_env: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/digital_operator.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    security_audit_allowed_hosts: str = ""

    # Disiapkan untuk fase berikutnya (secret hanya dari environment).
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_default_provider: Literal[
        "openai", "gemini", "anthropic", "openai_compatible"
    ] = "openai"
    llm_fallback_providers: str = "gemini,anthropic,openai_compatible"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_compatible_api_key: str = ""
    openai_compatible_base_url: str = "http://localhost:11434/v1"
    openai_compatible_model: str = ""
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @field_validator("log_level")
    @classmethod
    def _upper_level(cls, v: str) -> str:
        return v.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def security_audit_host_list(self) -> list[str]:
        return [
            host.strip()
            for host in self.security_audit_allowed_hosts.split(",")
            if host.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def llm_fallback_order(self) -> list[str]:
        supported = {"openai", "gemini", "anthropic", "openai_compatible"}
        configured = [
            provider.strip().lower()
            for provider in self.llm_fallback_providers.split(",")
            if provider.strip()
        ]
        return list(dict.fromkeys(
            provider for provider in configured if provider in supported
        ))


@lru_cache
def get_settings() -> Settings:
    return Settings()
