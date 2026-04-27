from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Kizuna"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://kizuna:kizuna@localhost:5432/kizuna"
    cors_origins: list[str] = ["http://localhost:5173"]
    notes_llm_provider_name: str = "lm-studio"
    notes_llm_base_url: str = "http://127.0.0.1:1234/v1"
    notes_llm_api_key: str = "lm-studio"
    notes_llm_model: str = "qwen3-14b"
    notes_llm_timeout_seconds: float = 20.0
    notes_llm_fallback_provider_name: str = "deepseek"
    notes_llm_fallback_base_url: str | None = None
    notes_llm_fallback_api_key: str = ""
    notes_llm_fallback_model: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="KIZUNA_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
