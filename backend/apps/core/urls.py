from django.urls import path

from apps.core.views import HealthCheckView, ReadinessCheckView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("health/ready/", ReadinessCheckView.as_view(), name="health-ready"),
]
