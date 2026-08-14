export function buildAnalyzeRequestBody(query, options = {}) {
  const {
    sessionId = null,
    enhanceWithHistory = true,
    maxIterations = 120,
    assistantMode = null,
    agentMode = 'expert',
    knowledgeBaseIds = null,
    modelTier = 'auto',
    skillIds = [],
    contextRefs = [],
    activeContexts = null,
    boardContext = null,
    mapContext = null,
    userIdentifier = null,
    isInterruption = false,
    previousPausedRunId = null
  } = options

  const body = {
    query,
    skill_ids: skillIds,
    context_refs: contextRefs,
    active_contexts: activeContexts,
    session_id: sessionId,
    user_id: userIdentifier,
    enhance_with_history: enhanceWithHistory,
    max_iterations: maxIterations,
    assistant_mode: assistantMode,
    mode: agentMode,
    knowledge_base_ids: knowledgeBaseIds,
    model_tier: modelTier,
    is_interruption: isInterruption,
    previous_paused_run_id: previousPausedRunId
  }

  if (boardContext !== null) body.board_context = boardContext
  if (mapContext !== null) body.map_context = mapContext
  return body
}
