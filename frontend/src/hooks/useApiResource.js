import { useCallback, useEffect, useState } from 'react'

/**
 * Ejecuta una petición a la API y expone su carga, su error y su resultado.
 *
 * `request` debe ser estable entre renders —el llamante la envuelve en
 * `useCallback`—, porque su identidad forma parte de la clave con la que se
 * descarta el resultado de una petición ya superada.
 *
 * @param {(options: {signal: AbortSignal}) => Promise<unknown>} request
 * @returns {{data: unknown｜null, error: Error｜null, isLoading: boolean, refetch: () => void}}
 */
export function useApiResource(request) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ request: null, attempt: -1, data: null, error: null })

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    request({ signal: controller.signal })
      .then((data) => {
        if (!cancelled) setState({ request, attempt, data, error: null })
      })
      .catch((error) => {
        if (!cancelled && error.name !== 'AbortError') {
          setState({ request, attempt, data: null, error })
        }
      })

    // Abortar corta la petición en vuelo, pero no deshace una respuesta que ya
    // se resolvió: la bandera cubre esa ventana entre la promesa asentada y la
    // limpieza del efecto.
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [request, attempt])

  // Reintentar es repetir un efecto cuyas entradas no han cambiado, y eso solo
  // se consigue moviendo una dependencia propia.
  const refetch = useCallback(() => setAttempt((previous) => previous + 1), [])

  // La respuesta guardada pertenece a la petición y al intento que la
  // produjeron. Si no son los vigentes, lo que hay que pintar es la carga de la
  // nueva, sin escribir estado.
  const isStale = state.request !== request || state.attempt !== attempt

  return {
    data: isStale ? null : state.data,
    error: isStale ? null : state.error,
    isLoading: isStale,
    refetch,
  }
}
