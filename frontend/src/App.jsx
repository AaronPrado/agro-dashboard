import { useCallback, useState } from 'react'
import { listAnimals } from './api/animals.js'
import { useApiResource } from './hooks/useApiResource.js'

function App() {
  const [pageNumber, setPageNumber] = useState(1)

  const request = useCallback(
    (options) => listAnimals({ page: pageNumber }, options),
    [pageNumber],
  )
  const { data: page, error, isLoading } = useApiResource(request)

  return (
    <main>
      <h1>Animales</h1>

      <nav className="pagination" aria-label="Paginación del censo">
        <button
          type="button"
          onClick={() => setPageNumber((current) => current - 1)}
          disabled={!page?.previous}
        >
          ← Anterior
        </button>
        <button
          type="button"
          onClick={() => setPageNumber((current) => current + 1)}
          disabled={!page?.next}
        >
          Siguiente →
        </button>
        <span className="pagination__position">Página {pageNumber}</span>
      </nav>

      {isLoading && <p className="status">Cargando animales…</p>}

      {error && (
        <div className="status status--error" role="alert">
          <strong>No se han podido cargar los animales.</strong>
          <p className="status__detail">{error.message}</p>
        </div>
      )}

      {page && page.results.length === 0 && (
        <p className="status">
          La API responde, pero no hay ningún animal dado de alta.
        </p>
      )}

      {page && page.results.length > 0 && (
        <table>
          <caption>
            {page.count} animales en la API; se muestran {page.results.length}.
          </caption>
          <thead>
            <tr>
              <th scope="col">Crotal</th>
              <th scope="col">Explotación</th>
              <th scope="col">Raza</th>
              <th scope="col">Partos</th>
              <th scope="col">Último parto</th>
              <th scope="col">Estado</th>
            </tr>
          </thead>
          <tbody>
            {page.results.map((animal) => (
              <tr key={animal.id}>
                <td>
                  <code>{animal.ear_tag}</code>
                </td>
                <td>{animal.farm_name}</td>
                <td>{animal.breed_display}</td>
                <td>{animal.lactation_number}</td>
                <td>{animal.last_calving_date ?? '—'}</td>
                <td>{animal.is_active ? 'Activa' : 'Baja'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}

export default App
