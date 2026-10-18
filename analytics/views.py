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
