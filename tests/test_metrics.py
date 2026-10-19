import pytest
from analytics.models import UserMetric


@pytest.mark.django_db
def test_metrics_summary(client):
    UserMetric.objects.create(user_id=1, event="login")
    UserMetric.objects.create(user_id=1, event="view_dashboard")
    UserMetric.objects.create(user_id=2, event="login")

    response = client.get("/api/metrics/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["total_events"] == 3
    assert data["unique_users"] == 2
