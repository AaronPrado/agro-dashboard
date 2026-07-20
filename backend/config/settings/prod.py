"""Ajustes de producción: endurecen la configuración base."""

from .base import *  # noqa: F403

DEBUG = False

# Endurecimiento básico. ALLOWED_HOSTS llega de DJANGO_ALLOWED_HOSTS (base.py).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
