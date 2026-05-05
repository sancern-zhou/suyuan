/**
 * 面板管理 Composable
 * 管理右侧面板、左侧边栏、管理面板的状态和交互
 */
import { ref, computed, watch } from 'vue'
import { PANEL_SIZES } from '@/utils/constants'

export function usePanelManagement(store = null) {
  // ========== 面板状态 ==========
  const managementPanel = ref(null) // 当前显示的管理面板
  const rightPanelVisible = ref(false) // 右侧面板是否可见
  const leftSidebarCollapsed = ref(false) // 左侧边栏是否折叠
  const vizPanelVisible = ref(false) // 可视化面板是否可见
  const officePanelVisible = ref(false) // Office文档面板是否可见
  const knowledgePanelVisible = ref(false) // 知识溯源面板是否可见
  const activeRightTab = ref('visualization') // 右侧面板活动标签页

  // ========== 宽度调整相关 ==========
  const defaultVizWidth = PANEL_SIZES.DEFAULT_VIZ_WIDTH
  const collapsedVizWidth = PANEL_SIZES.COLLAPSED_VIZ_WIDTH
  const minVizWidth = PANEL_SIZES.MIN_VIZ_WIDTH
  const maxVizWidth = PANEL_SIZES.MAX_VIZ_WIDTH

  const vizWidth = ref(defaultVizWidth)
  const isDragging = ref(false)
  const layoutRef = ref(null)

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

    // 检查是否有可视化图表
    const hasCharts = store.currentState.visualizationHistory?.length > 0 ||
      store.currentState.currentVisualization?.visuals?.length > 0

    // 检查知识问答检索来源，复用可视化面板展示知识溯源
    const messages = store.messages || store.currentState?.messages || []
    const hasSources = messages.some(msg =>
      (Array.isArray(msg?.data?.sources) && msg.data.sources.length > 0) ||
      (Array.isArray(msg?.sources) && msg.sources.length > 0)
    )

    // 检查是否有Office文档
    const hasOffice = officePanelVisible.value

    return hasCharts || hasSources || hasOffice
  })

  /**
   * 检测是否有Office文档操作
   */
  const hasOfficeDocuments = computed(() => {
    if (!store || !store.messages) return false

    if (store.lastOfficeDocument?.pdf_preview || store.lastOfficeDocument?.markdown_preview || store.lastOfficeDocument?.html_preview) {
      return true
    }

    return store.messages.some(msg => {
      if (msg?.type === 'tool_result' && msg?.data?.result) {
        const metadata = msg.data.result.metadata || {}
        const generator = metadata.generator

        const isOfficeTool = [
          'word_edit', 'find_replace_word', 'accept_word_changes',
          'unpack_office', 'pack_office', 'recalc_excel', 'add_ppt_slide',
          'read_pptx', 'create_pptx', 'analyze_pptx_template',
          'create_pptx_from_template', 'edit_pptx', 'validate_pptx',
          'read_file'
        ].includes(generator)

        // 对于 read_file，需要检查是否有 markdown_preview 或 pdf_preview
        if (generator === 'read_file') {
          const result = msg.data.result
          return !!(result.data?.pdf_preview || result.data?.markdown_preview)
        }

        return isOfficeTool
      }
      return false
    })
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
    rightPanelVisible.value = false
    leftSidebarCollapsed.value = false
    managementPanel.value = null
    activeRightTab.value = 'visualization'
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
    // 监听可视化内容变化
    watch(hasVizContent, (newValue) => {
      if (newValue && !vizPanelVisible.value) {
        vizPanelVisible.value = true
        if (!officePanelVisible.value) {
          activeRightTab.value = 'visualization'
        }
      }
    }, { immediate: true })

    // 监听Office文档变化
    watch(hasOfficeDocuments, (newValue) => {
      officePanelVisible.value = newValue
      // 当检测到Office文档时，自动切换到文档标签页
      if (newValue) {
        activeRightTab.value = 'document'
      }
    }, { immediate: true })

    // 监听知识溯源变化
    watch(hasKnowledgeSources, (newValue) => {
      knowledgePanelVisible.value = newValue
      // 当检测到知识溯源时，自动切换到知识标签页
      if (newValue) {
        activeRightTab.value = 'knowledge'
      }
    }, { immediate: true })

    // 监听图表历史变化，当有图表时且当前在document标签，切换回visualization标签
    if (store) {
      watch(() => store.currentState.visualizationHistory, (newHistory) => {
        const hasCharts = newHistory?.length > 0
        if (hasCharts && activeRightTab.value === 'document' && !officePanelVisible.value && !knowledgePanelVisible.value) {
          activeRightTab.value = 'visualization'
        }
      }, { immediate: true })
    }

    // 监听右侧面板显示状态
    watch([vizPanelVisible, officePanelVisible, knowledgePanelVisible], ([viz, office, knowledge]) => {
      const shouldShow = viz || office || knowledge
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

    // 监听office_document事件
    if (store) {
      watch(() => store.lastOfficeDocument, (doc) => {
        // 支持 PDF/Markdown/Notebook 预览，统一显示在"文档预览"标签页
        if (doc?.pdf_preview || doc?.markdown_preview || doc?.html_preview) {
          officePanelVisible.value = true
          activeRightTab.value = 'document'
        }
      }, { immediate: true })
    }
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
    activeRightTab,
    vizWidth,
    isDragging,
    layoutRef,

    // 计算属性
    vizPanelStyle,
    hasVizContent,
    hasOfficeDocuments,
    hasKnowledgeSources,

    // 方法
    toggleVizPanel,
    showManagementPanel,
    hideManagementPanel,
    resetPanelState,
    startDragging,
    stopDragging,
    resetWidth,
    setLayoutRef,
    setupWatchers,
    setupGlobalListeners,
    cleanupGlobalListeners
  }
}
