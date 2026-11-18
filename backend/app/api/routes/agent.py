import difflib
import hashlib
import logging
import os
import subprocess
import sys
import tempfile

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.planner import (
    NoProvidersConfigured,
    PlannerUnavailable,
    create_code_change,
)
from app.agent.dependency_audit import (
    DependencyAuditNotConfigured,
    DependencyAuditScopeDenied,
    DependencyAuditUnavailable,
    run_dependency_audit,
)
from app.agent.security_scan import run_local_security_scan
from app.agent.website_security_check import (
    WebsiteSecurityConfigurationError,
    WebsiteSecurityNotConfigured,
    WebsiteSecurityScopeDenied,
    WebsiteSecurityUnavailable,
    check_website_security,
)
from app.agent.web_research import (
    WebResearchNotConfigured,
    WebResearchUnavailable,
    research_public_web,
)
from app.agent.workspace import (
    MAX_DIFF_BYTES,
    MAX_PATCH_BYTES,
    PROJECT_ROOT,
    list_source_files,
    read_source_file,
    resolve_source_file,
)
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.agent_proposal import AgentProposal, AgentProposalStatus, utcnow
from app.schemas.agent import (
    AgentFile,
    AgentFileListResponse,
    CodeChangeRequest,
    CommandRequest,
    CommandResponse,
    DependencyAuditRequest,
    DependencyAuditResponse,
    ProposalListResponse,
    ProposalResponse,
    SecurityScanResponse,
    WebsiteSecurityCheckRequest,
    WebsiteSecurityCheckResponse,
    WebResearchRequest,
    WebResearchResponse,
)

logger = logging.getLogger("app.agent.routes")
router = APIRouter(prefix="/api/agent", tags=["coding-agent"])
MAX_COMMAND_OUTPUT_BYTES = 20 * 1024
COMMAND_TIMEOUT_SECONDS = 120


def _diff(path: str, original: str, proposed: str) -> str:
    lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    diff = "".join(lines)
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise HTTPException(status_code=413, detail="Patch terlalu besar untuk ditampilkan")
    return diff


def _proposal_response(proposal: AgentProposal) -> ProposalResponse:
    return ProposalResponse(
        id=proposal.id,
        instruction=proposal.instruction,
        file_path=proposal.file_path,
        summary=proposal.summary,
        original_content=proposal.original_content,
        proposed_content=proposal.proposed_content,
        diff=_diff(proposal.file_path, proposal.original_content, proposal.proposed_content),
        status=proposal.status,
        created_at=proposal.created_at,
        applied_at=proposal.applied_at,
    )


def _bounded_command_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    output = b""
    for stream in (stdout, stderr):
        if isinstance(stream, str):
            output += stream.encode("utf-8", errors="replace")
        elif stream:
            output += stream
    return output[-MAX_COMMAND_OUTPUT_BYTES:].decode("utf-8", errors="replace")


@router.get("/files", response_model=AgentFileListResponse)
def list_agent_files() -> AgentFileListResponse:
    return AgentFileListResponse(
        files=[AgentFile(path=path, size_bytes=size) for path, size in list_source_files()]
    )


@router.post("/security-scan", response_model=SecurityScanResponse)
def scan_local_project_security() -> SecurityScanResponse:
    result = run_local_security_scan()
    logger.info(
        "Completed local defensive scan: %s files, %s findings",
        result.scanned_files,
        len(result.findings),
    )
    return result


@router.post(
    "/website-security-check",
    response_model=WebsiteSecurityCheckResponse,
)
def scan_authorized_website_security(
    payload: WebsiteSecurityCheckRequest,
    settings: Settings = Depends(get_settings),
) -> WebsiteSecurityCheckResponse:
    try:
        result = check_website_security(
            payload.target_host,
            settings.security_audit_host_list,
            payload.confirm_authorized,
            target_path=payload.target_path,
        )
    except WebsiteSecurityNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WebsiteSecurityConfigurationError as exc:
        logger.error("Invalid SECURITY_AUDIT_ALLOWED_HOSTS configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WebsiteSecurityScopeDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except WebsiteSecurityUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    logger.info(
        "Completed passive website security check for %s with HTTP %s",
        result.host,
        result.status_code,
    )
    return result


@router.post(
    "/dependency-audit",
    response_model=DependencyAuditResponse,
)
def audit_project_dependencies(
    payload: DependencyAuditRequest,
) -> DependencyAuditResponse:
    try:
        result = run_dependency_audit(payload.confirm_external_lookup)
    except DependencyAuditNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DependencyAuditScopeDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except DependencyAuditUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    logger.info(
        "Completed dependency audit: npm affected packages=%s, PyPI affected packages=%s",
        result.npm.affected_packages,
        result.pypi.affected_packages,
    )
    return result


