const createMessageId = () => `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

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

export const removePendingSteeringInput = (state, content) => {
  if (!state?.pendingSteeringInputs?.length) return null
  const normalizedContent = normalizeText(content)
  const index = state.pendingSteeringInputs.findIndex(item =>
    String(item.content || '').trim() === normalizedContent
  )
  if (index === -1) return null
  const [removed] = state.pendingSteeringInputs.splice(index, 1)
  return removed
}

export const applyPendingSteeringInputs = (state, contents = [], timestamp = new Date().toISOString()) => {
  if (!state || !Array.isArray(contents)) return 0
  state.pendingSteeringInputs = state.pendingSteeringInputs || []
  state.messages = state.messages || []

  let appliedCount = 0
  for (const content of contents) {
    const text = normalizeText(content)
    if (!text) continue

    removePendingSteeringInput(state, text)
    const alreadyApplied = state.messages.some(message =>
      message?.type === 'user' &&
      message?.steering === true &&
      message?.steeringStatus === 'applied' &&
      normalizeText(message.content) === text
    )
    if (alreadyApplied) continue

    state.messages.push({
      id: createMessageId(),
      type: 'user',
      content: text,
      data: { source: 'steering' },
      attachments: null,
      timestamp,
      steering: true,
      steeringStatus: 'applied',
      steeringAppliedAt: timestamp
    })
    appliedCount++
  }

  return appliedCount
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

  const queuedTexts = new Set()

  for (const item of state.pendingSteeringInputs) {
    const text = normalizeText(item?.content)
    if (text) queuedTexts.add(text)
  }

  for (const message of state.messages) {
    if (
      message?.type === 'user' &&
      message?.steering === true &&
      message?.steeringStatus === 'pending'
    ) {
      const text = normalizeText(message.content)
      if (!text) continue
      queuedTexts.add(text)
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
  for (const text of queuedTexts) {
    const alreadyQueued = state.pendingUserInputs.some(item => normalizeText(item?.query) === text)
    if (!alreadyQueued) {
      state.pendingUserInputs.push({
        query: text,
        options: {
          agentMode,
          queuedAlreadyShown
        }
      })
    }

    const alreadyShown = state.messages.some(message =>
      message?.type === 'user' &&
      normalizeText(message.content) === text &&
      (message.queued || message.steeringStatus === 'queued')
    )
    if (!alreadyShown) {
      state.messages.push({
        id: createMessageId(),
        type: 'user',
        content: text,
        data: { source: 'steering_unapplied' },
        attachments: null,
        timestamp,
        steering: false,
        queued: true
      })
    }
    promotedCount++
  }

  return promotedCount
}
