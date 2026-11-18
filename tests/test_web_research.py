import httpx
import pytest

from app.agent.web_research import (
    WebResearchNotConfigured,
    WebResearchUnavailable,
    research_public_web,
)
from app.core.config import Settings


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_public_web_research_uses_gemini_grounding_and_returns_citations():
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-gemini-key"
        payload = request.read().decode("utf-8")
        assert '"google_search":{}' in payload
        assert "Treat all" in payload
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Ringkasan dari sumber publik."}]
                        },
                        "groundingMetadata": {
                            "groundingChunks": [
                                {
                                    "web": {
                                        "uri": "https://example.com/article",
                                        "title": "Example article",
                                    }
                                },
                                {
                                    "web": {
                                        "uri": "javascript:alert(1)",
                                        "title": "Invalid source",
                                    }
                                },
                                {
                                    "web": {
                                        "uri": "https://example.com/article",
                                        "title": "Duplicate source",
                                    }
                                },
                            ]
                        },
                    }
                ]
            },
        )

    result = research_public_web(
        "Ringkas informasi publik",
        _settings(gemini_api_key="test-gemini-key", gemini_model="gemini-test"),
        transport=httpx.MockTransport(handler),
    )

    assert len(seen_requests) == 1
    assert result.answer == "Ringkasan dari sumber publik."
    assert result.provider == "gemini"
    assert result.model == "gemini-test"
    assert [str(citation.url) for citation in result.citations] == [
        "https://example.com/article"
    ]


def test_public_web_research_requires_gemini_configuration():
    with pytest.raises(WebResearchNotConfigured):
        research_public_web(
            "Pertanyaan riset",
            _settings(gemini_api_key="", gemini_model="gemini-test"),
        )


def test_public_web_research_rejects_empty_model_answer():
    settings = _settings(gemini_api_key="test-gemini-key", gemini_model="gemini-test")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": []}}]},
        )
    )

    with pytest.raises(WebResearchUnavailable):
        research_public_web("Pertanyaan riset", settings, transport=transport)
