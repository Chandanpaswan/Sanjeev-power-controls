from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.forms import staff_required
from core.models import ActivityLog
from core.utils import log_activity, slug_is_reserved
from core.uploads import IMAGE_EXTENSIONS

from .forms import (
    BannerForm,
    BlogCategoryForm,
    BlogPostForm,
    FAQForm,
    MediaAssetEditForm,
    MediaAssetForm,
    MenuItemForm,
    PageForm,
    PageSectionFormSet,
    RedirectRuleForm,
    TestimonialForm,
)
from .models import (
    Banner,
    BlogCategory,
    BlogPost,
    FAQ,
    MediaAsset,
    MenuItem,
    Page,
    PageSection,
    RedirectRule,
    Testimonial,
)

PROTECTED_PAGE_SLUGS = {"home", "about", "quality", "contact", "privacy", "terms"}

# ---------------------------------------------------------------------------
# Website pages
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_page", raise_exception=True)
def page_list(request):
    pages = Page.objects.annotate(section_count=Count("sections"))
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if query:
        pages = pages.filter(
            Q(title__icontains=query)
            | Q(slug__icontains=query)
            | Q(hero_heading__icontains=query)
        )
    if status in {Page.STATUS_DRAFT, Page.STATUS_PUBLISHED}:
        pages = pages.filter(status=status)
    paginator = Paginator(pages.order_by("slug"), 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "dashboard/pages/list.html",
        {
            "pages": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "query": query,
            "status": status,
            "status_choices": Page.STATUS_CHOICES,
            "published_count": Page.objects.filter(status=Page.STATUS_PUBLISHED).count(),
            "draft_count": Page.objects.filter(status=Page.STATUS_DRAFT).count(),
            "querystring": params.urlencode(),
        },
    )


def _section_formset(request, page):
    formset = PageSectionFormSet(
        request.POST or None, request.FILES or None, instance=page
    )
    from core.uploads import image_asset_queryset

    assets = image_asset_queryset()
    for form in formset.forms:
        if "image_asset" in form.fields:
            form.fields["image_asset"].queryset = assets
            form.fields["image_asset"].empty_label = "No library image"
    return formset


def _clean_page_slug(form):
    slug = (form.cleaned_data.get("slug") or "").strip()
    if slug_is_reserved(slug):
        form.add_error("slug", "That slug is reserved for website administration.")
        return False
    return True


@staff_required
@permission_required("cms.add_page", raise_exception=True)
def page_create(request):
    form = PageForm(request.POST or None, request.FILES or None)
    page = Page()
    formset = _section_formset(request, page)
    if request.method == "POST":
        if form.is_valid() and _clean_page_slug(form):
            sections_valid = False
            with transaction.atomic():
                page = form.save(commit=False)
                page.updated_by = request.user
                page.save()
                formset = PageSectionFormSet(
                    request.POST, request.FILES, instance=page
                )
                if formset.is_valid():
                    formset.save()
                    sections_valid = True
                else:
                    transaction.set_rollback(True)
            if sections_valid:
                log_activity(
                    request,
                    ActivityLog.ACTION_CREATE,
                    f"Website page created: {page.title} (/{page.slug}/)",
                    target=page,
                )
                messages.success(request, f"Page “{page.title}” created.")
                return redirect("dashboard:page_list")
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/pages/form.html",
        {
            "form": form,
            "formset": formset,
            "page": page if page.pk else None,
            "mode": "create",
        },
    )


@staff_required
@permission_required("cms.change_page", raise_exception=True)
def page_edit(request, pk):
    page = get_object_or_404(Page, pk=pk)
    form = PageForm(request.POST or None, request.FILES or None, instance=page)
    formset = _section_formset(request, page)
    if request.method == "POST":
        if form.is_valid() and _clean_page_slug(form):
            if page.slug in PROTECTED_PAGE_SLUGS and (form.cleaned_data.get("slug") not in PROTECTED_PAGE_SLUGS):
                form.add_error(
                    "slug",
                    "This page key is wired into the public website and cannot be changed. Create a new page for a different URL.",
                )
            else:
                sections_valid = False
                with transaction.atomic():
                    page = form.save(commit=False)
                    page.updated_by = request.user
                    page.save()
                    formset = PageSectionFormSet(
                        request.POST, request.FILES, instance=page
                    )
                    if formset.is_valid():
                        formset.save()
                        sections_valid = True
                    else:
                        transaction.set_rollback(True)
                if sections_valid:
                    log_activity(
                        request,
                        ActivityLog.ACTION_UPDATE,
                        f"Website page updated: {page.title} (/{page.slug}/)",
                        target=page,
                    )
                    messages.success(request, f"Page “{page.title}” updated.")
                    return redirect("dashboard:page_list")
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/pages/form.html",
        {
            "form": form,
            "formset": formset,
            "page": page,
            "mode": "edit",
            "preview_url": page.get_absolute_url(),
        },
    )


