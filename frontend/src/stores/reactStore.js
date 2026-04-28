// ReAct Agent状态管理
// 多模式并行任务系统 - 按模式隔离状态

import { defineStore } from 'pinia'
import { agentAPI } from '@/services/reactApi'
import { autoSaveSession } from '@/api/session'

// 辅助函数：创建空的模式状态
const createEmptyModeState = () => ({
  // 基础状态
  sessionId: null,
  isAnalyzing: false,
  error: null,
  isInterruption: false,

  // 对话
  messages: [],
  currentMessage: '',

  // 分析状态
  isComplete: false,
  iterations: 0,
  maxIterations: 30,

  // 增强功能
  showReflexion: false,
  reflexionCount: 0,

  // 多专家系统状态
  expertSystemEnabled: false,
  expertResults: {},
  lastExpertResults: null,
  selectedExperts: [],

  // Office文档预览状态
  lastOfficeDocument: null,

  // 结果
  finalAnswer: '',
  finalAnswers: [],
  hasResults: false,

  // 可视化
  currentVisualization: null,
  visualizationHistory: [],
  groupedVisualizations: {
    weather: [],
    component: []
  },

  // 结果管理系统
  results: {
    map: null,
    charts: [],
    tables: [],
    text: ''
  },

  // 原有工作流字段
  sessionRound: 0,
  interventionQueue: [],

  // 消息分页加载状态
  pagination: {
    hasMoreMessages: false,
    totalMessageCount: 0,
    oldestSequence: null,
    loadingMore: false
  },

  // 流式渲染状态
  streamingAnswerMessageId: null,
  _forceRenderCount: 0,

  // 内部状态
  _lastProcessedExpertResultsHash: null
})

