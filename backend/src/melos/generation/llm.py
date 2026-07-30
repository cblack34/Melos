"""LLM model factory: a model id (+ optional catalog entry) -> a pydantic-ai Model.

The single place provider wiring lives (creation separate from use). Callers
receive a `Model` and stay provider-agnostic. A model id present in
``models.yaml`` (see ``catalog.py``) is built from its catalog entry; anything
else falls back to the code-based heuristics below, keyed on
``settings.llm_provider``. Every function here takes the model id it is
building *for* explicitly — never implicitly reads it off ``settings`` — so a
per-request override can never be silently ignored.
"""

from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from melos.config import LlmSettings
from melos.generation.catalog import (
    ModelCatalog,
    ModelCatalogEntry,
    ProviderConfig,
    Task,
)


def is_cloud_model(model_name: str) -> bool:
    """Ollama Cloud tags (``glm-5.2:cloud``, ``gpt-oss:120b-cloud``, ...)."""
    return model_name.lower().endswith((":cloud", "-cloud"))


def is_local_model(model_name: str, settings: LlmSettings) -> bool:
    """Running on this machine's Ollama, rather than a hosted endpoint."""
    return settings.llm_provider == "ollama" and not is_cloud_model(model_name)


def catalog_lookup(
    task: Task, model_name: str, catalog: ModelCatalog
) -> tuple[ModelCatalogEntry, ProviderConfig] | tuple[None, None]:
    entry = catalog.find(task, model_name)
    if entry is None:
        return None, None
    return entry, catalog.provider_for(entry)


def supports_native_output(
    model_name: str,
    settings: LlmSettings,
    entry: ModelCatalogEntry | None = None,
    provider: ProviderConfig | None = None,
) -> bool:
    """Whether this model's endpoint enforces json_schema natively.

    Local Ollama enforces json_schema via grammar-constrained decoding, so
    ``NativeOutput`` is used there. Ollama **Cloud** models accept but do not
    enforce the schema, and OpenRouter enforcement varies per endpoint — both
    use ``ToolOutput`` (the pydantic-ai default), the portable choice
    (docs/tech-stack.md).
    """
    if entry is not None and entry.native_output is not None:
        return entry.native_output
    if provider is not None:
        # A catalogued Ollama Cloud entry must set native_output: false itself
        # (see catalog.py) — this default is only correct for local Ollama.
        return provider.kind == "ollama"
    return is_local_model(model_name, settings)


def build_model(
    model_name: str,
    settings: LlmSettings,
    provider: ProviderConfig | None = None,
) -> Model:
    kind = provider.kind if provider is not None else settings.llm_provider
    if kind == "ollama":
        # Catalog base_url is an optional override of MELOS_OLLAMA_BASE_URL —
        # only set it in YAML when intentionally pointing at a non-default
        # host. Leaving it unset (the shipped default) preserves Docker
        # compose's host.docker.internal and any other env default.
        catalog_base_url = provider.base_url if provider is not None else None
        base_url = catalog_base_url or settings.ollama_base_url
        return OllamaModel(model_name, provider=OllamaProvider(base_url=base_url))
    # OpenRouter: OPENROUTER_API_KEY is read from the environment by the provider.
    return OpenRouterModel(model_name)


# DeepSeek's thinking mode rejects pydantic-ai's forced tool_choice outright
# (OpenRouter 400s: "Thinking mode does not support this tool_choice" —
# verified live; Claude and GPT-5-family models were tested with the
# identical forced tool_choice and have no such conflict, so this is a
# DeepSeek-specific incompatibility). This is the fallback for a `deepseek/*`
# id used *without* a matching models.yaml entry; a catalogued entry expresses
# the same fix as data (`reasoning: none`) instead.
_INCOMPATIBLE_REASONING_PREFIXES = ("deepseek/",)


def _no_thinking(
    model_name: str,
    settings: LlmSettings,
    entry: ModelCatalogEntry | None = None,
    provider: ProviderConfig | None = None,
) -> ModelSettings:
    """Disable thinking where it would otherwise burn tokens or break the call.

    Local Ollama thinking models (qwen3.x) burn thousands of reasoning tokens
    at ~12 t/s before the schema-constrained JSON starts — verified live: it
    blew the 32k context on a song generation and 400'd. Ollama's OpenAI-compat
    endpoint honors ``reasoning_effort: "none"`` (top-level ``think: false`` and
    Qwen's ``/no_think`` are ignored — tested). Because this is a strict
    downside with no offsetting quality benefit, **local Ollama always
    disables it** — the catalog's ``reasoning`` field only has a choice to
    make for hosted providers, where reasoning can genuinely help quality and
    the default is to leave it on.

    OpenRouter's unified ``reasoning: {"enabled": false}`` is the hosted
    mechanism (distinct from Ollama's param), applied when the catalog entry
    says ``reasoning: none``, or via the DeepSeek-prefix fallback above.
    """
    kind = provider.kind if provider is not None else None
    if kind == "ollama" or (kind is None and is_local_model(model_name, settings)):
        return ModelSettings(extra_body={"reasoning_effort": "none"})
    wants_off = (entry is not None and entry.reasoning == "none") or (
        entry is None
        and model_name.lower().startswith(_INCOMPATIBLE_REASONING_PREFIXES)
    )
    if wants_off:
        return ModelSettings(extra_body={"reasoning": {"enabled": False}})
    return ModelSettings()


def _max_tokens(
    model_name: str,
    settings: LlmSettings,
    local: int,
    hosted: int,
    entry: ModelCatalogEntry | None = None,
    provider: ProviderConfig | None = None,
) -> int:
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

    A catalog entry's explicit ``max_tokens`` always wins over this heuristic.
    """
    if entry is not None and entry.max_tokens is not None:
        return entry.max_tokens
    kind = provider.kind if provider is not None else None
    is_local = (
        kind == "ollama" if kind is not None else is_local_model(model_name, settings)
    )
    return local if is_local else hosted


def _timeout(default: float, entry: ModelCatalogEntry | None = None) -> float:
    return entry.timeout if entry is not None and entry.timeout is not None else default


def generation_model_settings(
    model_name: str,
    settings: LlmSettings,
    entry: ModelCatalogEntry | None = None,
    provider: ProviderConfig | None = None,
) -> ModelSettings:
    """Long-output settings for the song-generation call.

    A song is thousands of output tokens and local models are slow, so the
    timeout is generous either way.
    """
    return ModelSettings(
        max_tokens=_max_tokens(
            model_name,
            settings,
            local=16_000,
            hosted=64_000,
            entry=entry,
            provider=provider,
        ),
        timeout=_timeout(900, entry),
        **_no_thinking(model_name, settings, entry, provider),
    )


def meta_model_settings(
    model_name: str,
    settings: LlmSettings,
    entry: ModelCatalogEntry | None = None,
    provider: ProviderConfig | None = None,
) -> ModelSettings:
    """Three fields of output — the hosted budget is almost all reasoning room."""
    return ModelSettings(
        max_tokens=_max_tokens(
            model_name,
            settings,
            local=2_000,
            hosted=16_000,
            entry=entry,
            provider=provider,
        ),
        timeout=_timeout(300, entry),
        **_no_thinking(model_name, settings, entry, provider),
    )


def lyric_model_settings(model_name: str, settings: LlmSettings) -> ModelSettings:
    """Lyrics are a page of prose, not a song's worth of notes."""
    return ModelSettings(
        max_tokens=_max_tokens(model_name, settings, local=2_000, hosted=16_000),
        timeout=300,
        **_no_thinking(model_name, settings),
    )
