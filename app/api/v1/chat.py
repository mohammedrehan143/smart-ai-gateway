"""Public chat generation endpoint POST /v1/chat."""

from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from app.api.deps import get_orchestrator, verify_gateway_auth
from app.api.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.orchestrator import ChatOrchestrator

router = APIRouter(prefix="/v1", tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_gateway_auth)],
)
async def create_chat_completion(
    request: ChatCompletionRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    orchestrator: ChatOrchestrator = Depends(get_orchestrator),
) -> ChatCompletionResponse:
    """Public chat generation endpoint."""
    return await orchestrator.execute_chat(request, client_request_id=x_request_id)
