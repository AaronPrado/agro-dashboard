import { getBatchTimeline } from '../api/batches.js'
import { formatDate } from '../format.js'
import { useBatchResource } from '../hooks/useBatchResource.js'
import { BatchChart } from './BatchChart.jsx'
import { BatchRations } from './BatchRations.jsx'
import { ErrorState } from './ErrorState.jsx'

export function BatchTimeline({ batchId, dateFrom, dateTo }) {
  const { data, error, isLoading, refetch } = useBatchResource(getBatchTimeline, batchId, {
    dateFrom,
    dateTo,
  })

  if (isLoading)
    return (
      <p className="status" role="status">
        Cargando la serie del lote…
      </p>
    )

  if (error) {
    return (
      <ErrorState
        title="No se ha podido cargar la serie del lote."
        error={error}
        onRetry={refetch}
      />
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

      <BatchRations rationPeriods={data.ration_periods} />

      {days > 0 && (
        <BatchChart
          window={data.window}
          dailyYields={data.daily_yields}
          milkSamples={data.milk_samples}
          rationPeriods={data.ration_periods}
          notice={data.milk_analytes_notice}
        />
      )}
    </>
  )
}
