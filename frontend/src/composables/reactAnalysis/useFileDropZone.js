/**
 * 文件拖拽区域 Composable
 * 处理文件拖拽上传的交互逻辑
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { validateFiles } from './useKbFileValidation'

export function useFileDropZone(options = {}) {
  const {
    accept = null, // 接受的文件类型
    maxSize = null, // 最大文件大小
    multiple = true, // 是否允许多文件
    onDrop = null, // 放置回调
    onError = null // 错误回调
  } = options

  // ========== 状态 ==========
  const isDragging = ref(false)
  const dragOverCount = ref(0)
  const dropZoneRef = ref(null)

  // ========== 计算属性 ==========

  /**
   * 拖拽区域样式类
   */
  const dropZoneClass = computed(() => ({
    'drop-zone': true,
    'drag-over': isDragging.value,
    'drag-enter': isDragging.value
  }))

  /**
   * 是否可以放置
   */
  const canDrop = computed(() => {
    return isDragging.value && !dragOverCount.value
  })

  // ========== 方法 ==========

  /**
   * 处理拖拽进入
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragEnter = (event) => {
    event.preventDefault()
    event.stopPropagation()

    // 只处理文件拖拽
    if (event.dataTransfer?.types.includes('Files')) {
      dragOverCount.value++
      isDragging.value = true
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  /**
   * 处理拖拽离开
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
   * 处理拖拽悬停
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragOver = (event) => {
    event.preventDefault()
    event.stopPropagation()

    if (event.dataTransfer?.types.includes('Files')) {
      isDragging.value = true
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  /**
   * 处理文件放置
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDrop = async (event) => {
    event.preventDefault()
    event.stopPropagation()

    // 重置拖拽状态
    dragOverCount.value = 0
    isDragging.value = false

    const files = event.dataTransfer?.files
    if (!files || files.length === 0) return

    // 处理文件
    await processFiles(files)
  }

  /**
   * 处理文件
   * @param {FileList|Array} files - 文件列表
   */
  const processFiles = async (files) => {
    const fileArray = Array.from(files)

    // 验证文件
    const validation = validateFiles(fileArray, {
      maxSize,
      allowedTypes: accept
    })

    if (!validation.valid) {
      if (onError) {
        onError(validation.errors)
      }
      return
    }

    // 如果不支持多文件，只取第一个
    const filesToProcess = multiple ? fileArray : [fileArray[0]]

    // 触发回调
    if (onDrop) {
      await onDrop(filesToProcess)
    }
  }

  /**
   * 触发文件选择对话框
   * @param {HTMLInputElement} inputRef - 文件input元素引用
   */
  const triggerFileSelect = (inputRef) => {
    if (inputRef && inputRef.click) {
      inputRef.click()
    }
  }

  /**
   * 处理文件选择
   * @param {Event} event - 文件选择事件
   */
  const handleFileSelect = async (event) => {
    const files = event.target.files
    if (!files || files.length === 0) return

    await processFiles(files)

    // 清空input，允许重复选择同一文件
    event.target.value = ''
  }

  /**
   * 设置拖拽区域
   * @param {HTMLElement} element - 拖拽区域元素
   */
  const setupDropZone = (element) => {
    if (!element) return

    dropZoneRef.value = element

    element.addEventListener('dragenter', handleDragEnter)
    element.addEventListener('dragleave', handleDragLeave)
    element.addEventListener('dragover', handleDragOver)
    element.addEventListener('drop', handleDrop)
  }

  /**
   * 移除拖拽区域
   */
  const removeDropZone = () => {
    if (!dropZoneRef.value) return

    const element = dropZoneRef.value
    element.removeEventListener('dragenter', handleDragEnter)
    element.removeEventListener('dragleave', handleDragLeave)
    element.removeEventListener('dragover', handleDragOver)
    element.removeEventListener('drop', handleDrop)

    dropZoneRef.value = null
  }

  /**
   * 重置状态
   */
  const reset = () => {
    isDragging.value = false
    dragOverCount.value = 0
  }

  // ========== 生命周期 ==========

  onMounted(() => {
    // 如果有ref，自动设置
    if (dropZoneRef.value) {
      setupDropZone(dropZoneRef.value)
    }
  })

  onBeforeUnmount(() => {
    removeDropZone()
  })

  return {
    // 状态
    isDragging,
    dragOverCount,
    dropZoneRef,

    // 计算属性
    dropZoneClass,
    canDrop,

    // 方法
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleFileSelect,
    triggerFileSelect,
    setupDropZone,
    removeDropZone,
    reset
  }
}
