import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from app.api.dependencies import AssistantServiceDep
from app.schemas.assistant import AssistantRequest, AssistantResponse

router = APIRouter()

assistant_examples = {
    "directory_question": {
        "summary": "Ask a public directory question",
        "value": {
            "conversation_id": "conversation-123",
            "principal": {},
            "message": "What can Minzo help me find?",
        },
    },
    "business_context": {
        "summary": "Ask about the currently displayed business",
        "value": {
            "conversation_id": "conversation-124",
            "principal": {},
            "business_context": {
                "business_id": "00000000-0000-4000-8000-000000000001",
                "business_slug": "example-clinic",
            },
            "message": "Tell me about this business.",
        },
    },
}

AssistantPayload = Annotated[
    AssistantRequest,
    Body(openapi_examples=assistant_examples),
]


@router.post(
    "/messages",
    response_model=AssistantResponse,
    summary="Ask the Minzo assistant",
    description=(
        "Returns one structured JSON response. Use this endpoint in Swagger and for "
        "read-only questions. An optional user Authorization bearer header enables "
        "personal profile and review tools after Backend verifies it. "
        "The X-Service-Key header remains required. This assistant cannot change records."
    ),
)
async def assistant_message(
    payload: AssistantPayload,
    service: AssistantServiceDep,
) -> AssistantResponse:
    return await service.respond(payload)


@router.post(
    "/messages/stream",
    response_class=StreamingResponse,
    summary="Stream a Minzo assistant response",
    description=(
        "Streams Server-Sent Events (SSE). Event types are `start`, `token`, "
        "`done`, and `error`. Swagger can issue the request, but "
        "a frontend Fetch stream or `curl -N` displays tokens progressively."
    ),
    responses={
        200: {
            "description": "A Server-Sent Events stream.",
            "content": {"text/event-stream": {}},
        }
    },
)
async def stream_assistant_message(
    payload: AssistantPayload,
    service: AssistantServiceDep,
) -> StreamingResponse:
    return StreamingResponse(
        _assistant_events(service, payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _assistant_events(
    service: AssistantServiceDep,
    payload: AssistantRequest,
) -> AsyncIterator[str]:
    async for event in service.stream(payload):
        event_type = event["type"]
        yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
