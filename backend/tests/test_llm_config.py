import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UserError
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel

from melos.config import LlmSettings
from melos.generation.catalog import ModelCatalogEntry, ProviderConfig
from melos.generation.llm import (
    build_model,
    generation_model_settings,
    is_cloud_model,
    lyric_model_settings,
    meta_model_settings,
    supports_native_output,
)

# _env_file=None keeps developer .env files out of unit tests

OLLAMA_PROVIDER = ProviderConfig(kind="ollama")
OPENROUTER_PROVIDER = ProviderConfig(kind="openrouter")


def entry(**overrides: object) -> ModelCatalogEntry:
    defaults: dict[str, object] = {
        "id": "some/model",
        "label": "Some Model",
        "provider": "openrouter",
    }
    return ModelCatalogEntry.model_validate(defaults | overrides)


def test_defaults_are_local_ollama() -> None:
    config = LlmSettings(_env_file=None)
    assert config.llm_provider == "ollama"
    model = build_model(config.generation_model, config)
    assert isinstance(model, OllamaModel)
    assert model.model_name == "qwen3.6:27b"


def test_openrouter_provider_selected_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MELOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MELOS_GENERATION_MODEL", "anthropic/claude-sonnet-5")
    monkeypatch.setenv("MELOS_META_MODEL", "openai/gpt-5-nano")
    monkeypatch.setenv("MELOS_LYRIC_MODEL", "anthropic/claude-sonnet-5")
    config = LlmSettings(_env_file=None)
    model = build_model(config.generation_model, config)
    assert isinstance(model, OpenRouterModel)
    assert model.model_name == "anthropic/claude-sonnet-5"


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
    model = build_model(config.generation_model, config)
    assert isinstance(model, OllamaModel)
    assert model.base_url == "http://host.docker.internal:11434/v1/"


def test_catalog_provider_base_url_overrides_settings() -> None:
    # A catalog entry's own provider config wins, since it may point at a
    # different Ollama host than the session default.
    config = LlmSettings(_env_file=None)
    provider = ProviderConfig(kind="ollama", base_url="http://other-host:11434/v1")
    model = build_model("qwen3.6:27b", config, provider)
    assert isinstance(model, OllamaModel)
    assert model.base_url == "http://other-host:11434/v1/"


def test_catalog_ollama_without_base_url_uses_settings() -> None:
    # Shipped models.yaml omits ollama.base_url so MELOS_OLLAMA_BASE_URL wins
    # (critical under docker compose: host.docker.internal, not localhost).
    config = LlmSettings(
        _env_file=None, ollama_base_url="http://host.docker.internal:11434/v1"
    )
    provider = ProviderConfig(kind="ollama")  # base_url unset
    model = build_model("qwen3.6:27b", config, provider)
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
        build_model(config.generation_model, config)


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


def test_catalog_native_output_defaults_by_provider_kind() -> None:
    config = LlmSettings(_env_file=None)
    assert supports_native_output("x", config, entry(), OPENROUTER_PROVIDER) is False
    assert supports_native_output("x", config, entry(), OLLAMA_PROVIDER) is True


def test_catalog_native_output_explicit_flag_wins_over_provider_default() -> None:
    # An Ollama Cloud catalog entry needs this: same provider kind as local
    # Ollama, but it does not do grammar-constrained decoding.
    config = LlmSettings(_env_file=None)
    cloud_entry = entry(native_output=False)
    assert supports_native_output("x", config, cloud_entry, OLLAMA_PROVIDER) is False


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
        (
            generation_model_settings(hosted.generation_model, hosted),
            generation_model_settings(local.generation_model, local),
        ),
        (
            meta_model_settings(hosted.meta_model, hosted),
            meta_model_settings(local.meta_model, local),
        ),
        (
            lyric_model_settings(hosted.lyric_model, hosted),
            lyric_model_settings(local.lyric_model, local),
        ),
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
    assert (
        generation_model_settings(local.generation_model, local)["max_tokens"] == 16_000
    )
    assert meta_model_settings(local.meta_model, local)["max_tokens"] == 2_000
    assert lyric_model_settings(local.lyric_model, local)["max_tokens"] == 2_000


