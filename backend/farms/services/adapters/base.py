"""Contrato común de los adaptadores de fuente y primitivas de parseo.

Un adaptador traduce el formato de un sistema concreto al modelo canónico. No
toca el ORM ni conoce el resto de adaptadores: recibe texto y devuelve hechos.
Las primitivas de abajo no imponen un formato único a propósito — cada fuente
elige la suya, que es justamente en lo que se diferencian.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Protocol

from farms.models import SourceSystem
from farms.services.canonical import CanonicalBatch

EAR_TAG_SEPARATORS = re.compile(r"[\s\-_/.]")
EAR_TAG_COUNTRY_CODE = "ES"


class AdapterError(Exception):
    """Fallo al interpretar una entrega de una fuente."""


class SourceAdapter(Protocol):
    """Lo que cumple todo adaptador: una fuente declarada y un `parse`."""

    source: ClassVar[SourceSystem]

    def parse(self, payload: str) -> CanonicalBatch:
        """Traduce una entrega cruda de la fuente al modelo canónico."""
        ...


def normalize_ear_tag(raw: str) -> str:
    """Lleva el crotal a la forma canónica, venga como venga de la fuente.

    Cada sistema lo escribe a su manera —con separadores, sin código de país, en
    minúscula— y todos se refieren al mismo animal. Reconciliarlos aquí es lo que
    permite que cuatro ficheros distintos hablen de la misma vaca.
    """
    cleaned = EAR_TAG_SEPARATORS.sub("", raw).strip().upper()
    if not cleaned:
        raise ValueError("crotal vacío")
    if cleaned.isdigit():
        return f"{EAR_TAG_COUNTRY_CODE}{cleaned}"
    return cleaned


def parse_iso_date(raw: str) -> date:
    """Fecha en `YYYY-MM-DD`."""
    return date.fromisoformat(raw.strip())


def parse_dmy_date(raw: str, separator: str = "/") -> date:
    """Fecha en `DD/MM/YYYY`, con el separador que use la fuente."""
    return datetime.strptime(raw.strip(), f"%d{separator}%m{separator}%Y").date()


def parse_decimal(raw: str, *, decimal_separator: str = ".") -> Decimal:
    """Número decimal, con la coma o el punto que use la fuente."""
    text = raw.strip()
    if decimal_separator != ".":
        text = text.replace(decimal_separator, ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"no es un número: {raw!r}") from exc
