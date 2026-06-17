export const getMessageType = (message) => {
  const type = message?.type || message?.role
  return type === 'assistant' ? 'final' : type
}

export const isSteeringUserMessage = (message) => (
  getMessageType(message) === 'user' && message?.steering === true
)

export const isProcessBoundaryMessage = (message) => {
  const type = getMessageType(message)
  if (type === 'final' || type === 'error') return true
  return type === 'user' && !isSteeringUserMessage(message)
}

const PROCESS_MESSAGE_TYPES = new Set(['thought', 'tool_use', 'tool_result'])

export const isProcessMessage = (message) => PROCESS_MESSAGE_TYPES.has(getMessageType(message))

export const getExecutingProcessMessages = (messages = []) => {
  let lastFinalIndex = -1
  let lastUserIndex = -1

  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    const type = getMessageType(message)
    if (lastFinalIndex === -1 && type === 'final') {
      lastFinalIndex = i
    }
    if (lastUserIndex === -1 && type === 'user' && !isSteeringUserMessage(message)) {
      lastUserIndex = i
    }
    if (lastFinalIndex !== -1 && lastUserIndex !== -1) {
      break
    }
  }

  if (lastUserIndex > lastFinalIndex) {
    return messages.slice(lastUserIndex + 1).filter(isProcessMessage)
  }

  if (lastFinalIndex === -1) {
    return messages.filter(isProcessMessage)
  }

  return []
}

export const getUnifiedProcessMessages = (finalMessage, allMessages = []) => {
  const finalIndex = allMessages.findIndex(message =>
    (finalMessage?.id && message.id === finalMessage.id) || message === finalMessage
  )
  if (finalIndex === -1) {
    return []
  }

  let previousBoundaryIndex = -1
  for (let i = finalIndex - 1; i >= 0; i--) {
    if (isProcessBoundaryMessage(allMessages[i])) {
      previousBoundaryIndex = i
      break
    }
  }

  const beforeFinal = allMessages
    .slice(previousBoundaryIndex + 1, finalIndex)
    .filter(isProcessMessage)

  const afterFinal = []
  for (let i = finalIndex + 1; i < allMessages.length; i++) {
    if (isProcessBoundaryMessage(allMessages[i])) {
      break
    }
    if (isProcessMessage(allMessages[i])) {
      afterFinal.push(allMessages[i])
    }
  }

  return [...beforeFinal, ...afterFinal]
}
