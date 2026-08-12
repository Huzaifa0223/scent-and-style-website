from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import URLPattern, path

from . import views

app_name = "accounts"

urlpatterns: list[URLPattern] = [
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
