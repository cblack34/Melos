"""SSE generate stream (story #45)."""

import base64
import json
from collections.abc import Mapping
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from mido import MidiFile
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from melos.api.app import create_app
from melos.domain.generator import GenerationRequest
from melos.domain.models import Song
from melos.domain.progress import ProgressEvent, ProgressReporter
from melos.generation.ai import PydanticAISongGenerator
from melos.generation.meta import MetaResolver
from melos.generation.stub import StubSongGenerator

client = TestClient(create_app(StubSongGenerator()))


def _parse_sse(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        assert event_name is not None
        payload = json.loads("\n".join(data_lines))
        assert payload["phase"] == event_name
        events.append(payload)
    return events


def test_stream_returns_progress_then_midi() -> None:
    with client.stream(
        "POST", "/api/generate/stream", json={"prompt": "a happy tune"}
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.read().decode())

    phases = [e["phase"] for e in events]
    assert phases == [
        "request_received",
        "meta_skipped",
        "generation_started",
        "generation_completed",
        "export_started",
        "export_completed",
        "completed",
    ]
    done = events[-1]
    assert done["filename"] == "melos-sketch.mid"
    assert isinstance(done["midi_base64"], str)
    midi_bytes = base64.standard_b64decode(done["midi_base64"])
    midi = MidiFile(file=BytesIO(midi_bytes))
    assert midi.type == 1
    assert len(midi.tracks) >= 2


def test_stream_validation_error_is_http_422_not_sse() -> None:
    response = client.post("/api/generate/stream", json={"prompt": ""})
    assert response.status_code == 422
    assert "text/event-stream" not in response.headers.get("content-type", "")


def test_blob_generate_still_works() -> None:
    response = client.post("/api/generate", json={"prompt": "keep the blob path"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/midi"


class _FailingGenerator:
    async def generate(
        self,
        request: GenerationRequest,
        *,
        progress: ProgressReporter | None = None,
    ) -> Song:
        if progress is not None:
            await progress.report(
                ProgressEvent(phase="request_received", message="start")
            )
            await progress.report(
                ProgressEvent(phase="failed", message="raw model failure")
            )
        raise UnexpectedModelBehavior("exceeded maximum output retries (3)")


def test_stream_pipeline_failure_ends_with_failed_event() -> None:
    http = TestClient(create_app(_FailingGenerator()))  # type: ignore[arg-type]
    with http.stream(
        "POST", "/api/generate/stream", json={"prompt": "will fail"}
    ) as response:
        assert response.status_code == 200
        events = _parse_sse(response.read().decode())

    assert events[0]["phase"] == "request_received"
    assert events[-1]["phase"] == "failed"
    assert "generation failed" in str(events[-1]["message"])


GOOD_COMPACT: dict[str, object] = {
    "title": "Retry Song",
    "bpm": 100.0,
    "key": "C",
    "ts": "4/4",
    "tracks": [
        {
            "name": "Flute",
            "prog": 73,
            "voc": True,
            "notes": [{"s": 0, "d": 1, "p": 62, "lyr": "La"}],
        },
        {"name": "Bass", "prog": 33, "notes": [{"s": 0, "d": 2, "p": 38}]},
    ],
}


def _ai_with_retry() -> PydanticAISongGenerator:
    wrong = {**GOOD_COMPACT, "bpm": 120.0}
    remaining = [wrong, GOOD_COMPACT]

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, payload)])

    def explode(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("meta must be fully supplied")

    return PydanticAISongGenerator(
        FunctionModel(respond),
        MetaResolver(FunctionModel(explode), use_native_output=False),
        use_native_output=False,
    )


@pytest.mark.anyio
async def test_stream_includes_validation_retry_event() -> None:
    http = TestClient(create_app(_ai_with_retry()))
    payload: Mapping[str, object] = {
        "prompt": "retry once",
        "tempo_bpm": 100,
        "key": "C",
        "time_signature": {"numerator": 4, "denominator": 4},
        "include_instruments": ["Flute"],
    }
    with http.stream("POST", "/api/generate/stream", json=payload) as response:
        assert response.status_code == 200
        events = _parse_sse(response.read().decode())

    phases = [e["phase"] for e in events]
    assert "validation_retry" in phases
    retry = next(e for e in events if e["phase"] == "validation_retry")
    assert retry["attempt"] == 1
    reasons = retry["reasons"]
    assert isinstance(reasons, list)
    assert any("bpm" in str(reason) for reason in reasons)
    assert phases[-1] == "completed"
    assert events[-1]["filename"] == "retry-song.mid"