@router.post("/research", response_model=WebResearchResponse)
def research_public_web_endpoint(
    payload: WebResearchRequest,
    settings: Settings = Depends(get_settings),
) -> WebResearchResponse:
    try:
        result = research_public_web(payload.query, settings)
    except WebResearchNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WebResearchUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    logger.info(
        "Completed public web research with %s citations",
        len(result.citations),
    )
    return result


@router.get("/proposals", response_model=ProposalListResponse)
def list_proposals(
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    proposals = (
        db.query(AgentProposal)
        .filter(AgentProposal.status == AgentProposalStatus.PENDING)
        .order_by(AgentProposal.created_at.desc(), AgentProposal.id.desc())
        .limit(10)
        .all()
    )
    return ProposalListResponse(
        proposals=[_proposal_response(proposal) for proposal in proposals]
    )


@router.post(
    "/proposals",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_proposal(
    payload: CodeChangeRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProposalResponse:
    file_path, original, original_sha256 = read_source_file(payload.file_path)
    try:
        draft, _, _ = create_code_change(
            payload.instruction,
            file_path,
            original,
            settings,
        )
    except NoProvidersConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PlannerUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    proposed = draft.content
    if "\x00" in proposed or len(proposed.encode("utf-8")) > MAX_PATCH_BYTES:
        raise HTTPException(status_code=422, detail="AI menghasilkan patch yang tidak didukung")
    if proposed == original:
        raise HTTPException(
            status_code=422,
            detail=f"Tidak ada perubahan yang diusulkan: {draft.summary}",
        )
    _diff(file_path, original, proposed)

    proposal = AgentProposal(
        instruction=payload.instruction,
        file_path=file_path,
        summary=draft.summary,
        original_content=original,
        proposed_content=proposed,
        original_sha256=original_sha256,
        status=AgentProposalStatus.PENDING,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return _proposal_response(proposal)


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
def approve_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
) -> ProposalResponse:
    proposal = db.get(AgentProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal tidak ditemukan")
    if proposal.status != AgentProposalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Proposal ini sudah diproses")

    file_path, _, current_hash = read_source_file(proposal.file_path)
    if current_hash != proposal.original_sha256:
        raise HTTPException(
            status_code=409,
            detail="File berubah sejak proposal dibuat. Buat ulang proposal sebelum menerapkan.",
        )
    proposed = proposal.proposed_content
    if "\x00" in proposed or len(proposed.encode("utf-8")) > MAX_PATCH_BYTES:
        raise HTTPException(status_code=422, detail="Patch proposal tidak valid")

    path = resolve_source_file(file_path)
    file_mode = path.stat().st_mode
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".agent-tmp",
            delete=False,
        ) as temporary_file:
            content_to_write = proposed
            if "\r\n" in proposal.original_content:
                content_to_write = proposed.replace("\r\n", "\n").replace("\n", "\r\n")
            temporary_file.write(content_to_write)
            temporary_path = temporary_file.name
        latest_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if latest_hash != proposal.original_sha256:
            raise HTTPException(
                status_code=409,
                detail="File berubah saat patch disiapkan. Buat ulang proposal sebelum menerapkan.",
            )
        os.chmod(temporary_path, file_mode)
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        logger.exception("Could not apply coding-agent proposal %s", proposal_id)
        raise HTTPException(status_code=500, detail="Patch gagal diterapkan ke file") from exc
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                logger.exception("Could not remove temporary patch file for proposal %s", proposal_id)

    proposal.status = AgentProposalStatus.APPLIED
    proposal.applied_at = utcnow()
    db.commit()
    db.refresh(proposal)
    logger.info("Applied coding-agent proposal %s to %s", proposal_id, file_path)
    return _proposal_response(proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
def reject_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
) -> ProposalResponse:
    proposal = db.get(AgentProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal tidak ditemukan")
    if proposal.status != AgentProposalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Proposal ini sudah diproses")
    proposal.status = AgentProposalStatus.REJECTED
    db.commit()
    db.refresh(proposal)
    return _proposal_response(proposal)


@router.post("/commands/run", response_model=CommandResponse)
def run_approved_command(payload: CommandRequest) -> CommandResponse:
    command = [sys.executable, "-m", "pytest", "-q"]
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )
        return CommandResponse(
            command_id=payload.command_id,
            command=command,
            exit_code=result.returncode,
            timed_out=False,
            output=_bounded_command_output(result.stdout, result.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResponse(
            command_id=payload.command_id,
            command=command,
            exit_code=-1,
            timed_out=True,
            output=_bounded_command_output(exc.stdout, exc.stderr),
        )
