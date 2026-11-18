import json
import subprocess

import pytest

from app.agent.dependency_audit import (
    DependencyAuditScopeDenied,
    DependencyAuditUnavailable,
    run_dependency_audit,
)


def _prepare_manifests(root):
    (root / "frontend").mkdir()
    (root / "requirements-dev.txt").write_text(
        "-r requirements.txt\npytest>=8\n",
        encoding="utf-8",
    )
    (root / "frontend" / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"name": "digital-operator-web"},
                    "node_modules/react": {"version": "19.0.0"},
                    "node_modules/safe-package": {"version": "1.0.0"},
                }
            }
        ),
        encoding="utf-8",
    )


def test_dependency_audit_runs_fixed_advisory_commands_and_parses_findings(tmp_path):
    _prepare_manifests(tmp_path)
    calls = []
    npm_result = {
        "vulnerabilities": {
            "react": {
                "severity": "high",
                "via": [
                    {
                        "source": 1234,
                        "name": "react",
                        "title": "Example advisory",
                    }
                ],
                "nodes": ["node_modules/react"],
                "fixAvailable": {"name": "react", "version": "19.1.1"},
            }
        }
    }
    pypi_result = {
        "dependencies": [
            {
                "name": "fastapi",
                "version": "0.115.0",
                "vulns": [
                    {
                        "id": "PYSEC-2026-1",
                        "aliases": ["CVE-2026-0001"],
                        "fix_versions": ["0.116.0"],
                    }
                ],
            },
            {"name": "pytest", "version": "8.0.0", "vulns": []},
        ]
    }

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        payload = npm_result if command[0] == "npm.cmd" else pypi_result
        return subprocess.CompletedProcess(
            command,
            1 if command[0] == "npm.cmd" else 0,
            stdout=json.dumps(payload),
            stderr="",
        )

    result = run_dependency_audit(
        True,
        tmp_path,
        runner=fake_run,
        npm_executable="npm.cmd",
        pip_audit_executable="pip-audit",
    )

    assert len(calls) == 2
    assert calls[0][0] == ["npm.cmd", "audit", "--json"]
    assert calls[1][0][-1] == "requirements-dev.txt"
    assert all(call[1]["shell"] is False for call in calls)
    assert result.npm.affected_packages == 1
    assert result.npm.findings[0].installed_version == "19.0.0"
    assert result.npm.findings[0].fixed_versions == ["19.1.1"]
    assert result.pypi.affected_packages == 1
    assert result.pypi.findings[0].advisory_ids == [
        "PYSEC-2026-1",
        "CVE-2026-0001",
    ]


def test_dependency_audit_requires_external_lookup_consent(tmp_path):
    calls = []

    with pytest.raises(DependencyAuditScopeDenied):
        run_dependency_audit(
            False,
            tmp_path,
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_dependency_audit_rejects_malformed_advisory_responses(tmp_path):
    _prepare_manifests(tmp_path)
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        output = "not-json" if calls == 1 else json.dumps({"dependencies": []})
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    with pytest.raises(DependencyAuditUnavailable):
        run_dependency_audit(
            True,
            tmp_path,
            runner=fake_run,
            npm_executable="npm.cmd",
            pip_audit_executable="pip-audit",
        )

    assert calls == 1
