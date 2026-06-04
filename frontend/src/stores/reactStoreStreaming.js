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
