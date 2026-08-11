import { useEffect, useState } from 'react'
import { listFarms } from './api/farms.js'

function App() {
  const [page, setPage] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()

    listFarms({ signal: controller.signal })
      .then(setPage)
      .catch((cause) => {
        if (cause.name !== 'AbortError') setError(cause)
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Explotaciones</h1>

      {isLoading && <p className="status">Cargando explotaciones…</p>}

      {error && (
        <div className="status status--error" role="alert">
          <strong>No se han podido cargar las explotaciones.</strong>
          <p className="status__detail">{error.message}</p>
        </div>
      )}

      {page && page.results.length === 0 && (
        <p className="status">
          La API responde, pero no hay ninguna explotación dada de alta.
        </p>
      )}

      {page && page.results.length > 0 && (
        <table>
          <caption>
            {page.count} explotaciones en la API; se muestran{' '}
            {page.results.length}.
          </caption>
          <thead>
            <tr>
              <th scope="col">Nombre</th>
              <th scope="col">Código</th>
              <th scope="col">Municipio</th>
              <th scope="col">Provincia</th>
            </tr>
          </thead>
          <tbody>
            {page.results.map((farm) => (
              <tr key={farm.id}>
                <td>{farm.name}</td>
                <td>
                  <code>{farm.code}</code>
                </td>
                <td>{farm.municipality}</td>
                <td>{farm.province}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}

export default App
