"""Template helpers for product-specific WhatsApp enquiry links."""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def product_whatsapp_link(context, product):
    """Return an encoded ``wa.me`` link for a product, or an empty string.

    The request is used to build an absolute product URL so the pre-filled
    WhatsApp message includes the exact page the visitor was viewing.
    """
    site = context.get("site_profile")
    if site is None or product is None:
        return ""
    return site.product_whatsapp_link(product, context.get("request"))
