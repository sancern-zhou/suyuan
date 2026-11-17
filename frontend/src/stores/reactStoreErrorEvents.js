// 后端在瞬时故障（网关 504/过载/超时）事件上带 silent 标记：运行时会自动重试，
// 中间态失败只留服务端日志，不渲染成对话区气泡。
export const isSilentErrorEvent = (data = {}) => (
  !!data && typeof data === 'object' && data.silent === true
)

// 重试链耗尽时后端给友好文案（user_message），技术堆栈只进日志。
export const fatalErrorDisplayText = (data = {}) => {
  const friendly = data?.user_message
  if (typeof friendly === 'string' && friendly.trim()) return friendly.trim()
  const raw = data?.error
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  return '致命错误'
}
