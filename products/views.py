from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator

from .models import Category, Product


def product_list(request):
    products = Product.objects.filter(
        active=True, category__is_active=True
    ).select_related("category")
    categories = (
        Category.objects.filter(is_active=True)
        .annotate(active_count=Count("products", filter=Q(products__active=True)))
        .filter(active_count__gt=0)
        .order_by("name")
    )

    query = (request.GET.get("q") or "").strip()
    category_slug = (request.GET.get("category") or "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(specifications__icontains=query)
        )

    selected_category = None
    if category_slug:
        selected_category = categories.filter(slug=category_slug).first()
        if selected_category:
            products = products.filter(category=selected_category)

    products = products.order_by("-featured", "name")
    paginator = Paginator(products, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    query_params = request.GET.copy()
    query_params.pop("page", None)
    querystring = query_params.urlencode()

    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "total_count": paginator.count,
        "categories": categories,
        "selected_category": selected_category,
        "query": query,
        "querystring": querystring,
        "active_nav": "products",
    }
    return render(request, "products/list.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        slug=slug,
        active=True,
        category__is_active=True,
    )
    related = (
        Product.objects.filter(
            active=True, category=product.category, category__is_active=True
        )
        .exclude(pk=product.pk)
        .select_related("category")[:3]
    )
    return render(
        request,
        "products/detail.html",
        {
            "product": product,
            "related_products": related,
            "active_nav": "products",
        },
    )
