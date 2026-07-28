export function normalizeRestoredContent(content) {
  if (typeof content !== 'string') return content

  const trimmed = content.trim()
  const looksLikeSerializedString =
    trimmed.length >= 2 &&
    trimmed.startsWith('"') &&
    trimmed.endsWith('"') &&
    /\\(?:u[0-9a-fA-F]{4}|n|r|t|"|\\)/.test(trimmed)

  if (looksLikeSerializedString) {
    try {
      const decoded = JSON.parse(trimmed)
      return typeof decoded === 'string' ? decoded : content
    } catch {
      return content
    }
  }

  // Older session records can contain JSON Unicode escapes without the
  // surrounding JSON string delimiters. Decode those escapes before Markdown
  // rendering, while leaving ordinary backslash sequences untouched.
  if (!/\\u[0-9a-fA-F]{4}/.test(content)) return content
  return content.replace(/\\u([0-9a-fA-F]{4})/g, (_, codeUnit) =>
    String.fromCharCode(Number.parseInt(codeUnit, 16))
  )
}

export function normalizeRestoredMessages(messages) {
  if (!Array.isArray(messages)) return messages
  return messages.map((message) => {
    if (!message || typeof message !== 'object') return message
    const content = normalizeRestoredContent(message.content)
    return content === message.content ? message : { ...message, content }
  })
}
