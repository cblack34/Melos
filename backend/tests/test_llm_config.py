import pytest
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel

from melos.config import LlmSettings
from melos.generation.llm import generation_model, meta_model

# _env_file=None keeps developer .env files out of unit tests


def test_defaults_are_local_ollama() -> None:
    config = LlmSettings(_env_file=None)
    assert config.llm_provider == "ollama"
    model = generation_model(config)
    assert isinstance(model, OllamaModel)
    assert model.model_name == "qwen3.6:27b"
    assert meta_model(config).model_name == "qwen3.5:9b"


def test_openrouter_provider_selected_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="anthropic/claude-sonnet-5",
    )
    model = generation_model(config)
    assert isinstance(model, OpenRouterModel)
    assert model.model_name == "anthropic/claude-sonnet-5"


def test_ollama_base_url_is_configurable() -> None:
    config = LlmSettings(
        _env_file=None, ollama_base_url="http://host.docker.internal:11434/v1"
    )
    model = generation_model(config)
    assert isinstance(model, OllamaModel)


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELOS_GENERATION_MODEL", "qwen3.6:35b")
    config = LlmSettings(_env_file=None)
    assert config.generation_model == "qwen3.6:35b"
