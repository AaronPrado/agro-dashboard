const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
    constructor(message, { status = null, url }) {
        super(message)
        this.name = 'ApiError'
        this.status = status
        this.url = url
    }
}

export async function requestJson(path, { signal } = {}) {
    const url = `${BASE_URL}${path}`
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