@staff_required
@permission_required("cms.change_page", raise_exception=True)
@require_POST
def page_toggle_status(request, pk):
    page = get_object_or_404(Page, pk=pk)
    page.status = (
        Page.STATUS_DRAFT
        if page.status == Page.STATUS_PUBLISHED
        else Page.STATUS_PUBLISHED
    )
    page.updated_by = request.user
    page.save(update_fields=["status", "updated_by", "updated_at"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Page {page.get_status_display().lower()}: {page.title}",
        target=page,
    )
    messages.success(
        request,
        f"Page “{page.title}” is now {page.get_status_display().lower()}.",
    )
    return redirect(request.POST.get("next") or reverse("dashboard:page_list"))


@staff_required
@permission_required("cms.delete_page", raise_exception=True)
def page_delete(request, pk):
    page = get_object_or_404(Page, pk=pk)
    if page.slug in PROTECTED_PAGE_SLUGS:
        messages.error(
            request,
            "This page key is wired into the public website and cannot be deleted. "
            "Set it to draft to hide its managed content instead.",
        )
        return redirect("dashboard:page_edit", pk=page.pk)
    if request.method == "POST":
        title = page.title
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Website page deleted: {title} (/{page.slug}/)",
            target_type="cms.page",
            target_id=page.pk,
        )
        page.delete()
        messages.success(request, f"Page “{title}” deleted.")
        return redirect("dashboard:page_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete page",
            "object_label": page.title,
            "object_type": "page",
            "warning": "The page, its content and every page section will be permanently removed.",
            "cancel_url": reverse("dashboard:page_edit", args=[page.pk]),
        },
    )


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------
def _blog_queryset():
    return BlogPost.objects.select_related("category", "author", "featured_asset")


@staff_required
@permission_required("cms.view_blogpost", raise_exception=True)
def blog_list(request):
    posts = _blog_queryset()
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(excerpt__icontains=query)
            | Q(tags__icontains=query)
        )
    if status in {BlogPost.STATUS_DRAFT, BlogPost.STATUS_PUBLISHED}:
        posts = posts.filter(status=status)
    if category.isdigit():
        posts = posts.filter(category_id=int(category))
    paginator = Paginator(posts.order_by("-created_at"), 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "dashboard/blog/list.html",
        {
            "posts": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "query": query,
            "status": status,
            "selected_category": category,
            "categories": BlogCategory.objects.annotate(post_count=Count("posts")),
            "querystring": params.urlencode(),
            "published_count": BlogPost.objects.filter(
                status=BlogPost.STATUS_PUBLISHED
            ).count(),
            "draft_count": BlogPost.objects.filter(status=BlogPost.STATUS_DRAFT).count(),
        },
    )


@staff_required
@permission_required("cms.add_blogpost", raise_exception=True)
def blog_create(request):
    form = BlogPostForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        if not post.author_id:
            post.author = request.user
        post.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Blog post created: {post.title} ({post.get_status_display().lower()})",
            target=post,
        )
        messages.success(request, f"Blog post “{post.title}” created.")
        return redirect("dashboard:blog_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Write a blog post",
            "eyebrow": "Blog management",
            "description": "Draft posts are never shown publicly. Published posts appear on the public blog.",
            "submit_label": "Save post",
            "cancel_url": reverse("dashboard:blog_list"),
            "sections": form.section_fields(),
        },
    )


@staff_required
@permission_required("cms.change_blogpost", raise_exception=True)
def blog_edit(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    form = BlogPostForm(
        request.POST or None, request.FILES or None, instance=post, user=request.user
    )
    if request.method == "POST" and form.is_valid():
        post = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Blog post updated: {post.title}",
            target=post,
        )
        messages.success(request, f"Blog post “{post.title}” updated.")
        return redirect("dashboard:blog_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {post.title}",
            "eyebrow": "Blog management",
            "description": f"{post.get_status_display()} · {post.reading_minutes} minute read · slug /blog/{post.slug}/.",
            "submit_label": "Save post",
            "cancel_url": reverse("dashboard:blog_list"),
            "sections": form.section_fields(),
            "object": post,
            "preview_url": post.get_absolute_url() if post.is_public else None,
            "secondary_actions": [
                {
                    "label": "Manage categories",
                    "url": reverse("dashboard:blog_category_list"),
                    "icon": "layers",
                }
            ],
        },
    )


