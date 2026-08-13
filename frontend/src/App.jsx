import { useCallback, useState } from 'react'
import { listBatches } from './api/batches.js'
import { BatchPicker } from './components/BatchPicker.jsx'
import { BatchSummary } from './components/BatchSummary.jsx'
import { DateWindow } from './components/DateWindow.jsx'
import { useApiResource } from './hooks/useApiResource.js'

function App() {
  const [batchId, setBatchId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const request = useCallback((options) => listBatches({}, options), [])
  const { data: page, error, isLoading } = useApiResource(request)

  const batches = page?.results ?? []
  const selected = batches.find((batch) => String(batch.id) === batchId) ?? null

  return (
    <main>
      <h1>Vista de lote</h1>

      {isLoading && <p className="status">Cargando lotes…</p>}

      {error && (
        <div className="status status--error" role="alert">
          <strong>No se han podido cargar los lotes.</strong>
          <p className="status__detail">{error.message}</p>
        </div>
      )}

      {page && batches.length === 0 && (
        <p className="status">La API responde, pero no hay ningún lote dado de alta.</p>
      )}

      {batches.length > 0 && (
        <BatchPicker batches={batches} value={batchId} onChange={setBatchId} />
      )}

      {page && page.count > batches.length && (
        <p className="picker__note">
          Se muestran {batches.length} de {page.count} lotes.
        </p>
      )}

      {selected && (
        <section>
          <h2 className="batch__title">
            {selected.name} · {selected.farm_name} ({selected.farm_code})
          </h2>
          <p className="batch__note">Ración vigente: {selected.current_ration ?? '—'}</p>

          <DateWindow
            dateFrom={dateFrom}
            dateTo={dateTo}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onReset={() => {
              setDateFrom('')
              setDateTo('')
            }}
          />

          <BatchSummary batchId={selected.id} dateFrom={dateFrom} dateTo={dateTo} />
        </section>
      )}
    </main>
  )
}

export default App
