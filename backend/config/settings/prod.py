"""Ajustes de producción: endurecen la configuración base."""

from .base import *  # noqa: F403
from .base import REST_FRAMEWORK

DEBUG = False

# Endurecimiento básico
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# La API navegable es una herramienta de desarrollo
# En producción se sirve solo JSON.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
