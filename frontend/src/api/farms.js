import { requestJson } from './client.js'

export function listFarms({ page } = {}, { signal } = {}) {
    return requestJson('/farms/', { params: { page }, signal })
}
