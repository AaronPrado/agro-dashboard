/**
 * Presenta una fecha ISO (`2025-09-01`) en formato español.
 *
 * Reordena los trozos de la cadena en vez de construir un `Date`: `new
 * Date('2025-09-01')` se interpreta como medianoche UTC y al oeste de Greenwich
 * pintaría el día anterior.
 */
export function formatDate(value) {
  if (value === null) return '—'
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

/** Convierte una fecha ISO en el timestamp de su medianoche UTC. */
export function toTimestamp(value) {
  const [year, month, day] = value.split('-').map(Number)
  return Date.UTC(year, month - 1, day)
}

const dayLabel = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'UTC',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const monthLabel = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'UTC',
  month: 'short',
  year: '2-digit',
})

const numberLabel = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 })

const decimalLabel = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Rotula una marca de un eje de valores. */
export function formatNumber(value) {
  return numberLabel.format(value)
}

/**
 * Presenta con dos decimales fijos un valor que llega como cadena desde DRF.
 *
 * Se distingue de `formatNumber` en la escala: un eje omite los decimales que no
 * hacen falta, mientras que en una cifra medida la escala es parte del dato. Un
 * `null` es "no medido" y se pinta como tal, no como cero.
 */
export function formatDecimal(value) {
  return value === null ? '—' : decimalLabel.format(Number(value))
}

/** Rotula un punto del eje temporal. */
export function formatDay(timestamp) {
  return dayLabel.format(timestamp)
}

/** Rotula una marca mensual del eje temporal. */
export function formatMonth(timestamp) {
  return monthLabel.format(timestamp)
}
