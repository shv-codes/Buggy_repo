import pytest


@pytest.mark.django_db
def test_health_check_returns_ok(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "victim-service"
