"""Runtime configuration (env-driven, Pydantic Settings).

Dev default is local Ollama; production switches to OpenRouter purely via
environment (`MELOS_LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`, which
pydantic-ai's provider reads directly from `os.environ` — it never lives in
code, the repo, or this settings class). That real-environment read means a
project `.env` file only reaches the app under `docker compose` (its
`env_file:` directive sets real container env vars); for a direct `uv run`
invocation, export `OPENROUTER_API_KEY` in your shell instead. Model choices
and rationale: docs/tech-stack.md.
"""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/melos/config.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MELOS_", env_file=_REPO_ROOT / ".env", extra="ignore"
    )

    # "ai" generates via the configured LLM; "stub" keeps the deterministic
    # canned generator (frontend dev without a running model).
    generation_backend: Literal["ai", "stub"] = "ai"
    llm_provider: Literal["ollama", "openrouter"] = "ollama"
    ollama_base_url: str = "http://localhost:11434/v1"
    # Per-task models; defaults are the researched Ollama dev picks.
    # OpenRouter values (set via env): anthropic/claude-sonnet-5, openai/gpt-5-nano.
    generation_model: str = "qwen3.6:27b"
    meta_model: str = "qwen3.5:9b"
    # Lyric writing is creative prose, not structured music, and wants the same
    # tier as composition — so blank means "whatever generates the song". That
    # also keeps a new per-task model from invalidating an existing .env.
    lyric_model: str = ""

    @model_validator(mode="after")
    def _check_openrouter_model_ids(self) -> LlmSettings:
        if not self.lyric_model:
            self.lyric_model = self.generation_model
        per_task_fields = ("generation_model", "meta_model", "lyric_model")
        if self.llm_provider == "openrouter":
            for field in per_task_fields:
                value = getattr(self, field)
                if "/" not in value:
                    names = [f"MELOS_{name.upper()}" for name in per_task_fields]
                    env_vars = f"{', '.join(names[:-1])}, and {names[-1]}"
                    raise ValueError(
                        f"{field}={value!r} is not a valid OpenRouter model id"
                        " (expected 'provider/model', e.g."
                        f" 'anthropic/claude-sonnet-5'); set {env_vars} when"
                        " switching MELOS_LLM_PROVIDER=openrouter."
                    )
        return self
