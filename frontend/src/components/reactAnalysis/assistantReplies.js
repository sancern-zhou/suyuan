export function mergeAssistantReplies(state, replies) {
  if (!state?.sessionId || state.isAnalyzing) return []
  const visible = []
  const existing = new Set(state.messages.map(message => message.data?.notification_id).filter(Boolean))
  for (const reply of [...replies].reverse()) {
    if (reply.source_session_id !== state.sessionId || reply.delivery_state !== 'inbox_saved') continue
    if (!existing.has(reply.message_id)) {
      state.messages.push({
        id: reply.transcript_message_id,
        type: 'final', role: 'assistant', content: reply.content,
        timestamp: reply.created_at, streaming: false,
        data: { answer: reply.content, notification_id: reply.message_id, execution_session_id: reply.execution_session_id }
      })
      existing.add(reply.message_id)
    }
    visible.push(reply.message_id)
  }
  return visible
}
