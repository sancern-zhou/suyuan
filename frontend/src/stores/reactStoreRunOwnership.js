export const getEventRunId = (event = {}) => (
  event?.data?.run_id ||
  event?.run_id ||
  null
)

// 暂停屏障失败意味着对旧 run 的等待契约已以报错收场；保留
// pendingPausedRunId 只会让后续每条消息重复撞上同一道屏障。
export const shouldClearPendingPausedRunId = (data = {}) => (
  data?.code === 'pause_checkpoint_failed'
)

export const shouldApplyRunEvent = (state = {}, event = {}) => {
  const eventRunId = getEventRunId(event)
  if (!eventRunId) return true
  if (Array.isArray(state.ignoredRunIds) && state.ignoredRunIds.includes(eventRunId)) {
    return false
  }
  if (event.type === 'start') return true
  if (!state.activeRunId) return true
  return state.activeRunId === eventRunId
}
