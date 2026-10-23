const messageKey = message => message?.sequence_number != null
  ? `sequence:${message.sequence_number}`
  : message?.id ? `id:${message.id}` : null

export function prependHistory(state, incoming, normalize = value => value) {
  if (!incoming?.length) return
  const messages = normalize(incoming)
  const known = new Set(state.messages.map(messageKey).filter(Boolean))
  const unique = messages.filter(message => {
    const key = messageKey(message)
    if (!key) return true
    if (known.has(key)) return false
    known.add(key)
    return true
  })
  state.messages = [...unique, ...state.messages]
  // Advance from the source page even when all its messages already exist.
  const sequences = incoming.map(message => message.sequence_number).filter(Number.isFinite)
  if (sequences.length) state.pagination.oldestSequence = Math.min(...sequences)
}

export async function loadHistoryPage(state, fetchPage, isCurrent, normalize) {
  if (!state.sessionId || !state.pagination.hasMoreMessages || state.pagination.loadingMore) return
  state.pagination.loadingMore = true
  try {
    const result = await fetchPage(state.sessionId, state.pagination.oldestSequence, 30)
    if (!isCurrent()) return
    prependHistory(state, result.messages || [], normalize)
    state.pagination.hasMoreMessages = Boolean(result.has_more)
    state.pagination.totalMessageCount = result.total_count ?? state.pagination.totalMessageCount
  } finally {
    state.pagination.loadingMore = false
  }
}
