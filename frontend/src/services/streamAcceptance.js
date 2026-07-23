export function acceptStreamResponse(response, onAccepted) {
  if (!response?.ok) {
    throw new Error(`HTTP error! status: ${response?.status}`)
  }
  if (!response.body) {
    throw new Error('Response body is null')
  }
  if (typeof onAccepted === 'function') onAccepted()
  return response.body
}
