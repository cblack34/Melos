"""Runtime configuration (env-driven, Pydantic Settings).

Dev default is local Ollama; production switches to OpenRouter purely via
environment (`MELOS_LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`, which
pydantic-ai's provider reads from the environment itself — it never lives in
code or the repo). Model choices and rationale: docs/tech-stack.md.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MELOS_", env_file=".env", extra="ignore"
    )

    llm_provider: Literal["ollama", "openrouter"] = "ollama"
    ollama_base_url: str = "http://localhost:11434/v1"
    # Per-task models; defaults are the researched Ollama dev picks.
    # OpenRouter values (set via env): anthropic/claude-sonnet-5, openai/gpt-5-nano.
    generation_model: str = "qwen3.6:27b"
    meta_model: str = "qwen3.5:9b"
