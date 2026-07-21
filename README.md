# agro-dashboard

Dashboard de producción lechera para granjas de vacuno: una API en **Django REST
Framework** sobre **PostgreSQL** con datos realistas, y un frontend en **React**
que los visualiza. Proyecto de portfolio orientado a mostrar un flujo completo de
datos, desde su generación hasta su representación gráfica.

> ⚠️ **Estado: en construcción.** El proyecto está arrancando; las instrucciones
> de puesta en marcha se irán completando conforme avance la implementación.

## Dominio

El modelo de datos gira en torno a la explotación lechera:

- **Granja** — la explotación.
- **Animal** — cada vaca, identificada por su crotal, perteneciente a una granja.
- **Ordeño** — producción diaria de cada animal (litros).
- **Control lechero** — analítica mensual de cada animal: grasa y proteína (en
  porcentaje) y recuento de células somáticas (en células/ml, la unidad en la que
  el Reglamento (CE) 853/2004 fija el límite de 400.000 para la leche cruda de
  vaca; ese umbral es la base de las alertas de calidad).

Las reglas que no deben violarse nunca —un crotal no repetido dentro de la misma
granja, un único registro de producción por animal y día, litros y porcentajes no
negativos— se declaran como restricciones en la propia base de datos, de modo que
también las respete cualquier carga masiva de datos.

Los datos son **mockeados pero realistas**: la producción sigue la curva de
lactación (pico tras el parto y descenso hasta el secado), con variación por raza
y número de partos, caída estival por estrés térmico y casos borde deliberados
(huecos, valores atípicos, nulos y bajas a mitad de serie). Se generan de forma
reproducible mediante un comando de gestión, no con datos escritos a mano.

## Stack

- **Backend:** Django + Django REST Framework
- **Base de datos:** PostgreSQL
- **Frontend:** React (hooks) + Recharts
- **Entorno de desarrollo:** Docker Compose (Django + PostgreSQL)

## Principios de diseño

- **La agregación se hace en el backend.** Medias, totales, rankings y alertas se
  calculan en el ORM y viajan ya resueltos; el frontend solo representa.
- **Los datos entran por la misma capa que usaría una fuente externa real,** de
  modo que sustituir el generador de mocks por una ingesta real sea cambiar un
  módulo, no reescribir el proyecto.
- **El frontend consume siempre la API real,** con estados de carga y error
  explícitos; nunca datos embebidos en los componentes.

## Puesta en marcha

Pendiente. El entorno se levantará con Docker Compose (Django + PostgreSQL) y la
configuración sensible (`SECRET_KEY`, credenciales de la base de datos) se leerá
de variables de entorno a partir de un `.env` local; se versiona un `.env.example`
como plantilla. Las instrucciones concretas se añadirán al completar el esqueleto
del backend.

## Licencia

Distribuido bajo licencia **GNU GPL v3**. Ver el fichero [LICENSE](LICENSE).
