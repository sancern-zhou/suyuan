// State and command contract shared by the AI conversation and event views.
// The Agent may decide what to display; business mutations still go through
// authenticated APIs and explicit user confirmation.

export const SMART_EVENT_WORKSPACE_COMMANDS = Object.freeze({
  SHOW_LIST: 'show_event_list',
  OPEN_DETAIL: 'open_event_detail',
  FILTER_LIST: 'filter_event_list',
  FOCUS_EVIDENCE: 'focus_evidence',
  COMPARE_EVENTS: 'compare_events',
  OPEN_TASK: 'open_task',
  SHOW_HISTORY: 'show_operation_history',
})

export function createSmartEventWorkspaceState(overrides = {}) {
  return {
    mode: 'list',
    eventId: null,
    eventIds: [],
    taskId: null,
    conversationId: null,
    focus: null,
    filters: {},
    followAgent: true,
    history: [],
    ...overrides,
  }
}

function remember(state, next) {
  return {
    ...next,
    history: [...(state.history || []), {
      mode: state.mode,
      eventId: state.eventId,
      eventIds: state.eventIds,
      taskId: state.taskId,
      focus: state.focus,
    }].slice(-20),
  }
}

export function applySmartEventWorkspaceCommand(state, command) {
  const current = state || createSmartEventWorkspaceState()
  if (!command || typeof command !== 'object') return current
  const type = command.type || command.command
  const payload = command.payload || command

  if (type === SMART_EVENT_WORKSPACE_COMMANDS.SHOW_LIST || type === SMART_EVENT_WORKSPACE_COMMANDS.FILTER_LIST) {
    return remember(current, {
      ...current,
      mode: 'list',
      eventId: null,
      eventIds: [],
      focus: null,
      filters: { ...(current.filters || {}), ...(payload.query || payload.filters || {}) },
    })
  }
  if (type === SMART_EVENT_WORKSPACE_COMMANDS.OPEN_DETAIL) {
    if (!payload.event_id) return current
    return remember(current, {
      ...current,
      mode: 'detail',
      eventId: String(payload.event_id),
      eventIds: [],
      focus: payload.focus || null,
    })
  }
  if (type === SMART_EVENT_WORKSPACE_COMMANDS.FOCUS_EVIDENCE) {
    const eventId = payload.event_id ? String(payload.event_id) : current.eventId
    if (!eventId) return current
    return remember(current, {
      ...current,
      mode: 'evidence',
      eventId,
      focus: payload.focus || payload.evidence || null,
    })
  }
  if (type === SMART_EVENT_WORKSPACE_COMMANDS.COMPARE_EVENTS) {
    const ids = Array.isArray(payload.event_ids) ? payload.event_ids.map(String).filter(Boolean) : []
    if (ids.length < 2) return current
    return remember(current, { ...current, mode: 'compare', eventId: null, eventIds: ids, focus: payload.compare || null })
  }
  if (type === SMART_EVENT_WORKSPACE_COMMANDS.OPEN_TASK) {
    return { ...current, taskId: payload.task_id ? String(payload.task_id) : current.taskId }
  }
  if (type === SMART_EVENT_WORKSPACE_COMMANDS.SHOW_HISTORY) {
    return { ...current, mode: 'history', eventId: payload.event_id ? String(payload.event_id) : current.eventId }
  }
  return current
}

export function toSmartEventAgentContext(state) {
  const current = state || createSmartEventWorkspaceState()
  return {
    event_id: current.eventId,
    event_ids: current.eventIds,
    task_id: current.taskId,
    conversation_id: current.conversationId,
    workspace_mode: current.mode,
    focus: current.focus,
    filters: current.filters,
  }
}

// Tool results are the transport boundary for Agent-driven right-panel
// navigation.  Keep parsing tolerant so persisted messages from older clients
// can use either result.data.ui_command or result.ui_command.
export function extractSmartEventWorkspaceCommand(messages = []) {
  for (const message of [...messages].reverse()) {
    if (message?.type !== 'tool_result') continue
    const result = message.data?.result || {}
    const command = result.data?.ui_command || result.ui_command
    if (command && typeof command === 'object') return command
  }
  return null
}
