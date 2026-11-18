import ipaddress
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_serializer, field_validator

from app.models.agent_proposal import AgentProposalStatus


class CodeChangeDraft(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=128 * 1024)


class AgentFile(BaseModel):
    path: str
    size_bytes: int


class AgentFileListResponse(BaseModel):
    files: list[AgentFile]
    excluded_sensitive_files: bool = True


class CodeChangeRequest(BaseModel):
    instruction: str = Field(min_length=8, max_length=2000)
    file_path: str = Field(min_length=1, max_length=500)
    consent_to_send_source: bool

    @field_validator("instruction", "file_path")
    @classmethod
    def strip_values(cls, value: str) -> str:
        return value.strip()

    @field_validator("consent_to_send_source")
    @classmethod
    def require_source_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Persetujuan mengirim source ke provider diperlukan")
        return value


class ProposalResponse(BaseModel):
    id: int
    instruction: str
    file_path: str
    summary: str
    original_content: str
    proposed_content: str
    diff: str
    status: AgentProposalStatus
    created_at: datetime
    applied_at: datetime | None

    @field_serializer("created_at", "applied_at")
    def serialize_datetimes(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class CommandRequest(BaseModel):
    command_id: str = Field(pattern=r"^backend_tests$")
    confirm_execution: bool

    @field_validator("confirm_execution")
    @classmethod
    def require_explicit_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Persetujuan menjalankan perintah diperlukan")
        return value


class CommandResponse(BaseModel):
    command_id: str
    command: list[str]
    exit_code: int
    timed_out: bool
    output: str


class DependencyAuditRequest(BaseModel):
    confirm_external_lookup: bool

    @field_validator("confirm_external_lookup")
    @classmethod
    def require_external_lookup_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Persetujuan pemeriksaan dependency diperlukan.")
        return value


class DependencyFinding(BaseModel):
    ecosystem: Literal["npm", "pypi"]
    package: str = Field(max_length=200)
    installed_version: str = Field(max_length=100)
    severity: Literal["info", "low", "moderate", "high", "critical", "unknown"]
    advisory_ids: list[str] = Field(max_length=10)
    title: str = Field(max_length=500)
    fixed_versions: list[str] = Field(max_length=10)


class DependencyAuditSource(BaseModel):
    packages_scanned: int
    affected_packages: int
    findings: list[DependencyFinding]
    truncated: bool


class DependencyAuditResponse(BaseModel):
    checked_at: datetime
    npm: DependencyAuditSource
    pypi: DependencyAuditSource
    limitations: list[str]

    @field_serializer("checked_at")
    def serialize_checked_at(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ProposalListResponse(BaseModel):
    proposals: list[ProposalResponse]


class SecurityFinding(BaseModel):
    rule_id: str
    severity: Literal["high", "medium", "low"]
    title: str
    file_path: str
    line: int
    description: str
    recommendation: str
    confidence: Literal["low", "medium", "high"]


class SecurityScanResponse(BaseModel):
    scanned_files: int
    skipped_files: int
    findings: list[SecurityFinding]
    high_count: int
    medium_count: int
    low_count: int
    limitations: list[str]


class WebsiteSecurityCheckRequest(BaseModel):
    target_host: str = Field(min_length=4, max_length=253)
    target_path: str = Field(default="/", min_length=1, max_length=2048)
    confirm_authorized: bool

    @field_validator("target_host")
    @classmethod
    def validate_target_host(cls, value: str) -> str:
        hostname = value.strip().rstrip(".").lower()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError("Masukkan nama domain, bukan alamat IP.")
        if (
            not hostname
            or len(hostname) > 253
            or hostname == "localhost"
            or hostname.endswith((".localhost", ".local", ".internal", ".test"))
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in hostname.split(".")
            )
            or len(hostname.split(".")) < 2
        ):
            raise ValueError("Masukkan nama domain publik yang valid, tanpa URL.")
        return hostname

    @field_validator("target_path")
    @classmethod
    def validate_target_path(cls, value: str) -> str:
        path = value.strip()
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or "?" in path
            or "#" in path
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            raise ValueError(
                "Path harus dimulai dengan / dan tidak boleh berisi query atau fragment."
            )
        return path

    @field_validator("confirm_authorized")
    @classmethod
    def require_authorization_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Konfirmasi izin pemeriksaan diperlukan.")
        return value


class WebsiteSecurityFinding(BaseModel):
    header: str
    status: Literal["present", "missing"]
    severity: Literal["info", "low", "medium"]
    recommendation: str


class WebsiteSecurityCheckResponse(BaseModel):
    host: str
    target_path: str = "/"
    status_code: int
    tls_verified: bool
    findings: list[WebsiteSecurityFinding]
    checked_at: datetime
    limitations: list[str]

    @field_serializer("checked_at")
    def serialize_checked_at(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class WebResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pertanyaan riset tidak boleh kosong")
        return value


class WebResearchCitation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl


class WebResearchResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)
    citations: list[WebResearchCitation] = Field(max_length=10)
    provider: Literal["gemini"] = "gemini"
    model: str
