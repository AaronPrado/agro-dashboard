import { useCallback, useState } from 'react'
import { listBatches } from './api/batches.js'
import { BatchPicker } from './components/BatchPicker.jsx'
import { useApiResource } from './hooks/useApiResource.js'

function App() {
  const [batchId, setBatchId] = useState('')

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

      {selected && <p className="status">Lote seleccionado: {selected.name}</p>}
    </main>
  )
}

export default App
