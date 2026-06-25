const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function postMapProgramReceipt({ sessionId, receipt, fetchImpl = fetch } = {}) {
  if (!sessionId || !receipt?.program_id) {
    return null
  }

  const response = await fetchImpl(`${API_BASE_URL}/query-dashboard/map-program-receipts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      session_id: sessionId,
      receipt
    })
  })

  if (!response.ok) {
    throw new Error(`map program receipt failed: ${response.status}`)
  }

  return response.json()
}
