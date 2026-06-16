export const defaultContentToString = (content) => {
  if (content === null || content === undefined) {
    return ''
  }
  if (typeof content === 'string') {
    return content
  }
  if (Array.isArray(content)) {
    const textBlocks = content
      .filter(block => block.type === 'text' || block.type === 'thinking')
      .map(block => block.text || block.thinking || '')
    return textBlocks.length > 0 ? textBlocks.join('') : ''
  }
  if (typeof content === 'object') {
    if (content.text) return String(content.text)
    if (content.thinking) return String(content.thinking)
    if (content.message) return String(content.message)
    try {
      return JSON.stringify(content)
    } catch {
      return String(content)
    }
  }
  return String(content)
}

export const convertStreamingAnswerToThoughtIfToolPlanning = (
  modeState,
  contentToString = defaultContentToString
) => {
  const messageId = modeState?.streamingAnswerMessageId
  if (!messageId) return false

  const message = modeState.messages.find(m => m.id === messageId)
  if (!message || message.type !== 'final') return false

  const content = contentToString(message.content).trim()
  if (!content) {
    modeState.streamingAnswerMessageId = null
    modeState.finalAnswer = ''
    return true
  }

  Object.assign(message, {
    type: 'thought',
    content,
    streaming: false,
    data: {
      ...(message.data || {}),
      converted_from: 'pre_tool_streaming_text'
    }
  })

  modeState.streamingAnswerMessageId = null
  modeState.finalAnswer = ''
  modeState._forceRenderCount++
  return true
}

const PROCESS_MESSAGE_TYPES = new Set(['thought', 'tool_use', 'tool_result'])

const hasUnfinalizedProcessOutput = (messages = []) => {
  let lastBoundaryType = null
  for (let i = messages.length - 1; i >= 0; i--) {
    const type = messages[i]?.type || messages[i]?.role
    if (type === 'final' || type === 'assistant' || type === 'error') {
      lastBoundaryType = 'final'
      break
    }
    if (type === 'user' && !messages[i]?.steering) {
      lastBoundaryType = 'user'
      break
    }
  }

  if (lastBoundaryType !== 'user') return false
  return messages.some((message, index) => {
    const type = message?.type || message?.role
    if (!PROCESS_MESSAGE_TYPES.has(type)) return false
    const previousUserIndex = messages
      .slice(0, index)
      .reduce((lastIndex, item, itemIndex) => (
        (item?.type || item?.role) === 'user' && !item?.steering ? itemIndex : lastIndex
      ), -1)
    const previousFinalIndex = messages
      .slice(0, index)
      .reduce((lastIndex, item, itemIndex) => {
        const itemType = item?.type || item?.role
        return itemType === 'final' || itemType === 'assistant' || itemType === 'error' ? itemIndex : lastIndex
      }, -1)
    return previousUserIndex > previousFinalIndex
  })
}

export const freezeActiveAssistantOutput = (
  modeState,
  {
    reason = 'interrupted',
    content = '已暂停当前分析，保留已产生的分析过程。'
  } = {},
  contentToString = defaultContentToString
) => {
  if (!modeState) return false
  modeState.messages = modeState.messages || []

  const messageId = modeState.streamingAnswerMessageId
  if (messageId) {
    const message = modeState.messages.find(m => m.id === messageId)
    if (message && message.type === 'final') {
      const frozenContent = contentToString(message.content).trim()
      if (frozenContent) {
        Object.assign(message, {
          content: frozenContent,
          streaming: false,
          renderVersion: (message.renderVersion || 0) + 1,
          data: {
            ...(message.data || {}),
            frozen_from: reason
          }
        })
        modeState.streamingAnswerMessageId = null
        modeState.finalAnswer = frozenContent
        modeState._forceRenderCount = (modeState._forceRenderCount || 0) + 1
        return true
      }
    }
    modeState.streamingAnswerMessageId = null
  }

  if (!hasUnfinalizedProcessOutput(modeState.messages)) {
    return false
  }

  modeState.messages.push({
    id: `frozen_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
    type: 'final',
    content,
    data: {
      frozen_from: reason
    },
    attachments: null,
    timestamp: new Date().toISOString(),
    streaming: false
  })
  modeState.finalAnswer = content
  modeState._forceRenderCount = (modeState._forceRenderCount || 0) + 1
  return true
}
