import json

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.domain.generator import GenerationRequest
from melos.domain.models import TimeSignature
from melos.generation.meta import MetaResolver, ResolvedMeta

MODEL_ANSWER = {
    "tempo_bpm": 140,
    "key": "Am",
    "time_signature": {"numerator": 4, "denominator": 4},
}


def answering_model() -> FunctionModel:
    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, MODEL_ANSWER)])

    return FunctionModel(respond)


def capturing_model(prompts: list[str]) -> FunctionModel:
    """A model that records the user prompt text it was sent, then answers."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[-1]
        assert isinstance(request, ModelRequest)
        part = request.parts[-1]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, str)
        prompts.append(part.content)
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, MODEL_ANSWER)])

    return FunctionModel(respond)


def exploding_model() -> FunctionModel:
    def explode(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("LLM must not be called when all meta is supplied")

    return FunctionModel(explode)


async def resolve(model: FunctionModel, **request_fields: object) -> ResolvedMeta:
    request = GenerationRequest.model_validate({"prompt": "a song", **request_fields})
    return await MetaResolver(model, use_native_output=False).resolve(request)


@pytest.mark.anyio
async def test_no_llm_call_when_all_meta_supplied() -> None:
    resolved = await resolve(
        exploding_model(),
        tempo_bpm=88,
        key="Eb",
        time_signature={"numerator": 3, "denominator": 4},
    )
    assert resolved == ResolvedMeta(
        tempo_bpm=88,
        key="Eb",
        time_signature=TimeSignature(numerator=3, denominator=4),
    )


@pytest.mark.anyio
async def test_missing_meta_filled_by_model() -> None:
    resolved = await resolve(answering_model())
    assert resolved == ResolvedMeta.model_validate(MODEL_ANSWER)


@pytest.mark.anyio
async def test_supplied_values_always_win() -> None:
    resolved = await resolve(answering_model(), tempo_bpm=61, key="F#m")
    assert resolved.tempo_bpm == 61  # not the model's 140
    assert resolved.key == "F#m"  # not the model's Am
    assert resolved.time_signature == TimeSignature(numerator=4, denominator=4)


@pytest.mark.anyio
async def test_native_output_mode_used_when_requested() -> None:
    """use_native_output=True must drive the agent via NativeOutput, not
    ToolOutput: the model answers with a JSON TextPart, and no output tool
    is offered (info.output_tools is empty in that mode)."""

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert not info.output_tools
        return ModelResponse(parts=[TextPart(json.dumps(MODEL_ANSWER))])

    request = GenerationRequest.model_validate({"prompt": "a song"})
    resolver = MetaResolver(FunctionModel(respond), use_native_output=True)
    resolved = await resolver.resolve(request)
    assert resolved == ResolvedMeta.model_validate(MODEL_ANSWER)


@pytest.mark.anyio
async def test_prompt_lists_only_the_fixed_values() -> None:
    prompts: list[str] = []
    await resolve(
        capturing_model(prompts),
        tempo_bpm=61,
        time_signature={"numerator": 3, "denominator": 4},
    )
    prompt = prompts[0]
    assert "Song prompt: a song" in prompt
    assert "Fixed by the user (repeat these values exactly):" in prompt
    assert "tempo_bpm = 61" in prompt
    assert "time_signature = 3/4" in prompt
    assert "key" not in prompt  # not supplied, must not appear as "fixed"


@pytest.mark.anyio
async def test_prompt_says_nothing_fixed_when_all_missing() -> None:
    prompts: list[str] = []
    await resolve(capturing_model(prompts))
    assert "No values are fixed; choose all of them." in prompts[0]
