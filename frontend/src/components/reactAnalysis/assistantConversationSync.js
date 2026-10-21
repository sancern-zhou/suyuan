// A SQL snapshot replaces its own window; older loaded history stays in place.
export function mergeAssistantSnapshot(state, snapshot) {
  if (!state || state.isAnalyzing || state.sessionId !== snapshot.session_id || snapshot.unchanged) return false
  const incoming = snapshot.messages || []
  if (!incoming.length) return false
  const existing = new Map(state.messages.map(message => [message.id, message]))
  const older = state.messages.filter(message => Number.isInteger(message.sequence_number) &&
    message.sequence_number < snapshot.oldest_sequence)
  state.messages = [...older, ...incoming.map(message => ({
    ...message, streaming: false,
    ...(existing.get(message.id)?.expanded === undefined ? {} : { expanded: existing.get(message.id).expanded })
  }))]
  const final = [...state.messages].reverse().find(message => message.type === 'final')
  state.finalAnswer = final?.content || ''
  return true
}
