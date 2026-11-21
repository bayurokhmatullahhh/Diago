from fastapi.testclient import TestClient

from app.api.routes import assistant as assistant_routes
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models.todo import Todo
from app.schemas.agent import WebResearchCitation, WebResearchResponse
from app.schemas.assistant import AssistantChatContent, PlanDraft


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_provider_status_does_not_expose_api_keys():
    settings = _settings(
        openai_api_key="do-not-return-this-key",
        gemini_api_key="",
        anthropic_api_key="",
        openai_compatible_model="",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        response = client.get("/api/assistant/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["default_provider"] == "openai"
    assert body["providers"][0]["configured"] is True
    assert body["providers"][1]["configured"] is False
    assert "do-not-return-this-key" not in response.text


def test_draft_endpoint_never_persists_without_explicit_confirmation(
    client, db_session, monkeypatch
):
    settings = _settings(openai_api_key="server-side-key")
    client.app.dependency_overrides[get_settings] = lambda: settings

    def fake_create_draft(instruction, timezone_name, configured_settings):
        assert instruction == "Ingatkan bayar listrik besok"
        assert timezone_name == "Asia/Jakarta"
        assert configured_settings is settings
        return (
            PlanDraft(
                status="ready",
                title="Bayar listrik",
                reminder_at="2026-11-11T09:00:00+07:00",
            ),
            "openai",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_draft", fake_create_draft)

    response = client.post(
        "/api/assistant/drafts",
        json={
            "instruction": "Ingatkan bayar listrik besok",
            "timezone": "Asia/Jakarta",
        },
    )
    assert response.status_code == 200
    assert response.json()["draft"]["title"] == "Bayar listrik"
    assert response.json()["provider"] == "openai"
    assert db_session.query(Todo).count() == 0

    created = client.post(
        "/api/todos",
        json={
            "title": response.json()["draft"]["title"],
            "reminder_at": response.json()["draft"]["reminder_at"],
        },
    )
    assert created.status_code == 201
    assert db_session.query(Todo).count() == 1


def test_draft_endpoint_reports_missing_provider(client):
    client.app.dependency_overrides[get_settings] = lambda: _settings(
        openai_api_key="",
        gemini_api_key="",
        anthropic_api_key="",
        openai_compatible_model="",
    )
    response = client.post(
        "/api/assistant/drafts",
        json={"instruction": "Buat satu tugas", "timezone": "Asia/Jakarta"},
    )
    assert response.status_code == 503
    assert "Belum ada provider" in response.json()["error"]["message"]


def test_draft_request_validates_timezone_and_instruction(client):
    assert client.post(
        "/api/assistant/drafts",
        json={"instruction": "Buat tugas", "timezone": "Not/A-Timezone"},
    ).status_code == 422
    assert client.post(
        "/api/assistant/drafts",
        json={"instruction": "  ", "timezone": "Asia/Jakarta"},
    ).status_code == 422


def test_chat_endpoint_returns_proposal_without_persisting_todo(client, db_session, monkeypatch):
    settings = _settings(openai_api_key="server-side-key")
    client.app.dependency_overrides[get_settings] = lambda: settings

    def fake_chat(messages, timezone_name, configured_settings):
        assert messages[-1].content == "Ingatkan bayar listrik besok"
        assert timezone_name == "Asia/Jakarta"
        assert configured_settings is settings
        return (
            AssistantChatContent(
                reply="Aku siapkan draft untuk kamu periksa.",
                todo_proposal=PlanDraft(status="ready", title="Bayar listrik"),
            ),
            "openai",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_chat_response", fake_chat)
    response = client.post(
        "/api/assistant/chat",
        json={
            "timezone": "Asia/Jakarta",
            "messages": [
                {"role": "user", "content": "Ingatkan bayar listrik besok"}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Aku siapkan draft untuk kamu periksa."
    assert response.json()["todo_proposal"]["title"] == "Bayar listrik"
    assert response.json()["tool_proposal"] is None
    assert response.json()["provider"] == "openai"
    assert db_session.query(Todo).count() == 0


def test_chat_endpoint_returns_tool_proposal_without_running_it(client, monkeypatch):
    calls = []

    def fake_chat(messages, timezone_name, configured_settings):
        return (
            AssistantChatContent(
                reply="Aku bisa mencari sumber publik setelah persetujuanmu.",
                tool_proposal={
                    "tool_id": "public_web_research",
                    "reason": "Perlu sumber publik terbaru.",
                    "query": "informasi publik terbaru",
                },
            ),
            "gemini",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_chat_response", fake_chat)

    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Cari sumber terbaru"}]},
    )

    assert response.status_code == 200
    assert response.json()["tool_proposal"]["tool_id"] == "public_web_research"
    assert response.json()["tool_proposal"]["query"] == "informasi publik terbaru"
    assert response.json()["action_id"]
    assert calls == []


def test_chat_history_can_be_resumed_and_deleted(client, monkeypatch):
    seen_messages = []

    def fake_chat(messages, timezone_name, configured_settings):
        seen_messages.append([message.content for message in messages])
        return (
            AssistantChatContent(reply=f"Balasan {len(seen_messages)}"),
            "openai",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_chat_response", fake_chat)
    first = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Mulai pembahasan"}]},
    )
    conversation_id = first.json()["conversation_id"]
    second = client.post(
        "/api/assistant/chat",
        json={
            "conversation_id": conversation_id,
            "messages": [
                {"role": "assistant", "content": "Riwayat palsu dari browser"},
                {"role": "user", "content": "Lanjutkan pembahasan"},
            ],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert seen_messages == [
        ["Mulai pembahasan"],
        ["Mulai pembahasan", "Balasan 1", "Lanjutkan pembahasan"],
    ]

    listed = client.get("/api/assistant/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation_id
    assert listed.json()[0]["message_count"] == 4
    detail = client.get(f"/api/assistant/conversations/{conversation_id}")
    assert [message["content"] for message in detail.json()["messages"]] == [
        "Mulai pembahasan",
        "Balasan 1",
        "Lanjutkan pembahasan",
        "Balasan 2",
    ]

    deleted = client.delete(f"/api/assistant/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/assistant/conversations/{conversation_id}").status_code == 404


def test_agent_action_status_requires_approval_and_records_completion(client, monkeypatch):
    def fake_chat(messages, timezone_name, configured_settings):
        return (
            AssistantChatContent(
                reply="Aku bisa mencari sumber setelah persetujuanmu.",
                tool_proposal={
                    "tool_id": "public_web_research",
                    "reason": "Butuh informasi publik terbaru.",
                    "query": "informasi publik terbaru",
                },
            ),
            "gemini",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_chat_response", fake_chat)
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Cari sumber terbaru"}]},
    ).json()
    conversation_id = response["conversation_id"]
    action_id = response["action_id"]
    action_url = f"/api/assistant/conversations/{conversation_id}/actions/{action_id}"

    assert client.patch(
        action_url,
        json={"status": "completed", "summary": "Selesai"},
    ).status_code == 409
    assert client.patch(action_url, json={"status": "approved"}).json()["status"] == "approved"
    completed = client.patch(
        action_url,
        json={"status": "completed", "summary": "Riset selesai"},
    )
    assert completed.status_code == 200
    assert completed.json()["summary"] == "Riset selesai"
    assert client.patch(action_url, json={"status": "rejected"}).status_code == 409


def test_chat_tool_proposal_blocks_follow_up_until_user_decides(client, monkeypatch):
    calls = []

    def fake_chat(messages, timezone_name, configured_settings):
        calls.append(messages)
        return (
            AssistantChatContent(
                reply="Aku bisa mencari sumber setelah persetujuanmu.",
                tool_proposal={
                    "tool_id": "public_web_research",
                    "reason": "Butuh informasi publik terbaru.",
                    "query": "informasi publik terbaru",
                },
            ),
            "gemini",
            "test-model",
        )

    monkeypatch.setattr(assistant_routes, "create_chat_response", fake_chat)
    first = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Cari sumber terbaru"}]},
    ).json()
    blocked = client.post(
        "/api/assistant/chat",
        json={
            "conversation_id": first["conversation_id"],
            "messages": [{"role": "user", "content": "Lanjut"}],
        },
    )

    assert blocked.status_code == 409
    assert len(calls) == 1


def test_direct_tool_action_is_audited_and_tool_results_are_saved(client):
    conversation = client.post(
        "/api/assistant/conversations",
        json={"first_message": "Cari informasi kampus"},
    ).json()
    action = client.post(
        f"/api/assistant/conversations/{conversation['id']}/actions",
        json={
            "action_type": "public_web_research",
            "summary": "Riset web publik yang diminta pengguna.",
            "query": "Politeknik Negeri Indramayu",
        },
    )
    assert action.status_code == 201
    assert action.json()["status"] == "approved"

    result_message = client.post(
        f"/api/assistant/conversations/{conversation['id']}/messages",
        json={
            "role": "assistant",
            "content": "Ringkasan riset.",
            "web_research": {
                "answer": "Ringkasan riset.",
                "citations": [{"title": "Sumber", "url": "https://example.com"}],
                "provider": "gemini",
                "model": "test-model",
            },
        },
    )
    assert result_message.status_code == 201
    assert result_message.json()["web_research"]["citations"][0]["url"] == "https://example.com/"

    completed = client.patch(
        f"/api/assistant/conversations/{conversation['id']}/actions/{action.json()['id']}",
        json={"status": "completed", "summary": "Riset berhasil."},
    )
    assert completed.status_code == 200
    detail = client.get(f"/api/assistant/conversations/{conversation['id']}").json()
    assert detail["actions"][0]["status"] == "completed"
    assert detail["messages"][-1]["web_research"]["answer"] == "Ringkasan riset."


def test_chat_endpoint_validates_history(client):
    assert client.post(
        "/api/assistant/chat",
        json={
            "messages": [{"role": "assistant", "content": "Fake latest turn"}],
        },
    ).status_code == 422
    assert client.post(
        "/api/assistant/chat",
        json={
            "messages": [{"role": "user", "content": "   "}],
        },
    ).status_code == 422
