/**
 * 拖拽上传 Composable
 * 处理文件拖拽上传功能
 */
import { ref } from 'vue'
import { isValidFileType, isValidFileSize } from '@/utils/validators'
import { ALLOWED_FILE_TYPES, FILE_SIZE_LIMITS } from '@/utils/constants'

export function useDragAndDrop(options = {}) {
  const {
    // 允许的文件类型
    allowedTypes = Object.values(ALLOWED_FILE_TYPES).flat(),
    // 最大文件大小
    maxSize = FILE_SIZE_LIMITS.LARGE,
    // 文件处理函数
    onFilesDrop = null,
    // 拖拽区域元素引用
    dropZoneRef = null
  } = options

  // ========== 状态 ==========
  const isDragging = ref(false)
  const dragOverCount = ref(0) // 用于跟踪进入拖拽区域的次数

  // ========== 事件处理器 ==========

  /**
   * 处理拖拽进入事件
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragEnter = (event) => {
    event.preventDefault()
    event.stopPropagation()

    // 只处理文件拖拽
    if (event.dataTransfer.types.includes('Files')) {
      dragOverCount.value++
      isDragging.value = true
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  /**
   * 处理拖拽离开事件
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragLeave = (event) => {
    event.preventDefault()
    event.stopPropagation()

    dragOverCount.value--

    // 只有当所有拖拽元素都离开时才清除状态
    if (dragOverCount.value <= 0) {
      dragOverCount.value = 0
      isDragging.value = false
    }
  }

  /**
   * 处理拖拽悬停事件
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragOver = (event) => {
    event.preventDefault()
    event.stopPropagation()

    if (event.dataTransfer.types.includes('Files')) {
      isDragging.value = true
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  /**
   * 处理文件放置事件
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDrop = async (event) => {
    event.preventDefault()
    event.stopPropagation()

    // 重置拖拽状态
    dragOverCount.value = 0
    isDragging.value = false

    const files = event.dataTransfer.files
    if (!files || files.length === 0) return

    // 验证文件
    const validation = validateFiles(files)

    if (!validation.valid) {
      if (typeof options.onError === 'function') {
        options.onError(validation.errors)
      }
      return
    }

    // 调用文件处理函数
    if (typeof onFilesDrop === 'function') {
      await onFilesDrop(files)
    }
  }

  /**
   * 验证文件列表
   * @param {FileList} files - 文件列表
   * @returns {object} 验证结果
   */
  const validateFiles = (files) => {
    const errors = []

    for (let i = 0; i < files.length; i++) {
      const file = files[i]

      // 检查文件类型
      if (!isValidFileType(file, allowedTypes)) {
        errors.push(`文件 "${file.name}" 的类型不被支持`)
      }

      // 检查文件大小
      if (!isValidFileSize(file, maxSize)) {
        errors.push(`文件 "${file.name}" 超过大小限制`)
      }
    }

    return {
      valid: errors.length === 0,
      errors
    }
  }

  /**
   * 处理文件选择（通过input元素）
   * @param {Event} event - 文件选择事件
   */
  const handleFileSelect = async (event) => {
    const files = event.target.files
    if (!files || files.length === 0) return

    // 验证文件
    const validation = validateFiles(files)

    if (!validation.valid) {
      if (typeof options.onError === 'function') {
        options.onError(validation.errors)
      }
      return
    }

    // 调用文件处理函数
    if (typeof onFilesDrop === 'function') {
      await onFilesDrop(files)
    }

    // 清空input值，允许重复选择同一文件
    event.target.value = ''
  }

  /**
   * 触发文件选择对话框
   * @param {HTMLElement} inputRef - 文件input元素的引用
   */
  const triggerFileSelect = (inputRef) => {
    if (inputRef && inputRef.click) {
      inputRef.click()
    }
  }

  // ========== 拖拽样式 ==========

  /**
   * 拖拽区域的类名
   */
  const dragZoneClass = computed(() => ({
    'drag-over': isDragging.value,
    'drag-enter': isDragging.value
  }))

  return {
    // 状态
    isDragging,
    dragOverCount,
    dragZoneClass,

    // 事件处理器
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleFileSelect,
    triggerFileSelect,

    // 工具方法
    validateFiles
  }
}

/**
 * 创建简化的拖拽处理器（用于聊天区域）
 * @param {function} onFilesDrop - 文件处理函数
 * @returns {object} 拖拽处理器
 */
export function createChatDragHandler(onFilesDrop) {
  const isDragging = ref(false)

  const handleDragOver = (e) => {
    if (e.dataTransfer.types.includes('Files')) {
      isDragging.value = true
      e.dataTransfer.dropEffect = 'copy'
    }
  }

  const handleDragLeave = (e) => {
    // 检查鼠标是否真的离开了对话区
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX
    const y = e.clientY
    if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
      isDragging.value = false
    }
  }

  const handleDrop = async (e) => {
    isDragging.value = false

    const files = e.dataTransfer.files
    if (!files || files.length === 0) return

    if (typeof onFilesDrop === 'function') {
      await onFilesDrop(files)
    }
  }

  return {
    isDragging,
    handleDragOver,
    handleDragLeave,
    handleDrop
  }
}
