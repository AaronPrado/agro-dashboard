import { useEffect, useState } from 'react'

/**
 * Ejecuta una petición a la API y expone su carga, su error y su resultado.
 *
 * `request` debe ser estable entre renders —el llamante la envuelve en
 * `useCallback`—, porque su identidad es a la vez la dependencia del efecto y
 * la clave con la que se descarta el resultado de una petición ya superada.
 *
 * @param {(options: {signal: AbortSignal}) => Promise<unknown>} request
 * @returns {{data: unknown｜null, error: Error｜null, isLoading: boolean}}
 */
export function useApiResource(request) {
  const [state, setState] = useState({ request: null, data: null, error: null })

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    request({ signal: controller.signal })
      .then((data) => {
        if (!cancelled) setState({ request, data, error: null })
      })
      .catch((error) => {
        if (!cancelled && error.name !== 'AbortError') {
          setState({ request, data: null, error })
        }
      })

    // Abortar corta la petición en vuelo, pero no deshace una respuesta que ya
    // se resolvió: la bandera cubre esa ventana entre la promesa asentada y la
    // limpieza del efecto.
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [request])

  // La respuesta guardada pertenece a la petición que la produjo. Si no es la
  // vigente, lo que hay que pintar es la carga de la nueva, sin escribir estado.
  const isStale = state.request !== request

  return {
    data: isStale ? null : state.data,
    error: isStale ? null : state.error,
    isLoading: isStale,
  }
}
