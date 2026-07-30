import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UserError
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel

from melos.config import LlmSettings
from melos.generation.llm import (
    generation_model,
    generation_model_settings,
    is_cloud_model,
    lyric_model,
    meta_model,
    meta_model_settings,
    supports_native_output,
)

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
    monkeypatch.setenv("MELOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MELOS_GENERATION_MODEL", "anthropic/claude-sonnet-5")
    monkeypatch.setenv("MELOS_META_MODEL", "openai/gpt-5-nano")
    monkeypatch.setenv("MELOS_LYRIC_MODEL", "anthropic/claude-sonnet-5")
    config = LlmSettings(_env_file=None)
    model = generation_model(config)
    assert isinstance(model, OpenRouterModel)
    assert model.model_name == "anthropic/claude-sonnet-5"


def test_per_task_models_selected_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="anthropic/claude-sonnet-5",
        meta_model="openai/gpt-5-nano",
        lyric_model="anthropic/claude-opus-5",
    )
    assert meta_model(config).model_name == "openai/gpt-5-nano"
    lyric = lyric_model(config)
    assert isinstance(lyric, OpenRouterModel)
    assert lyric.model_name == "anthropic/claude-opus-5"


def test_lyric_model_defaults_to_the_generation_model() -> None:
    # Blank means "same model that composes the song", so adding this per-task
    # model does not invalidate a .env written before it existed.
    config = LlmSettings(_env_file=None, generation_model="qwen3.6:35b")
    assert config.lyric_model == "qwen3.6:35b"


def test_lyric_model_default_follows_an_openrouter_generation_model() -> None:
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="anthropic/claude-sonnet-5",
        meta_model="openai/gpt-5-nano",
    )
    assert config.lyric_model == "anthropic/claude-sonnet-5"


def test_openrouter_rejects_a_bare_lyric_model_id() -> None:
    # Every per-task model must be a provider/model id on OpenRouter, not just
    # the two that existed before lyric writing.
    with pytest.raises(ValidationError, match="lyric_model"):
        LlmSettings(
            _env_file=None,
            llm_provider="openrouter",
            generation_model="anthropic/claude-sonnet-5",
            meta_model="openai/gpt-5-nano",
            lyric_model="qwen3.6:27b",
        )


def test_openrouter_bare_model_error_names_all_three_env_vars() -> None:
    # The remediation hint must name every per-task env var, including the
    # one that actually failed -- a `match="lyric_model"` assertion alone
    # would also match the unrelated "lyric_model=..." prefix.
    with pytest.raises(
        ValidationError,
        match="MELOS_GENERATION_MODEL, MELOS_META_MODEL, and MELOS_LYRIC_MODEL",
    ):
        LlmSettings(
            _env_file=None,
            llm_provider="openrouter",
            generation_model="anthropic/claude-sonnet-5",
            meta_model="openai/gpt-5-nano",
            lyric_model="qwen3.6:27b",
        )


def test_ollama_base_url_is_configurable() -> None:
    config = LlmSettings(
        _env_file=None, ollama_base_url="http://host.docker.internal:11434/v1"
    )
    model = generation_model(config)
    assert isinstance(model, OllamaModel)
    assert model.base_url == "http://host.docker.internal:11434/v1/"


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MELOS_GENERATION_MODEL", "qwen3.6:35b")
    config = LlmSettings(_env_file=None)
    assert config.generation_model == "qwen3.6:35b"


def test_openrouter_without_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="openai/gpt-5-nano",
        meta_model="openai/gpt-5-nano",
        lyric_model="openai/gpt-5-nano",
    )
    with pytest.raises(UserError):
        generation_model(config)


def test_cloud_tags_detected() -> None:
    assert is_cloud_model("gpt-oss:120b-cloud")
    assert is_cloud_model("glm-5.2:cloud")
    assert not is_cloud_model("qwen3.6:27b")


def test_cloud_tags_detected_case_insensitively() -> None:
    assert is_cloud_model("gpt-oss:120b-CLOUD")
    assert is_cloud_model("GPT-OSS:120b-cloud")


def test_native_output_disabled_for_cloud_tags() -> None:
    config = LlmSettings(_env_file=None, generation_model="gpt-oss:120b-cloud")
    assert not supports_native_output(config.generation_model, config)


def test_native_output_enabled_for_local_ollama() -> None:
    config = LlmSettings(_env_file=None)
    assert supports_native_output(config.generation_model, config)


def test_reasoning_effort_disabled_for_local_only() -> None:
    local = LlmSettings(_env_file=None)
    cloud = LlmSettings(
        _env_file=None,
        generation_model="gpt-oss:120b-cloud",
        meta_model="gpt-oss:120b-cloud",
    )
    assert generation_model_settings(local).get("extra_body") == {
        "reasoning_effort": "none"
    }
    assert "extra_body" not in generation_model_settings(cloud)
    assert "extra_body" not in meta_model_settings(cloud)
