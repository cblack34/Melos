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


def supports_native_output(settings: LlmSettings) -> bool:
    """Whether the configured provider enforces json_schema natively.

    Ollama (local) enforces json_schema via grammar-constrained decoding, so
    ``NativeOutput`` is used there; everywhere else ``ToolOutput`` (the
    pydantic-ai default) is the portable choice (docs/tech-stack.md).
    """
    return settings.llm_provider == "ollama"


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


def generation_model_settings(settings: LlmSettings) -> ModelSettings:
    """Long-output settings for the song-generation call.

    A full song is thousands of output tokens; local models are slow, so the
    timeout is generous. Ollama's OpenAI-compatible endpoint has no per-request
    way to raise the context window — confirmed against Ollama's own docs
    (`docs/api/openai-compatibility.mdx` on ollama/ollama): "The OpenAI API
    does not have a way of setting the context size for a model. If you need
    to change the context size, create a `Modelfile`... `PARAMETER num_ctx
    <context size>`." So truncation risk from context fill remains for long
    songs on Ollama unless the configured model's Modelfile (or
    `OLLAMA_CONTEXT_LENGTH`) already sets a large context (docs/tech-stack.md).
    """
    return ModelSettings(max_tokens=32_000, timeout=900)
