from pydantic_ai.models.ollama import OllamaModel

from melos.api.app import default_lyric_writer
from melos.config import LlmSettings


def test_uses_the_configured_lyric_model() -> None:
    settings = LlmSettings(_env_file=None, lyric_model="qwen3.6:35b")
    writer = default_lyric_writer(settings)
    assert isinstance(writer._agent.model, OllamaModel)
    assert writer._agent.model.model_name == "qwen3.6:35b"
