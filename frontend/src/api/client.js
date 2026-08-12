const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
    constructor(message, { status = null, url }) {
        super(message)
        this.name = 'ApiError'
        this.status = status
        this.url = url
    }
}

function toQuery(params) {
    const search = new URLSearchParams()

    for (const [key, value] of Object.entries(params ?? {})) {
        // Un parámetro sin valor no es un filtro vacío: es la ausencia de filtro,
        // así que no viaja. `?page=` daría 400 en un endpoint que espera entero.
        if (value !== undefined && value !== null && value !== '') {
            search.set(key, value)
        }
    }

    const query = search.toString()
    return query ? `?${query}` : ''
}

export async function requestJson(path, { params, signal } = {}) {
    const url = `${BASE_URL}${path}${toQuery(params)}`
    let response

    try {
        response = await fetch(url, { headers: { Accept: 'application/json' }, signal })
    } catch (cause) {
        if (cause.name === 'AbortError') throw cause
        throw new ApiError('No se pudo contactar con la API.', { url })
    }

    if (!response.ok) {
        throw new ApiError(`La API respondió con ${response.status}.`, {
            status: response.status,
            url,
        })
    }

    return response.json()
}
