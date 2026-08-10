"""Adaptador del núcleo de control lechero.

La entrega es un informe mensual por explotación: cabecera con claves y cuerpo de
ancho fijo, una línea por animal del rebaño. Aporta dos cosas que ninguna otra
fuente sabe —el censo con la identidad de cada animal y la analítica oficial— y
cuatro cosas hay que traducirlas: el crotal por bloques, la fecha compacta, los
códigos de raza propios y el recuento de células, que llega en miles y con un
centinela numérico para lo no medido.
"""

from datetime import date
from typing import ClassVar

from farms.models import Animal, SourceSystem
from farms.services.adapters.base import (
    AdapterError,
    normalize_ear_tag,
    parse_compact_date,
    parse_decimal,
)
from farms.services.canonical import (
    AnimalRegistration,
    CanonicalBatch,
    FarmRegistration,
    MilkQualityRecord,
    Reject,
)

TITLE = "CONTROL LECHERO OFICIAL"
HEADER_SEPARATOR = "--"
HEADER_KEYS = ("EXPLOTACION", "NOMBRE", "CONCELLO", "PROVINCIA", "FECHA")

# Recuento de células somáticas: la fuente lo reporta en miles por mililitro y
# reserva un valor imposible para lo no medido.  [convención sin verificar]
SCC_MISSING = "9999999"
SCC_THOUSANDS = 1000

# Códigos de raza de la fuente traducidos al vocabulario del modelo.
BREED_CODES = {
    "HO": Animal.Breed.HOLSTEIN,
    "JE": Animal.Breed.JERSEY,
    "PA": Animal.Breed.BROWN_SWISS,
    "PR": Animal.Breed.PROCROSS,
    "XX": Animal.Breed.OTHER,
}

# Posiciones del cuerpo de ancho fijo. Es el contrato con la fuente: sin
# separador, lo único que delimita un campo es dónde empieza y dónde acaba.
EAR_TAG = slice(0, 20)
BIRTH_DATE = slice(20, 28)
BREED = slice(28, 30)
LACTATION = slice(30, 32)
LAST_CALVING = slice(32, 40)
CULLED = slice(40, 48)
CONTROLLED = slice(48, 49)
FAT = slice(49, 54)
PROTEIN = slice(54, 59)
SCC = slice(59, 66)

CENSUS_WIDTH = CONTROLLED.stop
CONTROL_WIDTH = SCC.stop


class MilkRecordingAdapter:
    """Traduce un informe mensual de control lechero al modelo canónico.

    A diferencia del robot, esta fuente se identifica sola: la explotación y la
    fecha del control viven en la cabecera, así que el adaptador no necesita
    contexto externo.
    """

    source: ClassVar[SourceSystem] = SourceSystem.MILK_RECORDING

    def parse(self, payload: str) -> CanonicalBatch:
        """Lee cabecera y cuerpo, y devuelve censo, analítica y lo rechazado."""
        lines = payload.splitlines()
        header, body_start = self._parse_header(lines)
        farm_code = header["EXPLOTACION"]
        control_date = parse_compact_date(header["FECHA"])

        batch = CanonicalBatch(source=self.source)
        batch.farms.append(
            FarmRegistration(
                code=farm_code,
                name=header["NOMBRE"],
                municipality=header["CONCELLO"],
                province=header["PROVINCIA"],
            )
        )
        for number, raw in enumerate(lines[body_start:], start=body_start + 1):
            if not raw.strip():
                continue
            try:
                self._parse_row(raw, farm_code, control_date, batch)
            except ValueError as exc:
                batch.rejects.append(Reject(line_number=number, raw=raw, reason=str(exc)))
        return batch

    def _parse_header(self, lines: list[str]) -> tuple[dict[str, str], int]:
        """Lee las claves de cabecera hasta el separador y devuelve dónde sigue.

        Falta de cabecera o de una clave obligatoria aborta: sin explotación ni
        fecha, ninguna fila del cuerpo significa nada.
        """
        if not lines or lines[0].strip() != TITLE:
            raise AdapterError(f"[{self.source}] no es un informe de control lechero")
        header: dict[str, str] = {}
        for index, raw in enumerate(lines[1:], start=1):
            if raw.strip() == HEADER_SEPARATOR:
                missing = [key for key in HEADER_KEYS if key not in header]
                if missing:
                    raise AdapterError(f"[{self.source}] faltan claves de cabecera: {missing}")
                return header, index + 1
            key, separator, value = raw.partition(":")
            if separator:
                header[key.strip()] = value.strip()
        raise AdapterError(f"[{self.source}] la cabecera no termina en {HEADER_SEPARATOR!r}")

    def _parse_row(
        self, raw: str, farm_code: str, control_date: date, batch: CanonicalBatch
    ) -> None:
        """Interpreta una línea del cuerpo: siempre censo, y analítica si la hubo."""
        if len(raw) < CENSUS_WIDTH:
            raise ValueError(f"la línea mide {len(raw)} y el censo ocupa {CENSUS_WIDTH}")
        breed_code = raw[BREED].strip()
        if breed_code not in BREED_CODES:
            raise ValueError(f"código de raza desconocido: {breed_code!r}")

        ear_tag = normalize_ear_tag(raw[EAR_TAG])
        batch.animals.append(
            AnimalRegistration(
                farm_code=farm_code,
                ear_tag=ear_tag,
                birth_date=parse_compact_date(raw[BIRTH_DATE]),
                breed=BREED_CODES[breed_code],
                lactation_number=int(raw[LACTATION]),
                last_calving_date=_optional_date(raw[LAST_CALVING]),
                culled_date=_optional_date(raw[CULLED]),
            )
        )
        if raw[CONTROLLED] != "S":
            return
        if len(raw) < CONTROL_WIDTH:
            raise ValueError(f"marcada con control y solo mide {len(raw)}")
        batch.quality.append(
            MilkQualityRecord(
                farm_code=farm_code,
                ear_tag=ear_tag,
                date=control_date,
                fat_pct=parse_decimal(raw[FAT], decimal_separator=","),
                protein_pct=parse_decimal(raw[PROTEIN], decimal_separator=","),
                somatic_cell_count=_scc(raw[SCC]),
            )
        )


def _optional_date(raw: str) -> date | None:
    """Fecha compacta que la fuente deja en blanco cuando no aplica."""
    return parse_compact_date(raw) if raw.strip() else None


def _scc(raw: str) -> int | None:
    """Recuento de células: de miles a células por mililitro, con su centinela.

    El centinela es un número válido, así que sin esta traducción una carga
    ingenua guardaría nueve millones de células como si fueran una medida.
    """
    text = raw.strip()
    if text == SCC_MISSING:
        return None
    return int(text) * SCC_THOUSANDS
