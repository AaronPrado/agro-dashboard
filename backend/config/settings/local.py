"""Ajustes de desarrollo local. No aptos para producción."""

from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
