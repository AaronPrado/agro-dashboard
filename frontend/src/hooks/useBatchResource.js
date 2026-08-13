import { useCallback } from 'react'

import { useApiResource } from './useApiResource.js'

/**
 * Pide un recurso del lote acotado por una ventana de fechas.
 *
 * Envuelve la estabilización de la petición que `useApiResource` exige, de modo
 * que los tres endpoints del lote —que comparten firma— no la repitan cada uno
 * por su cuenta.
 *
 * @param {(batchId: number, window: object, options: object) => Promise<unknown>} fetchBatch
 * @param {number} batchId
 * @param {{dateFrom?: string, dateTo?: string}} window
 */
export function useBatchResource(fetchBatch, batchId, { dateFrom, dateTo } = {}) {
  const request = useCallback(
    (options) => fetchBatch(batchId, { dateFrom, dateTo }, options),
    [fetchBatch, batchId, dateFrom, dateTo],
  )

  return useApiResource(request)
}
