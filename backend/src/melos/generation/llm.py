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


def supports_native_output(model_name: str, settings: LlmSettings) -> bool:
    """Whether this model's endpoint enforces json_schema natively.

    Local Ollama enforces json_schema via grammar-constrained decoding, so
    ``NativeOutput`` is used there. Ollama **Cloud** models accept but do not
    enforce the schema, and OpenRouter enforcement varies per endpoint — both
    use ``ToolOutput`` (the pydantic-ai default), the portable choice
    (docs/tech-stack.md).
    """
    return settings.llm_provider == "ollama" and not is_cloud_model(model_name)


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


def _no_thinking(model_name: str, settings: LlmSettings) -> ModelSettings:
    """Disable thinking on local Ollama models.

    Local thinking models (qwen3.x) burn thousands of reasoning tokens at
    ~12 t/s before the schema-constrained JSON starts — verified live: it
    blew the 32k context on a song generation and 400'd. Ollama's
    OpenAI-compat endpoint honors ``reasoning_effort: "none"`` (top-level
    ``think: false`` and Qwen's ``/no_think`` are ignored — tested). Cloud
    models keep their default reasoning: they are fast, and gpt-oss doesn't
    accept "none".
    """
    if settings.llm_provider == "ollama" and not is_cloud_model(model_name):
        return ModelSettings(extra_body={"reasoning_effort": "none"})
    return ModelSettings()


def generation_model_settings(settings: LlmSettings) -> ModelSettings:
    """Long-output settings for the song-generation call.

    A full song is thousands of output tokens; local models are slow, so the
    timeout is generous. max_tokens must leave context headroom: Ollama's
    OpenAI-compatible endpoint has no per-request way to raise the context
    window (per Ollama's own docs: use a Modelfile ``PARAMETER num_ctx`` or
    ``OLLAMA_CONTEXT_LENGTH``), so with the server's 32k auto-tier the
    prompt + retries + output all share 32k (docs/tech-stack.md).
    """
    return ModelSettings(
        max_tokens=16_000,
        timeout=900,
        **_no_thinking(settings.generation_model, settings),
    )


def meta_model_settings(settings: LlmSettings) -> ModelSettings:
    return ModelSettings(
        max_tokens=1_000, timeout=120, **_no_thinking(settings.meta_model, settings)
    )


def lyric_model(settings: LlmSettings) -> Model:
    return build_model(settings.lyric_model, settings)


def lyric_model_settings(settings: LlmSettings) -> ModelSettings:
    """Lyrics are a page of prose, not a song's worth of notes."""
    return ModelSettings(
        max_tokens=2_000, timeout=180, **_no_thinking(settings.lyric_model, settings)
    )