@staff_required
@permission_required("cms.change_blogpost", raise_exception=True)
@require_POST
def blog_toggle_status(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    post.status = (
        BlogPost.STATUS_DRAFT
        if post.status == BlogPost.STATUS_PUBLISHED
        else BlogPost.STATUS_PUBLISHED
    )
    if post.status == BlogPost.STATUS_PUBLISHED and not post.published_at:
        post.published_at = timezone.now()
    post.save(update_fields=["status", "published_at", "updated_at"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Blog post {post.get_status_display().lower()}: {post.title}",
        target=post,
    )
    messages.success(
        request,
        f"“{post.title}” is now {post.get_status_display().lower()}.",
    )
    return redirect(request.POST.get("next") or reverse("dashboard:blog_list"))


@staff_required
@permission_required("cms.delete_blogpost", raise_exception=True)
def blog_delete(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == "POST":
        title = post.title
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Blog post deleted: {title}",
            target_type="cms.blogpost",
            target_id=post.pk,
        )
        post.delete()
        messages.success(request, f"Blog post “{title}” deleted.")
        return redirect("dashboard:blog_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete blog post",
            "object_label": post.title,
            "object_type": "blog post",
            "warning": "The article will be permanently removed from the public blog.",
            "cancel_url": reverse("dashboard:blog_edit", args=[post.pk]),
        },
    )


# ---------------------------------------------------------------------------
# Blog categories
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_blogcategory", raise_exception=True)
def blog_category_list(request):
    categories = BlogCategory.objects.annotate(post_count=Count("posts")).order_by("name")
    return render(
        request,
        "dashboard/blog/categories.html",
        {"categories": categories, "total_count": categories.count()},
    )


@staff_required
@permission_required("cms.add_blogcategory", raise_exception=True)
def blog_category_create(request):
    form = BlogCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Blog category created: {category.name}",
            target=category,
        )
        messages.success(request, f"Blog category “{category.name}” created.")
        return redirect("dashboard:blog_category_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add blog category",
            "eyebrow": "Blog management",
            "description": "Categories group articles on the public blog.",
            "submit_label": "Create category",
            "cancel_url": reverse("dashboard:blog_category_list"),
            "sections": [
                {
                    "title": "Category",
                    "description": "",
                    "fields": [form["name"], form["slug"], form["description"]],
                }
            ],
        },
    )


@staff_required
@permission_required("cms.change_blogcategory", raise_exception=True)
def blog_category_edit(request, pk):
    category = get_object_or_404(BlogCategory, pk=pk)
    form = BlogCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Blog category updated: {category.name}",
            target=category,
        )
        messages.success(request, f"Blog category “{category.name}” updated.")
        return redirect("dashboard:blog_category_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {category.name}",
            "eyebrow": "Blog management",
            "description": f"{category.posts.count()} article(s) use this category.",
            "submit_label": "Save category",
            "cancel_url": reverse("dashboard:blog_category_list"),
            "sections": [
                {
                    "title": "Category",
                    "description": "",
                    "fields": [form["name"], form["slug"], form["description"]],
                }
            ],
        },
    )


@staff_required
@permission_required("cms.delete_blogcategory", raise_exception=True)
def blog_category_delete(request, pk):
    category = get_object_or_404(BlogCategory, pk=pk)
    post_count = category.posts.count()
    if request.method == "POST":
        name = category.name
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Blog category deleted: {name} ({post_count} posts kept uncategorised)",
        )
        category.delete()
        messages.success(
            request,
            f"Category “{name}” deleted. {post_count} article(s) were kept without a category.",
        )
        return redirect("dashboard:blog_category_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete blog category",
            "object_label": category.name,
            "object_type": "blog category",
            "warning": f"{post_count} article(s) will be kept but will no longer have a category.",
            "cancel_url": reverse("dashboard:blog_category_list"),
        },
    )


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_mediaasset", raise_exception=True)
def media_list(request):
    assets = MediaAsset.objects.select_related("uploaded_by")
    query = (request.GET.get("q") or "").strip()
    file_type = (request.GET.get("type") or "").strip()
    if query:
        assets = assets.filter(
            Q(title__icontains=query)
            | Q(alt_text__icontains=query)
            | Q(caption__icontains=query)
            | Q(file__icontains=query)
        )
    if file_type in {MediaAsset.TYPE_IMAGE, MediaAsset.TYPE_DOCUMENT}:
        assets = assets.filter(file_type=file_type)
    paginator = Paginator(assets, 24)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "dashboard/media/list.html",
        {
            "assets": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "query": query,
            "file_type": file_type,
            "upload_form": MediaAssetForm(),
            "image_count": MediaAsset.objects.filter(
                file_type=MediaAsset.TYPE_IMAGE
            ).count(),
            "document_count": MediaAsset.objects.filter(
                file_type=MediaAsset.TYPE_DOCUMENT
            ).count(),
            "querystring": params.urlencode(),
        },
    )


