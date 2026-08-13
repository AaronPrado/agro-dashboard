import { getBatchTimeline } from '../api/batches.js'
import { useBatchResource } from '../hooks/useBatchResource.js'

function formatDate(value) {
  if (value === null) return '—'
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

export function BatchRations({ batchId, dateFrom, dateTo }) {
  const { data, error, isLoading } = useBatchResource(getBatchTimeline, batchId, {
    dateFrom,
    dateTo,
  })

  if (isLoading) return <p className="status">Cargando la alimentación del lote…</p>

  if (error) {
    return (
      <div className="status status--error" role="alert">
        <strong>No se ha podido cargar la alimentación del lote.</strong>
        <p className="status__detail">{error.message}</p>
      </div>
    )
  }

  if (!data) return null

  const days = data.daily_yields.length

  return (
    <>
      <p className="batch__note">
        {days === 0
          ? 'Este lote no tiene producción registrada en el tramo consultado.'
          : `Mostrando del ${formatDate(data.window.date_from)} al ${formatDate(
              data.window.date_to,
            )} · ${days} días con producción.`}
      </p>

      <h3 className="batch__section">Alimentación</h3>

      {data.ration_periods.length === 0 ? (
        <p className="status">
          Sin periodos de ración en el tramo consultado. Se sitúan sobre el eje de
          producción, así que un lote sin producción no muestra ninguno; su ración vigente
          figura arriba.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Ración</th>
              <th scope="col">Formulada</th>
              <th scope="col">Desde</th>
              <th scope="col">Hasta</th>
            </tr>
          </thead>
          <tbody>
            {data.ration_periods.map((period) => (
              <tr key={`${period.ration_id}-${period.date_from}`}>
                <td>{period.ration}</td>
                <td>{formatDate(period.formulated_on)}</td>
                <td>{formatDate(period.date_from)}</td>
                <td>{period.date_to === null ? 'Vigente' : formatDate(period.date_to)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
