from fastapi import APIRouter, Depends, HTTPException, status

from app.agent.planner import (
    NoProvidersConfigured,
    PlannerUnavailable,
    PROVIDER_NAMES,
    configured_providers,
    create_chat_response,
    create_draft,
    provider_order,
)
from app.core.config import Settings, get_settings
from app.schemas.assistant import (
    AssistantChatResponse,
    ChatRequest,
    DraftRequest,
    DraftResponse,
    ProviderStatus,
    ProviderStatusResponse,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantChatResponse)
def chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> AssistantChatResponse:
    try:
        content, provider_id, model = create_chat_response(
            payload.messages,
            payload.timezone,
            settings,
        )
    except NoProvidersConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PlannerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AssistantChatResponse(
        reply=content.reply,
        todo_proposal=content.todo_proposal,
        tool_proposal=content.tool_proposal,
        provider=provider_id,
        model=model,
    )


@router.get("/providers", response_model=ProviderStatusResponse)
def list_providers(settings: Settings = Depends(get_settings)) -> ProviderStatusResponse:
    all_providers = {
        "openai": settings.openai_model,
        "gemini": settings.gemini_model,
        "anthropic": settings.anthropic_model,
        "openai_compatible": settings.openai_compatible_model,
    }
    configured = configured_providers(settings)
    order = provider_order(settings)
    return ProviderStatusResponse(
        default_provider=settings.llm_default_provider,
        fallback_order=[
            provider_id
            for provider_id in order
            if provider_id != settings.llm_default_provider
        ],
        providers=[
            ProviderStatus(
                id=provider_id,
                name=PROVIDER_NAMES[provider_id],
                model=model,
                configured=provider_id in configured,
                is_default=provider_id == settings.llm_default_provider,
            )
            for provider_id, model in all_providers.items()
        ],
    )


@router.post("/drafts", response_model=DraftResponse)
def create_task_draft(
    payload: DraftRequest,
    settings: Settings = Depends(get_settings),
) -> DraftResponse:
    try:
        draft, provider_id, model = create_draft(
            payload.instruction,
            payload.timezone,
            settings,
        )
    except NoProvidersConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PlannerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DraftResponse(draft=draft, provider=provider_id, model=model)
