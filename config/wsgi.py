import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from config.bootstrap import bootstrap  # noqa: E402  (needs app registry ready)

bootstrap()