def test_cloud_tags_get_the_hosted_budget() -> None:
    # Ollama Cloud goes through the local daemon but runs remotely and keeps
    # its default reasoning, so it needs the hosted headroom, not the local cap.
    config = LlmSettings(_env_file=None)
    assert meta_model_settings("gpt-oss:120b-cloud", config)["max_tokens"] >= 16_000


def test_catalog_max_tokens_and_timeout_override_the_heuristic() -> None:
    config = LlmSettings(_env_file=None)
    tight = entry(max_tokens=500, timeout=42)
    settings = generation_model_settings("x", config, tight, OPENROUTER_PROVIDER)
    assert settings["max_tokens"] == 500
    assert settings["timeout"] == 42


def test_reasoning_effort_disabled_for_local_only() -> None:
    local = LlmSettings(_env_file=None)
    cloud = LlmSettings(
        _env_file=None,
        generation_model="gpt-oss:120b-cloud",
        meta_model="gpt-oss:120b-cloud",
    )
    assert generation_model_settings(local.generation_model, local).get(
        "extra_body"
    ) == {"reasoning_effort": "none"}
    assert "extra_body" not in generation_model_settings(cloud.generation_model, cloud)
    assert "extra_body" not in meta_model_settings(cloud.meta_model, cloud)


def test_deepseek_on_openrouter_disables_reasoning_without_a_catalog_entry() -> None:
    # DeepSeek's thinking mode 400s on pydantic-ai's forced tool_choice
    # ("Thinking mode does not support this tool_choice") — verified live.
    # OpenRouter's reasoning:{"enabled": false} sidesteps it. This is the
    # name-prefix fallback for a deepseek/* id used without a catalog entry.
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="deepseek/deepseek-v4-flash",
        meta_model="openai/gpt-5-nano",
    )
    settings = generation_model_settings(
        "deepseek/deepseek-v4-flash", config, provider=OPENROUTER_PROVIDER
    )
    assert settings["extra_body"] == {"reasoning": {"enabled": False}}


def test_non_deepseek_openrouter_models_keep_default_reasoning() -> None:
    # Claude and GPT-5-family models were tested with the same forced
    # tool_choice and have no such conflict — this is a per-model fix, not a
    # blanket reasoning-off policy that would cost quality elsewhere.
    config = LlmSettings(
        _env_file=None,
        llm_provider="openrouter",
        generation_model="anthropic/claude-sonnet-5",
        meta_model="openai/gpt-5-nano",
    )
    assert "extra_body" not in generation_model_settings(
        "anthropic/claude-sonnet-5", config, provider=OPENROUTER_PROVIDER
    )


def test_catalog_reasoning_none_disables_reasoning_on_openrouter() -> None:
    config = LlmSettings(_env_file=None)
    settings = generation_model_settings(
        "some/model", config, entry(reasoning="none"), OPENROUTER_PROVIDER
    )
    assert settings["extra_body"] == {"reasoning": {"enabled": False}}


def test_catalog_reasoning_default_leaves_reasoning_on_for_openrouter() -> None:
    config = LlmSettings(_env_file=None)
    settings = generation_model_settings(
        "some/model", config, entry(reasoning="default"), OPENROUTER_PROVIDER
    )
    assert "extra_body" not in settings


def test_catalog_local_entry_always_disables_reasoning_regardless_of_field() -> None:
    # Local thinking has no offsetting quality benefit and a real cost (it
    # blew a 32k context in the past) — a catalogued local model can't opt
    # back in by leaving `reasoning` at its "default" value.
    config = LlmSettings(_env_file=None)
    settings = generation_model_settings(
        "some-local-model", config, entry(reasoning="default"), OLLAMA_PROVIDER
    )
    assert settings["extra_body"] == {"reasoning_effort": "none"}
