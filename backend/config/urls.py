"""Configuración de URLs raíz del proyecto."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("farms.urls")),
]
