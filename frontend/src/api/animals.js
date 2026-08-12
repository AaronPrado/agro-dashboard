import { requestJson } from './client.js'

export function listAnimals({ page } = {}, { signal } = {}) {
    return requestJson('/animals/', { params: { page }, signal })
}
