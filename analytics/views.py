from django.db import connection
from django.http import JsonResponse
from .models import UserMetric


def health_check(request):
    """Health check endpoint to verify service readiness."""
    return JsonResponse({"status": "ok", "service": "victim-service"})


def metrics_summary(request):
    """Aggregate metrics summary computed via the ORM."""
    total = UserMetric.objects.count()
    users = UserMetric.objects.values("user_id").distinct().count()
    return JsonResponse({
        "status": "ok",
        "total_events": total,
        "unique_users": users,
    })


def user_activity_report(request):
    """Raw-SQL user activity report endpoint."""
    cursor = connection.cursor()
    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
    rows = cursor.fetchall()
    data = [{"user_id": r[0], "event": r[1], "ts": str(r[2])} for r in rows]
    return JsonResponse({"status": "ok", "data": data})
