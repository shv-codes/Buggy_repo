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


def export_csv(request):
    """Export user activity in CSV format."""
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts")
        rows = cursor.fetchall()
        return JsonResponse({"status": "ok", "format": "csv", "count": len(rows)})
    except Exception as e:
        if "cursor" in locals():
            cursor.close()
        return JsonResponse({"error": str(e)}, status=500)
