"""Root URL configuration.

Storefront and portal URLs are added in later stages as those apps gain
views (Stage 3 onward). Django's default 404/500 handlers automatically
render ``templates/404.html``/``500.html`` when ``DEBUG=False`` — no custom
handler functions are needed for that.
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, path

from core.views import healthz

urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