@staff_required
@permission_required("cms.add_mediaasset", raise_exception=True)
def media_upload(request):
    form = MediaAssetForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        asset = form.save(commit=False)
        upload = form.cleaned_data.get("file")
        suffix = Path(getattr(upload, "name", "")).suffix.lower()
        asset.file_type = (
            MediaAsset.TYPE_IMAGE if suffix in IMAGE_EXTENSIONS else MediaAsset.TYPE_DOCUMENT
        )
        asset.file_size = getattr(upload, "size", 0) or 0
        if asset.file_type == MediaAsset.TYPE_IMAGE:
            try:
                from PIL import Image

                upload.seek(0)
                with Image.open(upload) as probe:
                    asset.width, asset.height = probe.size
                upload.seek(0)
            except Exception:
                pass
        asset.uploaded_by = request.user
        asset.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Media file uploaded: {asset.filename}",
            target=asset,
        )
        messages.success(request, f"“{asset.filename}” uploaded to the media library.")
        return redirect("dashboard:media_list")

    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Upload media",
            "eyebrow": "Media library",
            "description": "JPG, PNG, WebP, GIF images (up to 3 MB) or PDF documents (up to 5 MB). Executable and script files are rejected.",
            "submit_label": "Upload file",
            "cancel_url": reverse("dashboard:media_list"),
            "sections": [
                {
                    "title": "File",
                    "description": "The file is stored under a unique generated name.",
                    "fields": [form["file"]],
                },
                {
                    "title": "Details",
                    "description": "Alt text is used by screen readers and search engines.",
                    "fields": [form["title"], form["alt_text"], form["caption"]],
                },
            ],
            "enctype": "multipart/form-data",
        },
    )


@staff_required
@permission_required("cms.change_mediaasset", raise_exception=True)
def media_edit(request, pk):
    asset = get_object_or_404(MediaAsset, pk=pk)
    form = MediaAssetEditForm(request.POST or None, instance=asset)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Media details updated: {asset.filename}",
            target=asset,
        )
        messages.success(request, "Media details updated.")
        return redirect("dashboard:media_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {asset.filename}",
            "eyebrow": "Media library",
            "description": f"{asset.get_file_type_display()} · {asset.width or '—'} × {asset.height or '—'} px · uploaded {asset.created_at:%d %b %Y}.",
            "submit_label": "Save details",
            "cancel_url": reverse("dashboard:media_list"),
            "sections": [
                {
                    "title": "Media details",
                    "description": "",
                    "fields": [form["title"], form["alt_text"], form["caption"]],
                }
            ],
            "object": asset,
            "preview_url": asset.file.url if asset.is_image else None,
        },
    )


@staff_required
@permission_required("cms.delete_mediaasset", raise_exception=True)
def media_delete(request, pk):
    asset = get_object_or_404(MediaAsset, pk=pk)
    usage = asset.usage
    if request.method == "POST":
        if usage:
            messages.error(
                request,
                "This file is in use and cannot be deleted. Remove it from the listed records first.",
            )
            return redirect("dashboard:media_list")
        filename = asset.filename
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Media file deleted: {filename}",
            target_type="cms.mediaasset",
            target_id=asset.pk,
        )
        asset.file.delete(save=False)
        asset.delete()
        messages.success(request, f"“{filename}” deleted from the media library.")
        return redirect("dashboard:media_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete media file",
            "object_label": asset.filename,
            "object_type": "media file",
            "warning": (
                "This file is currently used by: " + "; ".join(usage) + "."
                if usage
                else "The file will be permanently removed from storage."
            ),
            "cancel_url": reverse("dashboard:media_list"),
            "blocked": bool(usage),
        },
    )


