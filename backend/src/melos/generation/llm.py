"""LLM model factory: settings -> a pydantic-ai Model instance.

The single place provider wiring lives (creation separate from use). Callers
receive a `Model` and stay provider-agnostic.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from melos.config import LlmSettings


def is_cloud_model(model_name: str) -> bool:
    """Ollama Cloud tags (``glm-5.2:cloud``, ``gpt-oss:120b-cloud``, ...)."""
    return model_name.lower().endswith((":cloud", "-cloud"))


def is_local_model(model_name: str, settings: LlmSettings) -> bool:
    """Running on this machine's Ollama, rather than a hosted endpoint."""
    return settings.llm_provider == "ollama" and not is_cloud_model(model_name)


def supports_native_output(model_name: str, settings: LlmSettings) -> bool:
    """Whether this model's endpoint enforces json_schema natively.

    Local Ollama enforces json_schema via grammar-constrained decoding, so
    ``NativeOutput`` is used there. Ollama **Cloud** models accept but do not
    enforce the schema, and OpenRouter enforcement varies per endpoint — both
    use ``ToolOutput`` (the pydantic-ai default), the portable choice
    (docs/tech-stack.md).
    """
    return is_local_model(model_name, settings)


def build_model(model_name: str, settings: LlmSettings) -> Model:
    if settings.llm_provider == "ollama":
        return OllamaModel(
            model_name, provider=OllamaProvider(base_url=settings.ollama_base_url)
        )
    # OpenRouter: OPENROUTER_API_KEY is read from the environment by the provider.
    return OpenRouterModel(model_name)


def generation_model(settings: LlmSettings) -> Model:
    return build_model(settings.generation_model, settings)


def meta_model(settings: LlmSettings) -> Model:
    return build_model(settings.meta_model, settings)


# Hosted reasoning models whose thinking mode rejects pydantic-ai's forced
# tool_choice (ToolOutput always forces one). Confirmed live: OpenRouter's
# `deepseek/*` endpoints 400 with "Thinking mode does not support this
# tool_choice"; Claude and GPT-5-family models were tested with the identical
# forced tool_choice and have no such conflict, so this is a per-model
# incompatibility, not a general reasoning+tool_choice rule — don't broaden it
# without the same live confirmation.
_INCOMPATIBLE_REASONING_PREFIXES = ("deepseek/",)


def _no_thinking(model_name: str, settings: LlmSettings) -> ModelSettings:
    """Disable thinking where it would otherwise burn tokens or break the call.

    Local thinking models (qwen3.x) burn thousands of reasoning tokens at
    ~12 t/s before the schema-constrained JSON starts — verified live: it
    blew the 32k context on a song generation and 400'd. Ollama's
    OpenAI-compat endpoint honors ``reasoning_effort: "none"`` (top-level
    ``think: false`` and Qwen's ``/no_think`` are ignored — tested). Cloud
    models keep their default reasoning: they are fast, and gpt-oss doesn't
    accept "none".

    On OpenRouter, DeepSeek's reasoning models reject a forced tool_choice
    outright while thinking — OpenRouter's unified ``reasoning: {"enabled":
    false}`` (verified live) sidesteps that, at the cost of losing DeepSeek's
    reasoning for this call.
    """
    if is_local_model(model_name, settings):
        return ModelSettings(extra_body={"reasoning_effort": "none"})
    if model_name.lower().startswith(_INCOMPATIBLE_REASONING_PREFIXES):
        return ModelSettings(extra_body={"reasoning": {"enabled": False}})
    return ModelSettings()


def _max_tokens(model_name: str, settings: LlmSettings, local: int, hosted: int) -> int:
    """Output budget, which means something different per deployment.

    Locally the budget is a *context* constraint: Ollama's OpenAI-compatible
    endpoint has no per-request way to raise the context window (per Ollama's
    docs, only a Modelfile ``PARAMETER num_ctx`` or ``OLLAMA_CONTEXT_LENGTH``),
    so with the server's 32k auto-tier the prompt, retries, and output all
    share 32k — and thinking is off, so the budget is spent on real output.

    On a hosted endpoint the budget must also cover **reasoning** tokens, which
    a reasoning model spends before emitting anything and which count against
    ``max_tokens``. That is not hypothetical: 1000 was ample for a three-field
    meta response locally, and `gpt-5-nano` on OpenRouter burned all of it
    thinking, failing with "token limit exceeded before any response was
    generated". Hosted ceilings are therefore generous — they are caps, not
    spend, so headroom costs nothing unless it is used.
    """
    return local if is_local_model(model_name, settings) else hosted


def generation_model_settings(settings: LlmSettings) -> ModelSettings:
    """Long-output settings for the song-generation call.

    A song is thousands of output tokens and local models are slow, so the
    timeout is generous either way.
    """
    return ModelSettings(
        max_tokens=_max_tokens(
            settings.generation_model, settings, local=16_000, hosted=64_000
        ),
        timeout=900,
        **_no_thinking(settings.generation_model, settings),
    )


def meta_model_settings(settings: LlmSettings) -> ModelSettings:
    """Three fields of output — the hosted budget is almost all reasoning room."""
    return ModelSettings(
        max_tokens=_max_tokens(
            settings.meta_model, settings, local=2_000, hosted=16_000
        ),
        timeout=300,
        **_no_thinking(settings.meta_model, settings),
    )


def lyric_model(settings: LlmSettings) -> Model:
    return build_model(settings.lyric_model, settings)


def lyric_model_settings(settings: LlmSettings) -> ModelSettings:
    """Lyrics are a page of prose, not a song's worth of notes."""
    return ModelSettings(
        max_tokens=_max_tokens(
            settings.lyric_model, settings, local=2_000, hosted=16_000
        ),
        timeout=300,
        **_no_thinking(settings.lyric_model, settings),
    )
