import ipaddress
import logging
import re
from datetime import datetime, timezone

import httpx

from app.schemas.agent import (
    WebsiteSecurityCheckResponse,
    WebsiteSecurityFinding,
)

logger = logging.getLogger("app.agent.website_security_check")

TIMEOUT_SECONDS = 8
LIMITATIONS = [
    "Hanya satu HTTPS GET ke path yang diminta pada host yang diizinkan; redirect tidak diikuti.",
    "Query string dan fragment URL tidak dikirim.",
    "Endpoint GET pada website dapat memiliki efek samping; gunakan hanya path yang diketahui aman dan read-only.",
    "Tidak melakukan crawl, login, eksploitasi, brute force, atau perubahan pada target.",
    "Pemeriksaan header dan TLS ini bersifat indikatif dan bukan audit keamanan penuh.",
]
HEADER_CHECKS = (
    (
        "Strict-Transport-Security",
        "medium",
        "Aktifkan HSTS dengan kebijakan yang sesuai setelah HTTPS dipastikan berfungsi.",
    ),
    (
        "Content-Security-Policy",
        "medium",
        "Rancang Content-Security-Policy yang sesuai dengan resource aplikasi.",
    ),
    (
        "X-Content-Type-Options",
        "low",
        "Pertimbangkan X-Content-Type-Options: nosniff.",
    ),
    (
        "Referrer-Policy",
        "low",
        "Tetapkan Referrer-Policy yang membatasi kebocoran informasi referrer.",
    ),
    (
        "Permissions-Policy",
        "low",
        "Batasi browser features yang tidak dibutuhkan melalui Permissions-Policy.",
    ),
)
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class WebsiteSecurityNotConfigured(Exception):
    """No website host has been explicitly allowlisted."""


class WebsiteSecurityScopeDenied(Exception):
    """The host or requested action is outside the authorized scope."""


class WebsiteSecurityConfigurationError(Exception):
    """The configured host allowlist contains an invalid entry."""


class WebsiteSecurityUnavailable(Exception):
    """The passive HTTPS request could not be completed."""


def _normalize_hostname(value: str) -> str:
    hostname = value.strip().rstrip(".").lower()
    if not hostname or len(hostname) > 253:
        raise ValueError("Host harus berupa nama domain yang valid.")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Host harus berupa nama domain yang valid.") from exc
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Masukkan nama domain, bukan alamat IP.")
    labels = hostname.split(".")
    if (
        len(labels) < 2
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal", ".test"))
        or any(not HOST_LABEL.fullmatch(label) for label in labels)
    ):
        raise ValueError("Host harus berupa domain publik yang valid.")
    return hostname


def _findings(headers: httpx.Headers) -> list[WebsiteSecurityFinding]:
    findings: list[WebsiteSecurityFinding] = []
    csp = headers.get("Content-Security-Policy", "").lower()
    has_frame_ancestors = any(
        directive.strip().startswith("frame-ancestors")
        for directive in csp.split(";")
    )
    frame_protection = bool(headers.get("X-Frame-Options")) or has_frame_ancestors
    checks = [
        *HEADER_CHECKS,
        (
            "X-Frame-Options / CSP frame-ancestors",
            "low",
            "Atur X-Frame-Options atau directive frame-ancestors pada CSP.",
        ),
    ]
    for header, severity, recommendation in checks:
        present = (
            frame_protection
            if header.startswith("X-Frame-Options")
            else bool(headers.get(header, "").strip())
        )
        findings.append(
            WebsiteSecurityFinding(
                header=header,
                status="present" if present else "missing",
                severity="info" if present else severity,
                recommendation=(
                    "Header terdeteksi; nilai dan kesesuaiannya perlu ditinjau terpisah."
                    if present
                    else recommendation
                ),
            )
        )
    return findings


def check_website_security(
    target_host: str,
    allowed_hosts: list[str],
    confirm_authorized: bool,
    target_path: str = "/",
    transport: httpx.BaseTransport | None = None,
) -> WebsiteSecurityCheckResponse:
    if not confirm_authorized:
        raise WebsiteSecurityScopeDenied("Konfirmasi izin pengujian diperlukan.")
    if (
        not target_path.startswith("/")
        or target_path.startswith("//")
        or "\\" in target_path
        or "?" in target_path
        or "#" in target_path
        or any(ord(character) < 32 or ord(character) == 127 for character in target_path)
    ):
        raise WebsiteSecurityScopeDenied("Path URL yang diminta tidak valid.")
    if not allowed_hosts:
        raise WebsiteSecurityNotConfigured(
            "Belum ada host yang diizinkan. Atur SECURITY_AUDIT_ALLOWED_HOSTS di backend."
        )
    try:
        hostname = _normalize_hostname(target_host)
        allowed = {_normalize_hostname(host) for host in allowed_hosts if host.strip()}
    except ValueError as exc:
        raise WebsiteSecurityConfigurationError(
            "Target atau host dalam SECURITY_AUDIT_ALLOWED_HOSTS tidak valid."
        ) from exc
    if not allowed:
        raise WebsiteSecurityNotConfigured(
            "Belum ada host yang diizinkan. Atur SECURITY_AUDIT_ALLOWED_HOSTS di backend."
        )
    if hostname not in allowed:
        raise WebsiteSecurityScopeDenied(
            "Host tidak ada di SECURITY_AUDIT_ALLOWED_HOSTS."
        )

    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            with client.stream(
                "GET",
                f"https://{hostname}{target_path}",
                headers={"Accept": "text/html", "User-Agent": "DigitalOperator-DefensiveCheck/0.1"},
            ) as response:
                status_code = response.status_code
                findings = _findings(response.headers)
    except httpx.HTTPError as exc:
        logger.warning(
            "Passive website security check failed for %s (%s)",
            hostname,
            type(exc).__name__,
        )
        raise WebsiteSecurityUnavailable(
            "Pemeriksaan HTTPS gagal. Pastikan host aktif dan sertifikat TLS valid."
        ) from exc

    return WebsiteSecurityCheckResponse(
        host=hostname,
        target_path=target_path,
        status_code=status_code,
        tls_verified=True,
        findings=findings,
        checked_at=datetime.now(timezone.utc),
        limitations=LIMITATIONS,
    )
