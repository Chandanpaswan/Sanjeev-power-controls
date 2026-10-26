from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import BlogCategory, BlogPost


def published_posts():
    return BlogPost.objects.filter(
        status=BlogPost.STATUS_PUBLISHED, published_at__lte=timezone.now()
    ).select_related("category", "author", "featured_asset")


def blog_list(request):
    posts = published_posts()
    categories = BlogCategory.objects.filter(
        posts__status=BlogPost.STATUS_PUBLISHED,
        posts__published_at__lte=timezone.now(),
    ).distinct()
    query = (request.GET.get("q") or "").strip()
    category_slug = (request.GET.get("category") or "").strip()
    tag = (request.GET.get("tag") or "").strip()

    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(excerpt__icontains=query)
            | Q(content__icontains=query)
            | Q(tags__icontains=query)
        )
    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if tag:
        posts = posts.filter(tags__icontains=tag)

    paginator = Paginator(posts, 6)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "blog/list.html",
        {
            "page_obj": page_obj,
            "posts": page_obj.object_list,
            "categories": categories,
            "query": query,
            "category_slug": category_slug,
            "tag": tag,
            "querystring": params.urlencode(),
            "active_nav": "blog",
        },
    )


def blog_detail(request, slug):
    post = get_object_or_404(published_posts(), slug=slug)
    return render(
        request,
        "blog/detail.html",
        {
            "post": post,
            "related_posts": post.related_posts(),
            "active_nav": "blog",
        },
    )
