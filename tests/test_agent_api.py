import subprocess

from app.agent import workspace
from app.api.routes import agent as agent_routes
from app.core.config import Settings, get_settings
from app.models.agent_proposal import AgentProposalStatus
from app.schemas.agent import (
    CodeChangeDraft,
    DependencyAuditResponse,
    DependencyAuditSource,
    SecurityFinding,
    SecurityScanResponse,
    WebsiteSecurityCheckResponse,
    WebResearchCitation,
    WebResearchResponse,
)


def _prepare_workspace(client, tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "sample.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(workspace, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent_routes, "PROJECT_ROOT", tmp_path)
    return client


def test_proposal_is_reviewed_and_only_applied_after_approval(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)

    def fake_generate(instruction, file_path, content, settings):
        assert instruction == "Change the value safely"
        assert file_path == "backend/sample.py"
        assert content.replace("\r\n", "\n") == "value = 1\n"
        return CodeChangeDraft(summary="Update value", content="value = 2\n"), "openai", "test"

    monkeypatch.setattr(agent_routes, "create_code_change", fake_generate)
    response = client.post(
        "/api/agent/proposals",
        json={
            "instruction": "Change the value safely",
            "file_path": "backend/sample.py",
            "consent_to_send_source": True,
        },
    )
    assert response.status_code == 201
    proposal = response.json()
    assert proposal["status"] == AgentProposalStatus.PENDING.value
    assert "-value = 1" in proposal["diff"]
    assert "+value = 2" in proposal["diff"]
    assert (tmp_path / "backend" / "sample.py").read_text(encoding="utf-8") == "value = 1\n"

    approved = client.post(f"/api/agent/proposals/{proposal['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == AgentProposalStatus.APPLIED.value
    assert (tmp_path / "backend" / "sample.py").read_text(encoding="utf-8") == "value = 2\n"
    assert b"\r\n" in (tmp_path / "backend" / "sample.py").read_bytes()
    assert client.post(f"/api/agent/proposals/{proposal['id']}/approve").status_code == 409


def test_stale_proposal_is_not_applied(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)
    monkeypatch.setattr(
        agent_routes,
        "create_code_change",
        lambda *_: (
            CodeChangeDraft(summary="Update value", content="value = 2\n"),
            "openai",
            "test",
        ),
    )
    proposal = client.post(
        "/api/agent/proposals",
        json={
            "instruction": "Change the value safely",
            "file_path": "backend/sample.py",
            "consent_to_send_source": True,
        },
    ).json()
    target = tmp_path / "backend" / "sample.py"
    target.write_text("value = 3\n", encoding="utf-8")

    response = client.post(f"/api/agent/proposals/{proposal['id']}/approve")
    assert response.status_code == 409
    assert target.read_text(encoding="utf-8") == "value = 3\n"


def test_proposal_can_be_rejected_without_changing_file(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)
    monkeypatch.setattr(
        agent_routes,
        "create_code_change",
        lambda *_: (
            CodeChangeDraft(summary="Update value", content="value = 2\n"),
            "openai",
            "test",
        ),
    )
    proposal = client.post(
        "/api/agent/proposals",
        json={
            "instruction": "Change the value safely",
            "file_path": "backend/sample.py",
            "consent_to_send_source": True,
        },
    ).json()

    rejected = client.post(f"/api/agent/proposals/{proposal['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == AgentProposalStatus.REJECTED.value
    assert (tmp_path / "backend" / "sample.py").read_text(encoding="utf-8") == "value = 1\n"
    assert client.post(f"/api/agent/proposals/{proposal['id']}/approve").status_code == 409


def test_agent_file_listing_excludes_secrets_and_build_folders(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "dump.json").write_text("{}", encoding="utf-8")

    response = client.get("/api/agent/files")
    assert response.status_code == 200
    paths = [item["path"] for item in response.json()["files"]]
    assert paths == ["backend/sample.py"]


def test_command_requires_explicit_approval_and_only_runs_backend_tests(
    client, tmp_path, monkeypatch
):
    _prepare_workspace(client, tmp_path, monkeypatch)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="tests passed", stderr="")

    monkeypatch.setattr(agent_routes.subprocess, "run", fake_run)
    denied = client.post(
        "/api/agent/commands/run",
        json={"command_id": "backend_tests", "confirm_execution": False},
    )
    assert denied.status_code == 422
    assert calls == []

    approved = client.post(
        "/api/agent/commands/run",
        json={"command_id": "backend_tests", "confirm_execution": True},
    )
    assert approved.status_code == 200
    assert approved.json()["exit_code"] == 0
    assert approved.json()["output"] == "tests passed"
    command, kwargs = calls[0]
    assert command[-3:] == ["-m", "pytest", "-q"]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == tmp_path


def test_command_timeout_returns_bounded_utf8_output(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output=b"partial \xe2\x9c\x93 output",
            stderr=b"",
        )

    monkeypatch.setattr(agent_routes.subprocess, "run", fake_run)
    response = client.post(
        "/api/agent/commands/run",
        json={"command_id": "backend_tests", "confirm_execution": True},
    )

    assert response.status_code == 200
    assert response.json()["timed_out"] is True
    assert "partial" in response.json()["output"]


def test_source_is_not_sent_without_explicit_consent(client, tmp_path, monkeypatch):
    _prepare_workspace(client, tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        agent_routes,
        "create_code_change",
        lambda *args: calls.append(args),
    )

    response = client.post(
        "/api/agent/proposals",
        json={
            "instruction": "Change the value safely",
            "file_path": "backend/sample.py",
            "consent_to_send_source": False,
        },
    )

    assert response.status_code == 422
    assert calls == []


def test_local_security_scan_returns_findings_without_source_content(client, monkeypatch):
    sentinel = "secret-value-that-must-not-leak"
    monkeypatch.setattr(
        agent_routes,
        "run_local_security_scan",
        lambda: SecurityScanResponse(
            scanned_files=8,
            skipped_files=2,
            findings=[
                SecurityFinding(
                    rule_id="hardcoded-credential",
                    severity="high",
                    title="Possible credential",
                    file_path="backend/config.py",
                    line=12,
                    description="A secret-like pattern was found.",
                    recommendation="Remove and rotate if real.",
                    confidence="medium",
                )
            ],
            high_count=1,
            medium_count=0,
            low_count=0,
            limitations=["Local, pattern-based checks only."],
        ),
    )

    response = client.post("/api/agent/security-scan")

    assert response.status_code == 200
    assert response.json()["scanned_files"] == 8
    assert response.json()["findings"][0]["file_path"] == "backend/config.py"
    assert response.json()["findings"][0]["line"] == 12
    assert sentinel not in response.text


def test_public_web_research_api_returns_grounded_sources(client, monkeypatch):
    monkeypatch.setattr(
        agent_routes,
        "research_public_web",
        lambda query, settings: WebResearchResponse(
            answer=f"Rangkuman untuk: {query}",
            citations=[
                WebResearchCitation(
                    title="Sumber publik",
                    url="https://example.com/research",
                )
            ],
            model="gemini-test",
        ),
    )

    response = client.post(
        "/api/agent/research",
        json={"query": "Apa kabar perkembangan AI?"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "gemini"
    assert response.json()["answer"] == "Rangkuman untuk: Apa kabar perkembangan AI?"
    assert response.json()["citations"] == [
        {"title": "Sumber publik", "url": "https://example.com/research"}
    ]


def test_website_security_check_requires_allowlist_and_manual_confirmation(client):
    settings = Settings(
        _env_file=None,
        security_audit_allowed_hosts="example.com",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings

    denied = client.post(
        "/api/agent/website-security-check",
        json={"target_host": "other.example", "confirm_authorized": True},
    )
    unconfirmed = client.post(
        "/api/agent/website-security-check",
        json={"target_host": "example.com", "confirm_authorized": False},
    )

    assert denied.status_code == 403
    assert unconfirmed.status_code == 422
    assert any(
        "Konfirmasi izin pemeriksaan diperlukan." in detail["msg"]
        for detail in unconfirmed.json()["error"]["details"]
    )


def test_website_security_check_returns_mocked_passive_report(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        security_audit_allowed_hosts="example.com",
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(
        agent_routes,
        "check_website_security",
        lambda target_host, allowed_hosts, confirm_authorized, target_path="/": WebsiteSecurityCheckResponse(
            host=target_host,
            target_path=target_path,
            status_code=200,
            tls_verified=True,
            findings=[],
            checked_at="2026-11-12T00:00:00Z",
            limitations=["Mocked, passive check."],
        ),
    )

    response = client.post(
        "/api/agent/website-security-check",
        json={
            "target_host": "example.com",
            "target_path": "/account/profile",
            "confirm_authorized": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["host"] == "example.com"
    assert response.json()["target_path"] == "/account/profile"
    assert response.json()["tls_verified"] is True
    assert response.json()["limitations"] == ["Mocked, passive check."]


def test_website_security_check_is_disabled_without_allowlist(client):
    settings = Settings(_env_file=None, security_audit_allowed_hosts="")
    client.app.dependency_overrides[get_settings] = lambda: settings

    response = client.post(
        "/api/agent/website-security-check",
        json={"target_host": "example.com", "confirm_authorized": True},
    )

    assert response.status_code == 503
    assert "SECURITY_AUDIT_ALLOWED_HOSTS" in response.json()["error"]["message"]


def test_dependency_audit_requires_explicit_external_lookup_confirmation(
    client, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        agent_routes,
        "run_dependency_audit",
        lambda confirmed: calls.append(confirmed),
    )

    response = client.post(
        "/api/agent/dependency-audit",
        json={"confirm_external_lookup": False},
    )

    assert response.status_code == 422
    assert calls == []


def test_dependency_audit_returns_mocked_report_after_confirmation(client, monkeypatch):
    monkeypatch.setattr(
        agent_routes,
        "run_dependency_audit",
        lambda confirmed: DependencyAuditResponse(
            checked_at="2026-11-12T00:00:00Z",
            npm=DependencyAuditSource(
                packages_scanned=4,
                affected_packages=0,
                findings=[],
                truncated=False,
            ),
            pypi=DependencyAuditSource(
                packages_scanned=8,
                affected_packages=1,
                findings=[],
                truncated=False,
            ),
            limitations=["Mocked advisory lookup."],
        ),
    )

    response = client.post(
        "/api/agent/dependency-audit",
        json={"confirm_external_lookup": True},
    )

    assert response.status_code == 200
    assert response.json()["npm"]["packages_scanned"] == 4
    assert response.json()["pypi"]["affected_packages"] == 1
