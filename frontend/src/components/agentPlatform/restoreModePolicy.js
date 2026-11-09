import { AGENT_MODE_IDS } from '../../config/agentModes.js'

const modeFromSessionId = sessionId => {
  if (!sessionId || typeof sessionId !== 'string') return null
  const match = sessionId.match(/^([a-z_]+)_session_/)
  return match?.[1] || null
}

export const resolveRestoredAgentMode = (sessionData, sessionId, currentMode) => {
  const candidates = [
    sessionData?.mode,
    sessionData?.metadata?.mode,
    modeFromSessionId(sessionId),
    currentMode,
    'assistant'
  ]

  return candidates
    .find(mode => AGENT_MODE_IDS.includes(mode)) || 'assistant'
}

/**
 * 会话的原生运行时模式（不经 UI 模式表过滤）。
 * 定时任务 custom 会话的原生模式不在前端模式切换器里，但续聊必须沿用：
 * 视图模式决定界面呈现，原生模式决定后端运行时与工具集。
 */
export const resolveRestoredNativeMode = sessionData => {
  const candidates = [sessionData?.mode, sessionData?.metadata?.mode]
  return candidates.find(mode => typeof mode === 'string' && mode) || null
}
