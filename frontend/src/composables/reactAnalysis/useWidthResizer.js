/**
 * 宽度调整 Composable
 * 处理面板宽度的拖动调整功能
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { PANEL_SIZES, STORAGE_KEYS } from '@/utils/constants'

export function useWidthResizer() {
  // ========== 状态 ==========
  const vizWidth = ref(PANEL_SIZES.DEFAULT_VIZ_WIDTH)
  const isDragging = ref(false)
  const layoutRef = ref(null)

  // ========== 常量 ==========
  const defaultVizWidth = PANEL_SIZES.DEFAULT_VIZ_WIDTH
  const collapsedVizWidth = PANEL_SIZES.COLLAPSED_VIZ_WIDTH
  const minVizWidth = PANEL_SIZES.MIN_VIZ_WIDTH
  const maxVizWidth = PANEL_SIZES.MAX_VIZ_WIDTH

  // ========== 计算属性 ==========

  /**
   * 面板宽度样式
   */
  const panelStyle = computed(() => ({
    width: `${vizWidth.value}%`,
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    maxHeight: '100vh',
    overflowX: 'hidden'
  }))

  /**
   * 拖动时的样式
   */
  const dragHandleClass = computed(() => ({
    dragging: isDragging.value
  }))

  // ========== 方法 ==========

  /**
   * 限制宽度在允许范围内
   * @param {number} value - 原始宽度值
   * @returns {number} 限制后的宽度值
   */
  const clampWidth = (value) => {
    return Math.min(maxVizWidth, Math.max(minVizWidth, value))
  }

  /**
   * 根据鼠标位置计算并更新宽度
   * @param {number} clientX - 鼠标X坐标
   */
  const updateWidthFromCursor = (clientX) => {
    if (!layoutRef.value) return

    const bounds = layoutRef.value.getBoundingClientRect()
    const vizPixels = bounds.right - clientX
    const percent = (vizPixels / bounds.width) * 100

    vizWidth.value = clampWidth(percent)
  }

  /**
   * 开始拖动
   * @param {MouseEvent} event - 鼠标事件
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
    saveWidthToStorage()
  }

  /**
   * 重置宽度到默认值
   * @param {boolean} isCollapsed - 左侧面板是否折叠
   */
  const resetWidth = (isCollapsed = false) => {
    vizWidth.value = isCollapsed ? collapsedVizWidth : defaultVizWidth
    saveWidthToStorage()
  }

  /**
   * 设置宽度为指定值
   * @param {number} width - 宽度百分比
   */
  const setWidth = (width) => {
    vizWidth.value = clampWidth(width)
    saveWidthToStorage()
  }

  /**
   * 保存宽度到本地存储
   */
  const saveWidthToStorage = () => {
    try {
      localStorage.setItem(STORAGE_KEYS.VIZ_WIDTH, vizWidth.value.toString())
    } catch (error) {
      console.warn('保存宽度到本地存储失败:', error)
    }
  }

  /**
   * 从本地存储加载宽度
   */
  const loadWidthFromStorage = () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.VIZ_WIDTH)
      if (saved) {
        const width = parseFloat(saved)
        if (!isNaN(width) && width >= minVizWidth && width <= maxVizWidth) {
          vizWidth.value = width
          return true
        }
      }
    } catch (error) {
      console.warn('从本地存储加载宽度失败:', error)
    }
    return false
  }

  /**
   * 处理鼠标移动事件
   * @param {MouseEvent} event - 鼠标事件
   */
  const handleMouseMove = (event) => {
    if (!isDragging.value) return

    // 如果鼠标按钮已经释放，自动停止拖动
    if (event.buttons === 0) {
      stopDragging()
      return
    }

    updateWidthFromCursor(event.clientX)
  }

  // ========== 生命周期 ==========

  /**
   * 添加全局事件监听器
   */
  const setupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', stopDragging)
    }
  }

  /**
   * 移除全局事件监听器
   */
  const cleanupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', stopDragging)
    }
  }

  // ========== 初始化 ==========

  // 组件挂载时加载保存的宽度
  onMounted(() => {
    loadWidthFromStorage()
    setupGlobalListeners()
  })

  // 组件卸载时清理监听器
  onBeforeUnmount(() => {
    cleanupGlobalListeners()
  })

  return {
    // 状态
    vizWidth,
    isDragging,
    layoutRef,

    // 计算属性
    panelStyle,
    dragHandleClass,

    // 方法
    startDragging,
    stopDragging,
    resetWidth,
    setWidth,
    clampWidth,
    loadWidthFromStorage,
    saveWidthToStorage
  }
}
