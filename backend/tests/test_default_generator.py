from melos.api.app import default_generator
from melos.config import LlmSettings
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.stub import StubSongGenerator


def test_stub_backend_selected_by_settings() -> None:
    settings = LlmSettings(_env_file=None, generation_backend="stub")
    assert isinstance(default_generator(settings), StubSongGenerator)


def test_ai_backend_is_the_default() -> None:
    settings = LlmSettings(_env_file=None)
    assert isinstance(default_generator(settings), PydanticAISongGenerator)
