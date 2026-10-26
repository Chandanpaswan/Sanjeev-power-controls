"""First-start setup for ephemeral preview deployments.

Vercel's filesystem is ephemeral, so a preview deployment cannot keep a local
SQLite database or uploaded media between instances. When ``DJANGO_AUTO_SETUP``
is enabled, this module creates the schema and demo content the first time a
function instance boots.

Durable deployments (PostgreSQL plus object storage) should leave
``DJANGO_AUTO_SETUP`` disabled and run migrations as a release step instead.
"""
import logging
import os

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _enabled():
    return os.environ.get("DJANGO_AUTO_SETUP", "").strip().lower() in _TRUTHY


def _ensure_superuser(user_model):
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
    if not username or not password:
        return
    if user_model.objects.filter(username=username).exists():
        return
    user_model.objects.create_superuser(
        username=username,
        email=os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip(),
        password=password,
    )
    logger.warning("Created preview superuser %r.", username)


def bootstrap():
    """Prepare the database for a preview instance. Safe to call repeatedly."""
    if not _enabled():
        return

    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from products.models import Product

    call_command("migrate", interactive=False, verbosity=0)
    call_command("setup_roles", verbosity=0)
    if not Product.objects.exists():
        call_command("seed_demo", verbosity=0)
    _ensure_superuser(get_user_model())
