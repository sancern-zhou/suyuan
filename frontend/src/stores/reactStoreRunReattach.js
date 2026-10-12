// 运行中任务（detached run）接流的状态跟踪（共享层）。
//
// 会话恢复时通过 GET /api/agent/stream 接回仍在运行的任务：流里除了业务事件
// （转发给 reactStore.handleEvent）外还有传输层事件（stream_open/stream_closed/
// stream_lost），以及"结束但无业务终止事件"（镜像丢失/过期）的边界情况。
// 本模块把事件过滤与结束态判定抽成纯函数，便于单元测试。

const TERMINAL_RUN_EVENT_TYPES = new Set(['complete', 'incomplete', 'fatal_error', 'interrupted'])
const TRANSPORT_EVENT_TYPES = new Set(['stream_open', 'stream_closed'])

export function createRunStreamTracker() {
  return { sawTerminal: false, sawStreamLost: false }
}

/**
 * 观察一帧接流事件。
 * @returns {boolean} 是否应把该业务事件转发给 handleEvent
 */
export function observeRunStreamEvent(tracker, event) {
  const type = event?.type
  if (type === 'stream_lost') {
    tracker.sawStreamLost = true
    return false
  }
  if (TRANSPORT_EVENT_TYPES.has(type)) {
    return false
  }
  if (TERMINAL_RUN_EVENT_TYPES.has(type)) {
    tracker.sawTerminal = true
  }
  return true
}

/**
 * 流结束后是否需要向用户提示"没有可展示的进度"：
 * 只有既没等到业务终止事件、会话里又没有任何可展示内容时才提示。
 */
export function shouldReportMissingRunProgress(tracker, messageCount = 0) {
  return !tracker.sawTerminal && (Number(messageCount) || 0) === 0
}
