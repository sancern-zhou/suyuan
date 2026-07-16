import { AGENT_MODE_IDS } from '../../config/agentModes.js'

export const isAgentModeRunning = (mode, state) => {
  if (state.modeStates?.[mode]?.isAnalyzing) return true

  return Object.values(state.sessionStates || {}).some(
    session => session.mode === mode && session.isAnalyzing
  )
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
