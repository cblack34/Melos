"""Model catalog: a YAML-defined menu of selectable provider/model combinations.

Lets a new model — or a per-model quirk like disabled reasoning — be added by
editing ``models.yaml``, not by writing code. A model absent from the catalog
still works through the code-based defaults in ``llm.py``; the catalog is
additive; it is not the only path a model id can take.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# catalog.py -> generation -> melos -> src -> backend (repo-root-relative
# models.yaml would not survive Docker: the build context is ./backend, so
# the file has to live inside it to be COPYed into the image).
_CATALOG_PATH = Path(__file__).resolve().parents[3] / "models.yaml"

Task = Literal["generation", "meta"]


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ollama", "openrouter"]
    base_url: str | None = None  # ollama only


class ModelCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    provider: str
    # "none" is data (this file), the wire format it maps to is code (llm.py) —
    # each provider kind has its own shape for "turn reasoning off".
    reasoning: Literal["default", "none"] = "default"
    # None means "infer from provider kind" (see llm.py); an Ollama Cloud
    # entry must set this explicitly since it shares ollama's kind but not
    # its grammar-constrained decoding.
    native_output: bool | None = None
    max_tokens: int | None = None
    timeout: float | None = None


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    models: dict[Task, list[ModelCatalogEntry]] = Field(default_factory=dict)

    def provider_for(self, entry: ModelCatalogEntry) -> ProviderConfig:
        return self.providers[entry.provider]

    def find(self, task: Task, model_id: str) -> ModelCatalogEntry | None:
        return next((e for e in self.models.get(task, []) if e.id == model_id), None)


@lru_cache
def load_catalog(path: Path = _CATALOG_PATH) -> ModelCatalog:
    """Parse ``models.yaml`` once per process.

    A missing file is not an error — everything falls back to ``llm.py``'s
    heuristics, so the catalog stays optional for anyone who never edits it.
    """
    if not path.exists():
        return ModelCatalog()
    data = yaml.safe_load(path.read_text())
    return ModelCatalog.model_validate(data or {})
