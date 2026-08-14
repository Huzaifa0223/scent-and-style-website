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
from django.contrib.sitemaps.views import sitemap
from django.urls import URLPattern, URLResolver, include, path

from core.views import healthz, robots_txt
from storefront.sitemaps import CategorySitemap, ProductSitemap, StaticViewSitemap

sitemaps = {
    "products": ProductSitemap,
    "categories": CategorySitemap,
    "static": StaticViewSitemap,
}

urlpatterns: list[URLPattern | URLResolver] = [
    path("django-admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("accounts/", include("accounts.urls")),
    path("search/", include("search.urls")),
    path("cart/", include("cart.urls")),
    path("admin-portal/", include("portal.urls")),
    path("", include("orders.urls")),
    path("", include("storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
