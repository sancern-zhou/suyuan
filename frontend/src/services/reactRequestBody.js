// 相对导入：本模块会被 node --test 直测，别名仅在 vite 下可解析。
import { projectConfig } from '../config/projectConfig.js'

export function buildAnalyzeRequestBody(query, options = {}) {
  const {
    sessionId = null,
    enhanceWithHistory = true,
    // null = 不设步数上限（后端靠上下文压缩续跑）；显式传值仍作兜底上限
    maxIterations = null,
    assistantMode = null,
    agentMode = 'expert',
    knowledgeBaseIds = null,
    // 默认档位随项目配置（frontend.default_model_tier）。
    modelTier = projectConfig.defaultModelTier,
    skillIds = [],
    contextRefs = [],
    activeContexts = null,
    boardContext = null,
    mapContext = null,
    userIdentifier = null,
    isInterruption = false,
    previousPausedRunId = null,
    pageContext = null
  } = options

  const body = {
    query,
    skill_ids: skillIds,
    context_refs: contextRefs,
    active_contexts: activeContexts,
    session_id: sessionId,
    user_id: userIdentifier,
    enhance_with_history: enhanceWithHistory,
    assistant_mode: assistantMode,
    mode: agentMode,
    knowledge_base_ids: knowledgeBaseIds,
    model_tier: modelTier,
    is_interruption: isInterruption,
    previous_paused_run_id: previousPausedRunId
  }

  if (maxIterations !== null) body.max_iterations = maxIterations
  if (boardContext !== null) body.board_context = boardContext
  if (mapContext !== null) body.map_context = mapContext
  if (agentMode === 'assistant' && pageContext) body.page_context = pageContext
  return body
}
