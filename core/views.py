from urllib.parse import urlencode

from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from cms.models import Banner, BlogPost, FAQ, Page, PageSection, Testimonial
from enquiries.forms import EnquiryForm
from products.models import Category, Product

from .models import SiteSettings
from .sitemaps import SITEMAPS


def _managed_page(slug):
    """Return a published managed page, or raise 404 for a draft.

    A missing page row is allowed: the built-in template remains the fallback
    for a fresh install. A page that exists but is not published must never be
    visible publicly.
    """
    page = (
        Page.objects.filter(slug=slug)
        .prefetch_related(
            Prefetch(
                "sections",
                queryset=PageSection.objects.filter(is_active=True),
                to_attr="public_sections",
            )
        )
        .first()
    )
    if page and page.status != Page.STATUS_PUBLISHED:
        raise Http404("This page is not published.")
    return page


def _published_posts(limit=3):
    return BlogPost.objects.filter(
        status=BlogPost.STATUS_PUBLISHED, published_at__lte=timezone.now()
    ).select_related("category", "author")[:limit]


def home(request):
    featured = list(
        Product.objects.filter(active=True, category__is_active=True, featured=True)
        .select_related("category")
        .order_by("name")[:3]
    )
    if len(featured) < 3:
        fallback = (
            Product.objects.filter(active=True, category__is_active=True)
            .exclude(pk__in=[product.pk for product in featured])
            .select_related("category")
            .order_by("name")[: 3 - len(featured)]
        )
        featured.extend(fallback)

    categories = list(
        Category.objects.filter(is_active=True)
        .annotate(active_count=Count("products", filter=Q(products__active=True)))
        .filter(active_count__gt=0)
        .order_by("name")
    )

    category_cards = []
    for category in categories:
        sample = (
            Product.objects.filter(
                category=category, active=True, category__is_active=True
            )
            .exclude(image="")
            .only("name", "image")
            .first()
            or Product.objects.filter(
                category=category, active=True, category__is_active=True
            ).only("name", "image").first()
        )
        category_cards.append({"category": category, "sample": sample})

    return render(
        request,
        "pages/home.html",
        {
            "cms_page": _managed_page("home"),
            "featured_products": featured,
            "category_cards": category_cards,
            "banners": list(Banner.objects.filter(is_active=True)),
            "testimonials": list(
                Testimonial.objects.filter(is_approved=True, is_published=True)
            ),
            "faqs": list(FAQ.objects.filter(is_published=True)),
            "recent_posts": _published_posts(),
        },
    )


def about(request):
    return render(request, "pages/about.html", {"cms_page": _managed_page("about")})


def quality(request):
    return render(request, "pages/quality.html", {"cms_page": _managed_page("quality")})


def contact(request):
    initial = {}
    product_slug = (request.GET.get("product") or "").strip()
    if product_slug:
        product = Product.objects.filter(active=True, slug=product_slug).first()
        if product:
            initial["product"] = product.pk

    form = EnquiryForm(initial=initial)
    return render(
        request,
        "pages/contact.html",
        {
            "form": form,
            "selected_product": initial.get("product"),
            "cms_page": _managed_page("contact"),
        },
    )


def contact_success(request):
    reference = (request.GET.get("ref") or "").strip()
    if not reference.replace("-", "").isalnum() or len(reference) > 20:
        reference = ""
    return render(request, "pages/contact_success.html", {"reference": reference})


def privacy(request):
    return render(request, "pages/privacy.html", {"cms_page": _managed_page("privacy")})


def terms(request):
    return render(request, "pages/terms.html", {"cms_page": _managed_page("terms")})


def credits(request):
    return render(request, "pages/credits.html")


def page_detail(request, slug):
    """Render any published managed page that has no dedicated route."""
    page = (
        Page.objects.filter(slug=slug, status=Page.STATUS_PUBLISHED)
        .prefetch_related(
            Prefetch(
                "sections",
                queryset=PageSection.objects.filter(is_active=True),
                to_attr="public_sections",
            )
        )
        .first()
    )
    if not page:
        raise Http404("Page not found.")
    return render(request, "pages/generic.html", {"cms_page": page})


@require_GET
def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("core:sitemap"))
    try:
        site = SiteSettings.load()
    except Exception:
        site = None

    if site is not None and not site.allow_search_indexing:
        lines = ["User-agent: *", "Disallow: /", "", f"Sitemap: {sitemap_url}", ""]
        return HttpResponse("\n".join(lines), content_type="text/plain")

    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin-panel/",
        "Disallow: /django-admin/",
        "Disallow: /enquiries/",
        "",
    ]
    if site is not None and site.robots_extra.strip():
        lines.extend([site.robots_extra.strip(), ""])
    lines.extend([f"Sitemap: {sitemap_url}", ""])
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap(request):
    return sitemap_view(request, SITEMAPS)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)
