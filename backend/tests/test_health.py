from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["service"] == "bodegaplanr-backend"
    assert payload["status"] == "ok"
    assert "timestamp" in payload
