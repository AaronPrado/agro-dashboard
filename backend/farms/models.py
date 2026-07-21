"""Modelos del dominio: granjas, animales y sus registros de producción."""

from django.db import models


class Farm(models.Model):
    """Explotación ganadera. Raíz de la jerarquía del dominio."""

    name = models.CharField("nombre", max_length=120)
    code = models.SlugField("código", max_length=30, unique=True)
    municipality = models.CharField("municipio", max_length=100)
    province = models.CharField("provincia", max_length=100)
    created_at = models.DateTimeField("alta en el sistema", auto_now_add=True)

    class Meta:
        verbose_name = "granja"
        verbose_name_plural = "granjas"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
