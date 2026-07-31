# agro-dashboard

Dashboard de producción lechera para granjas de vacuno: una API en **Django REST
Framework** sobre **PostgreSQL** con datos realistas, y un frontend en **React**
que los visualiza. Proyecto de portfolio orientado a mostrar un flujo completo de
datos, desde su generación hasta su representación gráfica.

> ⚠️ **Estado: en construcción.** El backend es funcional —modelos, generador de
> datos y API de lectura—; el frontend aún no está implementado.

## Dominio

El modelo de datos gira en torno a la explotación lechera:

- **Granja** — la explotación.
- **Animal** — cada vaca, identificada por su crotal, perteneciente a una granja.
- **Producción diaria** — lo que produce cada animal en un día (litros).
- **Control lechero individual** — analítica mensual de cada animal: grasa y proteína (en
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

Requisitos: Docker y Docker Compose.

1. **Configura el entorno.** La configuración sensible se lee de variables de
   entorno; `.env` no se versiona y `.env.example` sirve de plantilla:

   ```bash
   cp backend/.env.example backend/.env
   ```

   Rellena `DJANGO_SECRET_KEY` y `POSTGRES_PASSWORD` con valores url-safe:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

   > Los valores no pueden contener `$`: Docker Compose interpola el contenido de
   > los ficheros `env_file` y lo trataría como una referencia a otra variable.

2. **Levanta el stack.** Construye la imagen, arranca PostgreSQL y aplica las
   migraciones:

   ```bash
   make build && make up
   ```

   La API queda en `http://localhost:8000` y el panel de administración en
   `/admin/` (necesita un superusuario:
   `docker compose run --rm web python manage.py createsuperuser`).

3. **Puebla la base de datos** con datos mockeados reproducibles:

   ```bash
   make seed
   ```

   El comando acepta `--seed`, `--farms`, `--animals-per-farm`, `--start`, `--end`
   y `--clear`. Con la misma semilla y los mismos parámetros produce siempre los
   mismos datos; `--clear` lo hace idempotente.

`make help` lista el resto de tareas: `make test`, `make lint`, `make format`,
`make migrate`, `make shell`.

## API

Todos los endpoints son de **solo lectura**: los datos entran por la capa de
ingesta, no por HTTP. La raíz `GET /api/` publica un índice navegable de los
recursos, y en desarrollo cada endpoint se puede explorar desde el navegador con
la interfaz navegable de DRF.

| Endpoint | Filtros | Ordenación (`?ordering=`) |
|---|---|---|
| `/api/farms/` | `province` | `name`, `code`, `created_at` |
| `/api/animals/` | `farm`, `breed`, `active` | `ear_tag`, `birth_date`, `lactation_number` |
| `/api/daily-yields/` | `animal`, `farm`, `date_from`, `date_to` | `date`, `liters` |
| `/api/milk-records/` | `animal`, `farm`, `date_from`, `date_to` | `date`, `somatic_cell_count`, `fat_pct`, `protein_pct` |
| `/api/health/` | — | — |

Notas sobre el contrato:

- **Paginación** por número de página: la respuesta trae `count`, `next`,
  `previous` y `results`. El tamaño por defecto es de 50 registros y el cliente
  puede ajustarlo con `?page_size=`, hasta un máximo de 200.
- **Rango de fechas** cerrado por ambos extremos y con cada extremo opcional:
  `?date_from=2026-01-01&date_to=2026-01-31`.
- **`active`** no corresponde a ningún campo almacenado: se deriva de la fecha de
  baja del animal. `?active=true` devuelve los que siguen en la explotación.
- **Los valores decimales viajan como cadena** (`"liters": "28.40"`). Es el
  comportamiento por defecto de DRF y se conserva a propósito: preserva la
  exactitud de los importes, que se almacenan como decimales y no como coma
  flotante para que los agregados no dependan del orden de las filas.
- **Un valor ausente se representa como `null`,** que significa "no medido" y es
  distinto de cero. La producción diaria incluye huecos y lecturas nulas a propósito.
- **Un parámetro de consulta inválido devuelve `400`**, no un listado sin filtrar.

La producción diaria y los controles lecheros exponen el crotal y la granja de su
animal como campos planos, en lugar de anidar el objeto completo, para que un
listado extenso no repita los mismos datos en cada fila.

Ejemplo:

```bash
curl "http://localhost:8000/api/daily-yields/?farm=1&date_from=2026-01-01&date_to=2026-01-31&page_size=5"
```

## Desarrollo

Los tests y el linter se ejecutan dentro del contenedor:

```bash
make lint && make test
```

Además hay un `pre-commit` que pasa `ruff` en el host antes de cada commit
(engánchalo una vez con `cd backend && uv run pre-commit install`), y una CI de
GitHub Actions que corre lint y tests en cada push y pull request.

## Licencia

Distribuido bajo licencia **GNU GPL v3**. Ver el fichero [LICENSE](LICENSE).
