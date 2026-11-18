import httpx
import pytest
from pydantic import ValidationError

from app.agent.website_security_check import (
    WebsiteSecurityConfigurationError,
    WebsiteSecurityNotConfigured,
    WebsiteSecurityScopeDenied,
    WebsiteSecurityUnavailable,
    check_website_security,
)
from app.schemas.agent import WebsiteSecurityCheckRequest


def test_website_check_makes_one_https_get_and_reports_header_presence():
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            headers={
                "Strict-Transport-Security": "max-age=31536000",
                "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
                "X-Content-Type-Options": "nosniff",
            },
            content=b"response body is not included in the report",
        )

    result = check_website_security(
        "Example.com",
        ["example.com"],
        True,
        target_path="/account/profile",
        transport=httpx.MockTransport(handler),
    )

    assert len(seen_requests) == 1
    assert seen_requests[0].method == "GET"
    assert str(seen_requests[0].url) == "https://example.com/account/profile"
    assert result.host == "example.com"
    assert result.target_path == "/account/profile"
    assert result.status_code == 200
    assert result.tls_verified is True
    assert [finding.status for finding in result.findings] == [
        "present",
        "present",
        "present",
        "missing",
        "missing",
        "present",
    ]


def test_website_check_does_not_follow_redirects():
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/"})

    result = check_website_security(
        "example.com",
        ["example.com"],
        True,
        transport=httpx.MockTransport(handler),
    )

    assert len(seen_requests) == 1
    assert result.status_code == 302
    assert result.host == "example.com"


def test_website_check_requires_authorization_before_network_access():
    calls = []

    with pytest.raises(WebsiteSecurityScopeDenied):
        check_website_security(
            "example.com",
            ["example.com"],
            False,
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )

    assert calls == []


def test_website_check_requires_exact_allowlisted_hostname():
    calls = []
    with pytest.raises(WebsiteSecurityScopeDenied):
        check_website_security(
            "other.example",
            ["example.com"],
            True,
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )
    assert calls == []


def test_website_check_rejects_query_strings_before_network_access():
    calls = []
    with pytest.raises(WebsiteSecurityScopeDenied):
        check_website_security(
            "example.com",
            ["example.com"],
            True,
            target_path="/account?token=secret",
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )
    assert calls == []


def test_website_check_requires_valid_configured_public_hostname():
    with pytest.raises(WebsiteSecurityNotConfigured):
        check_website_security("example.com", [], True)

    with pytest.raises(WebsiteSecurityConfigurationError):
        check_website_security("example.com", ["localhost"], True)

    with pytest.raises(WebsiteSecurityConfigurationError):
        check_website_security("127.0.0.1", ["127.0.0.1"], True)


@pytest.mark.parametrize(
    "target_host",
    ["https://example.com", "example.com/path", "localhost", "192.0.2.1"],
)
def test_website_check_request_rejects_urls_paths_and_local_or_ip_targets(target_host):
    with pytest.raises(ValidationError):
        WebsiteSecurityCheckRequest(
            target_host=target_host,
            confirm_authorized=True,
        )


@pytest.mark.parametrize(
    "target_path",
    ["relative", "//other.example/path", "/account?token=secret", "/account#details", "/account\\admin"],
)
def test_website_check_request_accepts_only_absolute_paths_without_query_or_fragment(target_path):
    with pytest.raises(ValidationError):
        WebsiteSecurityCheckRequest(
            target_host="example.com",
            target_path=target_path,
            confirm_authorized=True,
        )


def test_website_check_surfaces_transport_failures():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable")

    with pytest.raises(WebsiteSecurityUnavailable):
        check_website_security(
            "example.com",
            ["example.com"],
            True,
            transport=httpx.MockTransport(handler),
        )
