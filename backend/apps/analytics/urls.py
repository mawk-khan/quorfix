from django.urls import path

from apps.analytics.views import (
    ActiveProjectsView,
    DistributionsView,
    RecentActivityView,
    ResolutionTimeView,
    SummaryView,
    TrendsView,
    WorkloadView,
)

urlpatterns = [
    path("analytics/summary/", SummaryView.as_view(), name="analytics-summary"),
    path("analytics/trends/", TrendsView.as_view(), name="analytics-trends"),
    path(
        "analytics/resolution-time/", ResolutionTimeView.as_view(), name="analytics-resolution-time"
    ),
    path("analytics/distributions/", DistributionsView.as_view(), name="analytics-distributions"),
    path("analytics/workload/", WorkloadView.as_view(), name="analytics-workload"),
    path(
        "analytics/recent-activity/", RecentActivityView.as_view(), name="analytics-recent-activity"
    ),
    path(
        "analytics/active-projects/", ActiveProjectsView.as_view(), name="analytics-active-projects"
    ),
]
