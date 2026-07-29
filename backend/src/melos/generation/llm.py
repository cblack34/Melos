"""LLM model factory: settings -> a pydantic-ai Model instance.

The single place provider wiring lives (creation separate from use). Callers
receive a `Model` and stay provider-agnostic.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.ollama import OllamaProvider

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
