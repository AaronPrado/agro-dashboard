import { getBatchTargetCheck } from '../api/batches.js'
import { useBatchResource } from '../hooks/useBatchResource.js'
import { ErrorState } from './ErrorState.jsx'

const STATUS = {
  within: { label: 'Dentro de rango', modifier: 'within' },
  below: { label: 'Por debajo', modifier: 'below' },
  above: { label: 'Por encima', modifier: 'above' },
  no_data: { label: 'Sin medir', modifier: 'no-data' },
}

function requirement(minValue, maxValue) {
  if (minValue !== null && maxValue !== null) return `${minValue} – ${maxValue}`
  if (minValue !== null) return `≥ ${minValue}`
  if (maxValue !== null) return `≤ ${maxValue}`
  return '—'
}

export function BatchTargetCheck({ batchId, dateFrom, dateTo }) {
  const { data, error, isLoading, refetch } = useBatchResource(getBatchTargetCheck, batchId, {
    dateFrom,
    dateTo,
  })

  if (isLoading) return <p className="status">Comparando con los perfiles de destino…</p>

  if (error) {
    return (
      <ErrorState
        title="No se ha podido comparar el lote con los perfiles de destino."
        error={error}
        onRetry={refetch}
      />
    )
  }

  if (!data) return null

  return (
    <>
      <h3 className="batch__section">Perfiles de destino comercial</h3>

      {data.profiles.length === 0 ? (
        <p className="status">El catálogo de perfiles de destino está vacío.</p>
      ) : (
        <>
          {data.profiles.map((profile) => (
            <article className="profile" key={profile.code}>
              <h4 className="profile__name">{profile.name}</h4>
              <p className="profile__count">
                {profile.measured === 0
                  ? 'Ningún analito de este perfil se ha medido en el tramo consultado.'
                  : `${profile.within_range} de ${profile.measured} analitos medidos están dentro de rango.`}
              </p>
              <p className="batch__note">{profile.description}</p>

              <table>
                <thead>
                  <tr>
                    <th scope="col">Analito</th>
                    <th scope="col" className="numeric">
                      Medido
                    </th>
                    <th scope="col" className="numeric">
                      Exigido
                    </th>
                    <th scope="col" className="numeric">
                      Muestras
                    </th>
                    <th scope="col">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.analytes.map((analyte) => {
                    const status = STATUS[analyte.status] ?? {
                      label: analyte.status,
                      modifier: 'no-data',
                    }

                    return (
                      <tr key={analyte.code}>
                        <td>
                          {analyte.name} ({analyte.unit})
                        </td>
                        <td className="numeric">{analyte.avg_value ?? '—'}</td>
                        <td className="numeric">
                          {requirement(analyte.min_value, analyte.max_value)}
                        </td>
                        <td className="numeric">{analyte.samples}</td>
                        <td>
                          <span className={`badge badge--${status.modifier}`}>{status.label}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </article>
          ))}

          <p className="notice">{data.target_check_notice}</p>
        </>
      )}
    </>
  )
}
