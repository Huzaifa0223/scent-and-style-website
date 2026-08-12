from __future__ import annotations

from django.urls import URLPattern, path

from search.views import SearchSuggestView

app_name = "search"

urlpatterns: list[URLPattern] = [
    path("suggest/", SearchSuggestView.as_view(), name="suggest"),
]