# ---------------------------------------------------------------------------
# SEO
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_redirectrule", raise_exception=True)
def seo_overview(request):
    pages = Page.objects.all()
    posts = BlogPost.objects.all()
    return render(
        request,
        "dashboard/seo/index.html",
        {
            "pages": pages,
            "posts": posts,
            "redirects": RedirectRule.objects.all(),
            "pages_missing_title": pages.filter(seo_title="").count(),
            "pages_missing_description": pages.filter(seo_description="").count(),
            "posts_missing_title": posts.filter(seo_title="").count(),
            "posts_missing_description": posts.filter(seo_description="").count(),
            "noindex_pages": pages.filter(noindex=True).count(),
            "noindex_posts": posts.filter(noindex=True).count(),
            "site": _site_settings(),
        },
    )


def _site_settings():
    from core.models import SiteSettings

    return SiteSettings.load()


@staff_required
@permission_required("cms.add_redirectrule", raise_exception=True)
def redirect_create(request):
    form = RedirectRuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Redirect created: {rule.old_path} → {rule.new_path}",
            target=rule,
        )
        messages.success(request, "Redirect rule created.")
        return redirect("dashboard:seo_overview")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add redirect",
            "eyebrow": "SEO management",
            "description": "Redirect an old public URL to a current one. Administration paths are refused.",
            "submit_label": "Create redirect",
            "cancel_url": reverse("dashboard:seo_overview"),
            "sections": [
                {
                    "title": "Redirect rule",
                    "description": "",
                    "fields": [form["old_path"], form["new_path"], form["status_code"], form["is_active"]],
                }
            ],
        },
    )


@staff_required
@permission_required("cms.change_redirectrule", raise_exception=True)
def redirect_edit(request, pk):
    rule = get_object_or_404(RedirectRule, pk=pk)
    form = RedirectRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Redirect updated: {rule.old_path} → {rule.new_path}",
            target=rule,
        )
        messages.success(request, "Redirect rule updated.")
        return redirect("dashboard:seo_overview")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Edit redirect",
            "eyebrow": "SEO management",
            "description": f"{rule.old_path} → {rule.new_path}",
            "submit_label": "Save redirect",
            "cancel_url": reverse("dashboard:seo_overview"),
            "sections": [
                {
                    "title": "Redirect rule",
                    "description": "",
                    "fields": [form["old_path"], form["new_path"], form["status_code"], form["is_active"]],
                }
            ],
        },
    )


@staff_required
@permission_required("cms.delete_redirectrule", raise_exception=True)
def redirect_delete(request, pk):
    rule = get_object_or_404(RedirectRule, pk=pk)
    if request.method == "POST":
        label = f"{rule.old_path} → {rule.new_path}"
        log_activity(request, ActivityLog.ACTION_DELETE, f"Redirect deleted: {label}")
        rule.delete()
        messages.success(request, "Redirect rule deleted.")
        return redirect("dashboard:seo_overview")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete redirect",
            "object_label": f"{rule.old_path} → {rule.new_path}",
            "object_type": "redirect rule",
            "warning": "Visitors to the old path will no longer be redirected.",
            "cancel_url": reverse("dashboard:seo_overview"),
        },
    )


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_testimonial", raise_exception=True)
def testimonial_list(request):
    testimonials = Testimonial.objects.all()
    status = (request.GET.get("status") or "").strip()
    if status == "published":
        testimonials = testimonials.filter(is_published=True, is_approved=True)
    elif status == "pending":
        testimonials = testimonials.filter(Q(is_published=True) | Q(is_approved=False))
    elif status == "hidden":
        testimonials = testimonials.filter(is_published=False)
    return render(
        request,
        "dashboard/testimonials/list.html",
        {
            "testimonials": testimonials,
            "total_count": Testimonial.objects.count(),
            "published_count": Testimonial.objects.filter(
                is_published=True, is_approved=True
            ).count(),
            "pending_count": Testimonial.objects.filter(
                Q(is_published=True) | Q(is_approved=False)
            ).count(),
            "status": status,
        },
    )


@staff_required
@permission_required("cms.add_testimonial", raise_exception=True)
def testimonial_create(request):
    form = TestimonialForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        testimonial = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Testimonial created: {testimonial.customer_name}",
            target=testimonial,
        )
        messages.success(
            request,
            "Testimonial created. Only approved and published testimonials appear publicly.",
        )
        return redirect("dashboard:testimonial_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add testimonial",
            "eyebrow": "Testimonials",
            "description": "Only real, permission-granted testimonials should be approved. Draft content is never public.",
            "submit_label": "Create testimonial",
            "cancel_url": reverse("dashboard:testimonial_list"),
            "sections": form.section_fields()
            if hasattr(form, "section_fields")
            else [
                {
                    "title": "Testimonial",
                    "description": "",
                    "fields": [
                        form["customer_name"],
                        form["designation"],
                        form["company"],
                        form["quote"],
                        form["rating"],
                        form["order"],
                    ],
                },
                {
                    "title": "Image & visibility",
                    "description": "Approve before publishing.",
                    "fields": [
                        form["photo"],
                        form["photo_asset"],
                        form["is_approved"],
                        form["is_published"],
                    ],
                },
            ],
            "enctype": "multipart/form-data",
        },
    )


