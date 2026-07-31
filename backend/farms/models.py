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


class Animal(models.Model):
    """Vaca de una explotación, identificada por su crotal."""

    class Breed(models.TextChoices):
        """Razas presentes en el vacuno de leche gallego."""

        HOLSTEIN = "holstein", "Frisona"
        JERSEY = "jersey", "Jersey"
        PROCROSS = "procross", "Procross"
        BROWN_SWISS = "brown_swiss", "Parda Alpina"
        OTHER = "other", "Otra"

    farm = models.ForeignKey(
        Farm,
        verbose_name="granja",
        on_delete=models.CASCADE,
        related_name="animals",
    )
    ear_tag = models.CharField("crotal", max_length=20)
    birth_date = models.DateField("fecha de nacimiento")
    breed = models.CharField("raza", max_length=11, choices=Breed, default=Breed.HOLSTEIN)
    lactation_number = models.PositiveSmallIntegerField("número de lactación", default=0)
    last_calving_date = models.DateField("último parto", null=True, blank=True)
    culled_date = models.DateField("fecha de baja", null=True, blank=True)

    class Meta:
        verbose_name = "animal"
        verbose_name_plural = "animales"
        ordering = ["farm", "ear_tag"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "ear_tag"],
                name="farms_animal_unique_farm_ear_tag",
            ),
            models.CheckConstraint(
                condition=models.Q(culled_date__isnull=True)
                | models.Q(culled_date__gte=models.F("birth_date")),
                name="farms_animal_culled_after_birth",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ear_tag} ({self.get_breed_display()})"

    @property
    def is_active(self) -> bool:
        """Indica si el animal sigue en la explotación.

        No hay campo propio: la baja se representa por la presencia de `culled_date`.
        """
        return self.culled_date is None


class DailyYield(models.Model):
    """Producción diaria registrada para un animal."""

    animal = models.ForeignKey(
        Animal,
        verbose_name="animal",
        on_delete=models.CASCADE,
        related_name="daily_yields",
    )
    date = models.DateField("fecha")
    liters = models.DecimalField("litros", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "producción diaria"
        verbose_name_plural = "producciones diarias"
        ordering = ["-date", "animal"]
        constraints = [
            models.UniqueConstraint(
                fields=["animal", "date"],
                name="farms_dailyyield_unique_animal_date",
            ),
            models.CheckConstraint(
                condition=models.Q(liters__isnull=True) | models.Q(liters__gte=0),
                name="farms_dailyyield_liters_not_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="farms_dailyyield_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.animal.ear_tag} · {self.date} · {self.liters} L"


class MilkRecord(models.Model):
    """Control lechero mensual: analítica de calidad de la leche de un animal."""

    # Límite legal de células somáticas en leche cruda de vaca en la UE,
    # fijado por el Reglamento (CE) 853/2004. Base del umbral de alerta.
    LEGAL_SCC_LIMIT = 400_000

    animal = models.ForeignKey(
        Animal,
        verbose_name="animal",
        on_delete=models.CASCADE,
        related_name="milk_records",
    )
    date = models.DateField("fecha del control")
    fat_pct = models.DecimalField(
        "grasa (%)", max_digits=4, decimal_places=2, null=True, blank=True
    )
    protein_pct = models.DecimalField(
        "proteína (%)", max_digits=4, decimal_places=2, null=True, blank=True
    )
    somatic_cell_count = models.PositiveIntegerField(
        "células somáticas (células/ml)", null=True, blank=True
    )

    class Meta:
        verbose_name = "control lechero individual"
        verbose_name_plural = "controles lecheros individuales"
        ordering = ["-date", "animal"]
        constraints = [
            models.UniqueConstraint(
                fields=["animal", "date"],
                name="farms_milkrecord_unique_animal_date",
            ),
            models.CheckConstraint(
                condition=models.Q(fat_pct__isnull=True) | models.Q(fat_pct__gte=0),
                name="farms_milkrecord_fat_pct_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(protein_pct__isnull=True) | models.Q(protein_pct__gte=0),
                name="farms_milkrecord_protein_pct_not_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="farms_milkrecord_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.animal.ear_tag} · control {self.date}"
