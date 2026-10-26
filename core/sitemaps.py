from django.contrib import sitemaps
from django.urls import reverse
from django.utils import timezone

from cms.models import BlogPost, Page
from products.models import Product


class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.7
    changefreq = "monthly"

    def items(self):
        return [
            "core:home",
            "core:about",
            "products:list",
            "core:quality",
            "blog:list",
            "core:contact",
            "core:privacy",
            "core:terms",
        ]

    def location(self, item):
        return reverse(item)


class ProductSitemap(sitemaps.Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return Product.objects.filter(active=True).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class ManagedPageSitemap(sitemaps.Sitemap):
    priority = 0.6
    changefreq = "monthly"

    def items(self):
        return Page.objects.filter(status=Page.STATUS_PUBLISHED).order_by("slug")

    def lastmod(self, obj):
        return obj.updated_at


class BlogPostSitemap(sitemaps.Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return BlogPost.objects.filter(
            status=BlogPost.STATUS_PUBLISHED, published_at__lte=timezone.now()
        ).order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "static": StaticViewSitemap,
    "products": ProductSitemap,
    "pages": ManagedPageSitemap,
    "blog": BlogPostSitemap,
}