export const useReactStore = defineStore('react', {
  state: () => {
    // 从localStorage恢复currentMode
    const savedMode = localStorage.getItem('current-mode') || 'assistant'

    return {
      // 当前激活的模式
      currentMode: savedMode,

      // 用户标识（跨会话持久化，用于记忆共享）
      // 默认为 null，使用模式内共享记忆（不跨模式共享）
      userIdentifier: null,

      // 所有模式的状态（按模式隔离）
      modeStates: {
        assistant: createEmptyModeState(),
        expert: createEmptyModeState(),
        query: createEmptyModeState(),
        code: createEmptyModeState(),
        report: createEmptyModeState(),
        chart: createEmptyModeState(),
        tracing: createEmptyModeState()
      },

      // 工具列表（全局共享）
      availableTools: []
    }
  },

  getters: {
    // ✅ 向后兼容：当前模式的状态（核心getter）
    currentState: (state) => {
      return state.modeStates[state.currentMode] || state.modeStates.assistant
    },

    // ✅ 向后兼容：sessionId
    sessionId: (state) => state.modeStates[state.currentMode]?.sessionId || null,

    // ✅ 向后兼容：isAnalyzing
    isAnalyzing: (state) => state.modeStates[state.currentMode]?.isAnalyzing || false,

    // ✅ 向后兼容：messages
    messages: (state) => state.modeStates[state.currentMode]?.messages || [],

    // ✅ 向后兼容：agentMode (返回currentMode)
    agentMode: (state) => state.currentMode,

    // ✅ 向后兼容：error
    error: (state) => state.modeStates[state.currentMode]?.error || null,

    // ✅ 向后兼容：finalAnswer
    finalAnswer: (state) => state.modeStates[state.currentMode]?.finalAnswer || '',

    // ✅ 向后兼容：hasResults
    hasResults: (state) => state.modeStates[state.currentMode]?.hasResults || false,

    // ✅ 向后兼容：visualizationHistory
    visualizationHistory: (state) => state.modeStates[state.currentMode]?.visualizationHistory || [],

    // ✅ 向后兼容：lastExpertResults
    lastExpertResults: (state) => state.modeStates[state.currentMode]?.lastExpertResults || null,

    // ✅ 向后兼容：lastOfficeDocument
    lastOfficeDocument: (state) => state.modeStates[state.currentMode]?.lastOfficeDocument || null,

    // ✅ 向后兼容：groupedVisualizations
    groupedVisualizations: (state) => state.modeStates[state.currentMode]?.groupedVisualizations || { weather: [], component: [] },

    // ✅ 向后兼容：currentVisualization
    currentVisualization: (state) => state.modeStates[state.currentMode]?.currentVisualization || null,

    // ✅ 向后兼容：isComplete
    isComplete: (state) => state.modeStates[state.currentMode]?.isComplete || false,

    // ✅ 向后兼容：iterations
    iterations: (state) => state.modeStates[state.currentMode]?.iterations || 0,

    // ✅ 向后兼容：maxIterations
    maxIterations: (state) => state.modeStates[state.currentMode]?.maxIterations || 30,

    // ✅ 向后兼容：sessionRound
    sessionRound: (state) => state.modeStates[state.currentMode]?.sessionRound || 0,

    // 新增：获取所有正在运行的模式
    runningModes: (state) => {
      return Object.entries(state.modeStates)
        .filter(([_, modeState]) => modeState.isAnalyzing)
        .map(([mode, _]) => mode)
    },

    // 新增：获取每个模式的消息数量
    modeMessageCounts: (state) => {
      const counts = {}
      for (const [mode, modeState] of Object.entries(state.modeStates)) {
        counts[mode] = modeState.messages.length
      }
      return counts
    },

    // 对话列表（排除内部事件）
    conversation: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      return currentMessages.filter(msg =>
        msg.type === 'user' || msg.type === 'agent' || msg.type === 'thought' || msg.type === 'final'
      )
    },

    // 分析日志（内部事件）
    analysisLog: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      return currentMessages.filter(msg =>
        msg.type === 'start' || msg.type === 'tool_use' || msg.type === 'tool_result' || msg.type === 'error'
      )
    },

    // 可输入状态
    canInput: (state) => {
      const currentModeState = state.modeStates[state.currentMode]
      return currentModeState ? !currentModeState.isAnalyzing : true
    },

    // 进度
    progress: (state) => {
      const currentModeState = state.modeStates[state.currentMode]
      if (!currentModeState || currentModeState.maxIterations === 0) return 0
      return Math.min(100, Math.round((currentModeState.iterations / currentModeState.maxIterations) * 100))
    },

    // 已完成的工具调用
    completedTools: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      return currentMessages
        .filter(m => m.type === 'tool_use' && m.data?.status === 'success' && m.data?.tool_name)
        .map(m => m.data.tool_name)
    }
  },

  actions: {
    // ========== 新增：模式切换核心逻辑 ==========

    /**
     * 切换到指定模式
     * - 保存当前模式状态到localStorage
     * - 切换模式
     * - 恢复目标模式状态
     */
    switchMode(newMode) {
      if (!['assistant', 'expert', 'query', 'code', 'report', 'chart', 'tracing'].includes(newMode)) {
        console.warn('[switchMode] Invalid mode:', newMode)
        return
      }

      if (newMode === this.currentMode) {
        console.log('[switchMode] Already in mode:', newMode)
        return
      }

      console.log('[switchMode] Switching from', this.currentMode, 'to', newMode)

      // 1. 保存当前模式状态到 localStorage
      this._persistModeState(this.currentMode)

      // 2. 切换模式
      const oldMode = this.currentMode
      this.currentMode = newMode
      localStorage.setItem('current-mode', newMode)

      // 3. 恢复目标模式状态
      this._restoreModeState(newMode)

      console.log('[switchMode] Mode switched successfully')
      console.log('[switchMode] Old mode running:', this.modeStates[oldMode]?.isAnalyzing)
      console.log('[switchMode] New mode running:', this.modeStates[newMode]?.isAnalyzing)
      console.log('[switchMode] ✅ Multi-mode parallel working enabled')
    },

    /**
     * 保存模式状态到 localStorage
     * - 只保存最近50条消息
     * - 保存完整的模式状态
     */
    _persistModeState(mode) {
      if (!this.modeStates[mode]) return

      const modeState = this.modeStates[mode]

      // 只保存最近50条消息（避免localStorage超限）
      const messagesToSave = modeState.messages.slice(-50)

      const stateToSave = {
        sessionId: modeState.sessionId,
        isAnalyzing: modeState.isAnalyzing,
        error: modeState.error,
        isInterruption: modeState.isInterruption,
        messages: messagesToSave,
        currentMessage: modeState.currentMessage,
        isComplete: modeState.isComplete,
        iterations: modeState.iterations,
        maxIterations: modeState.maxIterations,
        showReflexion: modeState.showReflexion,
        reflexionCount: modeState.reflexionCount,
        expertSystemEnabled: modeState.expertSystemEnabled,
        expertResults: modeState.expertResults,
        lastExpertResults: modeState.lastExpertResults,
        selectedExperts: modeState.selectedExperts,
        lastOfficeDocument: modeState.lastOfficeDocument,
        finalAnswer: modeState.finalAnswer,
        finalAnswers: modeState.finalAnswers,
        hasResults: modeState.hasResults,
        currentVisualization: modeState.currentVisualization,
        visualizationHistory: modeState.visualizationHistory,
        groupedVisualizations: modeState.groupedVisualizations,
        results: modeState.results,
        sessionRound: modeState.sessionRound,
        interventionQueue: modeState.interventionQueue,
        streamingAnswerMessageId: modeState.streamingAnswerMessageId,
        _forceRenderCount: modeState._forceRenderCount,
        _lastProcessedExpertResultsHash: modeState._lastProcessedExpertResultsHash
      }

      try {
        localStorage.setItem(`mode-state-${mode}`, JSON.stringify(stateToSave))
        console.log(`[_persistModeState] Saved ${mode} state with ${messagesToSave.length} messages`)
      } catch (error) {
        console.error(`[_persistModeState] Failed to save ${mode} state:`, error)
        // localStorage超限，清空旧状态重试
        try {
          const minimalState = {
            sessionId: modeState.sessionId,
            messages: messagesToSave.slice(-10), // 只保留最后10条
            isAnalyzing: modeState.isAnalyzing
          }
          localStorage.setItem(`mode-state-${mode}`, JSON.stringify(minimalState))
          console.log(`[_persistModeState] Saved minimal ${mode} state`)
        } catch (retryError) {
          console.error(`[_persistModeState] Failed to save minimal state:`, retryError)
        }
      }
    },

    /**
     * 从 localStorage 恢复模式状态
     */
    _restoreModeState(mode) {
      try {
        const savedStateJSON = localStorage.getItem(`mode-state-${mode}`)
        if (!savedStateJSON) {
          console.log(`[_restoreModeState] No saved state for ${mode}`)
          return
        }

        const savedState = JSON.parse(savedStateJSON)

        // 合并保存的状态到当前模式状态
        Object.assign(this.modeStates[mode], savedState)

        console.log(`[_restoreModeState] Restored ${mode} state with ${savedState.messages?.length || 0} messages`)
      } catch (error) {
        console.error(`[_restoreModeState] Failed to restore ${mode} state:`, error)
      }
    },

    /**
     * 重置指定模式的状态
     */
    resetMode(mode) {
      if (!this.modeStates[mode]) return

      // 创建新的空状态
      const emptyState = createEmptyModeState()
      Object.assign(this.modeStates[mode], emptyState)

      // 清除localStorage
      localStorage.removeItem(`mode-state-${mode}`)

      console.log(`[resetMode] Reset mode: ${mode}`)
    },

    /**
     * 重置所有模式的状态
     */
    resetAllModes() {
      for (const mode of ['assistant', 'expert', 'query', 'code', 'report', 'chart']) {
        this.resetMode(mode)
      }
      console.log('[resetAllModes] All modes reset')
    },

    /**
     * 清理旧的模式状态（超过7天）
     */
    cleanupOldStates() {
      const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000)
      let cleanedCount = 0

      for (const mode of ['assistant', 'expert', 'query', 'code', 'report', 'chart']) {
        const stateKey = `mode-state-${mode}`
        const savedStateJSON = localStorage.getItem(stateKey)

        if (savedStateJSON) {
          try {
            const savedState = JSON.parse(savedStateJSON)

            // 检查最后一条消息的时间戳
            const lastMessage = savedState.messages && savedState.messages[savedState.messages.length - 1]
            if (lastMessage && lastMessage.timestamp) {
              const lastMessageTime = new Date(lastMessage.timestamp).getTime()
              if (lastMessageTime < sevenDaysAgo) {
                localStorage.removeItem(stateKey)
                cleanedCount++
                console.log(`[cleanupOldStates] Cleaned up ${mode} state (last message from ${new Date(lastMessageTime).toLocaleDateString()})`)
              }
            }
          } catch (error) {
            console.error(`[cleanupOldStates] Failed to parse ${mode} state:`, error)
            // 如果解析失败，删除该状态
            localStorage.removeItem(stateKey)
            cleanedCount++
          }
        }
      }

      console.log(`[cleanupOldStates] Cleanup complete: ${cleanedCount} modes cleaned`)
      return cleanedCount
    },

    /**
     * 设置当前模式的消息列表（用于会话恢复）
     */
    setMessages(messages) {
      if (!Array.isArray(messages)) {
        console.warn('[setMessages] Invalid messages:', messages)
        return
      }
      this.currentState.messages = messages
      console.log(`[setMessages] Set ${messages.length} messages for mode ${this.currentMode}`)
    },

    /**
     * 从 sessionId 中提取模式
     * sessionId 格式: ${mode}_session_${timestamp}_${random}
     */
    extractModeFromSessionId(sessionId) {
      if (!sessionId || typeof sessionId !== 'string') {
        return null
      }
      const match = sessionId.match(/^([a-z]+)_session_/)
      return match ? match[1] : null
    },

    /**
     * 根据 sessionId 获取对应模式的状态
     */
    getModeStateBySessionId(sessionId) {
      const mode = this.extractModeFromSessionId(sessionId)
      if (!mode || !this.modeStates[mode]) {
        console.warn('[getModeStateBySessionId] Cannot find mode for sessionId:', sessionId)
        return this.currentState  // 降级：返回当前模式状态
      }
      return this.modeStates[mode]
    },

    /**
     * 设置当前模式的 sessionId（用于会话恢复）
     */
    setSessionId(sessionId) {
      if (!sessionId || typeof sessionId !== 'string') {
        console.warn('[setSessionId] Invalid sessionId:', sessionId)
        return
      }
      this.currentState.sessionId = sessionId
      console.log(`[setSessionId] Set sessionId for mode ${this.currentMode}:`, sessionId)
    },

    /**
     * 设置当前模式的可视化历史（用于会话恢复）
     */
    setVisualizationHistory(visualizations) {
      if (!Array.isArray(visualizations)) {
        console.warn('[setVisualizationHistory] Invalid visualizations:', visualizations)
        return
      }
      this.currentState.visualizationHistory = visualizations
      console.log(`[setVisualizationHistory] Set ${visualizations.length} visualizations for mode ${this.currentMode}`)
    },

    /**
     * 设置最近一次Office文档（用于会话恢复）
     */
    setLastOfficeDocument(doc) {
      if (!doc) return
      this.currentState.lastOfficeDocument = doc
      console.log(`[setLastOfficeDocument] Set office document for mode ${this.currentMode}`)
    },

    /**
     * 设置当前模式的专家结果（用于会话恢复）
     */
    setLastExpertResults(results) {
      this.currentState.lastExpertResults = results
      console.log(`[setLastExpertResults] Set expert results for mode ${this.currentMode}`)
    },

    /**
     * 设置当前模式的完成状态（用于会话恢复）
     */
    setComplete(isComplete) {
      this.currentState.isComplete = !!isComplete
      console.log(`[setComplete] Set complete=${isComplete} for mode ${this.currentMode}`)
    },

    /**
     * 批量设置会话状态（用于会话恢复）
     */
    restoreSessionState(sessionData) {
      if (!sessionData) return

      if (sessionData.session_id) {
        this.setSessionId(sessionData.session_id)
      }

      if (sessionData.conversation_history && Array.isArray(sessionData.conversation_history)) {
        this.setMessages(sessionData.conversation_history)
      }

      if (sessionData.visualizations && Array.isArray(sessionData.visualizations)) {
        this.setVisualizationHistory(sessionData.visualizations)
      }

      if (sessionData.last_result) {
        this.currentState.lastExpertResults = sessionData.last_result
      }

      if (sessionData.state === 'completed') {
        this.setComplete(true)
      }

      console.log(`[restoreSessionState] Session restored for mode ${this.currentMode}`)

      // 恢复分页状态
      if (sessionData.has_more_messages !== undefined) {
        this.currentState.pagination.hasMoreMessages = sessionData.has_more_messages
        this.currentState.pagination.totalMessageCount = sessionData.total_message_count || 0
        this.currentState.pagination.oldestSequence = sessionData.oldest_sequence ?? null
      }
    },

    // ========== 消息分页加载 ==========

    /**
     * 设置分页状态
     */
    setPagination(state) {
      Object.assign(this.currentState.pagination, state)
    },

    /**
     * 前置插入更早的消息（滚动加载更多）
     */
    prependMessages(messages) {
      if (!messages || messages.length === 0) return

      // 【修复】过滤掉与现有消息重复内容的消息
      const existingContents = new Set()
      this.currentState.messages.forEach(m => {
        if (m.content) {
          existingContents.add(m.content.substring(0, 100)) // 使用前100个字符作为内容指纹
        }
      })

      const beforeCount = messages.length
      messages = messages.filter(m => {
        if (!m.content) return true
        const contentFingerprint = m.content.substring(0, 100)
        const isDuplicate = existingContents.has(contentFingerprint)
        if (isDuplicate) {
          console.warn(`[prependMessages] 过滤重复消息: ${m.id}`, { content: m.content.substring(0, 50) })
        } else {
          existingContents.add(contentFingerprint)
        }
        return !isDuplicate
      })

      if (messages.length !== beforeCount) {
        console.log(`[prependMessages] 过滤了 ${beforeCount - messages.length} 条重复消息`)
      }

      this.currentState.messages = [...messages, ...this.currentState.messages]
      if (messages.length > 0) {
        this.currentState.pagination.oldestSequence = messages[0].sequence_number
      }
    },

    /**
     * 加载更多历史消息
     */
    async loadMoreMessages() {
      const sessionId = this.currentState.sessionId
      const oldestSequence = this.currentState.pagination.oldestSequence
      const hasMore = this.currentState.pagination.hasMoreMessages

      if (!sessionId || !hasMore) {
        console.log('[loadMoreMessages] 没有更多消息可加载')
        return
      }

      if (this.currentState.pagination.loadingMore) {
        console.log('[loadMoreMessages] 正在加载中，跳过')
        return
      }

      try {
        this.currentState.pagination.loadingMore = true
        console.log(`[loadMoreMessages] 开始加载更多消息，sessionId: ${sessionId}, oldestSequence: ${oldestSequence}`)

        // 调用 API 获取更多消息
        const { getSessionMessages } = await import('@/api/session')
        const result = await getSessionMessages(sessionId, oldestSequence, 30)

        console.log('[loadMoreMessages] API返回:', result)

        // 后端直接返回数据，不是 {success, data} 格式
        const messages = result.messages || []
        console.log(`[loadMoreMessages] 加载了 ${messages.length} 条消息`)

        if (messages.length > 0) {
          this.prependMessages(messages)
        }

        // 更新分页状态（注意字段名映射）
        this.currentState.pagination.hasMoreMessages = result.has_more || false
        this.currentState.pagination.totalMessageCount = result.total_count || this.currentState.pagination.totalMessageCount

        console.log(`[loadMoreMessages] 加载完成，hasMore: ${this.currentState.pagination.hasMoreMessages}, total: ${this.currentState.pagination.totalMessageCount}`)
      } catch (error) {
        console.error('[loadMoreMessages] 加载消息失败:', error)
        // 不抛出错误，避免中断用户体验
      } finally {
        this.currentState.pagination.loadingMore = false
      }
    },

    // ========== 原有方法（适配多模式）==========

    // 获取专家标签
    getExpertLabel(expertType) {
      const labelMap = {
        'weather': '气象专家',
        'component': '组分专家',
        'viz': '可视化专家',
        'report': '报告专家'
      }
      return labelMap[expertType] || expertType
    },

    // 初始化
    async init() {
      try {
        // 获取可用工具
        const tools = await agentAPI.getTools()
        this.availableTools = tools.tools
        console.log('Available tools:', this.availableTools)

        // 恢复所有模式的状态
        for (const mode of ['assistant', 'expert', 'query', 'code', 'report', 'chart']) {
          this._restoreModeState(mode)
        }
      } catch (error) {
        this.availableTools = []
        const currentMsgs = this.currentState.messages
        if (!currentMsgs.find(msg => msg.type === 'error' && msg.source === 'tools')) {
          this.addMessage('error', '工具列表加载失败，可稍后在顶部”工具管理”里重试。', { source: 'tools', error: error.message })
        }
        console.error('Failed to load tools:', error)
      }
    },

    // 继续会话（原有工作流逻辑）
    continueSession() {
      const current = this.currentState
      current.sessionRound = Math.max(current.sessionRound + 1, 1)
      current.isAnalyzing = false
      current.error = null
      // 保留finalAnswer，让它保持直到新答案到来
      // 保留messages，但清空本轮的可视化结果
      current.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }
    },

    // 创建会话ID（按模式隔离）
    createSessionId() {
      const current = this.currentState
      if (!current.sessionId) {
        const mode = this.currentMode
        current.sessionId = `${mode}_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        console.log('[createSessionId] Created session for', mode, ':', current.sessionId)
      }
    },

    // 重置当前模式的会话
    reset() {
      const current = this.currentState
      const emptyState = createEmptyModeState()

      // 保留一些字段
      emptyState.maxIterations = current.maxIterations

      Object.assign(current, emptyState)

      console.log('[reset] Reset current mode:', this.currentMode)
    },

    // 添加消息（添加到当前模式）
    addMessage(type, content, data = null, attachments = null, extraFields = {}) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type, // 'user', 'agent', 'thought', 'tool_use', 'tool_result', 'start', 'error', 'final'
        content,
        data,
        attachments, // 附件信息
        timestamp: new Date().toISOString(),
        ...extraFields  // 支持额外字段（如 streaming, streamingAnswerId 等）
      }
      this.currentState.messages.push(message)
      return message.id
    },

    /**
     * 添加消息到指定模式（用于事件路由）
     */
    addMessageToMode(mode, type, content, data = null, attachments = null, extraFields = {}) {
      console.log(`[addMessageToMode] Called with mode=${mode}, type=${type}`)
      console.log(`[addMessageToMode] this.currentMode=${this.currentMode}`)
      console.log(`[addMessageToMode] Available modes:`, Object.keys(this.modeStates))

      if (!mode || !this.modeStates[mode]) {
        console.warn('[addMessageToMode] Invalid mode:', mode, ', falling back to current mode', this.currentMode)
        mode = this.currentMode
      }

      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type,
        content,
        data,
        attachments,
        timestamp: new Date().toISOString(),
        ...extraFields
      }

      console.log(`[addMessageToMode] Adding message to mode ${mode}, before push: ${this.modeStates[mode].messages.length} messages`)
      this.modeStates[mode].messages.push(message)
      console.log(`[addMessageToMode] After push: ${this.modeStates[mode].messages.length} messages`)
      console.log(`[addMessageToMode] Current mode ${this.currentMode} has ${this.currentState.messages.length} messages`)

      return message.id
    },

    /**
     * 获取事件的目标模式状态
     */
    getEventTargetState(eventData) {
      const sessionId = eventData?.session_id
      const eventMode = this.extractModeFromSessionId(sessionId)

      if (!eventMode) {
        // 无法从 sessionId 提取模式，使用当前模式
        return this.currentState
      }

      if (!this.modeStates[eventMode]) {
        console.warn('[getEventTargetState] Invalid mode:', eventMode)
        return this.currentState
      }

      return this.modeStates[eventMode]
    },

    // 处理ReAct事件（根据sessionId路由到正确的模式）
    handleEvent(event) {
      console.log('[handleEvent] ========================================')
      console.log('[handleEvent] Received event:', event.type)
      console.log('[handleEvent] event.data:', event.data)
      console.log('[handleEvent] event.data?.session_id:', event.data?.session_id)
      console.log('[handleEvent] this.currentMode:', this.currentMode)

      const { type, data } = event

      // 确定目标模式
      // 【修复】完全基于session_id路由，支持真正的多模式并行任务
      const sessionId = data?.session_id || event?.session_id
      console.log('[handleEvent] sessionId:', sessionId)

      const eventMode = this.extractModeFromSessionId(sessionId)
      console.log('[handleEvent] Extracted eventMode:', eventMode)

      // 【关键修复】路由逻辑：
      // 1. 优先使用session_id提取的模式（支持并行任务）
      // 2. 如果没有session_id，使用currentMode（兼容旧版事件）
      // 3. 否则使用currentMode作为默认值
      const targetMode = eventMode || this.currentMode
      console.log('[handleEvent] targetMode:', targetMode)

      // 【调试】并行任务状态
      if (eventMode && eventMode !== this.currentMode) {
        console.log(`[handleEvent] ✅ PARALLEL TASK: routing to ${eventMode} (current: ${this.currentMode}, type: ${type})`)
        console.log(`[handleEvent] Current mode state:`, {
          mode: this.currentMode,
          isAnalyzing: this.currentState.isAnalyzing,
          messageCount: this.currentState.messages.length
        })
        console.log(`[handleEvent] Target mode state:`, {
          mode: eventMode,
          isAnalyzing: this.modeStates[eventMode]?.isAnalyzing,
          messageCount: this.modeStates[eventMode]?.messages?.length
        })
      }

      const targetState = this.modeStates[targetMode] || this.currentState
      console.log('[handleEvent] targetState:', targetState)
      console.log('[handleEvent] targetState.messages.length:', targetState?.messages?.length)

      // 如果事件属于非当前模式，记录日志
      if (eventMode && eventMode !== this.currentMode) {
        console.log(`[handleEvent] ⚠️ ROUTING event to mode ${eventMode} (current: ${this.currentMode}, type: ${type})`)
      }

      // 创建局部的 addMessage 函数，自动路由到正确的模式
      const addMessage = (msgType, msgContent, msgData = null, msgAttachments = null, msgExtraFields = {}) => {
        // 确保msgContent是字符串类型
        let contentStr = msgContent
        if (typeof msgContent !== 'string') {
          if (msgContent === null || msgContent === undefined) {
            contentStr = ''
          } else {
            contentStr = JSON.stringify(msgContent)
          }
        }

        const preview = contentStr.substring(0, 50)
        console.log(`[handleEvent] addMessage called: mode=${targetMode}, type=${msgType}, content=${preview}...`)
        const msgId = this.addMessageToMode(targetMode, msgType, contentStr, msgData, msgAttachments, msgExtraFields)
        console.log(`[handleEvent] Message added to ${targetMode}, total messages: ${this.modeStates[targetMode]?.messages?.length}`)
        return msgId
      }

      switch (type) {
        case 'start': {
          // 分析开始
          addMessage('start', `开始分析: ${data?.query || ''}`)
          if (data?.session_id) {
            targetState.sessionId = data.session_id
          }
          targetState.iterations = 0
          break
        }

        case 'thought': {
          // LLM思考
          const thoughtContent = data?.thought || '思考中...'
          const reasoningContent = data?.reasoning || ''
          addMessage('thought', thoughtContent, {
            reasoning: reasoningContent,
            iteration: data?.iteration,
            timestamp: data?.timestamp
          })

          // 检测Reflexion
          if (data?.thought && data.thought.includes('[Reflexion 反思]')) {
            targetState.showReflexion = true
            targetState.reflexionCount++
          }
          break
        }

        case 'tool_use': {
          // ✅ V3: Anthropic tool_use 事件
          const toolUseData = data || {}
          const toolName = toolUseData.tool_name || 'unknown'
          const toolUseId = toolUseData.tool_use_id
          const toolInput = toolUseData.input || {}

          // 格式化工具调用信息
          let toolUseContent = `🔧 Tool Use: ${toolName}`
          if (toolUseId) {
            toolUseContent += ` (ID: ${toolUseId.substring(0, 8)}...)`
          }

          // 添加工具调用消息
          addMessage('tool_use', toolUseContent, {
            tool_use_id: toolUseId,
            tool_name: toolName,
            input: toolInput,
            iteration: toolUseData.iteration,
            timestamp: toolUseData.timestamp
          })
          break
        }

        case 'tool_result': {
          // ✅ V3: Anthropic tool_result 事件
          const toolResultData = data || {}
          const resultToolUseId = toolResultData.tool_use_id
          const result = toolResultData.result || {}
          const isError = toolResultData.is_error || false

          // 格式化工具结果信息
          let toolResultContent = isError ? '❌ Tool Error' : '✅ Tool Result'
          if (resultToolUseId) {
            toolResultContent += ` (ID: ${resultToolUseId.substring(0, 8)}...)`
          }

          // 如果有summary，使用它
          if (result.summary) {
            toolResultContent += `: ${result.summary}`
          }

          // 添加工具结果消息
          addMessage('tool_result', toolResultContent, {
            tool_use_id: resultToolUseId,
            result: result,
            is_error: isError,
            iteration: toolResultData.iteration,
            timestamp: toolResultData.timestamp
          })
          break
        }

        case 'office_document': {
          // Office文档PDF预览事件（用于驱动文档预览面板）
          // 【修复】使用targetState而不是currentState
          targetState.lastOfficeDocument = {
            pdf_preview: data?.pdf_preview,
            markdown_preview: data?.markdown_preview,
            file_path: data?.file_path,
            generator: data?.generator,
            summary: data?.summary,
            timestamp: data?.timestamp
          }
          console.log('[reactStore] office_document事件:', {
            generator: data?.generator,
            pdf_id: data?.pdf_preview?.pdf_id,
            has_markdown_preview: !!data?.markdown_preview,
            file_path: data?.file_path,
            targetMode: targetMode
          })
          break
        }

        case 'notebook_document': {
          // Notebook HTML预览事件
          targetState.lastOfficeDocument = {
            html_preview: data?.html_preview,
            file_path: data?.file_path,
            file_type: data?.file_type || 'notebook',
            generator: data?.generator,
            summary: data?.summary,
            timestamp: data?.timestamp
          }
          break
        }

        case 'streaming_text': {
          // ✅ 真正的流式文本输出
          const chunk = data?.chunk || ''
          const isComplete = data?.is_complete || false

          // 调试日志已关闭（避免刷屏）
          // if (!this._streamDebug) {
          //   this._streamDebug = { startTime: Date.now(), chunkCount: 0 }
          // }
          // this._streamDebug.chunkCount++
          // const elapsed = Date.now() - this._streamDebug.startTime
          // console.log(`[streaming_text] Chunk #${this._streamDebug.chunkCount}, ${elapsed}ms, length: ${chunk.length}`)

          if (chunk) {
            // 【关键修复】如果是第一个块，创建新消息
            if (!targetState.streamingAnswerMessageId) {
              targetState.streamingAnswerMessageId = addMessage('final', '', {
                timestamp: data?.timestamp
              }, null, { streaming: true })
            }

            // 【关键修复】找到消息并直接追加内容（使用targetState而不是currentState）
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.content += chunk
              // 同步更新 finalAnswer
              targetState.finalAnswer += chunk
            }
          }

          // 如果是最后一块，清除标志并移除 streaming 标记
          if (isComplete) {
            // 调试日志已关闭（避免刷屏）
            // const totalTime = Date.now() - this._streamDebug.startTime
            // console.log(`[streaming_text] 完成！共 ${this._streamDebug.chunkCount} 个 chunks，总耗时 ${totalTime}ms`)
            // this._streamDebug = null

            // 【去重】如果当前轮次已有 tool_use 消息，说明这段文本只是 LLM 在调用工具前的
            // 中间说明（如"已找到技能文件，让我读取其内容。"），不是最终答案。
            // 删除这个错误创建的 final 消息，避免重复显示
            const hasToolUse = targetState.messages.some(m => m.type === 'tool_use')
            if (hasToolUse && targetState.streamingAnswerMessageId) {
              const msgIdx = targetState.messages.findIndex(m => m.id === targetState.streamingAnswerMessageId)
              if (msgIdx !== -1) {
                // 如果消息内容很短（中间说明通常很短），直接删除
                const msg = targetState.messages[msgIdx]
                if (msg && msg.content && msg.content.length < 200) {
                  targetState.messages.splice(msgIdx, 1)
                }
              }
            }

            if (targetState.streamingAnswerMessageId) {
              const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
              if (msg) {
                msg.streaming = false
                // 强制触发响应式更新，确保流式完成后重新渲染
                targetState._forceRenderCount++
              }
            }
            targetState.streamingAnswerMessageId = null

            // ✅ 自动保存会话：每次AI回复完成时保存
            if (targetState.sessionId && targetState.messages.length > 0) {
              console.log('[autoSave] AI回复完成，自动保存会话')
              // 使用 fire-and-forget 方式，不阻塞UI
              autoSaveSession(targetState.sessionId, targetState.messages, 'active').catch(err => {
                console.warn('[autoSave] 自动保存失败:', err)
              })
            }
          }
          break
        }

        case 'complete': {
          // 分析完成
          console.log('[event:complete] ========== 收到complete事件 ==========')
          console.log('[event:complete] 数据:', JSON.stringify(data, null, 2))
          console.log('[event:complete] has answer:', !!data?.answer)
          console.log('[event:complete] answer value:', data?.answer)
          console.log('[event:complete] has response:', !!data?.response)
          console.log('[event:complete] response value:', data?.response)
          console.log('[event:complete] has expert_results:', !!data?.expert_results)
          console.log('[event:complete] has visuals:', !!(data?.visuals && Array.isArray(data.visuals) && data.visuals.length > 0))

          // 【修复】使用targetState而不是currentState，确保状态更新到正确的模式
          targetState.isAnalyzing = false
          targetState.isComplete = true
          targetState.iterations = data?.iterations || targetState.iterations
          // ✅ 优先使用response字段，兼容answer字段
          targetState.finalAnswer = data?.response || data?.answer || ''
          targetState.hasResults = true

          // 记录最终答案（原有工作流逻辑）
          targetState.finalAnswers.push({
            run: targetState.sessionRound,
            content: data?.response || data?.answer || '分析完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          // 如果已经通过 answer_delta 流式创建了最终答案消息，则只更新其元数据，避免重复追加一条消息
          console.log('[event:complete] streamingAnswerMessageId:', targetState.streamingAnswerMessageId)
          if (targetState.streamingAnswerMessageId) {
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              // 【修复】确保流式结束状态，并触发响应式更新
              msg.streaming = false
              // 【关键修复】用后端返回的完整response覆盖content（确保格式正确）
              if (data?.response) {
                msg.content = data.response
                targetState.finalAnswer = data.response
              }
              // 使用 Object.assign 确保响应式更新
              Object.assign(msg, {
                data: {
                  ...(msg.data || {}),
                  iterations: data?.iterations,
                  session_id: data?.session_id,
                  timestamp: data?.timestamp,
                  expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
                  sources: data?.sources || null  // ✅ 知识问答参考来源
                }
              })
              // 触发数组响应式更新
              targetState.messages = [...targetState.messages]
              console.log('[event:complete] 更新已有消息的数据，streaming设置为false')
            }
          } else if (data?.answer || data?.response) {
            // 【修复】优先使用response字段，兼容answer字段
            const finalContent = data?.response || data?.answer || ''
            console.log('[event:complete] 添加final消息，content:', finalContent.substring(0, 50) + '...')
            addMessage('final', finalContent, {
              iterations: data?.iterations,
              session_id: data?.session_id,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
              sources: data?.sources || null  // ✅ 知识问答参考来源
            }, null, { streaming: false })  // 【修复】明确设置 streaming: false
            console.log('[event:complete] messages数量:', targetState.messages.length)
          } else {
            console.log('[event:complete] 警告：没有answer或response字段，不添加final消息')
          }

          // 处理可视化数据
          if (data?.visualization) {
            console.log('[event:complete] 处理visualization字段')
            this.handleResult(data.visualization)
          }

          // 【关键修复】处理多专家系统的最终结果
          if (data?.expert_results) {
            console.log('[event:complete] 调用 _processExpertResultsForVisualization')
            this._processExpertResultsForVisualization(data.expert_results)
            // 【重要】同时存储完整的专家结果供前端使用
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:complete] lastExpertResults已设置')
          }

          // 【新增】直接处理complete事件中的visuals字段（后端多专家系统返回的聚合visuals）
          if (data?.visuals && Array.isArray(data.visuals)) {
            console.log('[event:complete] 直接处理visuals字段，数量:', data.visuals.length)
            console.log('[event:complete] visuals详情:', data.visuals.map(v => ({ id: v.id, type: v.type })))
            for (const viz of data.visuals) {
              console.log('[event:complete] 添加visual:', viz.id, viz.type)
              this.recordVisualization({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
              // 【关键修复】同步更新 groupedVisualizations
              const targetGroup = this._classifyVizForComplete(viz)
              if (!targetState.groupedVisualizations[targetGroup]) {
                targetState.groupedVisualizations[targetGroup] = []
              }
              targetState.groupedVisualizations[targetGroup].push({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
              console.log(`[event:complete] 已添加到 ${targetGroup} 组，count=${targetState.groupedVisualizations[targetGroup].length}`)
            }
            targetState.hasResults = true
            console.log('[event:complete] 更新后的 groupedVisualizations:', JSON.stringify({
              weather: targetState.groupedVisualizations.weather?.length,
              component: targetState.groupedVisualizations.component?.length
            }))
          } else {
            console.log('[event:complete] 无visuals字段或为空')
          }

          // ✅ 处理sources字段（知识问答工作流返回的检索文档）
          if (data?.sources && Array.isArray(data.sources) && data.sources.length > 0) {
            console.log('[event:complete] 保存sources到最后消息，count:', data.sources.length)
            // 保存到当前消息的sources字段，供VisualizationPanel使用
            if (targetState.messages.length > 0) {
              const lastMsg = targetState.messages[targetState.messages.length - 1]
              // 确保data对象存在
              if (!lastMsg.data) {
                lastMsg.data = {}
              }
              // 保存到data.sources（优先）和msg.sources（兼容）
              lastMsg.data.sources = data.sources
              lastMsg.sources = data.sources
              targetState.messages = [...targetState.messages]
              console.log('[event:complete] sources已保存到lastMsg.data.sources和lastMsg.sources')
            }
          } else {
            console.log('[event:complete] 没有sources字段或为空')
          }

          // 流式最终答案结束，重置状态
          targetState.streamingAnswerMessageId = null
          break
        }

        case 'pipeline_completed': {
          // ✅ ExpertRouterV3 旧架构多专家并行完成事件
          console.log('[event:pipeline_completed] ========== 收到 ExpertRouterV3 完成事件 ==========')
          console.log('[event:pipeline_completed] 数据:', JSON.stringify(data, null, 2))

          // 【修复】使用targetState而不是currentState，确保状态更新到正确的模式
          targetState.isAnalyzing = false
          targetState.isComplete = true
          targetState.finalAnswer = data?.final_answer || ''
          targetState.hasResults = true

          // 记录最终答案
          targetState.finalAnswers.push({
            run: targetState.sessionRound,
            content: data?.final_answer || '溯源分析完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          addMessage('final', data?.final_answer || '溯源分析完成', {
            session_id: data?.session_id,
            timestamp: new Date().toISOString(),
            conclusions: data?.conclusions || null,
            recommendations: data?.recommendations || null,
            confidence: data?.confidence || null,
            data_ids: data?.data_ids || null,
            visuals: data?.visuals || null
          })

          // 处理可视化数据
          if (data?.visuals && Array.isArray(data.visuals)) {
            console.log('[event:pipeline_completed] 处理visuals字段，数量:', data.visuals.length)
            for (const viz of data.visuals) {
              this.recordVisualization({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
              // 同步更新 groupedVisualizations
              const targetGroup = this._classifyVizForComplete(viz)
              if (!targetState.groupedVisualizations[targetGroup]) {
                targetState.groupedVisualizations[targetGroup] = []
              }
              targetState.groupedVisualizations[targetGroup].push({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
            }
          }

          targetState.streamingAnswerMessageId = null
          break
        }

        case 'pipeline_failed': {
          // ✅ ExpertRouterV3 旧架构多专家并行失败事件
          console.log('[event:pipeline_failed] ========== 收到 ExpertRouterV3 失败事件 ==========')
          console.log('[event:pipeline_failed] 数据:', JSON.stringify(data, null, 2))

          targetState.isAnalyzing = false
          targetState.error = data?.error || '溯源分析失败'
          addMessage('error', `溯源分析失败: ${targetState.error}`, data)
          targetState.streamingAnswerMessageId = null
          break
        }

        case 'incomplete': {
          // 未完成（达到最大迭代）
          targetState.isAnalyzing = false
          targetState.isComplete = true
          targetState.iterations = data?.iterations || targetState.iterations
          // ✅ 优先使用response字段，兼容answer字段
          targetState.finalAnswer = data?.response || data?.answer || '分析未完成'

          // 记录最终答案（原有工作流逻辑）
          targetState.finalAnswers.push({
            run: targetState.sessionRound,
            content: data?.response || data?.answer || '分析未完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          if (targetState.streamingAnswerMessageId) {
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.data = {
                ...(msg.data || {}),
                iterations: data?.iterations,
                reason: data?.reason,
                timestamp: data?.timestamp,
                expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
              }
            }
          } else if (data?.answer) {
            addMessage('final', data.answer, {
              iterations: data?.iterations,
              reason: data?.reason,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
            })
          }

          // 处理多专家系统的最终结果（即使未完成也可能有部分结果）
          if (data?.expert_results) {
            console.log('[incomplete] 处理多专家系统最终结果:', data.expert_results)
            this._processExpertResultsForVisualization(data.expert_results)
            // 【重要】同时存储完整的专家结果供前端使用
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
          }

          // 流式最终答案结束，重置状态
          targetState.streamingAnswerMessageId = null
          break
        }

        case 'error': {
          // 迭代错误
          addMessage('error', `错误: ${data?.error || '未知错误'}`, data)
          break
        }

        case 'fatal_error': {
          // 致命错误
          targetState.isAnalyzing = false
          targetState.error = data?.error || '致命错误'
          addMessage('error', `致命错误: ${targetState.error}`, data)
          targetState.streamingAnswerMessageId = null
          break
        }

        case 'result': {
          // 处理结果事件（原有工作流逻辑）
          this.handleResult(data)
          break
        }

        case 'pipeline_started': {
          // 流水线开始事件
          addMessage('start', `开始多专家分析: ${data?.query || ''}`)
          break
        }

        case 'query_parsed': {
          // 查询解析完成事件
          addMessage('tool_result', `查询解析完成 - 地点: ${data?.location || '未知'} | 分析类型: ${data?.analysis_type || '未知'}`, {
            query_parsed: data
          })
          break
        }

        case 'experts_selected': {
          // 专家选择完成事件
          const experts = data?.selected_experts || []
          addMessage('tool_result', `已选择 ${experts.length} 个专家: ${experts.map(e => this.getExpertLabel(e)).join('、')}`, {
            selected_experts: experts
          })
          break
        }

        case 'expert_group_started': {
          // 专家组开始事件
          addMessage('tool_use', `启动专家组: ${data?.group?.map(e => this.getExpertLabel(e)).join('、')}`, {
            group: data?.group
          })
          break
        }

        case 'expert_started': {
          // 单个专家开始事件
          const expertName = this.getExpertLabel(data?.expert_type)
          addMessage('tool_use', `执行【${expertName}】专家任务 (工具数: ${data?.tool_count || 0})`, {
            expert_type: data?.expert_type,
            task_id: data?.task_id
          })
          break
        }

        case 'expert_completed': {
          // 专家完成事件
          const completedExpertName = this.getExpertLabel(data?.expert_type)
          addMessage('tool_result', `【${completedExpertName}】专家完成 - 状态: ${data?.status} | 数据ID: ${(data?.data_ids || []).length}个`, {
            expert_type: data?.expert_type,
            status: data?.status,
            data_ids: data?.data_ids
          })
          break
        }

        case 'expert_group_completed': {
          // 专家组完成事件
          addMessage('tool_result', `专家组执行完成: ${Object.entries(data?.results || {}).map(([k, v]) => `${this.getExpertLabel(k)}(${v})`).join('、')}`, {
            group_results: data?.results
          })
          break
        }

        case 'expert_result': {
          // 多专家系统结果事件
          console.log('[event:expert_result] ========== 收到expert_result事件 ==========')
          console.log('[event:expert_result] 完整数据:', JSON.stringify(data, null, 2))

          // 【关键修改】在主对话框中显示专家结果
          if (data && data.expert_results) {
            console.log('[event:expert_result] expert_results keys:', Object.keys(data.expert_results))

            const expertResultsText = Object.keys(data.expert_results)
              .map(expertType => {
                const expertData = data.expert_results[expertType]
                const status = expertData.status || 'unknown'
                const toolCount = expertData.tool_results?.length || 0
                const summary = expertData.analysis?.summary || '无摘要'
                const expertName = this.getExpertLabel(expertType)

                return `【${expertName}】状态: ${status} | 执行工具: ${toolCount}个\n摘要: ${summary.substring(0, 150)}...`
              })
              .join('\n\n')

            // 添加到主对话框显示
            addMessage('tool_result', `多专家系统阶段性结果:\n\n${expertResultsText}`, {
              expert_results: data.expert_results,
              is_expert_result: true
            })

            // 【关键修复】从专家结果中提取visuals并传递给可视化面板
            console.log('[event:expert_result] 调用 _processExpertResultsForVisualization')
            this._processExpertResultsForVisualization(data.expert_results)

            // 【重要】确保lastExpertResults具有正确的结构
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:expert_result] lastExpertResults已设置')
          } else {
            // 如果没有expert_results字段，直接存储data
            console.log('[event:expert_result] 无expert_results，直接存储data')
            targetState.lastExpertResults = data
          }
          break
        }

        case 'pipeline_error': {
          // 流水线错误事件
          addMessage('error', `多专家系统错误: ${data?.error || '未知错误'}`, data)
          break
        }

        case 'expert_error': {
          // 专家错误事件
          const errorExpertName = this.getExpertLabel(data?.expert_type)
          addMessage('error', `【${errorExpertName}】专家执行失败: ${data?.error || '未知错误'}`, data)
          break
        }


        case 'final_answer': {
          // ✅ 直接来自工作流的最终答案（无需Agent再次总结）
          console.log('[event:final_answer] 收到直接final_answer事件:', data)

          // 提取最终答案内容
          const finalContent = data?.content || ''
          const sources = data?.sources || []

          // 构建消息数据对象
          const msgData = {
            session_id: data?.session_id,
            timestamp: data?.timestamp,
            direct_from_workflow: data?.direct_from_workflow,
            sources: sources  // 保存sources供知识溯源面板使用（旧格式兼容）
          }

          // 添加final消息并设置streamingAnswerMessageId，避免complete事件重复添加
          const msgId = this.addMessage('final', finalContent, msgData, null, { streaming: false })
          this.currentState.streamingAnswerMessageId = msgId  // ✅ 设置标志，避免complete事件重复添加

          // 如果有sources，额外保存到message.data.sources（VisualizationPanel优先检查这里）
          if (sources && sources.length > 0) {
            const msg = this.currentState.messages.find(m => m.id === msgId)
            if (msg) {
              // 确保data对象存在
              if (!msg.data) {
                msg.data = {}
              }
              // 保存sources到data.sources
              msg.data.sources = sources
              console.log('[event:final_answer] sources已保存到msg.data.sources，count:', sources.length)
            }
          }

          // 更新finalAnswer
          this.currentState.finalAnswer = finalContent
          break
        }


        case 'message_start': {
          // 原生 Anthropic 事件：消息开始（可扩展为 token 监控）
          console.log('[event:message_start] Anthropic 消息开始', data?.usage)
          break
        }

        case 'message_delta': {
          // 原生 Anthropic 事件：消息增量（含 stop_reason 和 usage）
          console.log('[event:message_delta] Anthropic 消息增量', {
            stop_reason: data?.stop_reason,
            usage: data?.usage
          })
          break
        }

        case 'message_stop': {
          // 原生 Anthropic 事件：消息结束
          console.log('[event:message_stop] Anthropic 消息结束')
          break
        }

        default:
          console.warn('Unknown event type:', type)
      }

      // 更新迭代次数
      if (type === 'thought' || type === 'tool_use' || type === 'tool_result') {
        this.currentState.iterations += 0.5 // 每个循环算作0.5，因为thought+action+observation是一个完整循环
      }
    },

    // 记录可视化历史，并同步当前展示
    recordVisualization(visualization) {
      if (!visualization) return

      const record = {
        ...visualization,
        id: visualization.id || `viz_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
        timestamp: visualization.timestamp || new Date().toISOString()
      }

      this.currentState.currentVisualization = record
      this.currentState.visualizationHistory.push(record)
    },

    // 处理结果（UDF v2.0格式 + v3.0图表格式）
    handleResult(resultData) {
      if (!resultData) return

      console.log('[handleResult] 处理结果:', resultData)

      // 【UDF v2.0】处理visuals字段
      if (resultData.visuals && Array.isArray(resultData.visuals)) {
        console.log('[handleResult] 检测到UDF v2.0 visuals格式:', resultData.visuals)

        // 将每个visual提取并添加到历史记录
        // 兼容两种格式：VisualBlock格式 和 直接格式（EKMA专业图表等）
        resultData.visuals.forEach((visualBlock, index) => {
          let visualization
          if (visualBlock.payload) {
            // VisualBlock格式: {payload: {...}, meta: {...}}
            visualization = {
              ...visualBlock.payload,
              meta: {
                ...visualBlock.meta,
                schema_version: 'v2.0'
              },
              id: visualBlock.id || visualBlock.payload?.id || `viz_${Date.now()}_${index}_${Math.random().toString(36).substr(2, 5)}`,
              timestamp: new Date().toISOString()
            }
          } else {
            // 直接格式: {id, type, data, meta, ...} (如EKMA专业图表)
            visualization = {
              ...visualBlock,
              meta: {
                ...visualBlock.meta,
                schema_version: 'v2.0'
              },
              id: visualBlock.id || `viz_${Date.now()}_${index}_${Math.random().toString(36).substr(2, 5)}`,
              timestamp: new Date().toISOString()
            }
          }

          // 添加到历史记录
          this.recordVisualization(visualization)
          console.log('[handleResult] 添加visual到历史记录:', visualization)
        })

        console.log('[handleResult] UDF v2.0 visuals处理完成，已添加', resultData.visuals.length, '个图表到历史记录')
        this.currentState.hasResults = true
        return
      }

      // 处理v3.0格式或其他格式
      if (resultData.type === 'map' || resultData.mapConfig) {
        const mapData = resultData.mapConfig || resultData
        this.currentState.results.map = mapData

        const mapVisualization = {
          ...mapData,
          type: mapData.type || 'map',
          title: mapData.title || '地图可视化',
          data: mapData.data || mapData.config || mapData
        }

        this.recordVisualization(mapVisualization)
        console.log('[handleResult] 设置地图可视化')
      } else if (['chart', 'pie', 'bar', 'line', 'timeseries', 'radar', 'wind_rose', 'profile'].includes(resultData.type) || resultData.chartConfig) {
        // 处理v3.0图表格式：支持所有图表类型
        const chartData = resultData.chartConfig || resultData
        this.currentState.results.charts.push(chartData)

        const chartVisualization = {
          ...chartData,
          id: chartData.id || chartData.chartId || `chart_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          type: chartData.type || 'chart',
          title: chartData.title || '',
          data: chartData.data,
          meta: chartData.meta || {}
        }

        this.recordVisualization(chartVisualization)
        console.log('[handleResult] 设置图表可视化 (v3.0):', chartVisualization)
      } else if (resultData.type === 'table' || resultData.tableConfig) {
        const tableData = resultData.tableConfig || resultData
        this.currentState.results.tables.push(tableData)

        const tableVisualization = {
          type: 'table',
          title: tableData.title || '表格',
          data: tableData
        }

        this.recordVisualization(tableVisualization)
        console.log('[handleResult] 设置表格可视化')
      } else if (resultData.type === 'image' || resultData.image) {
        const imageVisualization = {
          type: 'image',
          title: resultData.title || '图片',
          data: resultData.data || resultData.image
        }

        this.recordVisualization(imageVisualization)
        console.log('[handleResult] 设置图片可视化')
      } else if (resultData.type === 'text' || resultData.text) {
        const text = resultData.text || resultData.content || ''
        this.currentState.results.text = this.currentState.results.text ? `${this.currentState.results.text}\n${text}` : text

        const textVisualization = {
          type: 'text',
          title: resultData.title || '文本',
          content: text
        }

        this.recordVisualization(textVisualization)
        console.log('[handleResult] 设置文本可视化')
      } else {
        this.recordVisualization(resultData)
        console.log('[handleResult] 设置通用可视化')
      }

      this.currentState.hasResults = true
    },

    // ✅ 向后兼容别名：analyze -> startAnalysis
    async analyze(query, options = {}) {
      return await this.startAnalysis(query, options)
    },

    // 开始分析
    async startAnalysis(query, options = {}) {
      const {
        assistantMode = null,
        useFullChemistry = false,  // RACM2完整化学机理分析选项
        gridResolution = 21,  // 网格分辨率选项
        agentMode = this.agentMode,  // ✅ 双模式架构：assistant | expert
        knowledgeBaseIds = null,  // ✅ 知识库ID列表
        attachments = null  // ✅ 附件列表
      } = options

      if (!query.trim() && (!attachments || attachments.length === 0)) {
        return
      }

      // 【修复】确定使用的模式：优先从 sessionId 提取，否则使用 currentMode
      let actualMode = agentMode
      if (this.currentState.sessionId) {
        const sessionMode = this.extractModeFromSessionId(this.currentState.sessionId)
        if (sessionMode) {
          actualMode = sessionMode
          console.log(`[startAnalysis] sessionId=${this.currentState.sessionId}, 提取模式=${sessionMode}, currentMode=${this.currentMode}`)
        }
      }

      // 首次分析或继续分析
      if (!this.currentState.sessionId) {
        this.createSessionId()
        this.currentState.sessionRound = 1
        this.currentState.finalAnswers = []
      } else {
        this.continueSession()
      }

      // 重置状态
      this.addMessage('user', query, null, attachments)
      this.currentState.currentMessage = ''
      this.currentState.isAnalyzing = true
      this.currentState.isComplete = false
      this.currentState.error = null
      this.currentState.iterations = 0

      // 如果是中断状态，传递给后端，然后重置标志
      const isInterruption = this.currentState.isInterruption
      if (isInterruption) {
        console.log('[ReAct] 检测到用户中断，将传递给后端')
        this.currentState.isInterruption = false  // 重置标志
      }

      // 重置Reflexion状态
      this.currentState.showReflexion = false
      this.currentState.reflexionCount = 0

      // 清空本轮结果
      this.currentState.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }

      try {
        // ✅ 特殊处理：tracing 模式使用旧架构 ExpertRouterV3
        if (actualMode === 'tracing') {
          console.log('[startAnalysis] 使用 ExpertRouterV3 旧架构（多专家并行）')
          await agentAPI.analyzeV3(query, {
            sessionId: this.currentState.sessionId,
            precision: 'standard',  // fast/standard/full
            enableCheckpoint: false,
            onEvent: (event) => {
              this.handleEvent(event)
            }
          })
        } else {
          // 调用新架构 ReAct Agent
          await agentAPI.analyze(query, {
            sessionId: this.currentState.sessionId,
            userIdentifier: this.userIdentifier,  // ✅ 传递用户标识（跨会话持久化）
            enhanceWithHistory: true,
            maxIterations: this.maxIterations,
            assistantMode: assistantMode,  // 传递助手模式
            useFullChemistry: useFullChemistry,  // RACM2完整化学机理分析选项
            gridResolution: gridResolution,  // 网格分辨率选项
            isInterruption: isInterruption,  // ✅ 传递中断标志
            agentMode: actualMode,  // ✅ 使用从 sessionId 提取的模式
            knowledgeBaseIds: knowledgeBaseIds,  // ✅ 传递知识库ID列表
            attachments: attachments,  // ✅ 传递附件列表
            onEvent: (event) => {
              this.handleEvent(event)
            }
          })
        }
      } catch (error) {
        // 检查是否为用户主动取消
        if (error.name === 'AbortError' || error.message === 'The user aborted a request.') {
          console.log('分析已取消')
          // 取消不是错误，不需要设置error状态
          // isAnalyzing已在pauseAnalysis中设置为false
        } else {
          console.error('Analysis failed:', error)
          this.currentState.isAnalyzing = false
          this.currentState.error = error.message
          this.addMessage('error', `分析失败: ${error.message}`)
        }
      }
    },

    // 继续分析（新问题）
    async continueAnalysis(query, options = {}) {
      if (this.currentState.isAnalyzing) {
        const confirmStop = confirm('当前正在分析中，是否停止并开始新分析？')
        if (!confirmStop) {
          return
        }
        agentAPI.cancel()
        this.currentState.isAnalyzing = false
      }

      // 使用 startAnalysis，它会处理会话延续
      await this.startAnalysis(query, options)
    },

    // 停止分析
    stopAnalysis() {
      agentAPI.cancel()
      this.currentState.isAnalyzing = false
      // 不添加系统消息
    },

    // 暂停分析（与stopAnalysis相同）
    pauseAnalysis() {
      agentAPI.cancel()
      this.currentState.isAnalyzing = false
      this.currentState.isComplete = false
      this.currentState.error = null
      this.currentState.isInterruption = true  // 标记为中断状态
      // 不添加系统消息
    },

    // 重新分析
    async restart() {
      this.reset()
    },

    // 【新增】在complete事件中直接处理visuals时的分类函数
    _classifyVizForComplete(viz) {
      const meta = viz.meta || {}
      const title = (viz.title || '').toLowerCase()
      const toolName = (meta.tool_name || '').toLowerCase()

      // 气象相关的关键词
      const weatherKeywords = ['轨迹', 'trajectory', '气象', 'weather', 'meteorology', '风向', 'wind', '上风向', 'upwind', 'hysplit', '后向轨迹', '反向轨迹', '高度剖面', 'profile']

      // 1. 优先使用有效的 expert_source
      if (meta.expert_source && ['weather', 'component'].includes(meta.expert_source)) {
        return meta.expert_source
      }

      // 2. 检查标题和工具名是否包含气象关键词
      for (const keyword of weatherKeywords) {
        if (title.includes(keyword.toLowerCase()) || toolName.includes(keyword.toLowerCase())) {
          return 'weather'
        }
      }

      // 3. 检查图表类型 - image类型如果是轨迹相关也归为weather
      if (viz.type === 'map' || viz.type === 'wind_rose' || viz.type === 'profile' ||
          viz.type === 'weather_timeseries' || viz.type === 'pressure_pbl_timeseries') {
        return 'weather'
      }

      // 4. 如果是image类型，根据工具名判断
      if (viz.type === 'image') {
        if (toolName.includes('trajectory') || toolName.includes('meteorological')) {
          return 'weather'
        }
      }

      // 5. 默认归类为 component
      return 'component'
    },

    // 【新增方法】从专家结果中提取visuals并传递给可视化面板
    _processExpertResultsForVisualization(expertResults) {
      if (!expertResults) {
        console.warn('[expert_result] 专家结果为空，跳过处理')
        return
      }

      // 防重复检查
      const expertResultsHash = JSON.stringify(expertResults)
      if (this._lastProcessedExpertResultsHash === expertResultsHash) {
        console.log('[processExpertResults] 跳过重复处理')
        return
      }
      this._lastProcessedExpertResultsHash = expertResultsHash

      console.log('[processExpertResults] 开始处理专家结果')
      console.log('[processExpertResults] expertResults keys:', Object.keys(expertResults))

      // 重置分组
      const groups = { weather: [], component: [] }

      // Schema类型映射表
      const weatherSchemas = ['weather', 'meteorology', 'meteorology_unified', 'trajectory', 'upwind_analysis', 'trajectory_simulation', 'hysplit']
      const componentSchemas = ['air_quality_unified', 'guangdong_stations', 'vocs_unified', 'vocs', 'pmf_result', 'obm_ofp_result', 'particulate_analysis']

      // 气象相关的关键词（用于标题和工具名匹配）
      const weatherKeywords = ['轨迹', 'trajectory', '气象', 'weather', 'meteorology', '风向', 'wind', '上风向', 'upwind', 'hysplit', '后向轨迹', '反向轨迹', '高度剖面', 'profile']

      // 分类函数
      const classifyViz = (viz) => {
        const meta = viz.meta || {}
        const title = (viz.title || '').toLowerCase()
        const toolName = (meta.tool_name || '').toLowerCase()

        // 1. 优先使用有效的 expert_source
        if (meta.expert_source && ['weather', 'component'].includes(meta.expert_source)) {
          return meta.expert_source
        }

        // 2. 检查标题和工具名是否包含气象关键词
        for (const keyword of weatherKeywords) {
          if (title.includes(keyword.toLowerCase()) || toolName.includes(keyword.toLowerCase())) {
            return 'weather'
          }
        }

        // 3. 从 source_data_ids 解析
        if (meta.source_data_ids?.length > 0) {
          const schemaType = meta.source_data_ids[0].split(':')[0]
          if (weatherSchemas.includes(schemaType)) return 'weather'
          if (componentSchemas.includes(schemaType)) return 'component'
        }

        // 4. 检查图表类型 - 【新增】image类型如果是轨迹相关也归为weather
        if (viz.type === 'map' || viz.type === 'wind_rose' || viz.type === 'profile' ||
            viz.type === 'weather_timeseries' || viz.type === 'pressure_pbl_timeseries') {
          return 'weather'
        }

        // 【新增】如果是image类型，根据工具名判断
        if (viz.type === 'image') {
          if (toolName.includes('trajectory') || toolName.includes('meteorological')) {
            return 'weather'
          }
        }

        // 5. 默认归类为 component
        return 'component'
      }

      // 一次性遍历并分类
      for (const [expertType, expertData] of Object.entries(expertResults)) {
        console.log(`[processExpertResults] 处理专家: ${expertType}`)
        const toolResults = expertData.tool_results || []
        console.log(`[processExpertResults] 工具数量: ${toolResults.length}`)

        for (const toolResult of toolResults) {
          const result = toolResult.result || toolResult.data || toolResult
          if (!result) {
            console.log(`[processExpertResults] 工具 ${toolResult.tool} result为空，跳过`)
            continue
          }

          console.log(`[processExpertResults] 工具 ${toolResult.tool}: result type=${result.type}, visuals=`, result.visuals)

          // 提取 visuals
          // 兼容两种格式：VisualBlock格式 和 直接格式（EKMA专业图表等）
          const visuals = result.visuals || []
          console.log(`[processExpertResults] 提取到 ${visuals.length} 个visuals`)

          for (const visualBlock of visuals) {
            console.log(`[processExpertResults] 处理visual: id=${visualBlock.id || visualBlock.payload?.id}, type=${visualBlock.type || visualBlock.payload?.type}`)

            let viz
            if (visualBlock.payload) {
              // VisualBlock格式: {payload: {...}, meta: {...}}
              viz = {
                ...visualBlock.payload,
                meta: {
                  ...visualBlock.meta,
                  tool_name: toolResult.tool || toolResult.tool_name,
                  schema_version: 'v2.0'
                }
              }
            } else {
              // 直接格式: {id, type, data, meta, ...} (如EKMA专业图表)
              viz = {
                ...visualBlock,
                meta: {
                  ...visualBlock.meta,
                  tool_name: toolResult.tool || toolResult.tool_name,
                  schema_version: 'v2.0'
                }
              }
            }

            // 分类并存储
            const targetGroup = classifyViz(viz)
            console.log(`[processExpertResults] 分类结果: ${viz.id} -> ${targetGroup}`)
            viz.meta.expert_source = targetGroup  // 确保 meta 中有正确的分类
            groups[targetGroup].push(viz)
            this.currentState.visualizationHistory.push(viz)
          }

          // 兼容直接的可视化格式（包括EKMA专业图表的image类型）
          if (result.type && ['map', 'chart', 'pie', 'bar', 'line', 'timeseries', 'radar', 'profile', 'wind_rose', 'weather_timeseries', 'pressure_pbl_timeseries', 'heatmap', 'image'].includes(result.type)) {
            console.log(`[processExpertResults] 处理直接格式: type=${result.type}`)
            const viz = {
              ...result,
              meta: {
                ...result.meta,
                tool_name: toolResult.tool || toolResult.tool_name,
                schema_version: 'v2.0'
              }
            }
            const targetGroup = classifyViz(viz)
            console.log(`[processExpertResults] 直接格式分类: ${result.type} -> ${targetGroup}`)
            viz.meta.expert_source = targetGroup
            groups[targetGroup].push(viz)
            this.currentState.visualizationHistory.push(viz)
          }
        }
      }

      // 更新分组状态
      this.currentState.groupedVisualizations = groups
      this.currentState.expertResults = expertResults
      this.currentState.lastExpertResults = { expert_results: expertResults }

      console.log(`[processExpertResults] 完成: weather=${groups.weather.length}, component=${groups.component.length}`)
      console.log(`[processExpertResults] weather图表详情:`, groups.weather.map(v => ({ id: v.id, type: v.type, title: v.title })))
    }
  }
})
