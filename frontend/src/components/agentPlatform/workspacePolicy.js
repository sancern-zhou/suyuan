import { AGENT_MODE_IDS } from '../../config/agentModes.js'
import { projectConfig } from '../../config/projectConfig.js'

// 前端合法智能体模式 id = 共享静态目录 ∪ 项目清单声明。清单可声明共享目录没有
// 的项目专属模式（如 gd_query/station_fault_diagnosis/operations_analysis），
// 这些模式经 agentModeOverrides 提供完整展示定义（见 agentModes.getAgentMode）。
// 选择门控、任务工作台映射、会话恢复等一律以本并集为准，不能只查静态目录。
export const resolveKnownAgentModeIds = (config = projectConfig) => Object.freeze([
  ...new Set([...AGENT_MODE_IDS, ...(Array.isArray(config?.agentModeIds) ? config.agentModeIds : [])])
])

export const KNOWN_AGENT_MODE_IDS = resolveKnownAgentModeIds()

export const isKnownAgentMode = mode => KNOWN_AGENT_MODE_IDS.includes(mode)

export const getRunningAgentSessionId = (mode, state) => {
  const activeSessionId = state.activeSessionByMode?.[mode]
  const activeSession = activeSessionId ? state.sessionStates?.[activeSessionId] : null
  if (activeSession?.mode === mode && activeSession.isAnalyzing) {
    return activeSessionId
  }

  const runningEntry = Object.entries(state.sessionStates || {}).find(
    ([, session]) => session.mode === mode && session.isAnalyzing
  )
  return runningEntry?.[0] || null
}

export const isAgentModeRunning = (mode, state) => {
  if (state.modeStates?.[mode]?.isAnalyzing) return true

  return Boolean(getRunningAgentSessionId(mode, state))
}

export const resolveTaskWorkspaceMode = (task, currentMode) => {
  const taskMode = typeof task?.execution_mode === 'string'
    ? task.execution_mode.trim()
    : ''
  return isKnownAgentMode(taskMode) ? taskMode : currentMode
}

export const resolveAgentSelection = (mode, state) => {
  if (!isKnownAgentMode(mode)) {
    return { mode, action: 'invalid' }
  }

  return {
    mode,
    action: isAgentModeRunning(mode, state) ? 'open-running' : 'reset-and-open'
  }
}
