"""Modelos de la cadena agrícola: de la parcela al silo analizado."""

from django.db import models

from farms.models.farm import Farm
from farms.models.ingestion import Sourced


class Plot(Sourced):
    """Parcela de cultivo de una explotación."""

    farm = models.ForeignKey(
        Farm,
        verbose_name="granja",
        on_delete=models.CASCADE,
        related_name="plots",
    )
    name = models.CharField("nombre", max_length=120)
    code = models.CharField("código", max_length=40)
    area_ha = models.DecimalField("superficie (ha)", max_digits=7, decimal_places=4)

    class Meta:
        verbose_name = "parcela"
        verbose_name_plural = "parcelas"
        ordering = ["farm", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "code"],
                name="farms_plot_unique_farm_code",
            ),
            models.CheckConstraint(
                condition=models.Q(area_ha__gt=0),
                name="farms_plot_area_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.area_ha} ha)"


class Crop(Sourced):
    """Campaña de cultivo sobre una parcela: qué se sembró y cuándo se recogió."""

    class Species(models.TextChoices):
        """Especies forrajeras contempladas."""

        MAIZE = "maize", "Maíz forrajero"
        ITALIAN_RYEGRASS = "italian_ryegrass", "Raigrás italiano"
        GRASS_MIX = "grass_mix", "Pradera polifita"
        OTHER = "other", "Otra"

    plot = models.ForeignKey(
        Plot,
        verbose_name="parcela",
        on_delete=models.CASCADE,
        related_name="crops",
    )
    species = models.CharField("especie", max_length=16, choices=Species)
    season = models.PositiveSmallIntegerField("campaña")
    sowing_date = models.DateField("siembra", null=True, blank=True)
    harvest_date = models.DateField("cosecha", null=True, blank=True)

    class Meta:
        verbose_name = "cultivo"
        verbose_name_plural = "cultivos"
        ordering = ["-season", "plot"]
        constraints = [
            models.UniqueConstraint(
                fields=["plot", "season", "species"],
                name="farms_crop_unique_plot_season_species",
            ),
            models.CheckConstraint(
                condition=models.Q(sowing_date__isnull=True)
                | models.Q(harvest_date__isnull=True)
                | models.Q(harvest_date__gte=models.F("sowing_date")),
                name="farms_crop_harvest_after_sowing",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_species_display()} · {self.plot.name} · {self.season}"


class Silage(Sourced):
    """Silo de forraje conservado, procedente de una campaña de cultivo."""

    crop = models.ForeignKey(
        Crop,
        verbose_name="cultivo",
        on_delete=models.CASCADE,
        related_name="silages",
    )
    code = models.CharField("código del silo", max_length=40)
    sealed_date = models.DateField("cierre", null=True, blank=True)
    opened_date = models.DateField("apertura", null=True, blank=True)

    class Meta:
        verbose_name = "ensilado"
        verbose_name_plural = "ensilados"
        ordering = ["-sealed_date", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["crop", "code"],
                name="farms_silage_unique_crop_code",
            ),
            models.CheckConstraint(
                condition=models.Q(sealed_date__isnull=True)
                | models.Q(opened_date__isnull=True)
                | models.Q(opened_date__gte=models.F("sealed_date")),
                name="farms_silage_opened_after_sealed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.crop.get_species_display()} {self.crop.season}"


class NIRAnalysis(Sourced):
    """Análisis NIR de un ensilado: la cabecera de la muestra.

    Los valores no son columnas de este modelo: cuelgan como resultados por
    analito, de modo que el mismo esquema sirva para el forraje y para la leche.
    """

    silage = models.ForeignKey(
        Silage,
        verbose_name="ensilado",
        on_delete=models.CASCADE,
        related_name="nir_analyses",
    )
    date = models.DateField("fecha del análisis")
    laboratory = models.CharField("laboratorio", max_length=120, blank=True)

    class Meta:
        verbose_name = "análisis NIR"
        verbose_name_plural = "análisis NIR"
        ordering = ["-date", "silage"]
        constraints = [
            models.UniqueConstraint(
                fields=["silage", "date"],
                name="farms_niranalysis_unique_silage_date",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="farms_niranalysis_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.silage.code} · NIR {self.date}"


class RawMaterial(models.Model):
    """Materia prima comprada que puede entrar en una ración."""

    class Category(models.TextChoices):
        """Familias de materia prima."""

        CONCENTRATE = "concentrate", "Concentrado"
        FORAGE = "forage", "Forraje"
        BYPRODUCT = "byproduct", "Subproducto"
        MINERAL = "mineral", "Corrector mineral-vitamínico"
        OTHER = "other", "Otra"

    name = models.CharField("nombre", max_length=120, unique=True)
    category = models.CharField("categoría", max_length=11, choices=Category)

    class Meta:
        verbose_name = "materia prima"
        verbose_name_plural = "materias primas"
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name
