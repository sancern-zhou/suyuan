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

export async function listCognitiveMapFiles(mapId) {
  return await request(`${BASE_URL}/${mapId}/files`)
}

export async function listCognitiveMapEntities(mapId) {
  return await request(`${BASE_URL}/${mapId}/entities`)
}

export async function updateCognitiveMapEntity(mapId, entityId, params) {
  return await request(`${BASE_URL}/${mapId}/entities/${entityId}`, {
    method: 'PATCH',
    body: JSON.stringify(params)
  })
}

export async function deleteCognitiveMapEntity(mapId, entityId) {
  return await request(`${BASE_URL}/${mapId}/entities/${entityId}`, {
    method: 'DELETE'
  })
}

export async function listCognitiveMapRelations(mapId) {
  return await request(`${BASE_URL}/${mapId}/relations`)
}

export async function updateCognitiveMapRelation(mapId, relationId, params) {
  return await request(`${BASE_URL}/${mapId}/relations/${relationId}`, {
    method: 'PATCH',
    body: JSON.stringify(params)
  })
}

export async function deleteCognitiveMapRelation(mapId, relationId) {
  return await request(`${BASE_URL}/${mapId}/relations/${relationId}`, {
    method: 'DELETE'
  })
}

export async function listCognitiveMapEvidence(mapId) {
  return await request(`${BASE_URL}/${mapId}/evidence`)
}

export async function listCognitiveMapBuildRuns(mapId) {
  return await request(`${BASE_URL}/${mapId}/build-runs`)
}

export async function getCognitiveMapEvaluation(mapId) {
  return await request(`${BASE_URL}/${mapId}/evaluation`)
}
