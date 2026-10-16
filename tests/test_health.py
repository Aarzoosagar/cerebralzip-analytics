"""Step 0 sanity test: the app starts and /health responds correctly."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vercel_origin_is_allowed_by_cors() -> None:
    origin = "https://cerebralzip-analytics.vercel.app"
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
