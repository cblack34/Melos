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
    lyric_model_settings,
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


def test_hosted_budgets_leave_room_for_reasoning_tokens() -> None:
    # A reasoning model spends tokens thinking before it emits anything, and
    # those count against max_tokens: gpt-5-nano burned a 1000-token meta
    # budget entirely on reasoning ("token limit exceeded before any response
    # was generated"). Hosted ceilings must be far larger than the output.
    hosted = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="anthropic/claude-sonnet-5",
        meta_model="openai/gpt-5-nano",
    )
    local = LlmSettings(_env_file=None)
    for hosted_settings, local_settings in (
        (generation_model_settings(hosted), generation_model_settings(local)),
        (meta_model_settings(hosted), meta_model_settings(local)),
        (lyric_model_settings(hosted), lyric_model_settings(local)),
    ):
        hosted_cap = hosted_settings["max_tokens"]
        local_cap = local_settings["max_tokens"]
        assert hosted_cap > local_cap
        assert hosted_cap >= 16_000


def test_local_budgets_match_documented_32k_context_values() -> None:
    # These exact values are a hard *context* constraint per _max_tokens's
    # docstring (prompt + retries + output all share the local 32k window),
    # not just "smaller than hosted" -- pin them so a future edit can't
    # silently eat into that shared budget without a test catching it.
    local = LlmSettings(_env_file=None)
    assert generation_model_settings(local)["max_tokens"] == 16_000
    assert meta_model_settings(local)["max_tokens"] == 2_000
    assert lyric_model_settings(local)["max_tokens"] == 2_000


def test_cloud_tags_get_the_hosted_budget() -> None:
    # Ollama Cloud goes through the local daemon but runs remotely and keeps
    # its default reasoning, so it needs the hosted headroom, not the local cap.
    cloud = LlmSettings(_env_file=None, meta_model="gpt-oss:120b-cloud")
    assert meta_model_settings(cloud)["max_tokens"] >= 16_000


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
