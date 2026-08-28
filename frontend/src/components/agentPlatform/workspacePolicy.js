import { AGENT_MODE_IDS } from '../../config/agentModes.js'

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

// Workspace tasks may be configured with non-chat modes (social/custom). Only
// switch the conversation when the task explicitly targets a supported agent.
export const resolveTaskWorkspaceMode = (task, currentMode) => {
  const taskMode = typeof task?.execution_mode === 'string'
    ? task.execution_mode.trim()
    : ''
  return AGENT_MODE_IDS.includes(taskMode) ? taskMode : currentMode
}

export const resolveAgentSelection = (mode, state) => {
  if (!AGENT_MODE_IDS.includes(mode)) {
    return { mode, action: 'invalid' }
  }

  return {
    mode,
    action: isAgentModeRunning(mode, state) ? 'open-running' : 'reset-and-open'
  }
}
