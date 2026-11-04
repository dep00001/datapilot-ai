from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "datapilot" in data["service"].lower()

def test_providers_endpoint():
    with TestClient(app) as client:
        # Providers endpoint requires auth
        r = client.get("/api/settings/providers")
        assert r.status_code in (200, 401)
