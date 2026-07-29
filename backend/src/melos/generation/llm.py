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
    timeout is generous. For Ollama the context window must be raised
    explicitly — truncation there comes from context fill, not an output cap
    (docs/tech-stack.md).
    """
    model_settings = ModelSettings(max_tokens=32_000, timeout=900)
    if settings.llm_provider == "ollama":
        model_settings["extra_body"] = {"context_length": 32_768}
    return model_settings
