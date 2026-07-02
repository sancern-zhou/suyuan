const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/cognitive-maps`

async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }

  if (method !== 'GET' && method !== 'HEAD' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const userId = localStorage.getItem('userId') || 'anonymous'
  headers['X-User-Id'] = userId

  const response = await fetch(url, {
    ...options,
    method,
    headers
  })

  if (!response.ok) {
    const errorText = await response.text()
    let errorDetail = errorText
    try {
      const errorJson = JSON.parse(errorText)
      errorDetail = errorJson.detail || errorJson.message || errorText
    } catch (error) {
      // Keep raw response text.
    }
    throw new Error(errorDetail || `HTTP error! status: ${response.status}`)
  }

  if (response.status === 204) {
    return null
  }

  return await response.json()
}

export async function listCognitiveMaps() {
  return await request(BASE_URL)
}

export async function createCognitiveMap(params) {
  return await request(BASE_URL, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

export async function deleteCognitiveMap(mapId) {
  return await request(`${BASE_URL}/${mapId}`, {
    method: 'DELETE'
  })
}

export async function getCognitiveMapBindings(mapId) {
  return await request(`${BASE_URL}/${mapId}/bindings`)
}

export async function updateCognitiveMapBindings(mapId, params) {
  return await request(`${BASE_URL}/${mapId}/bindings`, {
    method: 'PUT',
    body: JSON.stringify(params)
  })
}

export async function queryCognitiveMaps(params) {
  return await request(`${BASE_URL}/query`, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

export async function queryCognitiveMapGraph(mapId, params) {
  return await request(`${BASE_URL}/${mapId}/query-graph`, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

export async function uploadCognitiveMapFile(mapId, file) {
  const formData = new FormData()
  formData.append('file', file)

  return await request(`${BASE_URL}/${mapId}/files`, {
    method: 'POST',
    body: formData
  })
}

export async function buildCognitiveMap(mapId, params = {}) {
  return await request(`${BASE_URL}/${mapId}/build`, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

export async function publishCognitiveMap(mapId) {
  return await request(`${BASE_URL}/${mapId}/publish`, {
    method: 'POST'
  })
}

export async function listCognitiveMapFiles(mapId) {
  return await request(`${BASE_URL}/${mapId}/files`)
}

export async function listCognitiveMapBuildRuns(mapId) {
  return await request(`${BASE_URL}/${mapId}/build-runs`)
}

export async function getCognitiveMapEvaluation(mapId) {
  return await request(`${BASE_URL}/${mapId}/evaluation`)
}

export async function getCognitiveMapEvidenceDetail(mapId, evidenceId) {
  return await request(`${BASE_URL}/${mapId}/evidence/${evidenceId}`)
}
