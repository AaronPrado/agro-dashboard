"""Esquemas de paginación de la API."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Paginación por número de página con tamaño ajustable.

    `PageNumberPagination` toma el tamaño de `PAGE_SIZE` en settings y no deja
    que el cliente lo cambie: habilitarlo exige declarar `page_size_query_param`.
    El tope `max_page_size` evita que una petición pueda arrastrar la tabla
    entera de ordeños en una sola respuesta.
    """

    page_size_query_param = "page_size"
    max_page_size = 200
