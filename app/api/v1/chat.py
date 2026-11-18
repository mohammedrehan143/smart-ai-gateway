"""Public chat generation endpoint POST /v1/chat."""

from __future__ import annotations

import asyncio
import json
from typing import Optional, Union
from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import StreamingResponse
from app.api.deps import AuthenticatedUser, get_authenticated_user, get_orchestrator, verify_gateway_auth
from app.api.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.orchestrator import ChatOrchestrator

router = APIRouter(prefix="/v1", tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
    include_in_schema=False,
)
async def create_chat_completion(
    request: ChatCompletionRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    orchestrator: ChatOrchestrator = Depends(get_orchestrator),
) -> Union[ChatCompletionResponse, StreamingResponse]:
    """Public chat generation endpoint supporting standard JSON and SSE streaming."""
    # Enforce tenant identity
    if not request.routing.user_id or not user.is_admin:
        request.routing.user_id = user.user_id
    if not request.user or not user.is_admin:
        request.user = user.user_id
    if request.stream:

        async def event_generator():
            completion = await orchestrator.execute_chat(request, client_request_id=x_request_id)
            choice = completion.choices[0] if completion.choices else None
            content = choice.message.content if choice and choice.message.content else ""
            tool_calls = choice.message.tool_calls if choice and choice.message.tool_calls else None

            if tool_calls:
                tc_chunk = {
                    "id": completion.id,
                    "object": "chat.completion.chunk",
                    "created": completion.created,
                    "model": completion.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content, "tool_calls": tool_calls},
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "tool_calls": tool_calls,
                }
                yield f"data: {json.dumps(tc_chunk)}\n\n"
            elif content:
                words = content.split(" ")
                for idx, word in enumerate(words):
                    chunk_piece = word if idx == len(words) - 1 else word + " "
                    chunk_data = {
                        "id": completion.id,
                        "object": "chat.completion.chunk",
                        "created": completion.created,
                        "model": completion.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk_piece},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    await asyncio.sleep(0.015)

            final_data = {
                "id": completion.id,
                "object": "chat.completion.chunk",
                "created": completion.created,
                "model": completion.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"tool_calls": tool_calls} if tool_calls else {},
                        "finish_reason": "tool_calls" if tool_calls else (choice.finish_reason if choice else "stop"),
                    }
                ],
                "usage": completion.usage.model_dump(),
                "routing": completion.routing.model_dump(),
                "latency_ms": completion.latency_ms,
                "trace_id": completion.trace_id,
                "cached": completion.cached,
                "provider": completion.provider,
            }
            if tool_calls:
                final_data["tool_calls"] = tool_calls
            yield f"data: {json.dumps(final_data)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return await orchestrator.execute_chat(request, client_request_id=x_request_id)
