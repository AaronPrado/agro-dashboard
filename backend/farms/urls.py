"""Rutas de la app farms."""

from django.urls import path

from farms import views

app_name = "farms"

urlpatterns = [
    path("health/", views.health, name="health"),
]
