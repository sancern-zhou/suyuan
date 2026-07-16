import { AGENT_MODE_IDS } from '../../config/agentModes.js'

const modeFromSessionId = sessionId => {
  if (!sessionId || typeof sessionId !== 'string') return null
  const match = sessionId.match(/^([a-z]+)_session_/)
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

  return candidates.find(mode => AGENT_MODE_IDS.includes(mode)) || 'assistant'
}
