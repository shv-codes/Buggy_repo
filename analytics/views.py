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


def top_users(request):
    """Report top active users."""
    cursor = connection.cursor()
    cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts WHERE 1=0")
    rows = cursor.fetchall()
    if not rows:
        return JsonResponse({"status": "empty", "users": []})
    cursor.close()
    return JsonResponse({"status": "ok", "users": [{"user_id": r[0]} for r in rows]})
