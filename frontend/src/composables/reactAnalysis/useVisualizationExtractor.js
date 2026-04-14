/**
 * 可视化内容提取 Composable
 * 从消息中提取、去重和合并可视化内容
 */
import { computed } from 'vue'

export function useVisualizationExtractor(store) {
  // ========== 计算属性 ==========

  /**
   * 所有可视化内容（去重）
   */
  const allVisualizations = computed(() => {
    const vizList = []

    // 从可视化历史中获取
    if (store.currentState.visualizationHistory?.length) {
      vizList.push(...store.currentState.visualizationHistory)
    }

    // 从当前可视化中获取
    if (store.currentState.currentVisualization) {
      if (store.currentState.currentVisualization.visuals) {
        // 兼容两种格式：VisualBlock格式 和 直接格式
        const visuals = store.currentState.currentVisualization.visuals.map(v => {
          if (v.payload) {
            return { ...v.payload, meta: v.meta }
          } else {
            return v
          }
        })
        vizList.push(...visuals)
      } else {
        vizList.push(store.currentState.currentVisualization)
      }
    }

    // 从分组可视化中获取（多专家模式）
    if (store.currentState.groupedVisualizations) {
      const { weather = [], component = [] } = store.currentState.groupedVisualizations
      vizList.push(...weather, ...component)
    }

    // 去重
    return deduplicateVisuals(vizList)
  })

  /**
   * 是否有可视化内容
   */
  const hasVisualizations = computed(() => {
    return allVisualizations.value && allVisualizations.value.length > 0
  })

  /**
   * 可视化数量
   */
  const visualizationCount = computed(() => {
    return allVisualizations.value?.length || 0
  })

  /**
   * 按类型分组的可视化
   */
  const visualizationsByType = computed(() => {
    const grouped = {}

    for (const viz of allVisualizations.value) {
      const type = viz.type || 'unknown'
      if (!grouped[type]) {
        grouped[type] = []
      }
      grouped[type].push(viz)
    }

    return grouped
  })

  // ========== 方法 ==========

  /**
   * 去重可视化列表
   * @param {Array} visuals - 可视化列表
   * @returns {Array} 去重后的列表
   */
  const deduplicateVisuals = (visuals) => {
    const seen = new Set()

    return visuals.filter(viz => {
      if (!viz) return false

      // 生成唯一键
      const key = generateVisualKey(viz)

      // 检查是否已存在
      if (seen.has(key)) return false

      seen.add(key)
      return true
    })
  }

  /**
   * 生成可视化的唯一键
   * @param {object} viz - 可视化对象
   * @returns {string} 唯一键
   */
  const generateVisualKey = (viz) => {
    // 优先使用ID
    if (viz.id) return viz.id

    // 否则使用类型+数据生成键
    const type = viz.type || 'unknown'
    const dataStr = JSON.stringify(viz.data || '')

    return `${type}_${dataStr}`
  }

  /**
   * 从消息中提取可视化
   * @param {Array} messages - 消息列表
   * @returns {Array} 可视化列表
   */
  const extractFromMessages = (messages) => {
    const visuals = []

    for (const msg of messages) {
      if (msg.type === 'observation' && msg.data?.observation?.visuals) {
        visuals.push(...msg.data.observation.visuals)
      }
    }

    return deduplicateVisuals(visuals)
  }

  /**
   * 合并可视化列表
   * @param {Array} vizLists - 多个可视化列表
   * @returns {Array} 合并后的列表
   */
  const mergeVisualizations = (...vizLists) => {
    const allVisuals = vizLists.flat()
    return deduplicateVisuals(allVisuals)
  }

  /**
   * 按类型筛选可视化
   * @param {string} type - 可视化类型
   * @returns {Array} 筛选后的列表
   */
  const filterByType = (type) => {
    return allVisualizations.value.filter(viz => viz.type === type)
  }

  /**
   * 按ID查找可视化
   * @param {string} id - 可视化ID
   * @returns {object|null} 可视化对象
   */
  const findById = (id) => {
    return allVisualizations.value.find(viz => viz.id === id) || null
  }

  /**
   * 获取最新的可视化
   * @param {number} count - 数量
   * @returns {Array} 最新的可视化列表
   */
  const getLatest = (count = 1) => {
    return allVisualizations.value.slice(-count)
  }

  /**
   * 清空可视化历史
   */
  const clearHistory = () => {
    store.setVisualizationHistory([])
  }

  return {
    // 计算属性
    allVisualizations,
    hasVisualizations,
    visualizationCount,
    visualizationsByType,

    // 方法
    deduplicateVisuals,
    extractFromMessages,
    mergeVisualizations,
    filterByType,
    findById,
    getLatest,
    clearHistory
  }
}
