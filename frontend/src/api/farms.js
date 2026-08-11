import { requestJson } from './client.js'

export function listFarms({ signal } = {}) {
    return requestJson('/farms/', { signal })
}