@staff_required
@permission_required("cms.change_testimonial", raise_exception=True)
def testimonial_edit(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    form = TestimonialForm(
        request.POST or None, request.FILES or None, instance=testimonial
    )
    if request.method == "POST" and form.is_valid():
        testimonial = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Testimonial updated: {testimonial.customer_name}",
            target=testimonial,
        )
        messages.success(request, "Testimonial updated.")
        return redirect("dashboard:testimonial_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {testimonial.customer_name}",
            "eyebrow": "Testimonials",
            "description": "Review the wording and approval status before publishing.",
            "submit_label": "Save testimonial",
            "cancel_url": reverse("dashboard:testimonial_list"),
            "sections": [
                {
                    "title": "Testimonial",
                    "description": "",
                    "fields": [
                        form["customer_name"],
                        form["designation"],
                        form["company"],
                        form["quote"],
                        form["rating"],
                        form["order"],
                    ],
                },
                {
                    "title": "Image & visibility",
                    "description": "Approve before publishing. Unapproved content is never shown publicly.",
                    "fields": [
                        form["photo"],
                        form["photo_asset"],
                        form["is_approved"],
                        form["is_published"],
                    ],
                },
            ],
            "enctype": "multipart/form-data",
            "object": testimonial,
        },
    )


@staff_required
@permission_required("cms.change_testimonial", raise_exception=True)
@require_POST
def testimonial_toggle(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if not testimonial.is_approved and not testimonial.is_published:
        messages.error(
            request,
            "Approve this testimonial before publishing it to the public site.",
        )
        return redirect(request.POST.get("next") or reverse("dashboard:testimonial_list"))
    testimonial.is_published = not testimonial.is_published
    testimonial.save(update_fields=["is_published"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Testimonial {'published' if testimonial.is_published else 'unpublished'}: {testimonial.customer_name}",
        target=testimonial,
    )
    messages.success(
        request,
        f"Testimonial is now {'published' if testimonial.is_published else 'hidden'}.",
    )
    return redirect(request.POST.get("next") or reverse("dashboard:testimonial_list"))


@staff_required
@permission_required("cms.delete_testimonial", raise_exception=True)
def testimonial_delete(request, pk):
    testimonial = get_object_or_404(Testimonial, pk=pk)
    if request.method == "POST":
        name = testimonial.customer_name
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Testimonial deleted: {name}",
            target_type="cms.testimonial",
            target_id=testimonial.pk,
        )
        testimonial.delete()
        messages.success(request, "Testimonial deleted.")
        return redirect("dashboard:testimonial_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete testimonial",
            "object_label": testimonial.customer_name,
            "object_type": "testimonial",
            "warning": "The testimonial will be permanently removed from the website.",
            "cancel_url": reverse("dashboard:testimonial_list"),
        },
    )


# ---------------------------------------------------------------------------
# FAQs
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_faq", raise_exception=True)
def faq_list(request):
    faqs = FAQ.objects.all()
    query = (request.GET.get("q") or "").strip()
    if query:
        faqs = faqs.filter(
            Q(question__icontains=query)
            | Q(answer__icontains=query)
            | Q(category__icontains=query)
        )
    return render(
        request,
        "dashboard/faqs/list.html",
        {
            "faqs": faqs,
            "total_count": FAQ.objects.count(),
            "published_count": FAQ.objects.filter(is_published=True).count(),
            "query": query,
        },
    )


@staff_required
@permission_required("cms.add_faq", raise_exception=True)
def faq_create(request):
    form = FAQForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        faq = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"FAQ created: {faq.question[:80]}",
            target=faq,
        )
        messages.success(request, "FAQ created.")
        return redirect("dashboard:faq_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add FAQ",
            "eyebrow": "FAQs",
            "description": "Use clear, factual answers. Only publish claims you can support.",
            "submit_label": "Create FAQ",
            "cancel_url": reverse("dashboard:faq_list"),
            "sections": [
                {
                    "title": "Question & answer",
                    "description": "",
                    "fields": [form["question"], form["answer"]],
                },
                {
                    "title": "Organisation",
                    "description": "",
                    "fields": [form["category"], form["order"], form["is_published"]],
                },
            ],
        },
    )


