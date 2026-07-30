"""The lyric-writing helper: what reaches the model, and what comes back."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.api.app import create_app
from melos.generation.lyric_writer import LyricRequest, LyricWriter
from melos.generation.stub import StubSongGenerator

WRITTEN = "[verse 1]\nMorning light\n\n[chorus]\nCarry me home"


def writer(prompts: list[str] | None = None) -> LyricWriter:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            request = messages[-1]
            assert isinstance(request, ModelRequest)
            part = request.parts[-1]
            assert isinstance(part, UserPromptPart)
            assert isinstance(part.content, str)
            prompts.append(part.content)
        payload = {"lyrics": WRITTEN}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])

    return LyricWriter(FunctionModel(respond), use_native_output=False)


@pytest.mark.anyio
async def test_writes_lyrics_from_a_topic() -> None:
    written = await writer().write(LyricRequest(topic="coming home at dawn"))
    assert written.lyrics == WRITTEN


@pytest.mark.anyio
async def test_every_signal_reaches_the_model() -> None:
    prompts: list[str] = []
    await writer(prompts).write(
        LyricRequest(
            prompt="dreamy lo-fi",
            topic="rain on a window",
            lyrics="[verse 1]\nHalf a line I already wrote",
        )
    )
    prompt = prompts[0]
    assert "Song style: dreamy lo-fi" in prompt
    assert "What to write about: rain on a window" in prompt
    assert "Half a line I already wrote" in prompt
    assert "[verse 1]" in prompt  # existing tags preserved for context


@pytest.mark.anyio
async def test_says_so_when_there_are_no_existing_lyrics() -> None:
    prompts: list[str] = []
    await writer(prompts).write(LyricRequest(topic="a road trip"))
    assert "no existing lyrics" in prompts[0]


@pytest.mark.anyio
async def test_existing_lyrics_are_framed_as_the_users_work() -> None:
    prompts: list[str] = []
    await writer(prompts).write(LyricRequest(lyrics="Something I wrote"))
    assert "preserve the user's lines" in prompts[0]


def test_a_request_needs_at_least_one_signal() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        LyricRequest()


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_whitespace_only_signals_do_not_count(blank: str) -> None:
    with pytest.raises(ValidationError, match="at least one"):
        LyricRequest(prompt=blank, topic=blank, lyrics=blank)


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        LyricRequest.model_validate({"topic": "x", "mood": "happy"})


@pytest.mark.anyio
async def test_native_output_mode_reads_a_json_text_part() -> None:
    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert not info.output_tools  # native mode offers no output tool
        return ModelResponse(parts=[TextPart(json.dumps({"lyrics": WRITTEN}))])

    native = LyricWriter(FunctionModel(respond), use_native_output=True)
    written = await native.write(LyricRequest(topic="anything"))
    assert written.lyrics == WRITTEN


# --- endpoint --------------------------------------------------------------


def client() -> TestClient:
    return TestClient(create_app(StubSongGenerator(), writer()))


def test_endpoint_returns_written_lyrics() -> None:
    response = client().post("/api/lyrics", json={"topic": "a winter drive"})
    assert response.status_code == 200
    assert response.json() == {"lyrics": WRITTEN}


def test_endpoint_rejects_an_empty_request() -> None:
    assert client().post("/api/lyrics", json={}).status_code == 422


def test_endpoint_rejects_unknown_fields() -> None:
    payload = {"topic": "x", "style": "jazz"}
    assert client().post("/api/lyrics", json=payload).status_code == 422
