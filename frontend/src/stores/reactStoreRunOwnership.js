export const getEventRunId = (event = {}) => (
  event?.data?.run_id ||
  event?.run_id ||
  null
)

export const shouldApplyRunEvent = (state = {}, event = {}) => {
  const eventRunId = getEventRunId(event)
  if (!eventRunId) return true
  if (event.type === 'start') return true
  if (Array.isArray(state.ignoredRunIds) && state.ignoredRunIds.includes(eventRunId)) {
    return false
  }
  if (!state.activeRunId) return true
  return state.activeRunId === eventRunId
}
