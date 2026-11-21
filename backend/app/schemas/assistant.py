from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.schemas.agent import SecurityScanResponse, WebResearchResponse

class DraftRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=4000)
    timezone: str = Field(default="Asia/Jakarta", max_length=100)

    @field_validator("instruction")
    @classmethod
    def instruction_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Instruksi tidak boleh kosong")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone tidak dikenal") from exc
        return value


class PlanDraft(BaseModel):
    status: Literal["ready", "needs_clarification"]
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    clarification_questions: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            return value or None
        return value

    @field_validator("due_at", "reminder_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Waktu dari AI harus menyertakan timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_draft_state(self) -> "PlanDraft":
        if self.status == "ready" and not self.title:
            raise ValueError("Draft siap harus memiliki judul tugas")
        if self.status == "needs_clarification" and not self.clarification_questions:
            raise ValueError("Draft ambigu harus menjelaskan pertanyaan klarifikasi")
        return self

    @field_serializer("due_at", "reminder_at")
    def serialize_datetimes(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc)


class DraftResponse(BaseModel):
    draft: PlanDraft
    provider: str
    model: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pesan chat tidak boleh kosong")
        return value


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=16)
    timezone: str = Field(default="Asia/Jakarta", max_length=100)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone tidak dikenal") from exc
        return value

    @model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("Pesan terakhir harus berasal dari pengguna")
        if sum(len(message.content) for message in self.messages) > 16000:
            raise ValueError("Riwayat chat terlalu panjang")
        return self


class AssistantToolProposal(BaseModel):
    tool_id: Literal["public_web_research", "local_security_scan"]
    reason: str = Field(min_length=1, max_length=500)
    query: str | None = Field(default=None, min_length=3, max_length=2000)

    @field_validator("reason", "query")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_tool_input(self) -> "AssistantToolProposal":
        if self.tool_id == "public_web_research" and not self.query:
            raise ValueError("Riset web memerlukan query yang jelas")
        if self.tool_id == "local_security_scan" and self.query is not None:
            raise ValueError("Scan project lokal tidak menerima query")
        return self


class AssistantChatContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=6000)
    todo_proposal: PlanDraft | None = None
    tool_proposal: AssistantToolProposal | None = None

    @field_validator("reply")
    @classmethod
    def reply_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Jawaban AI tidak boleh kosong")
        return value

    @model_validator(mode="after")
    def allow_one_pending_action(self) -> "AssistantChatContent":
        if self.todo_proposal is not None and self.tool_proposal is not None:
            raise ValueError("Satu respons hanya boleh mengusulkan satu aksi")
        return self


class AssistantChatResponse(BaseModel):
    reply: str
    todo_proposal: PlanDraft | None = None
    tool_proposal: AssistantToolProposal | None = None
    provider: str
    model: str
    conversation_id: str
    action_id: str | None = None


class AgentActionResponse(BaseModel):
    id: str
    action_type: str
    status: Literal["pending", "approved", "rejected", "completed", "failed"]
    summary: str
    details: dict
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    completed_at: datetime | None

    @field_serializer("created_at", "updated_at", "approved_at", "completed_at")
    def serialize_action_datetimes(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class StoredChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    todo_proposal: PlanDraft | None = None
    tool_proposal: AssistantToolProposal | None = None
    action_id: str | None = None
    security_scan: SecurityScanResponse | None = None
    web_research: WebResearchResponse | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message: str

    @field_serializer("created_at", "updated_at")
    def serialize_conversation_datetimes(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ConversationDetail(ConversationSummary):
    messages: list[StoredChatMessage]
    actions: list[AgentActionResponse]


class AgentActionUpdate(BaseModel):
    status: Literal["approved", "rejected", "completed", "failed"]
    summary: str | None = Field(default=None, max_length=1000)


class AgentActionCreate(BaseModel):
    action_type: Literal["public_web_research", "local_security_scan"]
    summary: str = Field(min_length=1, max_length=1000)
    query: str | None = Field(default=None, min_length=3, max_length=2000)

    @model_validator(mode="after")
    def validate_action_input(self) -> "AgentActionCreate":
        if self.action_type == "public_web_research" and not self.query:
            raise ValueError("Riset web memerlukan query")
        if self.action_type == "local_security_scan" and self.query is not None:
            raise ValueError("Scan lokal tidak menerima query")
        return self


class ConversationMessageCreate(BaseModel):
    role: Literal["user", "assistant"] = "assistant"
    content: str = Field(min_length=1, max_length=6000)
    security_scan: SecurityScanResponse | None = None
    web_research: WebResearchResponse | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Isi pesan tidak boleh kosong")
        return value

    @model_validator(mode="after")
    def attachments_require_assistant_message(self) -> "ConversationMessageCreate":
        if self.role == "user" and (
            self.security_scan is not None or self.web_research is not None
        ):
            raise ValueError("Lampiran tool hanya dapat disimpan pada pesan assistant.")
        return self


class ConversationCreate(BaseModel):
    first_message: str = Field(min_length=1, max_length=4000)

    @field_validator("first_message")
    @classmethod
    def first_message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pesan awal tidak boleh kosong")
        return value

class ProviderStatus(BaseModel):
    id: str
    name: str
    model: str
    configured: bool
    is_default: bool


class ProviderStatusResponse(BaseModel):
    default_provider: str
    fallback_order: list[str]
    providers: list[ProviderStatus]
