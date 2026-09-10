import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatDay, formatMonth, formatNumber, toTimestamp } from '../format.js'
import { bandColor } from '../rationBands.js'

const SYNC_ID = 'batch-timeline'
const CHART_MARGIN = { top: 8, right: 8, bottom: 0, left: 0 }
const PRODUCTION_COLOR = '#2b6cb0'
const QUALITY_COLOR = '#0b6b3a'

/** Primeros de mes dentro del dominio, para no rotular en fechas arbitrarias. */
function monthTicks(from, to) {
  const ticks = []
  const cursor = new Date(from)
  cursor.setUTCDate(1)
  while (cursor.getTime() <= to) {
    const tick = cursor.getTime()
    if (tick >= from) ticks.push(tick)
    cursor.setUTCMonth(cursor.getUTCMonth() + 1)
  }
  return ticks
}

/**
 * Empareja el punto señalado en el otro gráfico con el más cercano en el tiempo
 * de este.
 *
 * Los dos gráficos comparten eje pero no grano —la producción es diaria y la
 * muestra de leche mensual—, así que emparejar por valor exacto solo
 * sincronizaría los días en que ambas series tienen dato.
 *
 * `ticks` son los puntos del gráfico que recibe, con su valor del eje y su
 * índice en los datos; `activeLabel` viaja como cadena aunque el eje sea
 * numérico, de ahí la conversión.
 */
function nearestInTime(ticks, { activeLabel }) {
  const target = Number(activeLabel)
  if (ticks.length === 0 || Number.isNaN(target)) return -1

  let nearest = 0
  for (let index = 1; index < ticks.length; index += 1) {
    if (Math.abs(ticks[index].value - target) < Math.abs(ticks[nearest].value - target)) {
      nearest = index
    }
  }
  return ticks[nearest].index
}

/** Los analitos presentes en las muestras, en el orden en que aparecen. */
function analytesOf(milkSamples) {
  const analytes = []
  for (const sample of milkSamples) {
    for (const result of sample.results) {
      if (!analytes.some((analyte) => analyte.code === result.code)) {
        analytes.push({ code: result.code, name: result.name, unit: result.unit })
      }
    }
  }
  return analytes
}

export function BatchChart({
  window: dataWindow,
  dailyYields,
  milkSamples,
  rationPeriods,
  notice,
}) {
  const [chosen, setChosen] = useState('')

  const analytes = analytesOf(milkSamples)
  // El analito se deriva en el render en vez de corregirse con un efecto: al
  // cambiar de lote el código elegido puede no estar entre los medidos aquí.
  const selected = analytes.find((analyte) => analyte.code === chosen) ?? analytes[0] ?? null

  // Los dos gráficos comparten eje, y el dominio sale de las dos series: una
  // muestra fuera de la ventana de producción ensancharía si no solo el eje de
  // calidad, y las bandas dejarían de coincidir entre uno y otro.
  const stamps = [
    toTimestamp(dataWindow.date_from),
    toTimestamp(dataWindow.date_to),
    ...milkSamples.map((sample) => toTimestamp(sample.date)),
  ]
  const domain = [Math.min(...stamps), Math.max(...stamps)]
  const ticks = monthTicks(domain[0], domain[1])

  const production = dailyYields.map((point) => ({
    t: toTimestamp(point.date),
    liters: point.total_liters === null ? null : Number(point.total_liters),
  }))

  const quality = selected
    ? milkSamples.map((sample) => {
        const result = sample.results.find((entry) => entry.code === selected.code)
        return { t: toTimestamp(sample.date), value: result ? Number(result.value) : null }
      })
    : []

  const bands = rationPeriods.map((period, index) => (
    <ReferenceArea
      key={`${period.ration_id}-${period.date_from}`}
      x1={toTimestamp(period.starts_on)}
      x2={toTimestamp(period.ends_on)}
      fill={bandColor(index)}
      fillOpacity={0.65}
    />
  ))

  return (
    <>
      <h3 className="batch__section">Ración, producción y calidad en el tiempo</h3>

      <div
        className="chart"
        role="img"
        aria-label="Producción diaria del lote en litros, con una banda de color por periodo de ración. Esos periodos, con sus fechas, están en la tabla de alimentación."
      >
        <ResponsiveContainer width="100%" height={200}>
          <LineChart
            data={production}
            syncId={SYNC_ID}
            syncMethod={nearestInTime}
            margin={CHART_MARGIN}
          >
            <CartesianGrid stroke="#e6eaef" />
            {bands}
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={domain}
              ticks={ticks}
              tickFormatter={formatMonth}
            />
            <YAxis unit=" L" tickFormatter={formatNumber} />
            <Tooltip labelFormatter={formatDay} />
            <Line
              dataKey="liters"
              name="Producción del lote"
              unit=" L"
              stroke={PRODUCTION_COLOR}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {selected === null ? (
        <p className="status">Este lote no tiene muestras de leche en el tramo consultado.</p>
      ) : (
        <>
          <div className="picker">
            <label className="picker__label" htmlFor="analyte">
              Analito
            </label>
            <select
              id="analyte"
              value={selected.code}
              onChange={(event) => setChosen(event.target.value)}
            >
              {analytes.map((analyte) => (
                <option key={analyte.code} value={analyte.code}>
                  {analyte.name} ({analyte.unit})
                </option>
              ))}
            </select>
          </div>

          <div
            className="chart"
            role="img"
            aria-label={`${selected.name}, en ${selected.unit}, por fecha de muestra, sobre las mismas bandas de ración. Los valores medios están en la tabla del perfil analítico.`}
          >
            <ResponsiveContainer width="100%" height={200}>
              <LineChart
                data={quality}
                syncId={SYNC_ID}
                syncMethod={nearestInTime}
                margin={CHART_MARGIN}
              >
                <CartesianGrid stroke="#e6eaef" />
                {bands}
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={domain}
                  ticks={ticks}
                  tickFormatter={formatMonth}
                />
                <YAxis tickFormatter={formatNumber} />
                <Tooltip labelFormatter={formatDay} />
                <Line
                  dataKey="value"
                  name={selected.name}
                  unit={` ${selected.unit}`}
                  stroke={QUALITY_COLOR}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p className="notice">{notice}</p>

          <details className="reading">
            <summary>Supuestos de esta gráfica</summary>
            <ul>
              <li>
                <strong>El contraste entre raciones es más ancho que el real, y satura.</strong>{' '}
                El generador lo planta con los rangos del contraste entre pasto y ración
                completa, más marcado que el contraste entre ensilados que aquí se modela, y
                los valores tocan los extremos del rango publicado de cada analito. Por eso el
                cambio aparece como un escalón y no como una transición.
              </li>
              <li>
                <strong>La gráfica supone que la leche se muestrea por lote.</strong> Ese dato
                puede venir de un muestreo específico, de un segundo tanque, o de agregar por
                lote el análisis por vaca de un robot de ordeño — esta última vía es la misma
                integración de datos que sostiene el resto del proyecto.
              </li>
              <li>
                <strong>Supone también sala de ordeño con una única ración por lote.</strong>{' '}
                Con robot, parte del pienso se asigna según la producción de cada vaca, y
                entonces la relación entre ración y leche deja de leerse en una sola dirección.
              </li>
              <li>
                <strong>Cada muestra es un hecho en su fecha</strong>, no un valor vigente todo
                el mes: al recorrer la producción se resalta la muestra más próxima, que puede
                estar a semanas del día señalado.
              </li>
            </ul>
          </details>
        </>
      )}
    </>
  )
}
