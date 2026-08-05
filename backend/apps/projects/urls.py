from rest_framework.routers import SimpleRouter

from apps.projects.views import ProjectViewSet

router = SimpleRouter(trailing_slash=True)
router.register("projects", ProjectViewSet, basename="project")

urlpatterns = router.urls
