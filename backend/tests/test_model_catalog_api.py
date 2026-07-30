"""Per-request model override: /api/models and /api/generate."""

from typing import Literal

import pytest
from fastapi.testclient import TestClient

from melos.api.app import create_app
from melos.config import LlmSettings
from melos.generation.catalog import ModelCatalog
from melos.generation.stub import StubSongGenerator

CATALOG = ModelCatalog.model_validate(
    {
        "providers": {
            "openrouter": {"kind": "openrouter"},
        },
        "models": {
            "generation": [
                {
                    "id": "openrouter/known-gen",
                    "label": "Known Gen Model",
                    "provider": "openrouter",
                }
            ],
            "meta": [
                {
                    "id": "openrouter/known-meta",
                    "label": "Known Meta Model",
                    "provider": "openrouter",
                }
            ],
        },
    }
)


def client(generation_backend: Literal["ai", "stub"] = "stub") -> TestClient:
    settings = LlmSettings(_env_file=None, generation_backend=generation_backend)
    return TestClient(
        create_app(StubSongGenerator(), settings=settings, catalog=CATALOG)
    )


def test_models_endpoint_lists_the_catalog() -> None:
    response = client().get("/api/models")
    assert response.status_code == 200
    body = response.json()
    assert body["generation"] == [
        {"id": "openrouter/known-gen", "label": "Known Gen Model"}
    ]
    assert body["meta"] == [
        {"id": "openrouter/known-meta", "label": "Known Meta Model"}
    ]


def test_generation_without_override_uses_the_stub() -> None:
    response = client().post("/api/generate", json={"prompt": "a tune"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"


def test_unknown_generation_model_override_rejected() -> None:
    response = client().post(
        "/api/generate",
        json={"prompt": "a tune", "generation_model": "not-in-the-catalog"},
    )
    assert response.status_code == 422
    assert "not-in-the-catalog" in response.json()["detail"]


def test_unknown_meta_model_override_rejected() -> None:
    response = client().post(
        "/api/generate",
        json={"prompt": "a tune", "meta_model": "not-in-the-catalog"},
    )
    assert response.status_code == 422
    assert "not-in-the-catalog" in response.json()["detail"]


def test_known_override_bypasses_stub_and_reaches_the_real_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The stub is configured, but picking a catalogued model is an explicit
    # request for AI generation -- it should be honored, not silently ignored.
    # No OPENROUTER_API_KEY is set, so construction fails with a mapped 500
    # rather than a raw one; reaching that 500 (not a 200 from the stub, and
    # not an unhandled crash) proves the override path was taken.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = client(generation_backend="stub").post(
        "/api/generate",
        json={"prompt": "a tune", "generation_model": "openrouter/known-gen"},
    )
    assert response.status_code == 500
    assert "generator misconfigured" in response.json()["detail"]


def test_overriding_one_task_does_not_validate_the_others_untouched_default() -> None:
    # settings.meta_model (the server default, "qwen3.5:9b") is not in this
    # test's tiny catalog. Overriding only generation_model must not 422 on
    # account of a meta default the client never touched and cannot fix.
    response = client().post(
        "/api/generate",
        json={"prompt": "a tune", "generation_model": "openrouter/known-gen"},
    )
    assert response.status_code != 422


def test_override_model_with_empty_catalog_task_falls_through_uncaught() -> None:
    # An empty catalog task list means "nothing to validate against"; an
    # override naming a task with no catalog entries at all should not 422
    # just because the list is empty (distinct from "id not found in a
    # populated list").
    empty_catalog = ModelCatalog()
    settings = LlmSettings(_env_file=None)
    app = create_app(StubSongGenerator(), settings=settings, catalog=empty_catalog)
    response = TestClient(app).get("/api/models")
    assert response.json() == {"generation": [], "meta": []}
