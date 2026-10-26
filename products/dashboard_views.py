from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.forms import staff_required
from core.models import ActivityLog
from core.utils import log_activity

from .forms import CategoryForm, ProductForm, ProductImageForm
from .models import Category, Product

GALLERY_LIMIT = 8

SORT_OPTIONS = {
    "name": ("name", "Name A–Z"),
    "-name": ("-name", "Name Z–A"),
    "newest": ("-created_at", "Newest first"),
    "oldest": ("created_at", "Oldest first"),
    "updated": ("-updated_at", "Recently updated"),
    "sku": ("sku", "SKU"),
    "category": ("category__name", "Category"),
}


def _product_queryset():
    return Product.objects.select_related("category").annotate(
        gallery_total=Count("gallery", distinct=True),
        enquiry_total=Count("enquiries", distinct=True),
    )


@staff_required
@permission_required("products.view_product", raise_exception=True)
def product_list(request):
    products = _product_queryset()
    query = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    status = (request.GET.get("status") or "").strip()
    sort = (request.GET.get("sort") or "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(sku__icontains=query)
            | Q(short_description__icontains=query)
            | Q(category__name__icontains=query)
        )
    if category_id.isdigit():
        products = products.filter(category_id=int(category_id))
    if status == "active":
        products = products.filter(active=True)
    elif status == "inactive":
        products = products.filter(active=False)
    elif status == "featured":
        products = products.filter(featured=True)
    elif status == "draft":
        products = products.filter(active=False)

    order = SORT_OPTIONS.get(sort, ("-featured", "name"))
    products = products.order_by(*order)

    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    status_counts = {
        "all": Product.objects.count(),
        "active": Product.objects.filter(active=True).count(),
        "inactive": Product.objects.filter(active=False).count(),
        "featured": Product.objects.filter(featured=True).count(),
    }

    return render(
        request,
        "dashboard/products/list.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "status_counts": status_counts,
            "categories": Category.objects.order_by("name"),
            "query": query,
            "selected_category": category_id,
            "status": status,
            "sort": sort,
            "sort_options": [
                (value, label) for value, (_, label) in SORT_OPTIONS.items()
            ],
            "querystring": params.urlencode(),
        },
    )


@staff_required
@permission_required("products.add_product", raise_exception=True)
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Product created: {product.name} ({product.sku})",
            target=product,
        )
        messages.success(
            request,
            f"Product “{product.name}” created. It is "
            f"{'live on the public catalogue' if product.active else 'saved as a draft'}.",
        )
        return redirect("dashboard:product_list")
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/products/form.html",
        {"form": form, "mode": "create"},
    )


@staff_required
@permission_required("products.change_product", raise_exception=True)
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Product updated: {product.name} ({product.sku})",
            target=product,
        )
        messages.success(request, f"Product “{product.name}” updated.")
        return redirect("dashboard:product_list")
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/products/form.html",
        {"form": form, "mode": "edit", "product": product},
    )


