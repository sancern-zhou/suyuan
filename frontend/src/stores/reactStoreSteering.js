import { enqueueUserInput } from './reactStoreQueue.js'

const normalizeText = (content) => String(content || '').trim()

export const addPendingSteeringInput = (state, content, timestamp = new Date().toISOString()) => {
  if (!state || !content) return null
  state.pendingSteeringInputs = state.pendingSteeringInputs || []
  const item = {
    id: `steer_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    content,
    status: 'pending',
    timestamp
  }
  state.pendingSteeringInputs.push(item)
  return item.id
}

export const removePendingSteeringInput = (state, content, inputId = null) => {
  if (!state?.pendingSteeringInputs?.length) return null
  const normalizedContent = normalizeText(content)
  const index = state.pendingSteeringInputs.findIndex(item => (
    inputId
      ? item?.id === inputId
      : String(item.content || '').trim() === normalizedContent
  ))
  if (index === -1) return null
  const [removed] = state.pendingSteeringInputs.splice(index, 1)
  return removed
}

export const applyPendingSteeringInputs = (
  state,
  contents = [],
  timestamp = new Date().toISOString(),
  inputIds = []
) => {
  if (!state || !Array.isArray(contents)) return 0
  state.pendingSteeringInputs = state.pendingSteeringInputs || []
  state.messages = state.messages || []

  let appliedCount = 0
  for (const [index, content] of contents.entries()) {
    const text = normalizeText(content)
    if (!text) continue

    const removed = removePendingSteeringInput(state, text, inputIds[index] || null)
    if (!removed) continue

    appliedCount++
    const alreadyShown = state.messages.some(message => (
      message?.steeringInputId === removed.id ||
      message?.id === removed.id
    ))
    if (!alreadyShown) {
      state.messages.push({
        id: removed.id,
        steeringInputId: removed.id,
        type: 'user',
        content: text,
        data: { source: 'steering_applied' },
        attachments: null,
        timestamp: removed.timestamp || timestamp,
        steering: true,
        steeringStatus: 'applied'
      })
    }
  }

  return appliedCount
}

export const fallbackSteeringInputToQueue = (
  state,
  content,
  steeringInputId,
  timestamp = new Date().toISOString()
) => {
  if (!state || !steeringInputId) return null
  return enqueueUserInput(state, {
    query: content,
    options: {
      agentMode: 'assistant',
      clientMessageId: `queued_${steeringInputId}`
    },
    data: {
      source: 'steering_fallback',
      steering_input_id: steeringInputId
    },
    timestamp
  })
}

export const promoteUnappliedSteeringInputsToQueue = (
  state,
  options = {}
) => {
  if (!state) return 0
  const {
    agentMode = 'assistant',
    queuedAlreadyShown = true,
    timestamp = new Date().toISOString()
  } = options

  state.pendingSteeringInputs = state.pendingSteeringInputs || []
  state.pendingUserInputs = state.pendingUserInputs || []
  state.messages = state.messages || []

  const queuedItems = []

  for (const item of state.pendingSteeringInputs) {
    const text = normalizeText(item?.content)
    if (!text) continue
    queuedItems.push({
      id: item.id || `steer_legacy_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
      text,
      timestamp: item.timestamp || timestamp
    })
  }

  for (const message of state.messages) {
    if (
      message?.type === 'user' &&
      message?.steering === true &&
      message?.steeringStatus === 'pending'
    ) {
      const text = normalizeText(message.content)
      if (!text) continue
      const id = message.steeringInputId || message.clientMessageId || message.id
      if (!queuedItems.some(item => item.id === id)) {
        queuedItems.push({ id, text, timestamp: message.timestamp || timestamp })
      }
      message.steeringStatus = 'queued'
      message.queued = true
      message.data = {
        ...(message.data || {}),
        source: 'steering_unapplied'
      }
    }
  }

  state.pendingSteeringInputs = []

  let promotedCount = 0
  for (const item of queuedItems) {
    const clientMessageId = `queued_${item.id}`
    const wasQueued = state.pendingUserInputs.some(entry => (
      entry?.clientMessageId === clientMessageId
    ))
    enqueueUserInput(state, {
      query: item.text,
      options: {
        agentMode,
        queuedAlreadyShown,
        clientMessageId
      },
      data: {
        source: 'steering_unapplied',
        steering_input_id: item.id
      },
      timestamp: item.timestamp
    })
    if (!wasQueued) promotedCount++
  }

  return promotedCount
}
