import { requestJson } from './client.js'

export function listBatches({ farm } = {}, { signal } = {}) {
    return requestJson('/batches/', { params: { farm }, signal })
}

export function getBatchSummary(batchId, { dateFrom, dateTo } = {}, { signal } = {}) {
    return requestJson(`/batches/${batchId}/summary/`, {
        params: { date_from: dateFrom, date_to: dateTo },
        signal,
    })
}

export function getBatchTimeline(batchId, { dateFrom, dateTo } = {}, { signal } = {}) {
    return requestJson(`/batches/${batchId}/timeline/`, {
        params: { date_from: dateFrom, date_to: dateTo },
        signal,
    })
}

export function getBatchTargetCheck(batchId, { dateFrom, dateTo } = {}, { signal } = {}) {
    return requestJson(`/batches/${batchId}/target-check/`, {
        params: { date_from: dateFrom, date_to: dateTo },
        signal,
    })
}
