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
import { buildResourceGroups, targetTab } from '@/services/resourceGroups.js'
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'

export function usePanelManagement(store = null) {
  const resourceStore = useSessionResourceStore()
  // ========== 面板状态 ==========
  const managementPanel = ref(null) // 当前显示的管理面板
  const rightPanelVisible = ref(false) // 右侧面板是否可见
  const rightPanelDismissed = ref(false) // 用户手动关闭后不被资源刷新强制重开
  const leftSidebarCollapsed = ref(false) // 左侧边栏是否折叠
  const knowledgePanelVisible = ref(false) // 知识溯源面板是否可见
  const activeRightTab = ref('files') // 右侧面板活动标签页
  const activeTabUserSelected = ref(false)

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

  // ========== 面板切换方法 ==========

  /**
   * 切换可视化面板显示/隐藏
   */
  const toggleVizPanel = async () => {
    const newState = !rightPanelVisible.value
    if (!newState && !await confirmResourcePreviewLeave()) return false
    rightPanelVisible.value = newState
    rightPanelDismissed.value = !newState

    // 联动左侧面板
    if (newState) {
      leftSidebarCollapsed.value = true
    } else {
      leftSidebarCollapsed.value = false
    }
    return true
  }

  const changeRightTab = async tab => {
    if (!tab || tab === activeRightTab.value) return true
    if (!await confirmResourcePreviewLeave()) return false
    activeRightTab.value = tab
    activeTabUserSelected.value = true
    return true
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
    knowledgePanelVisible.value = false
    rightPanelVisible.value = false
    rightPanelDismissed.value = false
    leftSidebarCollapsed.value = false
    managementPanel.value = null
    activeRightTab.value = 'files'
    activeTabUserSelected.value = false
    const sessionId = resourceStore.activeSessionId
    if (sessionId && resourceStore.activeSessionState?.selectionOrigin === 'explicit') {
      resourceStore.selectResource(sessionId, null)
      resourceStore.selectGroup(sessionId, null)
    }
  }

  const openMessageAttachmentPreview = async ({ sessionId, resourceId } = {}) => {
    const token = ++attachmentPreviewToken
    try {
      if (!await confirmResourcePreviewLeave()) return null
      const resource = await resolveMessageAttachmentResource(
        resourceStore,
        sessionId,
        { resource_id: resourceId }
      )
      if (token !== attachmentPreviewToken || resourceStore.activeSessionId !== sessionId) return null
      resourceStore.selectGroup(sessionId, resource.group_id)
      resourceStore.selectResource(sessionId, resource.resource_id, 'explicit')
      const state = resourceStore.sessionState(sessionId)
      const group = buildResourceGroups(state?.resources || [])
        .find(item => item.group_id === resource.group_id)
      activeRightTab.value = group ? targetTab(group) : 'files'
      activeTabUserSelected.value = true
      rightPanelVisible.value = true
      rightPanelDismissed.value = false
      leftSidebarCollapsed.value = true
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
    let previousArtifactCount = 0
    let previousSessionId = null
    watch(
      () => [resourceStore.activeSessionId, resourceStore.activeSessionState?.resourceVersion],
      () => {
        const sessionId = resourceStore.activeSessionId
        const summary = resourceSummary.value
        if (sessionId !== previousSessionId) {
          previousSessionId = sessionId
          previousArtifactCount = 0
          activeTabUserSelected.value = false
          rightPanelDismissed.value = false
        }
        if (sessionId && summary.hasArtifacts && !explicitAttachment.value) {
          const restored = chooseRestoredResource(resourceStore, sessionId)
          if (restored && !activeTabUserSelected.value) {
            activeRightTab.value = restored.targetTab
          }
          if (previousArtifactCount === 0 && summary.counts.files > 0 && !rightPanelDismissed.value) {
            rightPanelVisible.value = true
            leftSidebarCollapsed.value = true
            vizWidth.value = collapsedVizWidth
          }
        }
        previousArtifactCount = summary.counts.files
      },
      { immediate: true }
    )

    // 监听知识溯源变化
    watch(hasKnowledgeSources, (newValue) => {
      knowledgePanelVisible.value = newValue
      // 当检测到知识溯源时，自动切换到知识标签页
      if (newValue && !activeTabUserSelected.value) {
        activeRightTab.value = 'knowledge'
        if (!rightPanelDismissed.value) rightPanelVisible.value = true
      }
    }, { immediate: true })

    // 监听右侧面板显示状态
    watch([hasVizContent, knowledgePanelVisible], ([artifacts, knowledge]) => {
      const shouldShow = artifacts || knowledge
      if (shouldShow && rightPanelVisible.value) {
        // 右侧面板展开时，自动折叠左侧面板
        leftSidebarCollapsed.value = true
      } else if (!shouldShow) {
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
    rightPanelDismissed,
    leftSidebarCollapsed,
    knowledgePanelVisible,
    activeRightTab,
    vizWidth,
    isDragging,
    layoutRef,

    // 计算属性
    vizPanelStyle,
    hasVizContent,
    hasKnowledgeSources,
    resourceSummary,

    // 方法
    toggleVizPanel,
    changeRightTab,
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
