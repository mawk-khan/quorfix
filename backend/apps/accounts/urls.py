from django.urls import path

from apps.accounts.views import DemoLoginView, LoginView, LogoutView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("demo-login/", DemoLoginView.as_view(), name="demo-login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
