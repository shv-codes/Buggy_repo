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


def db_probe(request):
    """Direct DB health probe using raw psycopg2 connection."""
    import psycopg2
    from django.conf import settings
    db_conf = settings.DATABASES["default"]
    conn = psycopg2.connect(
        host=db_conf.get("HOST", "localhost"),
        port=db_conf.get("PORT", 5432),
        dbname=db_conf.get("NAME", "victim_db"),
        user=db_conf.get("USER", "postgres"),
        password=db_conf.get("PASSWORD", "postgres"),
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    return JsonResponse({"status": "ok", "probe": "db_connected"})
