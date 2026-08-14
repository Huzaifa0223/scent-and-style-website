"""``django.contrib.sitemaps`` wiring (§34, roadmap Stage 12) — one
sitemap class per section, all mounted at the single ``/sitemap.xml``
roadmap gate 2 names ("includes every published product and category,
and excludes drafts").
"""

from __future__ import annotations

from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.db.models import QuerySet
from django.urls import reverse

from catalog.models import Category, Product


class ProductSitemap(Sitemap[Product]):
    changefreq = "weekly"
    priority = 0.8

    def items(self) -> QuerySet[Product]:
        # Published only — a draft or archived product's URL isn't a
        # real public page, and listing one would invite a crawler to a
        # 404 (or, worse, index a product the merchant deliberately
        # unpublished).
        return Product.objects.filter(status=Product.Status.PUBLISHED).order_by("pk")

    def lastmod(self, item: Product) -> datetime:
        return item.updated_at

    def location(self, item: Product) -> str:
        return item.get_absolute_url()


class CategorySitemap(Sitemap[Category]):
    changefreq = "weekly"
    priority = 0.6

    def items(self) -> QuerySet[Category]:
        return Category.objects.filter(is_published=True).order_by("pk")

    def lastmod(self, item: Category) -> datetime:
        return item.updated_at

    def location(self, item: Category) -> str:
        return item.get_absolute_url()


class StaticViewSitemap(Sitemap[str]):
    """Fixed, always-public pages with no per-object model behind them."""

    priority = 0.5
    changefreq = "daily"

    def items(self) -> list[str]:
        return ["storefront:home", "storefront:product_list", "orders:tracking"]

    def location(self, item: str) -> str:
        return reverse(item)
