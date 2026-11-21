from datetime import datetime, timezone


def test_create_list_update_and_delete_todo(client):
    due_at = "2026-11-12T08:30:00+07:00"
    reminder_at = "2026-11-12T08:00:00+07:00"
    created = client.post(
        "/api/todos",
        json={
            "title": "Kirim proposal",
            "notes": "Review sebelum kirim",
            "due_at": due_at,
            "reminder_at": reminder_at,
        },
    )
    assert created.status_code == 201
    todo = created.json()
    assert todo["title"] == "Kirim proposal"
    assert todo["due_at"] == "2026-11-12T01:30:00Z"
    assert todo["reminder_at"] == "2026-11-12T01:00:00Z"
    assert todo["reminder_sent_at"] is None
    assert todo["status"] == "pending"
    todo_id = todo["id"]

    listed = client.get("/api/todos")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [todo_id]

    completed = client.patch(f"/api/todos/{todo_id}", json={"status": "completed"})
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["reminder_at"] is None
    assert datetime.fromisoformat(
        completed.json()["completed_at"].replace("Z", "+00:00")
    ).tzinfo == timezone.utc
    assert client.get("/api/todos?status=pending").json() == []

    deleted = client.delete(f"/api/todos/{todo_id}")
    assert deleted.status_code == 204
    assert client.get("/api/todos").json() == []


def test_todo_validation_and_not_found(client):
    assert client.post("/api/todos", json={"title": "  "}).status_code == 422
    assert (
        client.post(
            "/api/todos", json={"title": "No timezone", "due_at": "2026-11-12T08:30:00"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/todos",
            json={"title": "No reminder timezone", "reminder_at": "2026-11-12T08:30:00"},
        ).status_code
        == 422
    )
    assert client.patch("/api/todos/1", json={"title": None}).status_code == 422
    assert client.patch("/api/todos/1", json={"status": None}).status_code == 422
    assert client.patch("/api/todos/999", json={"title": "Not found"}).status_code == 404
    assert client.delete("/api/todos/999").status_code == 404


def test_cors_allows_local_frontend_origins(client):
    origin = "http://localhost:5173"
    response = client.options(
        "/api/todos",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_reminder_can_be_rescheduled_or_cleared(client):
    created = client.post(
        "/api/todos",
        json={"title": "Atur reminder", "reminder_at": "2026-11-12T08:00:00Z"},
    ).json()

    rescheduled = client.patch(
        f"/api/todos/{created['id']}",
        json={"reminder_at": "2026-11-13T08:00:00Z"},
    ).json()
    assert rescheduled["reminder_at"] == "2026-11-13T08:00:00Z"
    assert rescheduled["reminder_sent_at"] is None

    cleared = client.patch(
        f"/api/todos/{created['id']}", json={"reminder_at": None}
    ).json()
    assert cleared["reminder_at"] is None


def test_projects_group_tasks_and_support_search_and_filters(client):
    project = client.post(
        "/api/projects",
        json={"name": "  Website  ", "description": "  Refresh landing page  "},
    )
    assert project.status_code == 201
    project_data = project.json()
    assert project_data["name"] == "Website"
    assert project_data["description"] == "Refresh landing page"

    task = client.post(
        "/api/todos",
        json={
            "title": "Review hero copy",
            "notes": "Check the landing page",
            "project_id": project_data["id"],
            "priority": "high",
        },
    )
    assert task.status_code == 201
    assert task.json()["project_id"] == project_data["id"]
    assert task.json()["priority"] == "high"
    filtered = client.get(
        f"/api/todos?project_id={project_data['id']}&priority=high&q=landing"
    ).json()
    assert filtered[0]["id"] == task.json()["id"]
    assert client.get(f"/api/todos?project_id={project_data['id']}&q=missing").json() == []
    missing_project = client.patch(
        f"/api/todos/{task.json()['id']}", json={"project_id": 999}
    )
    assert missing_project.status_code == 404

    deleted = client.delete(f"/api/projects/{project_data['id']}")
    assert deleted.status_code == 204
    remaining = client.get("/api/todos").json()
    assert remaining[0]["project_id"] is None
    assert remaining[0]["priority"] == "high"


def test_project_name_validation_and_conflict(client):
    assert client.post("/api/projects", json={"name": "  "}).status_code == 422
    created = client.post("/api/projects", json={"name": "Work"})
    assert created.status_code == 201
    renamed = client.patch(
        f"/api/projects/{created.json()['id']}", json={"name": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert client.post("/api/projects", json={"name": "Renamed"}).status_code == 409
    assert client.patch("/api/projects/999", json={"name": "Missing"}).status_code == 404
