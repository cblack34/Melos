from pathlib import Path

import pytest

from melos.generation.catalog import ModelCatalog, load_catalog

YAML = """
providers:
  ollama:
    kind: ollama
    base_url: http://localhost:11434/v1
  openrouter:
    kind: openrouter

models:
  generation:
    - id: qwen3.6:27b
      label: Qwen 3.6 27B (local)
      provider: ollama
      reasoning: none
    - id: anthropic/claude-sonnet-5
      label: Claude Sonnet 5
      provider: openrouter
  meta:
    - id: openai/gpt-5-nano
      label: GPT-5 nano
      provider: openrouter
"""


@pytest.fixture
def catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(YAML)
    return path


def test_loads_providers_and_models(catalog_file: Path) -> None:
    catalog = load_catalog(catalog_file)
    assert set(catalog.providers) == {"ollama", "openrouter"}
    assert [m.id for m in catalog.models["generation"]] == [
        "qwen3.6:27b",
        "anthropic/claude-sonnet-5",
    ]
    assert [m.id for m in catalog.models["meta"]] == ["openai/gpt-5-nano"]


def test_find_returns_the_matching_entry(catalog_file: Path) -> None:
    catalog = load_catalog(catalog_file)
    entry = catalog.find("generation", "qwen3.6:27b")
    assert entry is not None
    assert entry.reasoning == "none"
    assert catalog.find("generation", "not-a-real-model") is None
    assert catalog.find("meta", "qwen3.6:27b") is None  # wrong task


def test_provider_for_resolves_the_named_provider(catalog_file: Path) -> None:
    catalog = load_catalog(catalog_file)
    entry = catalog.find("generation", "anthropic/claude-sonnet-5")
    assert entry is not None
    assert catalog.provider_for(entry).kind == "openrouter"


def test_missing_file_is_an_empty_catalog_not_an_error(tmp_path: Path) -> None:
    catalog = load_catalog(tmp_path / "does-not-exist.yaml")
    assert catalog == ModelCatalog()
    assert catalog.find("generation", "anything") is None


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("providers: {}\nmodels: {}\nnonsense: true\n")
    with pytest.raises(Exception, match="nonsense"):
        load_catalog(path)


def test_shipped_catalog_parses_and_every_provider_reference_resolves() -> None:
    # The real backend/models.yaml, not a fixture -- catches a typo'd
    # provider name or malformed entry before it ships.
    catalog = load_catalog()
    assert catalog.models  # non-empty: the repo's catalog is not blank
    for entries in catalog.models.values():
        for entry in entries:
            assert entry.provider in catalog.providers, (
                f"{entry.id!r} references unknown provider {entry.provider!r}"
            )
