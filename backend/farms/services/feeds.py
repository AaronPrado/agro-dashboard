"""Emisores del crudo de cada fuente: del dominio al texto que exportaría el sistema.

Estos emisores son andamio del mock y desaparecen el día que las entregas lleguen
de sistemas reales; los adaptadores que las leen, no. Por eso los cuatro viven
juntos aquí mientras que cada adaptador tiene su propio módulo.
"""

import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from farms.services.adapters.base import EAR_TAG_COUNTRY_CODE
from farms.services.adapters.field_notebook import (
    CATEGORY_CODES,
    COLUMNS,
    INGREDIENT_RAW_MATERIAL,
    INGREDIENT_SILAGE,
    SPECIES_CODES,
)
from farms.services.adapters.milk_recording import BREED_CODES, SCC_THOUSANDS
from farms.services.agronomy import RAW_MATERIALS
from farms.services.generation import AnimalData, FarmData, MilkRecordData

MILKING_ROBOT_HEADER = "crotal;fecha;hora;kg"

# El robot registra cada ordeño por separado. El reparto del total diario entre
# ellos es arbitrario y no afecta a la suma, que es el dato del generador.
MILKING_HOURS = (6, 17)
EVENING_SHARE_RANGE = (0.45, 0.60)


def milking_robot_feed(rng: random.Random, farm: FarmData) -> str:
    """Exportación del robot de ordeño de una explotación, una fila por ordeño.

    Escribe como escribiría el sistema de origen y no como conviene al modelo: el
    crotal sin el código de país, la fecha en DD/MM/YYYY, la coma decimal y los
    kilos de la báscula. La explotación no aparece: el fichero es de un robot, y
    el robot es de una granja.
    """
    lines = [MILKING_ROBOT_HEADER]
    for animal in farm.animals:
        local_tag = animal.ear_tag.removeprefix(EAR_TAG_COUNTRY_CODE)
        for entry in animal.daily_yields:
            if entry.kg is None:
                lines.append(f"{local_tag};{_dmy(entry.date)};{_clock(rng, 0)};")
                continue
            for index, kg in enumerate(_split_milkings(rng, entry.kg)):
                lines.append(f"{local_tag};{_dmy(entry.date)};{_clock(rng, index)};{_comma(kg)}")
    return "\n".join(lines)