@staff_required
@permission_required("cms.change_faq", raise_exception=True)
def faq_edit(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    form = FAQForm(request.POST or None, instance=faq)
    if request.method == "POST" and form.is_valid():
        faq = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"FAQ updated: {faq.question[:80]}",
            target=faq,
        )
        messages.success(request, "FAQ updated.")
        return redirect("dashboard:faq_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Edit FAQ",
            "eyebrow": "FAQs",
            "description": faq.question,
            "submit_label": "Save FAQ",
            "cancel_url": reverse("dashboard:faq_list"),
            "sections": [
                {
                    "title": "Question & answer",
                    "description": "",
                    "fields": [form["question"], form["answer"]],
                },
                {
                    "title": "Organisation",
                    "description": "",
                    "fields": [form["category"], form["order"], form["is_published"]],
                },
            ],
            "object": faq,
        },
    )


@staff_required
@permission_required("cms.delete_faq", raise_exception=True)
def faq_delete(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    if request.method == "POST":
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"FAQ deleted: {faq.question[:80]}",
            target_type="cms.faq",
            target_id=faq.pk,
        )
        faq.delete()
        messages.success(request, "FAQ deleted.")
        return redirect("dashboard:faq_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete FAQ",
            "object_label": faq.question,
            "object_type": "FAQ",
            "warning": "The question will be permanently removed from the public FAQ list.",
            "cancel_url": reverse("dashboard:faq_list"),
        },
    )


# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_banner", raise_exception=True)
def banner_list(request):
    return render(
        request,
        "dashboard/banners/list.html",
        {
            "banners": Banner.objects.all(),
            "total_count": Banner.objects.count(),
            "active_count": Banner.objects.filter(is_active=True).count(),
        },
    )


@staff_required
@permission_required("cms.add_banner", raise_exception=True)
def banner_create(request):
    form = BannerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        banner = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Banner created: {banner.title}",
            target=banner,
        )
        messages.success(request, "Banner created.")
        return redirect("dashboard:banner_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add banner",
            "eyebrow": "Banners & sliders",
            "description": "The lowest ordered active banner is used as the public home page hero image.",
            "submit_label": "Create banner",
            "cancel_url": reverse("dashboard:banner_list"),
            "sections": [
                {
                    "title": "Content",
                    "description": "",
                    "fields": [form["title"], form["heading"], form["description"], form["cta_text"], form["cta_url"]],
                },
                {
                    "title": "Images",
                    "description": "Upload desktop and mobile versions, or choose library images.",
                    "fields": [
                        form["desktop_image"],
                        form["desktop_asset"],
                        form["mobile_image"],
                        form["mobile_asset"],
                    ],
                },
                {
                    "title": "Display",
                    "description": "",
                    "fields": [form["order"], form["is_active"]],
                },
            ],
            "enctype": "multipart/form-data",
        },
    )


@staff_required
@permission_required("cms.change_banner", raise_exception=True)
def banner_edit(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    form = BannerForm(request.POST or None, request.FILES or None, instance=banner)
    if request.method == "POST" and form.is_valid():
        banner = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Banner updated: {banner.title}",
            target=banner,
        )
        messages.success(request, "Banner updated.")
        return redirect("dashboard:banner_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {banner.title}",
            "eyebrow": "Banners & sliders",
            "description": f"Order {banner.order} · {'active' if banner.is_active else 'inactive'}.",
            "submit_label": "Save banner",
            "cancel_url": reverse("dashboard:banner_list"),
            "sections": [
                {
                    "title": "Content",
                    "description": "",
                    "fields": [form["title"], form["heading"], form["description"], form["cta_text"], form["cta_url"]],
                },
                {
                    "title": "Images",
                    "description": "Upload desktop and mobile versions, or choose library images.",
                    "fields": [
                        form["desktop_image"],
                        form["desktop_asset"],
                        form["mobile_image"],
                        form["mobile_asset"],
                    ],
                },
                {
                    "title": "Display",
                    "description": "",
                    "fields": [form["order"], form["is_active"]],
                },
            ],
            "enctype": "multipart/form-data",
            "object": banner,
            "preview_url": banner.desktop_url or None,
        },
    )


@staff_required
@permission_required("cms.delete_banner", raise_exception=True)
def banner_delete(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    if request.method == "POST":
        title = banner.title
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Banner deleted: {title}",
            target_type="cms.banner",
            target_id=banner.pk,
        )
        banner.delete()
        messages.success(request, f"Banner “{title}” deleted.")
        return redirect("dashboard:banner_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete banner",
            "object_label": banner.title,
            "object_type": "banner",
            "warning": "The banner will be permanently removed from the website.",
            "cancel_url": reverse("dashboard:banner_list"),
        },
    )


