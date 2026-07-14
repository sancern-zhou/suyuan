import { authFetch } from '@/auth/http.js'
/**
 * 会话管理 Composable
 * 处理会话的创建、恢复、清理等操作
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  listSessions,
  restoreSession,
  getSessionMessages,
  getSessionVisualizations,
  getSessionOfficeDocuments,
  getSessionDrawioBoard,
  deleteSession as deleteSessionRequest,
  markSessionCase,
  unmarkSessionCase
} from '@/api/session'

export function useSessionManagement(store) {
  // ========== 状态 ==========
  const showSessionManager = ref(false)
  const sessionHistoryLoading = ref(false)
  const persistedSessionHistoryData = ref([])
  const sessionHistoryStats = ref(null)
  let autoRefreshTimer = null
  let refreshInFlight = null

  const runAfterFirstPaint = (callback) => {
    if (typeof window === 'undefined') {
      setTimeout(callback, 0)
      return
    }
    const schedule = window.requestIdleCallback || ((cb) => setTimeout(cb, 0))
    schedule(callback)
  }

  const loadLazyArtifacts = async (sessionId, options = {}) => {
    const {
      loadVisualizations = true,
      loadOfficeDocuments = true,
      loadDrawioBoard = true
    } = options

    if (!sessionId) return

    console.log('[会话恢复] 开始自动加载延迟资源:', {
      sessionId,
      loadVisualizations,
      loadOfficeDocuments,
      loadDrawioBoard
    })

    const tasks = []

    if (loadVisualizations && !store.currentState.lazyArtifacts?.visualizationsLoaded) {
      store.setLazyArtifacts({ loadingVisualizations: true })
      tasks.push(
        getSessionVisualizations(sessionId)
          .then(response => {
            if (store.currentState.sessionId !== sessionId) return
            const visualizations = response?.visualizations || []
            console.log('[会话恢复] 图表延迟加载完成:', visualizations.length)
            store.setVisualizationHistory(visualizations)
            store.setLazyArtifacts({
              hasVisualizations: visualizations.length > 0,
              visualizationCount: visualizations.length,
              visualizationsLoaded: true,
              loadingVisualizations: false
            })
          })
          .catch(error => {
            console.error('[会话恢复] 延迟加载图表失败:', error)
            if (store.currentState.sessionId === sessionId) {
              store.setLazyArtifacts({ loadingVisualizations: false })
            }
          })
      )
    }

    if (loadOfficeDocuments && !store.currentState.lazyArtifacts?.officeDocumentsLoaded) {
      store.setLazyArtifacts({ loadingOfficeDocuments: true })
      tasks.push(
        getSessionOfficeDocuments(sessionId)
          .then(response => {
            if (store.currentState.sessionId !== sessionId) return
            const officeDocs = response?.office_documents || []
            console.log('[会话恢复] 文档延迟加载完成:', officeDocs.length)
            if (officeDocs.length > 0) {
              if (typeof store.setOfficeDocumentHistory === 'function') {
                store.setOfficeDocumentHistory(officeDocs)
              } else {
                store.setLastOfficeDocument(officeDocs[officeDocs.length - 1])
              }
            }
            store.setLazyArtifacts({
              hasOfficeDocuments: officeDocs.length > 0,
              officeDocumentCount: officeDocs.length,
              officeDocumentsLoaded: true,
              loadingOfficeDocuments: false
            })
          })
          .catch(error => {
            console.error('[会话恢复] 延迟加载文档失败:', error)
            if (store.currentState.sessionId === sessionId) {
              store.setLazyArtifacts({ loadingOfficeDocuments: false })
            }
          })
      )
    }

    const shouldLoadDrawioBoard = loadDrawioBoard &&
      store.currentState.lazyArtifacts?.hasDrawioBoard &&
      !store.currentState.lazyArtifacts?.drawioBoardLoaded

    if (shouldLoadDrawioBoard) {
      store.setLazyArtifacts({ loadingDrawioBoard: true })
      tasks.push(
        getSessionDrawioBoard(sessionId)
          .then(response => {
            if (store.currentState.sessionId !== sessionId) return
            const drawioBoard = response?.drawio_board || null
            console.log('[会话恢复] 画板延迟加载完成:', !!drawioBoard)
            if (drawioBoard && typeof store.restoreDrawioBoardFromSession === 'function') {
              store.restoreDrawioBoardFromSession({ drawio_board: drawioBoard })
            }
            store.setLazyArtifacts({
              hasDrawioBoard: !!drawioBoard,
              drawioBoardLoaded: true,
              loadingDrawioBoard: false
            })
          })
          .catch(error => {
            console.error('[会话恢复] 延迟加载画板失败:', error)
            if (store.currentState.sessionId === sessionId) {
              store.setLazyArtifacts({ loadingDrawioBoard: false })
            }
          })
      )
    }

    await Promise.allSettled(tasks)
  }

  const localSessionHistoryData = computed(() => {
    return Object.values(store.sessionStates || {})
      .filter(session => session.sessionId)
      .map(session => {
        const firstUser = session.messages?.find(m => m.type === 'user')
        const lastMessage = session.messages?.[session.messages.length - 1]
        const hasError = session.messages?.some(m => m.type === 'error') || !!session.error
        return {
          session_id: session.sessionId,
          query: firstUser?.content || '新对话',
          updated_at: lastMessage?.timestamp || new Date().toISOString(),
          created_at: session.createdAt,
          has_error: hasError,
          state: session.isAnalyzing ? 'running' : (hasError ? 'error' : 'completed'),
          status: session.isAnalyzing ? 'running' : (hasError ? 'error' : 'completed'),
          is_running: !!session.isAnalyzing,
          is_local: true,
          message_count: session.messages?.length || 0
        }
      })
  })

  const sessionHistoryData = computed(() => {
    const byId = new Map()
    for (const session of persistedSessionHistoryData.value) {
      byId.set(session.session_id, {
        ...session,
        status: session.status || session.state || (session.has_error ? 'error' : 'completed')
      })
    }
    for (const session of localSessionHistoryData.value) {
      byId.set(session.session_id, {
        ...(byId.get(session.session_id) || {}),
        ...session
      })
    }

    return Array.from(byId.values()).sort((a, b) => {
      if (!!a.is_running !== !!b.is_running) return a.is_running ? -1 : 1
      return new Date(b.updated_at || 0) - new Date(a.updated_at || 0)
    })
  })

  const applySessionCaseState = (sessionId, isCase, metadataOverride = null) => {
    const markedAt = new Date().toISOString()
    persistedSessionHistoryData.value = persistedSessionHistoryData.value.map(session => {
      if (session.session_id !== sessionId) return session

      const metadata = metadataOverride
        ? { ...metadataOverride }
        : {
            ...(session.metadata || {}),
            is_case: isCase,
            ...(isCase ? { case_marked_at: markedAt } : {})
          }

      if (!isCase) {
        delete metadata.case_marked_at
      }

      return {
        ...session,
        metadata
      }
    })
  }

  // ========== 计算属性 ==========

  /**
   * 当前会话ID
   */
  const currentSessionId = computed(() => store.currentState.sessionId)

  /**
   * 当前消息数量
   */
  const currentMessageCount = computed(() => store.currentState.messages?.length || 0)

  /**
   * 是否正在分析
   */
  const isAnalyzing = computed(() => store.currentState.isAnalyzing)

  /**
   * 是否可以输入
   */
  const canInput = computed(() => store.canInput)

  // ========== 会话操作方法 ==========

  /**
   * 发送消息
   * @param {string|object} payload - 消息内容或包含选项的对象
   */
  const handleSend = async (payload) => {
    // 处理新的输入格式：可能是字符串（向后兼容）或对象
    const query = typeof payload === 'string' ? payload : payload.query
    const knowledgeBaseIds = typeof payload === 'object' ? payload.knowledgeBaseIds || [] : []
    const agentMode = typeof payload === 'object' ? payload.agentMode || store.agentMode : store.agentMode
    const attachments = typeof payload === 'object' ? payload.attachments || null : null
    const modelTier = typeof payload === 'object' ? payload.modelTier || 'auto' : 'auto'

    // 构建分析选项
    const options = {
      knowledgeBaseIds,
      agentMode,  // ✅ 传递agentMode参数
      modelTier,
      attachments  // ✅ 传递附件信息
    }

    // 使用store的分析方法
    try {
      await store.analyze(query, options)
    } finally {
      refreshSessionHistory({ silent: true })
    }
  }

  /**
   * 暂停分析
   */
  const handlePause = async () => {
    await store.pauseAnalysis()
  }

  /**
   * 重新开始会话
   */
  const handleRestart = () => {
    store.restart()
  }

  /**
   * 切换分析状态
   */
  const toggleAnalysis = async () => {
    if (isAnalyzing.value) {
      await handlePause()
    } else {
      // 恢复分析（如果支持）
      console.log('恢复分析功能待实现')
    }
  }

  // ========== 会话恢复 ==========

  /**
   * 执行会话恢复的统一逻辑
   * @param {string} sessionId - 会话ID
   * @param {object} options - 恢复选项
   * @returns {object} 恢复结果
   */
  const doRestoreSession = async (sessionId, options = {}) => {
    const {
      messageLimit = 100,
      restoreOfficeDocs = true,
      lazyArtifacts = true
    } = options

    try {
      // 1. 调用恢复API
      const restoreResult = await restoreSession(sessionId, { messageLimit, lazyArtifacts })

      if (!restoreResult) {
        return {
          success: false,
          error: '恢复失败：API返回为空'
        }
      }

      // 后端返回格式：{ message: "...", session: {...} }
      const sessionData = restoreResult.session || restoreResult
      let messages = sessionData.conversation_history || []

      // 详细分析 final 消息（只根据type字段判断）
      const finalMessages = messages.filter(m => {
        const msgType = (m.type || '').toLowerCase()
        return msgType === 'final' || msgType === 'assistant'
      })

      // 辅助函数：安全提取 content 预览（支持字符串和 content blocks 格式）
      const getContentPreview = (content) => {
        if (typeof content === 'string') {
          return content.substring(0, 100)
        }
        if (Array.isArray(content)) {
          // 提取文本类型的 content block（Anthropic 格式）
          const textBlock = content.find(block => block.type === 'text')
          return textBlock?.text?.substring(0, 100) || '[结构化内容]'
        }
        return '[未知格式]'
      }

      // 【修复】final消息按ID去重，只过滤真正重复ID的消息
      const idMap = new Map()
      finalMessages.forEach(m => {
        if (m.id) {
          if (idMap.has(m.id)) {
            // 发现重复ID
            const existing = idMap.get(m.id)
            console.warn('[会话恢复] 发现重复ID的final消息:', {
              id: m.id,
              原消息时间: existing.timestamp || 'N/A',
              重复消息时间: m.timestamp || 'N/A'
            })
          } else {
            idMap.set(m.id, m)
          }
        }
      })

      // 只保留每个ID的第一次出现
      const seenIds = new Set(idMap.keys())
      const beforeCount = messages.length
      messages = messages.filter(m => {
        // 只检查final/assistant消息的ID
        const msgType = (m.type || '').toLowerCase()
        if (msgType === 'final' || msgType === 'assistant') {
          return !m.id || seenIds.has(m.id)
        }
        return true
      })

      if (messages.length !== beforeCount) {
        console.log(`[会话恢复] 按ID去重：${beforeCount} → ${messages.length} (过滤${beforeCount - messages.length}条)`)
      }

      // 2. 提取可视化内容（优先使用 metadata.visualizations）
      let visuals = []

      // lazy 模式下图表由独立接口在首屏消息显示后自动加载
      if (lazyArtifacts) {
        visuals = []
      } else if (sessionData.metadata?.visualizations && Array.isArray(sessionData.metadata.visualizations)) {
        // 优先从 session.metadata.visualizations 获取完整可视化数据
        visuals = sessionData.metadata.visualizations

        // 【修复】补充 tool_result 消息的缺失 data.result.visuals（旧会话兼容）
        let fixedCount = 0
        messages.forEach(msg => {
          if (msg.type === 'tool_result' && msg.data) {
            const hasResultVisuals = msg.data?.result?.visuals && Array.isArray(msg.data.result.visuals)
            const hasResultsVisuals = msg.data?.results && Array.isArray(msg.data.results) &&
                                     msg.data.results.some(r => r.visuals && Array.isArray(r.visuals))

            if (!hasResultVisuals && !hasResultsVisuals) {
              const toolUseId = msg.data?.tool_use_id
              const toolName = msg.data?.tool_name || ''
              const matchingVisuals = visuals.filter(v => {
                const vToolName = v.meta?.generator || v.meta?.tool_name || ''
                const vToolUseId = v.meta?.tool_use_id
                return vToolName === toolName || vToolUseId === toolUseId
              })

              if (matchingVisuals.length > 0) {
                if (!msg.data.result) {
                  msg.data.result = {}
                }
                msg.data.result.visuals = matchingVisuals
                fixedCount++
              }
            }
          }
        })
      } else {
        // 降级方案：从消息中提取
        visuals = extractVisualsFromMessages(messages)
      }

      // 3. 更新store
      store.reset()
      store.setSessionId(sessionId)
      store.setMessages(messages)
      if (typeof store.restoreDrawioBoardFromSession === 'function') {
        store.restoreDrawioBoardFromSession(sessionData)
      }
      store.setLazyArtifacts({
        hasVisualizations: !!sessionData.has_lazy_visualizations,
        visualizationCount: sessionData.visualization_count || 0,
        visualizationsLoaded: !lazyArtifacts,
        loadingVisualizations: false,
        hasOfficeDocuments: !!sessionData.has_lazy_office_documents,
        officeDocumentCount: sessionData.office_document_count || 0,
        officeDocumentsLoaded: !lazyArtifacts,
        loadingOfficeDocuments: false,
        hasDrawioBoard: !!sessionData.has_lazy_drawio_board,
        drawioBoardLoaded: !lazyArtifacts,
        loadingDrawioBoard: false
      })

      // 设置分页信息
      if (sessionData.has_more_messages !== undefined || sessionData.total_message_count !== undefined) {
        store.setPagination({
          hasMoreMessages: sessionData.has_more_messages || false,
          totalMessageCount: sessionData.total_message_count || messages.length,
          oldestSequence: sessionData.oldest_sequence,
          loadingMore: false
        })
      }

      if (!lazyArtifacts) {
        // 无论 visuals 是否为空都要设置，确保清空旧会话的图表数据
        store.setVisualizationHistory(visuals)
      }

      // 4. 恢复Office文档
      if (restoreOfficeDocs && !lazyArtifacts) {
        let officeDocs = sessionData.office_documents || []

        // 如果sessionData中没有，从消息中提取
        if (officeDocs.length === 0) {
          const extractedDocs = extractOfficeDocuments(messages)
          if (extractedDocs.length > 0) {
            officeDocs = extractedDocs
          }
        }

        if (officeDocs.length > 0) {
          if (typeof store.setOfficeDocumentHistory === 'function') {
            store.setOfficeDocumentHistory(officeDocs)
          } else {
            store.setLastOfficeDocument(officeDocs[officeDocs.length - 1])
          }
        }
      }

      if (lazyArtifacts) {
        console.log('[会话恢复] 首屏消息已恢复，准备调度延迟资源自动加载:', sessionId)
        runAfterFirstPaint(() => {
          loadLazyArtifacts(sessionId, {
            loadVisualizations: true,
            loadOfficeDocuments: restoreOfficeDocs,
            loadDrawioBoard: true
          })
        })
      }

      return {
        success: true,
        messageCount: messages.length,
        visualCount: lazyArtifacts ? (sessionData.visualization_count || 0) : visuals.length,
        officeDocCount: lazyArtifacts ? (sessionData.office_document_count || 0) : (restoreOfficeDocs ? (sessionData.office_documents || []).length : 0)
      }

    } catch (error) {
      console.error('[会话恢复] 恢复会话时出错:', error)
      if (store.sessionStates?.[sessionId]) {
        store._activateSession(sessionId)
        return {
          success: true,
          session: store.sessionStates[sessionId],
          local: true,
          degraded: true,
          error: error.message
        }
      }
      return {
        success: false,
        error: error.message
      }
    }
  }

  /**
   * 从消息中提取可视化内容
   * @param {array} messages - 消息列表
   * @returns {array} 可视化列表
   */
  const extractVisualsFromMessages = (messages) => {
    const visuals = []

    for (const msg of messages) {
      if (msg.type === 'tool_result') {
        // ✅ 支持两种格式：
        // 1. 单个工具：data.result.visuals
        // 2. 多个工具：data.results[].visuals
        const result = msg.data?.result
        const results = msg.data?.results

        // 格式1：单个工具 result.visuals
        if (result) {
          // result.visuals 在顶层
          if (Array.isArray(result.visuals) && result.visuals.length > 0) {
            visuals.push(...result.visuals)
          }
          // result.data.visuals
          if (Array.isArray(result.data?.visuals) && result.data.visuals.length > 0) {
            visuals.push(...result.data.visuals)
          }
          // 多工具结果：result.tool_results[].result.visuals
          if (Array.isArray(result.tool_results)) {
            for (const tr of result.tool_results) {
              const rv = tr?.result?.visuals
              if (Array.isArray(rv) && rv.length > 0) {
                visuals.push(...rv)
              }
            }
          }
        }

        // 格式2：多个工具 results[].visuals
        if (Array.isArray(results)) {
          for (const r of results) {
            if (Array.isArray(r.visuals) && r.visuals.length > 0) {
              visuals.push(...r.visuals)
            }
            if (Array.isArray(r.data?.visuals) && r.data.visuals.length > 0) {
              visuals.push(...r.data.visuals)
            }
          }
        }
      }
    }

    // 去重（基于ID）
    const seen = new Set()
    const deduplicated = visuals.filter(v => {
      if (!v.id) return true
      if (seen.has(v.id)) return false
      seen.add(v.id)
      return true
    })

    return deduplicated
  }

  /**
   * 从消息中提取Office文档
   * @param {array} messages - 消息列表
   * @returns {array} Office文档列表
   */
  const extractOfficeDocuments = (messages) => {
    const docs = []

    for (const msg of messages) {
      if (msg.type === 'tool_result') {
        const result = msg.data?.result
        if (!result) continue

        const resultData = result.data
        if (!resultData) continue

        // 提取所有可用预览，避免 report 同时带 markdown/html 时丢失 HTML iframe 预览
        if (resultData.pdf_preview || resultData.markdown_preview || resultData.html_preview || resultData.svg_preview) {
          docs.push({
            pdf_preview: resultData.pdf_preview,
            markdown_preview: resultData.markdown_preview,
            html_preview: resultData.html_preview,
            svg_preview: resultData.svg_preview,
            file_path: resultData.file_path || resultData.path || resultData.pdf_preview?.pdf_path || resultData.svg_preview?.svg_path,
            file_type: resultData.file_type || resultData.html_preview?.file_type || resultData.svg_preview?.file_type,
            related_files: resultData.related_files,
            artifacts: resultData.artifacts,
            refs: resultData.refs,
            assets: resultData.assets,
            generator: resultData.generator || result?.metadata?.generator || 'word_processor',
            summary: result.summary
          })
        }
      }
    }

    return docs
  }

  const activateLocalSessionIfAvailable = (sessionId) => {
    const localSessionState = store.sessionStates?.[sessionId]
    if (!localSessionState) return false

    const hasMessages = Array.isArray(localSessionState.messages) && localSessionState.messages.length > 0
    const hasVisibleState = hasMessages ||
      !!localSessionState.isAnalyzing ||
      !!localSessionState.isComplete ||
      !!localSessionState.finalAnswer

    if (!hasVisibleState) return false

    store._activateSession(sessionId, localSessionState.mode)
    console.log('[会话切换] 已激活本地会话状态，跳过后端恢复:', {
      sessionId,
      messageCount: localSessionState.messages?.length || 0,
      isAnalyzing: !!localSessionState.isAnalyzing
    })
    return true
  }

  /**
   * 处理会话恢复
   * @param {string} sessionId - 会话ID
   */
  const handleSessionRestore = async (sessionId) => {
    if (activateLocalSessionIfAvailable(sessionId)) {
      return true
    }

    const result = await doRestoreSession(sessionId, { messageLimit: 100, restoreOfficeDocs: true })

    if (result.success) {
      return true
    } else {
      console.error('[会话恢复] 恢复会话失败:', result.error)
      return false
    }
  }

  /**
   * 从侧边栏快速加载会话
   * @param {string} sessionId - 会话ID
   */
  const handleLoadSession = async (sessionId) => {
    if (activateLocalSessionIfAvailable(sessionId)) {
      return true
    }

    const result = await doRestoreSession(sessionId, {
      messageLimit: 100,
      restoreOfficeDocs: true
    })

    return result.success
  }

  // ========== 会话历史管理 ==========

  /**
   * 刷新会话历史
   */
  const refreshSessionHistory = async (options = {}) => {
    const { silent = false } = options
    if (refreshInFlight) return refreshInFlight

    if (!silent) sessionHistoryLoading.value = true
    try {
      refreshInFlight = (async () => {
        const data = await listSessions({ limit: 200 })
        persistedSessionHistoryData.value = data.sessions || []
        sessionHistoryStats.value = data.stats || null
      })()
      await refreshInFlight
    } catch (error) {
      console.error('Failed to refresh session history:', error)
    } finally {
      refreshInFlight = null
      if (!silent) sessionHistoryLoading.value = false
    }
  }

  const localSessionSignature = computed(() => {
    return localSessionHistoryData.value
      .map(session => `${session.session_id}:${session.status}:${session.message_count}:${session.updated_at}`)
      .join('|')
  })

  watch(localSessionSignature, () => {
    refreshSessionHistory({ silent: true })
  })

  onMounted(() => {
    refreshSessionHistory({ silent: true })
    autoRefreshTimer = window.setInterval(() => {
      refreshSessionHistory({ silent: true })
    }, 15000)
  })

  onUnmounted(() => {
    if (autoRefreshTimer) {
      window.clearInterval(autoRefreshTimer)
      autoRefreshTimer = null
    }
  })

  /**
   * 清理会话
   */
  const handleSessionCleanup = async () => {
    try {
      const response = await authFetch('/api/sessions/cleanup', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to cleanup sessions')

      const data = await response.json()
      alert(`已清理 ${data.deleted_count} 个过期会话`)
      await refreshSessionHistory()
    } catch (error) {
      console.error('Failed to cleanup sessions:', error)
      alert('清理失败: ' + error.message)
    }
  }

  /**
   * 删除会话
   * @param {string} sessionId - 会话ID
   */
  const deleteSessions = async (sessionIds) => {
    const ids = Array.from(new Set((sessionIds || []).filter(Boolean)))
    if (ids.length === 0) return false

    const message = ids.length === 1
      ? '确定要删除此会话吗？此操作不可恢复。'
      : `确定要删除选中的 ${ids.length} 个会话吗？此操作不可恢复。`
    if (!confirm(message)) return false

    try {
      await Promise.all(ids.map(sessionId => deleteSessionRequest(sessionId)))
      await refreshSessionHistory()
      return true
    } catch (error) {
      console.error('Failed to delete sessions:', error)
      alert('删除失败: ' + error.message)
      return false
    }
  }

  /**
   * 删除单个会话
   * @param {string} sessionId - 会话ID
   */
  const deleteSession = async (sessionId) => {
    return deleteSessions([sessionId])
  }

  const handleToggleSessionCase = async (session) => {
    if (!session?.session_id) return false

    const isCase = session.metadata?.is_case === true
    const previousMetadata = { ...(session.metadata || {}) }
    applySessionCaseState(session.session_id, !isCase)

    try {
      if (isCase) {
        await unmarkSessionCase(session.session_id)
      } else {
        await markSessionCase(session.session_id)
      }
      refreshSessionHistory({ silent: true })
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('session-case-updated'))
      }
      return true
    } catch (error) {
      applySessionCaseState(session.session_id, isCase, previousMetadata)
      console.error('Failed to toggle session case:', error)
      alert('案例标记失败: ' + error.message)
      return false
    }
  }

  // ========== 会话管理器控制 ==========

  /**
   * 打开会话管理器
   */
  const openSessionManager = () => {
    showSessionManager.value = true
    refreshSessionHistory()
  }

  /**
   * 关闭会话管理器
   */
  const closeSessionManager = () => {
    showSessionManager.value = false
  }

  return {
    // 状态
    showSessionManager,
    sessionHistoryLoading,
    sessionHistoryData,
    sessionHistoryStats,

    // 计算属性
    currentSessionId,
    currentMessageCount,
    isAnalyzing,
    canInput,

    // 会话操作
    handleSend,
    handlePause,
    handleRestart,
    toggleAnalysis,

    // 会话恢复
    handleSessionRestore,
    handleLoadSession,
    doRestoreSession,

    // 会话历史
    refreshSessionHistory,
    handleSessionCleanup,
    deleteSession,
    deleteSessions,
    handleToggleSessionCase,

    // 会话管理器
    openSessionManager,
    closeSessionManager
  }
}
