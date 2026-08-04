"""Modelos del dominio, repartidos por área y reexportados como un solo espacio.

El paquete conserva la importación canónica `from farms.models import X`, de modo
que la división en módulos no altera el resto del proyecto. Un modelo solo queda
registrado en la app si su módulo se importa aquí.
"""

from farms.models.dairy import Animal, DailyYield, MilkRecord
from farms.models.farm import Farm

__all__ = [
    "Animal",
    "DailyYield",
    "Farm",
    "MilkRecord",
]
