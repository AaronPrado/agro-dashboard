"""Vistas de la app farms."""

from django.db import connection
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse


def health(request: HttpRequest) -> JsonResponse:
    """Comprueba que la API responde y que PostgreSQL es accesible.

    Devuelve 200 con estado "ok" si la conexión a la base de datos funciona,
    o 503 si la base de datos no está disponible.
    """
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse(
            {"status": "error", "database": "unavailable"},
            status=503,
        )
    return JsonResponse({"status": "ok", "database": "ok"})
