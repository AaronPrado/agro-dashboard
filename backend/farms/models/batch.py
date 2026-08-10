"""Modelos del lote de animales y su alimentación, con vigencia temporal."""

from django.core.exceptions import ValidationError
from django.db import models

from farms.models.agronomy import RawMaterial, Silage
from farms.models.dairy import Animal
from farms.models.farm import Farm
from farms.models.ingestion import Sourced


class DatedPeriod(models.Model):
    """Base de las relaciones con vigencia: un intervalo de fechas cerrado.

    `date_to` nulo significa "vigente". El no-solape se comprueba en `clean()`,
    de modo que solo alcanza a quien pase por `full_clean()`; una escritura
    masiva puede introducir solapes y es responsabilidad de quien la hace.
    """

    date_from = models.DateField("desde")
    date_to = models.DateField("hasta", null=True, blank=True)

    class Meta:
        abstract = True

    def overlap_scope(self) -> dict[str, object]:
        """Filtro que delimita el conjunto dentro del cual no puede haber solape."""
        raise NotImplementedError

    def clean(self) -> None:
        super().clean()
        if self.date_from is None:
            return
        candidatos = self.__class__.objects.filter(**self.overlap_scope())
        if self.pk is not None:
            candidatos = candidatos.exclude(pk=self.pk)
        # Dos intervalos cerrados se solapan si cada uno empieza antes de que el
        # otro acabe; un extremo nulo se comporta como una fecha infinita.
        candidatos = candidatos.filter(
            models.Q(date_to__isnull=True) | models.Q(date_to__gte=self.date_from)
        )
        if self.date_to is not None:
            candidatos = candidatos.filter(date_from__lte=self.date_to)
        if candidatos.exists():
            raise ValidationError("El periodo se solapa con otro ya registrado.")


class AnimalBatch(Sourced):
    """Lote de animales: la unidad a la que se asigna una ración."""

    farm = models.ForeignKey(
        Farm,
        verbose_name="granja",
        on_delete=models.CASCADE,
        related_name="batches",
    )
    name = models.CharField("nombre", max_length=80)

    class Meta:
        verbose_name = "lote de animales"
        verbose_name_plural = "lotes de animales"
        ordering = ["farm", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="farms_animalbatch_unique_farm_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class AnimalBatchMembership(DatedPeriod, Sourced):
    """Pertenencia de un animal a un lote durante un periodo."""

    animal = models.ForeignKey(
        Animal,
        verbose_name="animal",
        on_delete=models.CASCADE,
        related_name="batch_memberships",
    )
    batch = models.ForeignKey(
        AnimalBatch,
        verbose_name="lote",
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    class Meta:
        verbose_name = "pertenencia a lote"
        verbose_name_plural = "pertenencias a lote"
        ordering = ["-date_from", "animal"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_to__isnull=True)
                | models.Q(date_to__gte=models.F("date_from")),
                name="farms_animalbatchmembership_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["animal"],
                condition=models.Q(date_to__isnull=True),
                name="farms_animalbatchmembership_one_open_per_animal",
            ),
        ]
        indexes = [
            models.Index(fields=["date_from"], name="farms_abmembership_from_idx"),
        ]

    def __str__(self) -> str:
        hasta = self.date_to or "vigente"
        return f"{self.animal.ear_tag} · {self.batch.name} · {self.date_from} → {hasta}"

    def overlap_scope(self) -> dict[str, object]:
        return {"animal_id": self.animal_id}


class Ration(Sourced):
    """Ración formulada para una explotación.

    Una ración es una formulación cerrada: reformularla es crear otra, no editar
    esta. Así el periodo de `BatchRation` basta para saber qué comió un lote en
    cada momento, sin necesidad de historificar la composición.
    """

    farm = models.ForeignKey(
        Farm,
        verbose_name="granja",
        on_delete=models.CASCADE,
        related_name="rations",
    )
    name = models.CharField("nombre", max_length=80)
    formulated_on = models.DateField("fecha de formulación")

    class Meta:
        verbose_name = "ración"
        verbose_name_plural = "raciones"
        ordering = ["farm", "name", "-formulated_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name", "formulated_on"],
                name="farms_ration_unique_farm_name_formulated_on",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.formulated_on})"


class RationIngredient(Sourced):
    """Un componente de una ración, con su aporte en materia seca.

    El componente es un ensilado propio o una materia prima comprada, nunca las
    dos cosas ni ninguna. Se modela con dos claves ajenas excluyentes en vez de
    una relación genérica, para que la integridad la sostenga la base de datos.
    """

    ration = models.ForeignKey(
        Ration,
        verbose_name="ración",
        on_delete=models.CASCADE,
        related_name="ingredients",
    )
    silage = models.ForeignKey(
        Silage,
        verbose_name="ensilado propio",
        on_delete=models.PROTECT,
        related_name="ration_ingredients",
        null=True,
        blank=True,
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        verbose_name="materia prima",
        on_delete=models.PROTECT,
        related_name="ration_ingredients",
        null=True,
        blank=True,
    )
    dry_matter_kg = models.DecimalField(
        "kg de materia seca por animal y día", max_digits=5, decimal_places=2
    )

    class Meta:
        verbose_name = "ingrediente de la ración"
        verbose_name_plural = "ingredientes de la ración"
        ordering = ["ration", "-dry_matter_kg"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(silage__isnull=True, raw_material__isnull=False)
                | models.Q(silage__isnull=False, raw_material__isnull=True),
                name="farms_rationingredient_exactly_one_source",
            ),
            models.CheckConstraint(
                condition=models.Q(dry_matter_kg__gt=0),
                name="farms_rationingredient_dry_matter_positive",
            ),
            models.UniqueConstraint(
                fields=["ration", "silage"],
                name="farms_rationingredient_unique_ration_silage",
            ),
            models.UniqueConstraint(
                fields=["ration", "raw_material"],
                name="farms_rationingredient_unique_ration_raw_material",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.silage or self.raw_material} · {self.dry_matter_kg} kg MS"

    def clean(self) -> None:
        super().clean()
        if self.silage_id is None or self.ration_id is None:
            return
        if self.silage.crop.plot.farm_id != self.ration.farm_id:
            raise ValidationError("El ensilado pertenece a otra explotación.")


class BatchRation(DatedPeriod, Sourced):
    """Ración que come un lote durante un periodo."""

    batch = models.ForeignKey(
        AnimalBatch,
        verbose_name="lote",
        on_delete=models.CASCADE,
        related_name="ration_periods",
    )
    ration = models.ForeignKey(
        Ration,
        verbose_name="ración",
        on_delete=models.PROTECT,
        related_name="batch_periods",
    )

    class Meta:
        verbose_name = "ración del lote"
        verbose_name_plural = "raciones del lote"
        ordering = ["-date_from", "batch"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_to__isnull=True)
                | models.Q(date_to__gte=models.F("date_from")),
                name="farms_batchration_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["batch"],
                condition=models.Q(date_to__isnull=True),
                name="farms_batchration_one_open_per_batch",
            ),
        ]
        indexes = [
            models.Index(fields=["date_from"], name="farms_batchration_from_idx"),
        ]

    def __str__(self) -> str:
        hasta = self.date_to or "vigente"
        return f"{self.batch.name} · {self.ration.name} · {self.date_from} → {hasta}"

    def overlap_scope(self) -> dict[str, object]:
        return {"batch_id": self.batch_id}
