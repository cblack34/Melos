"""Progress hooks shared by Melos's Pydantic AI agents."""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import ModelRequestContext

from melos.domain.progress import ProgressEvent, report_progress


async def _report_model_response(
    _ctx: RunContext[Any],
    *,
    request_context: ModelRequestContext,
    response: ModelResponse,
) -> ModelResponse:
    """Expose provider request IDs for successful responses, including retries."""
    del request_context
    if response.provider_response_id is not None:
        await report_progress(
            ProgressEvent(
                phase="model_response",
                message=response.model_name or "Model response received",
                model_id=response.model_name,
                provider_response_id=response.provider_response_id,
            )
        )
    return response


def progress_hooks() -> Hooks:
    """Build hooks per agent so each response can be correlated with its provider."""
    return Hooks(after_model_request=_report_model_response)
