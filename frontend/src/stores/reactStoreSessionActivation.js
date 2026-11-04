export function shouldActivateStartedSession(type, sessionId, targetMode, currentMode, activeSessionId) {
  return type === 'start' && Boolean(sessionId) && targetMode === currentMode && activeSessionId !== sessionId
}
