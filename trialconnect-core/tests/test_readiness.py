from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_readiness_endpoint() -> None:
    response = client.get("/api/v1/readiness")
    assert response.status_code == 200
    json_body = response.json()
    assert "ready" in json_body["status"] or "degraded" in json_body["status"]
    assert "database" in json_body
    assert "redis" in json_body
