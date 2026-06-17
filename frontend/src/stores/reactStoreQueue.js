const normalizeText = (content) => String(content || '').trim()

export const createClientMessageId = (prefix = 'client_msg') => (
  `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
)

export const hasShownClientMessage = (state = {}, clientMessageId = null) => {
  if (!clientMessageId || !Array.isArray(state.messages)) return false
  return state.messages.some(message => message.clientMessageId === clientMessageId)
}

export const enqueueUserInput = (
  state,
  {
    query,
    options = {},
    data = null,
    attachments = null,
    timestamp = new Date().toISOString()
  } = {}
) => {
  if (!state) return null
  const text = normalizeText(query)
  if (!text && !attachments) return null

  state.pendingUserInputs = state.pendingUserInputs || []
  state.messages = state.messages || []

  const clientMessageId = options.clientMessageId || createClientMessageId('queued_user')
  const queuedOptions = {
    ...options,
    clientMessageId,
    queuedAlreadyShown: true
  }

  if (!state.pendingUserInputs.some(item => item?.clientMessageId === clientMessageId)) {
    state.pendingUserInputs.push({
      query,
      options: queuedOptions,
      clientMessageId
    })
  }

  if (!hasShownClientMessage(state, clientMessageId)) {
    state.messages.push({
      id: clientMessageId,
      clientMessageId,
      type: 'user',
      content: query,
      data,
      attachments,
      timestamp,
      queued: true
    })
  }

  return clientMessageId
}
