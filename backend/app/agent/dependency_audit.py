import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.workspace import PROJECT_ROOT
from app.schemas.agent import (
    DependencyAuditResponse,
    DependencyAuditSource,
    DependencyFinding,
)

logger = logging.getLogger("app.agent.dependency_audit")

COMMAND_TIMEOUT_SECONDS = 180
MAX_FINDINGS = 200
MAX_ADVISORY_OUTPUT_BYTES = 5 * 1024 * 1024
LIMITATIONS = [
    "Nama dan versi dependency dikirim ke npm dan PyPI advisory services; source code dan secrets tidak dikirim.",
    "Hasil bergantung pada data advisory yang tersedia dan tidak mencakup salah konfigurasi runtime.",
    "Temuan dependency perlu ditinjau sebelum upgrade; audit ini tidak mengubah file atau memasang versi baru.",
]


class DependencyAuditNotConfigured(Exception):
    """A required local dependency audit tool or manifest is unavailable."""


class DependencyAuditUnavailable(Exception):
    """An advisory lookup failed or returned an unsupported result."""


class DependencyAuditScopeDenied(Exception):
    """External advisory lookup was not explicitly approved."""


def _run_json_command(
    command: list[str],
    cwd: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    try:
        result = runner(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DependencyAuditNotConfigured(
            "Tool audit dependency belum tersedia. Install requirements-dev.txt dan Node.js."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        logger.warning("Dependency audit command timed out: %s", command[0])
        raise DependencyAuditUnavailable(
            "Pencarian advisory dependency melewati batas waktu."
        ) from exc

    if result.returncode not in {0, 1}:
        logger.warning(
            "Dependency audit command failed (%s, exit %s)",
            command[0],
            result.returncode,
        )
        raise DependencyAuditUnavailable(
            "Layanan audit dependency gagal. Periksa koneksi dan tool audit."
        )
    if not isinstance(result.stdout, str):
        raise DependencyAuditUnavailable(
            "Layanan audit dependency tidak mengembalikan hasil."
        )
    if len(result.stdout.encode("utf-8")) > MAX_ADVISORY_OUTPUT_BYTES:
        raise DependencyAuditUnavailable(
            "Hasil audit dependency melebihi batas ukuran yang didukung."
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Dependency audit returned invalid JSON (%s)", command[0])
        raise DependencyAuditUnavailable(
            "Layanan audit dependency mengembalikan format yang tidak valid."
        ) from exc
    if not isinstance(payload, dict):
        raise DependencyAuditUnavailable(
            "Layanan audit dependency mengembalikan format yang tidak didukung."
        )
    return payload


def _npm_source(
    payload: dict[str, Any],
    package_lock: dict[str, Any],
) -> DependencyAuditSource:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise DependencyAuditUnavailable("Hasil npm audit tidak memiliki daftar temuan.")
    lock_packages = package_lock.get("packages", {})
    if not isinstance(lock_packages, dict):
        raise DependencyAuditUnavailable("package-lock.json tidak memiliki daftar paket.")

    findings: list[DependencyFinding] = []
    for package, vulnerability in sorted(vulnerabilities.items()):
        if not isinstance(vulnerability, dict):
            raise DependencyAuditUnavailable("Hasil npm audit tidak dapat dibaca.")
        via = vulnerability.get("via", [])
        if not isinstance(via, list):
            raise DependencyAuditUnavailable("Hasil npm audit tidak dapat dibaca.")
        direct_advisories = [item for item in via if isinstance(item, dict)]
        if not direct_advisories:
            direct_advisories = [{}]
        nodes = vulnerability.get("nodes", [])
        installed_version = "unknown"
        if isinstance(nodes, list):
            for node in nodes:
                package_info = lock_packages.get(node) if isinstance(node, str) else None
                if isinstance(package_info, dict) and isinstance(package_info.get("version"), str):
                    installed_version = package_info["version"]
                    break
        fix = vulnerability.get("fixAvailable")
        fixed_versions = (
            [fix["version"][:100]]
            if isinstance(fix, dict) and isinstance(fix.get("version"), str)
            else []
        )
        severity = vulnerability.get("severity")
        if severity not in {"low", "moderate", "high", "critical"}:
            severity = "unknown"
        for advisory in direct_advisories:
            source = advisory.get("source")
            advisory_ids = [str(source)[:100]] if source is not None else []
            title = advisory.get("title") or advisory.get("name") or f"Advisory untuk {package}"
            findings.append(
                DependencyFinding(
                    ecosystem="npm",
                    package=package[:200],
                    installed_version=installed_version[:100],
                    severity=severity,
                    advisory_ids=advisory_ids,
                    title=str(title)[:500],
                    fixed_versions=fixed_versions,
                )
            )
    total_packages = sum(
        1 for name in lock_packages if isinstance(name, str) and name
    )
    return DependencyAuditSource(
        packages_scanned=total_packages,
        affected_packages=len(vulnerabilities),
        findings=findings[:MAX_FINDINGS],
        truncated=len(findings) > MAX_FINDINGS,
    )


def _pypi_source(payload: dict[str, Any]) -> DependencyAuditSource:
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        raise DependencyAuditUnavailable("Hasil pip-audit tidak memiliki daftar paket.")

    findings: list[DependencyFinding] = []
    affected_packages: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise DependencyAuditUnavailable("Hasil pip-audit tidak dapat dibaca.")
        package = dependency.get("name")
        version = dependency.get("version")
        vulnerabilities = dependency.get("vulns", [])
        if (
            not isinstance(package, str)
            or not isinstance(version, str)
            or not isinstance(vulnerabilities, list)
        ):
            raise DependencyAuditUnavailable("Hasil pip-audit tidak dapat dibaca.")
        if vulnerabilities:
            affected_packages.add(package)
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise DependencyAuditUnavailable("Hasil pip-audit tidak dapat dibaca.")
            aliases = vulnerability.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            advisory_id = vulnerability.get("id")
            advisory_ids = [
                str(value)[:100]
                for value in [advisory_id, *aliases]
                if isinstance(value, str) and value
            ][:10]
            fixes = vulnerability.get("fix_versions", [])
            fixed_versions = (
                [value[:100] for value in fixes if isinstance(value, str)][:10]
                if isinstance(fixes, list)
                else []
            )
            findings.append(
                DependencyFinding(
                    ecosystem="pypi",
                    package=package[:200],
                    installed_version=version[:100],
                    severity="unknown",
                    advisory_ids=advisory_ids,
                    title=f"Known advisory: {advisory_id}" if isinstance(advisory_id, str) else "Known package advisory",
                    fixed_versions=fixed_versions,
                )
            )
    return DependencyAuditSource(
        packages_scanned=len(dependencies),
        affected_packages=len(affected_packages),
        findings=findings[:MAX_FINDINGS],
        truncated=len(findings) > MAX_FINDINGS,
    )


def run_dependency_audit(
    confirm_external_lookup: bool,
    root: Path = PROJECT_ROOT,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    npm_executable: str | None = None,
    pip_audit_executable: str | None = None,
) -> DependencyAuditResponse:
    if not confirm_external_lookup:
        raise DependencyAuditScopeDenied(
            "Persetujuan pengiriman metadata dependency ke layanan advisory diperlukan."
        )
    if not (root / "frontend" / "package-lock.json").is_file():
        raise DependencyAuditNotConfigured("frontend/package-lock.json tidak ditemukan.")
    if not (root / "requirements-dev.txt").is_file():
        raise DependencyAuditNotConfigured("requirements-dev.txt tidak ditemukan.")

    npm_executable = npm_executable or shutil.which("npm")
    pip_audit_executable = pip_audit_executable or shutil.which("pip-audit")
    if not npm_executable or not pip_audit_executable:
        raise DependencyAuditNotConfigured(
            "Audit memerlukan Node.js/npm dan pip-audit. Install Node.js serta requirements-dev.txt."
        )
    run = runner or subprocess.run
    npm_payload = _run_json_command(
        [npm_executable, "audit", "--json"],
        root / "frontend",
        run,
    )
    try:
        package_lock = json.loads(
            (root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyAuditNotConfigured(
            "package-lock.json tidak dapat dibaca."
        ) from exc
    if not isinstance(package_lock, dict):
        raise DependencyAuditUnavailable("package-lock.json memiliki format yang tidak didukung.")

    pypi_payload = _run_json_command(
        [
            pip_audit_executable,
            "--format",
            "json",
            "--progress-spinner",
            "off",
            "-r",
            "requirements-dev.txt",
        ],
        root,
        run,
    )
    return DependencyAuditResponse(
        checked_at=datetime.now(timezone.utc),
        npm=_npm_source(npm_payload, package_lock),
        pypi=_pypi_source(pypi_payload),
        limitations=LIMITATIONS,
    )
