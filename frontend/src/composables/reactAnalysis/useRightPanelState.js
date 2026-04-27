/**
 * 右侧面板状态管理 Composable
 * 管理右侧面板的显示、隐藏、标签页切换等
 */
import { ref, computed, watch } from 'vue'

export function useRightPanelState(store = null) {
  // ========== 状态 ==========
  const vizPanelVisible = ref(false)
  const officePanelVisible = ref(false)
  const rightPanelVisible = ref(false)
  const activeRightTab = ref('visualization') // 'visualization' | 'document'

  // ========== 计算属性 ==========

  /**
   * 是否有可视化内容
   */
  const hasVizContent = computed(() => {
    if (!store) return false

    const hasCharts = store.currentState.visualizationHistory?.length > 0 ||
      store.currentState.currentVisualization?.visuals?.length > 0

    return hasCharts
  })

  /**
   * 是否有Office文档
   */
  const hasOfficeDocuments = computed(() => {
    if (!store || !store.messages) return false

    return store.messages.some(msg => {
      if (msg?.type === 'tool_result' && msg?.data?.result) {
        const metadata = msg.data.result.metadata || {}
        const generator = metadata.generator

        const isOfficeTool = [
          'word_edit', 'find_replace_word', 'accept_word_changes',
          'unpack_office', 'pack_office', 'recalc_excel', 'add_ppt_slide',
          'read_file'
        ].includes(generator)

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
   * 是否显示标签页切换按钮
   */
  const showTabs = computed(() => {
    return vizPanelVisible.value && officePanelVisible.value
  })

  // ========== 方法 ==========

  /**
   * 切换到可视化标签页
   */
  const switchToVisualization = () => {
    activeRightTab.value = 'visualization'
  }

  /**
   * 切换到文档标签页
   */
  const switchToDocument = () => {
    activeRightTab.value = 'document'
  }

  /**
   * 重置面板状态
   */
  const resetPanelState = () => {
    vizPanelVisible.value = false
    officePanelVisible.value = false
    rightPanelVisible.value = false
    activeRightTab.value = 'visualization'
  }

  /**
   * 显示面板（根据内容类型）
   * @param {string} type - 'visualization' | 'document' | 'auto'
   */
  const showPanel = (type = 'auto') => {
    rightPanelVisible.value = true

    if (type === 'visualization') {
      vizPanelVisible.value = true
      activeRightTab.value = 'visualization'
    } else if (type === 'document') {
      officePanelVisible.value = true
      activeRightTab.value = 'document'
    } else if (type === 'auto') {
      // 自动检测
      if (hasOfficeDocuments.value) {
        officePanelVisible.value = true
        activeRightTab.value = 'document'
      } else if (hasVizContent.value) {
        vizPanelVisible.value = true
        activeRightTab.value = 'visualization'
      }
    }
  }

  /**
   * 隐藏面板
   */
  const hidePanel = () => {
    rightPanelVisible.value = false
  }

  // ========== 监听器 ==========

  /**
   * 设置自动监听器
   */
  const setupWatchers = () => {
    // 监听可视化内容变化
    watch(hasVizContent, (newValue) => {
      if (newValue && !vizPanelVisible.value) {
        vizPanelVisible.value = true
      }
    }, { immediate: true })

    // 监听Office文档变化
    watch(hasOfficeDocuments, (newValue) => {
      officePanelVisible.value = newValue
      if (newValue) {
        activeRightTab.value = 'document'
      }
    }, { immediate: true })

    // 监听面板可见性变化
    watch([vizPanelVisible, officePanelVisible], ([viz, office]) => {
      const shouldShow = viz || office
      rightPanelVisible.value = shouldShow
    }, { immediate: true })

    // 监听office_document事件
    if (store) {
      watch(() => store.lastOfficeDocument, (doc) => {
        if (doc?.pdf_preview) {
          officePanelVisible.value = true
          activeRightTab.value = 'document'
        }
      })
    }
  }

  return {
    // 状态
    vizPanelVisible,
    officePanelVisible,
    rightPanelVisible,
    activeRightTab,

    // 计算属性
    hasVizContent,
    hasOfficeDocuments,
    showTabs,

    // 方法
    switchToVisualization,
    switchToDocument,
    resetPanelState,
    showPanel,
    hidePanel,
    setupWatchers
  }
}
