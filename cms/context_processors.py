from __future__ import annotations

from .models import MenuItem


def site_content(request):
    """Expose managed navigation to every public template.

    If no menu rows exist yet, public templates fall back to their built-in
    navigation so a new deployment is never left without navigation.
    """
    try:
        header_menu = list(
            MenuItem.objects.filter(location=MenuItem.LOCATION_HEADER, is_active=True)
        )
        footer_menu = list(
            MenuItem.objects.filter(location=MenuItem.LOCATION_FOOTER, is_active=True)
        )
    except Exception:
        header_menu, footer_menu = [], []
    return {"header_menu": header_menu, "footer_menu": footer_menu}
