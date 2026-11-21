from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.assistant_history import AgentAction, ChatConversation
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
    AgentActionResponse,
    AgentActionCreate,
    AgentActionUpdate,
    AssistantChatResponse,
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationMessageCreate,
    ConversationSummary,
    DraftRequest,
    DraftResponse,
    ProviderStatus,
    ProviderStatusResponse,
    StoredChatMessage,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantChatResponse)
def chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AssistantChatResponse:
    conversation = None
    if payload.conversation_id:
        conversation = db.get(ChatConversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
        if any(action.status in {"pending", "approved"} for action in conversation.actions):
            raise HTTPException(
                status_code=409,
                detail="Selesaikan atau tolak usulan yang masih menunggu sebelum melanjutkan chat.",
            )
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in conversation.messages
        ]
        history.append(payload.messages[-1].model_dump())
        messages = [
            type(payload.messages[-1]).model_validate(message)
            for message in history[-16:]
        ]
    else:
        messages = payload.messages

    try:
        content, provider_id, model = create_chat_response(
            messages,
            payload.timezone,
            settings,
        )
    except NoProvidersConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PlannerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    if conversation is None:
        first_user_message = next(
            message.content for message in messages if message.role == "user"
        )
        conversation = ChatConversation(
            title=first_user_message[:120],
            messages=[],
        )
        db.add(conversation)

    stored_messages = list(conversation.messages)
    if payload.conversation_id:
        latest_user_message = messages[-1]
        stored_messages.append(
            StoredChatMessage(
                role=latest_user_message.role,
                content=latest_user_message.content,
                created_at=now,
            ).model_dump(mode="json")
        )
    else:
        stored_messages.extend(
            StoredChatMessage(
                role=message.role,
                content=message.content,
                created_at=now,
            ).model_dump(mode="json")
            for message in messages
        )

    action_id = None
    action_type = None
    action_summary = None
    action_details = {}
    if content.todo_proposal is not None and content.todo_proposal.status == "ready":
        action_type = "create_todo"
        action_summary = content.todo_proposal.title or "Usulan pembuatan tugas"
        action_details = {"todo_proposal": content.todo_proposal.model_dump(mode="json")}
    elif content.tool_proposal is not None:
        action_type = content.tool_proposal.tool_id
        action_summary = content.tool_proposal.reason
        action_details = {"tool_proposal": content.tool_proposal.model_dump(mode="json")}

    if action_type is not None:
        action = AgentAction(
            conversation=conversation,
            action_type=action_type,
            status="pending",
            summary=action_summary,
            details=action_details,
        )
        db.add(action)
        db.flush()
        action_id = action.id

    stored_messages.append(
        StoredChatMessage(
            role="assistant",
            content=content.reply,
            created_at=now,
            todo_proposal=content.todo_proposal,
            tool_proposal=content.tool_proposal,
            action_id=action_id,
        ).model_dump(mode="json")
    )
    conversation.messages = stored_messages
    conversation.updated_at = now
    db.commit()

    return AssistantChatResponse(
        reply=content.reply,
        todo_proposal=content.todo_proposal,
        tool_proposal=content.tool_proposal,
        provider=provider_id,
        model=model,
        conversation_id=conversation.id,
        action_id=action_id,
    )


def _conversation_summary(conversation: ChatConversation) -> ConversationSummary:
    last_message = conversation.messages[-1]["content"] if conversation.messages else ""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages),
        last_message=last_message,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationSummary]:
    conversations = db.scalars(
        select(ChatConversation).order_by(
            ChatConversation.updated_at.desc(), ChatConversation.id.desc()
        )
    ).all()
    return [_conversation_summary(conversation) for conversation in conversations]


@router.post(
    "/conversations",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    now = datetime.now(timezone.utc)
    conversation = ChatConversation(
        title=payload.first_message[:120],
        messages=[
            StoredChatMessage(
                role="user",
                content=payload.first_message,
                created_at=now,
            ).model_dump(mode="json")
        ],
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationDetail(
        **_conversation_summary(conversation).model_dump(),
        messages=conversation.messages,
        actions=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
    summary = _conversation_summary(conversation)
    return ConversationDetail(
        **summary.model_dump(),
        messages=conversation.messages,
        actions=[
            AgentActionResponse.model_validate(action, from_attributes=True)
            for action in conversation.actions
        ],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=StoredChatMessage,
    status_code=status.HTTP_201_CREATED,
)
def append_conversation_message(
    conversation_id: str,
    payload: ConversationMessageCreate,
    db: Session = Depends(get_db),
) -> StoredChatMessage:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
    now = datetime.now(timezone.utc)
    message = StoredChatMessage(
        role=payload.role,
        content=payload.content,
        created_at=now,
        security_scan=payload.security_scan,
        web_research=payload.web_research,
    )
    conversation.messages = [*conversation.messages, message.model_dump(mode="json")]
    conversation.updated_at = now
    db.commit()
    return message


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Response:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/conversations/{conversation_id}/actions/{action_id}",
    response_model=AgentActionResponse,
)
def update_agent_action(
    conversation_id: str,
    action_id: str,
    payload: AgentActionUpdate,
    db: Session = Depends(get_db),
) -> AgentActionResponse:
    action = db.get(AgentAction, action_id)
    if action is None or action.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Aktivitas agent tidak ditemukan")
    valid_transition = (
        action.status == "pending" and payload.status in {"approved", "rejected"}
    ) or (
        action.status == "approved" and payload.status in {"completed", "failed"}
    )
    if not valid_transition:
        raise HTTPException(status_code=409, detail="Status aktivitas tidak dapat diubah")

    now = datetime.now(timezone.utc)
    action.status = payload.status
    action.updated_at = now
    if payload.status == "approved":
        action.approved_at = now
    if payload.status in {"completed", "failed"}:
        action.completed_at = now
    if payload.summary:
        action.summary = payload.summary
    db.commit()
    db.refresh(action)
    return AgentActionResponse.model_validate(action, from_attributes=True)


@router.post(
    "/conversations/{conversation_id}/actions",
    response_model=AgentActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_action(
    conversation_id: str,
    payload: AgentActionCreate,
    db: Session = Depends(get_db),
) -> AgentActionResponse:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
    now = datetime.now(timezone.utc)
    action = AgentAction(
        conversation_id=conversation_id,
        action_type=payload.action_type,
        status="approved",
        summary=payload.summary,
        details={"query": payload.query} if payload.query else {},
        approved_at=now,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return AgentActionResponse.model_validate(action, from_attributes=True)


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