@staff_required
@permission_required("products.change_product", raise_exception=True)
@require_POST
def product_toggle_active(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.active = not product.active
    product.save(update_fields=["active", "updated_at"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Product {'published' if product.active else 'unpublished'}: {product.name}",
        target=product,
    )
    messages.success(
        request,
        f"“{product.name}” is now "
        f"{'published' if product.active else 'inactive (hidden from the public site)'}.",
    )
    return redirect(request.POST.get("next") or reverse("dashboard:product_list"))


@staff_required
@permission_required("products.change_product", raise_exception=True)
@require_POST
def product_toggle_featured(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.featured = not product.featured
    product.save(update_fields=["featured", "updated_at"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Product {'featured' if product.featured else 'unfeatured'}: {product.name}",
        target=product,
    )
    messages.success(
        request,
        f"“{product.name}” is {'now featured' if product.featured else 'no longer featured'}.",
    )
    return redirect(request.POST.get("next") or reverse("dashboard:product_list"))


@staff_required
@permission_required("products.add_product", raise_exception=True)
def product_duplicate(request, pk):
    source = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        base_sku = f"{source.sku}-COPY"
        sku = base_sku
        counter = 2
        while Product.objects.filter(sku__iexact=sku).exists():
            sku = f"{base_sku}{counter}"
            counter += 1

        with transaction.atomic():
            product = Product.objects.create(
                name=f"{source.name} (copy)"[:140],
                sku=sku,
                category=source.category,
                short_description=source.short_description,
                description=source.description,
                features=source.features,
                specifications=source.specifications,
                image=source.image,
                image_asset=source.image_asset,
                image_alt=source.image_alt,
                featured=False,
                active=False,
                seo_title=source.seo_title,
                seo_description=source.seo_description,
                seo_keywords=source.seo_keywords,
                canonical_url="",
            )
            for image in source.gallery.all():
                image.pk = None
                image.product = product
                image.save()

        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Product duplicated: {source.name} → {product.name} ({product.sku})",
            target=product,
        )
        messages.success(
            request,
            f"“{source.name}” duplicated as a draft. Review the copy before publishing.",
        )
        return redirect("dashboard:product_edit", pk=product.pk)

    return render(
        request,
        "dashboard/confirm_action.html",
        {
            "title": "Duplicate product",
            "object_label": source.name,
            "object_type": "product",
            "message": (
                "A copy will be created with a new SKU and a draft status. "
                "Gallery images and specifications are copied; enquiries are not."
            ),
            "confirm_label": "Duplicate product",
            "cancel_url": reverse("dashboard:product_list"),
        },
    )


@staff_required
@permission_required("products.delete_product", raise_exception=True)
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        name = product.name
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Product deleted: {name}",
            target=product,
        )
        product.delete()
        messages.success(request, f"Product “{name}” deleted.")
        return redirect("dashboard:product_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete product",
            "object_label": product.name,
            "object_type": "product",
            "warning": (
                "Enquiries linked to this product will remain, but will no longer "
                "show a product. This cannot be undone."
            ),
            "cancel_url": reverse("dashboard:product_list"),
        },
    )


# ---------------------------------------------------------------------------
# Product gallery
# ---------------------------------------------------------------------------
@staff_required
@permission_required("products.change_product", raise_exception=True)
def product_gallery(request, pk):
    product = get_object_or_404(Product, pk=pk)
    images = product.gallery.select_related("asset")
    form = ProductImageForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if images.count() >= GALLERY_LIMIT:
            messages.error(
                request,
                f"This product already has the maximum of {GALLERY_LIMIT} gallery images.",
            )
            return redirect("dashboard:product_gallery", pk=product.pk)
        if form.is_valid():
            image = form.save(commit=False)
            image.product = product
            image.order = image.order or images.count()
            image.save()
            log_activity(
                request,
                ActivityLog.ACTION_CREATE,
                f"Gallery image added to {product.name}",
                target=product,
            )
            messages.success(request, "Gallery image added.")
            return redirect("dashboard:product_gallery", pk=product.pk)
        messages.error(request, "The gallery image could not be saved. Please check the file.")

    return render(
        request,
        "dashboard/products/gallery.html",
        {
            "product": product,
            "images": images,
            "form": form,
            "gallery_limit": GALLERY_LIMIT,
            "image_count": images.count(),
            "can_add": images.count() < GALLERY_LIMIT,
        },
    )


@staff_required
@permission_required("products.change_product", raise_exception=True)
@require_POST
def product_gallery_delete(request, pk, image_pk):
    product = get_object_or_404(Product, pk=pk)
    image = get_object_or_404(product.gallery, pk=image_pk)
    image.delete()
    log_activity(
        request,
        ActivityLog.ACTION_DELETE,
        f"Gallery image removed from {product.name}",
        target=product,
    )
    messages.success(request, "Gallery image removed.")
    return redirect("dashboard:product_gallery", pk=product.pk)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@staff_required
@permission_required("products.view_category", raise_exception=True)
def category_list(request):
    categories = Category.objects.annotate(
        product_count=Count("products", distinct=True),
        active_count=Count("products", filter=Q(products__active=True), distinct=True),
    ).order_by("name")
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if query:
        categories = categories.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)

    return render(
        request,
        "dashboard/categories/list.html",
        {
            "categories": categories,
            "query": query,
            "status": status,
            "total_count": categories.count(),
            "all_count": Category.objects.count(),
            "active_count": Category.objects.filter(is_active=True).count(),
            "inactive_count": Category.objects.filter(is_active=False).count(),
        },
    )


@staff_required
@permission_required("products.add_category", raise_exception=True)
def category_create(request):
    form = CategoryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Category created: {category.name}",
            target=category,
        )
        messages.success(request, f"Category “{category.name}” created.")
        return redirect("dashboard:category_list")
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/categories/form.html",
        {"form": form, "mode": "create"},
    )


@staff_required
@permission_required("products.change_category", raise_exception=True)
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Category updated: {category.name}",
            target=category,
        )
        messages.success(request, f"Category “{category.name}” updated.")
        return redirect("dashboard:category_list")
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/categories/form.html",
        {"form": form, "mode": "edit", "category": category},
    )


@staff_required
@permission_required("products.delete_category", raise_exception=True)
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    product_count = category.products.count()

    if product_count:
        return render(
            request,
            "dashboard/confirm_delete.html",
            {
                "title": "Delete category",
                "object_label": category.name,
                "object_type": "category",
                "blocked": True,
                "warning": (
                    f"This category has {product_count} linked "
                    f"product{'s' if product_count != 1 else ''}. Django protects "
                    "this relationship, so reassign or delete those products before "
                    "deleting the category."
                ),
                "cancel_url": reverse("dashboard:category_list"),
            },
        )

    if request.method == "POST":
        name = category.name
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Category deleted: {name}",
            target_type="products.category",
            target_id=category.pk,
        )
        category.delete()
        messages.success(request, f"Category “{name}” deleted.")
        return redirect("dashboard:category_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete category",
            "object_label": category.name,
            "object_type": "category",
            "warning": (
                "This category has no products. Deleting it cannot be undone."
            ),
            "cancel_url": reverse("dashboard:category_list"),
        },
    )