def _split_milkings(rng: random.Random, total: Decimal) -> list[Decimal]:
    """Reparte el total del día entre dos ordeños conservando la suma exacta.

    El segundo se redondea y el primero absorbe la diferencia, de modo que sumar
    las filas devuelve exactamente el kilaje del día y el viaje de ida y vuelta
    por el fichero no pierde ni un gramo.
    """
    share = Decimal(str(round(rng.uniform(*EVENING_SHARE_RANGE), 4)))
    evening = (total * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [total - evening, evening]


def _clock(rng: random.Random, index: int) -> str:
    """Hora del ordeño: la fuente la registra, el modelo no la guarda."""
    return f"{MILKING_HOURS[index]:02d}:{rng.randint(0, 59):02d}"


def _dmy(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _comma(value: Decimal) -> str:
    return str(value).replace(".", ",")


MILK_RECORDING_TITLE = "CONTROL LECHERO OFICIAL"
MILK_RECORDING_SEPARATOR = "--"
SCC_MISSING = "9999999"

# El vocabulario del modelo traducido al código de la fuente: la inversa del
# mapeo del adaptador, para que el código de cada raza se declare una sola vez.
BREED_TO_CODE = {breed: code for code, breed in BREED_CODES.items()}


def milk_recording_feeds(farm: FarmData) -> dict[date, str]:
    """Informes mensuales del núcleo de control, uno por fecha de control.

    Cada informe lista el rebaño entero de esa fecha, no solo los animales
    medidos: el censo es lo que esta fuente aporta y ninguna otra sabe.
    """
    dates = sorted({record.date for a in farm.animals for record in a.milk_records})
    return {control_date: _milk_recording_report(farm, control_date) for control_date in dates}


def _milk_recording_report(farm: FarmData, control_date: date) -> str:
    """Un informe: cabecera con claves y una línea de ancho fijo por animal."""
    lines = [
        MILK_RECORDING_TITLE,
        f"EXPLOTACION: {farm.code}",
        f"NOMBRE     : {farm.name}",
        f"CONCELLO   : {farm.municipality}",
        f"PROVINCIA  : {farm.province}",
        f"FECHA      : {control_date:%Y%m%d}",
        MILK_RECORDING_SEPARATOR,
    ]
    for animal in farm.animals:
        if animal.culled_date is not None and animal.culled_date < control_date:
            continue  # dado de baja: deja de figurar en los informes siguientes
        record = next((r for r in animal.milk_records if r.date == control_date), None)
        lines.append(_milk_recording_row(animal, record))
    return "\n".join(lines)


def _milk_recording_row(animal: AnimalData, record: MilkRecordData | None) -> str:
    """Una línea de ancho fijo: identidad siempre, analítica solo si hubo control."""
    row = (
        f"{_spaced_ear_tag(animal.ear_tag):<20}"
        f"{animal.birth_date:%Y%m%d}"
        f"{BREED_TO_CODE[animal.breed]}"
        f"{animal.lactation_number:02d}"
        f"{_compact(animal.last_calving_date)}"
        f"{_compact(animal.culled_date)}"
        f"{'S' if record else 'N'}"
    )
    if record is None:
        return row
    return (
        f"{row}"
        f"{_comma(record.fat_pct):>5}"
        f"{_comma(record.protein_pct):>5}"
        f"{_thousands(record.somatic_cell_count)}"
    )


def _spaced_ear_tag(ear_tag: str) -> str:
    """El núcleo de control escribe el crotal por bloques, no de corrido."""
    country, digits = ear_tag[:2], ear_tag[2:]
    return f"{country} {digits[:4]} {digits[4:8]} {digits[8:]}"


def _compact(day: date | None) -> str:
    return f"{day:%Y%m%d}" if day is not None else " " * 8


def _thousands(count: int | None) -> str:
    """Miles de células por mililitro; el centinela ocupa el mismo ancho."""
    return SCC_MISSING if count is None else f"{count // SCC_THOUSANDS:07d}"


FIELD_NOTEBOOK_TITLE = "CUADERNO DE CAMPO"
NOTEBOOK_SEPARATOR = "\t"
NOTEBOOK_MISSING = "-"

# Las inversas de los mapeos del adaptador, por el mismo motivo que en las razas:
# el código de cada especie y de cada categoría se declara una sola vez.
SPECIES_TO_CODE = {species: code for code, species in SPECIES_CODES.items()}
CATEGORY_TO_CODE = {category: code for code, category in CATEGORY_CODES.items()}


def field_notebook_feed(farm: FarmData) -> str:
    """Exportación plana del cuaderno de campo de una explotación.

    Seis secciones con sus encabezados, filas separadas por tabulador, coma
    decimal y fechas con el año en dos cifras, que es como quedan al exportar una
    hoja de cálculo llevada a mano.
    """
    lines = [
        FIELD_NOTEBOOK_TITLE,
        f"EXPLOTACION{NOTEBOOK_SEPARATOR}{farm.code}",
        "--",
    ]
    lines += _notebook_section("[PARCELAS]")
    for plot in farm.plots:
        lines.append(_notebook_row(plot.code, plot.name, _comma_2dp(plot.area_ha)))

    lines += _notebook_section("[CULTIVOS]")
    for plot in farm.plots:
        for crop in plot.crops:
            lines.append(
                _notebook_row(
                    plot.code,
                    SPECIES_TO_CODE[crop.species],
                    str(crop.season),
                    _short_year(crop.sowing_date),
                    _short_year(crop.harvest_date),
                )
            )

    lines += _notebook_section("[SILOS]")
    for plot in farm.plots:
        for crop in plot.crops:
            for silage in crop.silages:
                lines.append(
                    _notebook_row(
                        plot.code,
                        str(crop.season),
                        SPECIES_TO_CODE[crop.species],
                        silage.code,
                        _short_year(silage.sealed_date),
                        _short_year(silage.opened_date),
                    )
                )

    lines += _notebook_section("[MATERIAS_PRIMAS]")
    for name, category in RAW_MATERIALS:
        lines.append(_notebook_row(name, CATEGORY_TO_CODE[category]))

    lines += _notebook_section("[RACIONES]")
    for ration in farm.rations:
        lines.append(_notebook_row(ration.name, _short_year(ration.formulated_on)))

    lines += _notebook_section("[INGREDIENTES]")
    for ration in farm.rations:
        for ingredient in ration.ingredients:
            silo = ingredient.silage_code is not None
            lines.append(
                _notebook_row(
                    ration.name,
                    _short_year(ration.formulated_on),
                    INGREDIENT_SILAGE if silo else INGREDIENT_RAW_MATERIAL,
                    ingredient.silage_code if silo else ingredient.raw_material,
                    _comma_2dp(ingredient.dry_matter_kg),
                )
            )
    return "\n".join(lines)


def _notebook_section(name: str) -> list[str]:
    """Marcador de sección y su fila de encabezados, tomada del contrato."""
    return [name, NOTEBOOK_SEPARATOR.join(COLUMNS[name])]


def _notebook_row(*values: str) -> str:
    return NOTEBOOK_SEPARATOR.join(values)


def _comma_2dp(value: Decimal) -> str:
    """Número con dos decimales y coma, como lo escribe una hoja de cálculo."""
    return f"{value:.2f}".replace(".", ",")


def _short_year(day: date | None) -> str:
    """Fecha del cuaderno: dos cifras de año, y la marca de lo que no aplica."""
    return NOTEBOOK_MISSING if day is None else f"{day:%d-%m-%y}"