# ---------------------------------------------------------------------------
# Navigation menu
# ---------------------------------------------------------------------------
@staff_required
@permission_required("cms.view_menuitem", raise_exception=True)
def menu_list(request):
    return render(
        request,
        "dashboard/navigation/list.html",
        {
            "header_items": MenuItem.objects.filter(
                location=MenuItem.LOCATION_HEADER
            ).order_by("order", "pk"),
            "footer_items": MenuItem.objects.filter(
                location=MenuItem.LOCATION_FOOTER
            ).order_by("order", "pk"),
            "total_count": MenuItem.objects.count(),
        },
    )


@staff_required
@permission_required("cms.add_menuitem", raise_exception=True)
def menu_create(request):
    form = MenuItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Menu item created: {item.label}",
            target=item,
        )
        messages.success(request, f"Menu item “{item.label}” created.")
        return redirect("dashboard:menu_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add menu item",
            "eyebrow": "Navigation menu",
            "description": "Choose a managed page route or enter a custom URL. Only safe destinations are accepted.",
            "submit_label": "Create menu item",
            "cancel_url": reverse("dashboard:menu_list"),
            "sections": [
                {
                    "title": "Destination",
                    "description": "",
                    "fields": [form["label"], form["url_name"], form["url"]],
                },
                {
                    "title": "Display",
                    "description": "",
                    "fields": [form["location"], form["order"], form["is_active"], form["open_in_new_tab"]],
                },
            ],
        },
    )


@staff_required
@permission_required("cms.change_menuitem", raise_exception=True)
def menu_edit(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    form = MenuItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Menu item updated: {item.label}",
            target=item,
        )
        messages.success(request, f"Menu item “{item.label}” updated.")
        return redirect("dashboard:menu_list")
    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {item.label}",
            "eyebrow": "Navigation menu",
            "description": f"Currently resolves to {item.resolved_url}.",
            "submit_label": "Save menu item",
            "cancel_url": reverse("dashboard:menu_list"),
            "sections": [
                {
                    "title": "Destination",
                    "description": "",
                    "fields": [form["label"], form["url_name"], form["url"]],
                },
                {
                    "title": "Display",
                    "description": "",
                    "fields": [form["location"], form["order"], form["is_active"], form["open_in_new_tab"]],
                },
            ],
            "object": item,
        },
    )


@staff_required
@permission_required("cms.delete_menuitem", raise_exception=True)
def menu_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == "POST":
        label = item.label
        log_activity(request, ActivityLog.ACTION_DELETE, f"Menu item deleted: {label}")
        item.delete()
        messages.success(request, f"Menu item “{label}” deleted.")
        return redirect("dashboard:menu_list")
    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete menu item",
            "object_label": item.label,
            "object_type": "menu item",
            "warning": "The link will be removed from the public navigation.",
            "cancel_url": reverse("dashboard:menu_list"),
        },
    )


@staff_required
@permission_required("cms.change_menuitem", raise_exception=True)
@require_POST
def menu_move(request, pk, direction):
    item = get_object_or_404(MenuItem, pk=pk)
    if direction not in {"up", "down"}:
        messages.error(request, "Choose a valid move direction.")
        return redirect("dashboard:menu_list")

    with transaction.atomic():
        siblings = list(
            MenuItem.objects.select_for_update()
            .filter(location=item.location)
            .order_by("order", "pk")
        )
        index = next((i for i, sibling in enumerate(siblings) if sibling.pk == item.pk), None)
        if index is None:
            messages.error(request, "The menu item could not be found.")
            return redirect("dashboard:menu_list")
        swap_index = index - 1 if direction == "up" else index + 1
        if swap_index < 0 or swap_index >= len(siblings):
            messages.info(request, "This menu item is already at the edge of its section.")
            return redirect("dashboard:menu_list")
        # Normalise the ordering first so duplicate values cannot block the move.
        for position, sibling in enumerate(siblings, start=1):
            if sibling.order != position:
                sibling.order = position
                sibling.save(update_fields=["order"])
        first, second = siblings[index], siblings[swap_index]
        first.order, second.order = second.order, first.order
        first.save(update_fields=["order"])
        second.save(update_fields=["order"])

    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Menu item moved {direction}: {item.label}",
        target=item,
    )
    messages.success(request, f"Menu item “{item.label}” moved {direction}.")
    return redirect("dashboard:menu_list")
