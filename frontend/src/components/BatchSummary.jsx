import { getBatchSummary } from '../api/batches.js'
import { useBatchResource } from '../hooks/useBatchResource.js'

const decimal = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function format(value) {
  return value === null ? '—' : decimal.format(Number(value))
}

export function BatchSummary({ batchId, dateFrom, dateTo }) {
  const { data, error, isLoading } = useBatchResource(getBatchSummary, batchId, {
    dateFrom,
    dateTo,
  })

  if (isLoading) return <p className="status">Cargando el resumen del lote…</p>

  if (error) {
    return (
      <div className="status status--error" role="alert">
        <strong>No se ha podido cargar el resumen del lote.</strong>
        <p className="status__detail">{error.message}</p>
      </div>
    )
  }

  if (!data) return null

  return (
    <>
      <h3 className="batch__section">Producción y calidad</h3>
      <p className="batch__note">
        {data.active_animals} animales en el lote. El censo no lo acota la ventana: las
        fechas acotan las series fechadas, no quién pertenece al lote.
      </p>

      {data.total_liters === null ? (
        <p className="status">
          Este lote no tiene producción registrada en la ventana elegida.
        </p>
      ) : (
        <dl className="metrics">
          <div>
            <dt>Litros totales</dt>
            <dd>{format(data.total_liters)}</dd>
          </div>
          <div>
            <dt>Media diaria por animal</dt>
            <dd>{format(data.avg_daily_liters)} l</dd>
          </div>
          <div>
            <dt>Grasa media</dt>
            <dd>{format(data.avg_fat_pct)} %</dd>
          </div>
          <div>
            <dt>Proteína media</dt>
            <dd>{format(data.avg_protein_pct)} %</dd>
          </div>
          <div>
            <dt>Controles sobre el límite de células</dt>
            <dd>
              {data.scc_over_limit} de {data.milk_records}
            </dd>
          </div>
        </dl>
      )}

      <h3 className="batch__section">Perfil analítico de la leche</h3>

      {data.milk_analytes.length === 0 ? (
        <p className="status">
          No hay muestras de leche de este lote en la ventana elegida.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Analito</th>
              <th scope="col">Media</th>
              <th scope="col">Unidad</th>
              <th scope="col">Muestras</th>
            </tr>
          </thead>
          <tbody>
            {data.milk_analytes.map((analyte) => (
              <tr key={analyte.code}>
                <td>{analyte.name}</td>
                <td>{analyte.avg_value}</td>
                <td>{analyte.unit}</td>
                <td>{analyte.samples}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
