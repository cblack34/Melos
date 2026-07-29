import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
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
