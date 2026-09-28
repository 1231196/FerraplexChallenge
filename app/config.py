from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ferrapex_api_base_url: str
    ferrapex_api_key: SecretStr
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    database_url: str = "sqlite:///./data/ferrapex.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
