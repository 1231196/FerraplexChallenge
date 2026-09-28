import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("FERRAPEX_API_BASE_URL", "https://api.test")
    monkeypatch.setenv("FERRAPEX_API_KEY", "k")

    settings = Settings(_env_file=None)

    assert settings.ferrapex_api_key.get_secret_value() == "k"
    assert settings.ollama_model == "qwen3:8b"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.database_url == "sqlite:///./data/ferrapex.db"


def test_missing_api_key_is_a_configuration_error(monkeypatch):
    monkeypatch.delenv("FERRAPEX_API_KEY", raising=False)
    monkeypatch.setenv("FERRAPEX_API_BASE_URL", "https://api.test")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
