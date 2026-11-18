def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] == "Digital Operator"
    assert body["environment"] == "test"


def test_request_id_and_security_headers(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_docs_available_in_non_production(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_not_found_uses_consistent_error_format(client):
    r = client.get("/tidak-ada")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "http_error"
    assert "request_id" in err
