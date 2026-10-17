/** Read current Agent SSE events without consuming a partial network frame. */
export async function readReportResponse(response) {
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  if (!response.body) throw new Error('报告响应没有数据流')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sessionId

  const consumeFrame = (frame) => {
    const lines = frame.split(/\r?\n/)
    const type = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
    const payload = lines.filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart()).join('\n')
    if (!payload) return null // Keepalive comments are not business events.
    const data = JSON.parse(payload)
    sessionId = data.session_id || sessionId
    if (type === 'fatal_error' || type === 'error' || type === 'interrupted') {
      throw new Error(data.error || data.reason || '报告生成失败')
    }
    if (type !== 'complete') return null
    if (data.status && !['completed', 'success'].includes(data.status)) {
      throw new Error(data.reason || '报告尚未完成，请在会话中继续')
    }
    const reportContent = data.answer ?? data.response
    if (typeof reportContent !== 'string' || !reportContent.trim()) {
      throw new Error('报告生成结束，但未返回报告内容')
    }
    return { reportContent, sessionId }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let delimiter
      while ((delimiter = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, delimiter.index)
        buffer = buffer.slice(delimiter.index + delimiter[0].length)
        const result = consumeFrame(frame)
        if (result) return result
      }
      if (done) break
    }
    throw new Error('报告数据流已结束，但未收到完成事件')
  } finally {
    reader.releaseLock()
  }
}
