export function restoredConversationPolicy(session = {}) {
  const readOnly = session.source === 'social' || session.read_only_on_web === true
  return {
    readOnly,
    notice: readOnly ? '微信会话历史仅支持查看' : '',
    newConversationRequired: readOnly
  }
}
