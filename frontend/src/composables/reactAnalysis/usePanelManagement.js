/**
 * 面板管理 Composable
 * 管理右侧面板、左侧边栏、管理面板的状态和交互
 */
import { ref, computed, watch } from 'vue'
import { PANEL_SIZES } from '@/utils/constants'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { summarizeRightPanelResources } from '@/components/resources/rightPanelResources.js'
import { chooseRestoredResource } from '@/services/sessionResourceLifecycle.js'
import { resolveMessageAttachmentResource } from '@/services/messageAttachmentPreview.js'

export function usePanelManagement(store = null) {
  const resourceStore = useSessionResourceStore()
  // ========== 面板状态 ==========
  const managementPanel = ref(null) // 当前显示的管理面板
  const rightPanelVisible = ref(false) // 右侧面板是否可见
  const leftSidebarCollapsed = ref(false) // 左侧边栏是否折叠
  const vizPanelVisible = ref(false) // 可视化面板是否可见
  const officePanelVisible = ref(false) // Office文档面板是否可见
  const knowledgePanelVisible = ref(false) // 知识溯源面板是否可见
  const boardPanelVisible = ref(false) // Draw.io画板面板是否可见
  const activeRightTab = ref('files') // 右侧面板活动标签页

  // ========== 宽度调整相关 ==========
  const defaultVizWidth = PANEL_SIZES.DEFAULT_VIZ_WIDTH
  const collapsedVizWidth = PANEL_SIZES.COLLAPSED_VIZ_WIDTH
  const minVizWidth = PANEL_SIZES.MIN_VIZ_WIDTH
  const maxVizWidth = PANEL_SIZES.MAX_VIZ_WIDTH

  const vizWidth = ref(defaultVizWidth)
  const isDragging = ref(false)
  const layoutRef = ref(null)
  const resourceSummary = computed(() => summarizeRightPanelResources(
    resourceStore.activeSessionState?.resources || []
  ))
  const explicitAttachment = computed(() => {
    const sessionId = resourceStore.activeSessionId
    const state = resourceStore.activeSessionState
    if (!sessionId || state?.selectionOrigin !== 'explicit') return null
    const selected = resourceStore.selectedResource(sessionId)
    return selected?.role === 'attachment' ? selected : null
  })
  let attachmentPreviewToken = 0

  // ========== 计算属性 ==========

  /**
   * 面板宽度样式
   */
  const vizPanelStyle = computed(() => ({
    width: `${vizWidth.value}%`,
    flex: `0 0 ${vizWidth.value}%`,
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    maxHeight: '100vh',
    overflowX: 'hidden'
  }))

  /**
   * 检测是否有可视化内容
   */
  const hasVizContent = computed(() => {
    if (!store) return false

    // 检查知识问答检索来源，复用可视化面板展示知识溯源
    const messages = store.messages || store.currentState?.messages || []
    const hasSources = messages.some(msg =>
      (Array.isArray(msg?.data?.sources) && msg.data.sources.length > 0) ||
      (Array.isArray(msg?.sources) && msg.sources.length > 0)
    )

    return resourceSummary.value.hasArtifacts || !!explicitAttachment.value || hasSources
  })

  /**
   * 检测是否有Office文档操作
   */
  const hasOfficeDocuments = computed(() => {
    return resourceSummary.value.counts.document > 0
  })

  /**
   * 检测是否有知识溯源信息
   */
  const hasKnowledgeSources = computed(() => {
    if (!store || !store.messages) return false

    return store.messages.some(msg => {
      if (msg?.data?.sources && Array.isArray(msg.data.sources) && msg.data.sources.length > 0) {
        return true
      }
      if (msg?.sources && Array.isArray(msg.sources) && msg.sources.length > 0) {
        return true
      }
      return false
    })
  })

  /**
   * 检测是否有Draw.io画板
   */
  const hasBoardContent = computed(() => {
    return resourceSummary.value.counts.board > 0
  })

  // ========== 面板切换方法 ==========

  /**
   * 切换可视化面板显示/隐藏
   */
  const toggleVizPanel = () => {
    const newState = !rightPanelVisible.value
    rightPanelVisible.value = newState

    // 联动左侧面板
    if (newState) {
      leftSidebarCollapsed.value = true
      vizWidth.value = collapsedVizWidth
    } else {
      leftSidebarCollapsed.value = false
    }
  }

  /**
   * 显示管理面板
   * @param {string} panelType - 面板类型
   */
  const showManagementPanel = (panelType) => {
    if (managementPanel.value === panelType) {
      managementPanel.value = null
    } else {
      managementPanel.value = panelType
    }
  }

  /**
   * 隐藏所有管理面板
   */
  const hideManagementPanel = () => {
    managementPanel.value = null
  }

  /**
   * 重置面板状态（用于新会话）
   */
  const resetPanelState = () => {
    vizPanelVisible.value = false
    officePanelVisible.value = false
    knowledgePanelVisible.value = false
    boardPanelVisible.value = false
    rightPanelVisible.value = false
    leftSidebarCollapsed.value = false
    managementPanel.value = null
    activeRightTab.value = 'files'
    const sessionId = resourceStore.activeSessionId
    if (sessionId && resourceStore.activeSessionState?.selectionOrigin === 'explicit') {
      resourceStore.selectResource(sessionId, null)
      resourceStore.selectGroup(sessionId, null)
    }
  }

  const openMessageAttachmentPreview = async ({ sessionId, resourceId } = {}) => {
    const token = ++attachmentPreviewToken
    try {
      const resource = await resolveMessageAttachmentResource(
        resourceStore,
        sessionId,
        { resource_id: resourceId }
      )
      if (token !== attachmentPreviewToken || resourceStore.activeSessionId !== sessionId) return null
      resourceStore.selectGroup(sessionId, resource.group_id)
      resourceStore.selectResource(sessionId, resource.resource_id, 'explicit')
      activeRightTab.value = 'document'
      officePanelVisible.value = true
      rightPanelVisible.value = true
      leftSidebarCollapsed.value = true
      vizWidth.value = collapsedVizWidth
      return resource
    } catch (error) {
      if (token === attachmentPreviewToken) {
        console.error('[message-attachment-preview] failed', error)
        window.alert(error?.message || '附件资源不可用')
      }
      return null
    }
  }

  // ========== 宽度调整方法 ==========

  /**
   * 限制宽度在允许范围内
   */
  const clampWidth = (value) => {
    return Math.min(maxVizWidth, Math.max(minVizWidth, value))
  }

  /**
   * 根据鼠标位置更新宽度
   */
  const updateWidthFromCursor = (clientX) => {
    if (!layoutRef.value || typeof layoutRef.value.getBoundingClientRect !== 'function') {
      return
    }
    try {
      const bounds = layoutRef.value.getBoundingClientRect()
      const vizPixels = bounds.right - clientX
      const percent = (vizPixels / bounds.width) * 100
      vizWidth.value = clampWidth(percent)
    } catch (error) {
      console.warn('[usePanelManagement] updateWidthFromCursor error:', error)
    }
  }

  /**
   * 开始拖动
   */
  const startDragging = (event) => {
    isDragging.value = true
    updateWidthFromCursor(event.clientX)
  }

  /**
   * 停止拖动
   */
  const stopDragging = () => {
    isDragging.value = false
  }

  /**
   * 重置宽度到默认值
   */
  const resetWidth = () => {
    vizWidth.value = leftSidebarCollapsed.value ? collapsedVizWidth : defaultVizWidth
  }

  /**
   * 设置 layoutRef（由父组件调用）
   */
  const setLayoutRef = (el) => {
    layoutRef.value = el
  }

  /**
   * 处理鼠标移动（拖动时）
   */
  const handleMouseMove = (event) => {
    if (!isDragging.value) {
      return
    }

    updateWidthFromCursor(event.clientX)
  }

  /**
   * 处理鼠标释放（停止拖动）
   */
  const handleMouseUp = () => {
    if (isDragging.value) {
      stopDragging()
    }
  }

  // ========== 监听器 ==========

  /**
   * 监听内容变化，自动显示/隐藏面板
   */
  const setupWatchers = () => {
    watch(
      () => [resourceStore.activeSessionId, resourceStore.activeSessionState?.resourceVersion],
      () => {
        const sessionId = resourceStore.activeSessionId
        const summary = resourceSummary.value
        vizPanelVisible.value = summary.counts.visualization > 0
        officePanelVisible.value = summary.counts.document > 0 || !!explicitAttachment.value
        boardPanelVisible.value = summary.counts.board > 0
        if (sessionId && summary.hasArtifacts && !explicitAttachment.value) {
          const restored = chooseRestoredResource(resourceStore, sessionId)
          if (restored) activeRightTab.value = restored.targetTab
        }
      },
      { immediate: true }
    )

    // 监听知识溯源变化
    watch(hasKnowledgeSources, (newValue) => {
      knowledgePanelVisible.value = newValue
      // 当检测到知识溯源时，自动切换到知识标签页
      if (newValue) {
        activeRightTab.value = 'knowledge'
      }
    }, { immediate: true })

    // 监听右侧面板显示状态
    watch([hasVizContent, knowledgePanelVisible], ([artifacts, knowledge]) => {
      const shouldShow = artifacts || knowledge
      if (shouldShow) {
        rightPanelVisible.value = true
        // 右侧面板展开时，自动折叠左侧面板
        leftSidebarCollapsed.value = true
        vizWidth.value = collapsedVizWidth
      } else {
        rightPanelVisible.value = false
        // 右侧面板收起时，恢复左侧面板
        leftSidebarCollapsed.value = false
      }
    }, { immediate: true })

  }

  // ========== 生命周期 ==========

  /**
   * 添加全局鼠标移动监听器
   */
  const setupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
  }

  /**
   * 移除全局监听器
   */
  const cleanupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }

  return {
    // 状态
    managementPanel,
    rightPanelVisible,
    leftSidebarCollapsed,
    vizPanelVisible,
    officePanelVisible,
    knowledgePanelVisible,
    boardPanelVisible,
    activeRightTab,
    vizWidth,
    isDragging,
    layoutRef,

    // 计算属性
    vizPanelStyle,
    hasVizContent,
    hasOfficeDocuments,
    hasKnowledgeSources,
    hasBoardContent,
    resourceSummary,

    // 方法
    toggleVizPanel,
    showManagementPanel,
    hideManagementPanel,
    resetPanelState,
    startDragging,
    stopDragging,
    resetWidth,
    openMessageAttachmentPreview,
    setLayoutRef,
    setupWatchers,
    setupGlobalListeners,
    cleanupGlobalListeners
  }
}
