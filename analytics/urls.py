from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("metrics/", views.metrics_summary, name="metrics_summary"),
    path("reports/user-activity/", views.user_activity_report, name="user_activity_report"),
]
