/**
 * 知识库文件上传 Composable
 * 处理文件上传的核心逻辑
 */
import { ref } from 'vue'
import { useKbUploadProgress } from './useKbUploadProgress'
import { validateFiles } from './useKbFileValidation'
import { FILE_SIZE_LIMITS } from '@/utils/constants'

export function useKbFileUpload(kbStore, options = {}) {
  const {
    maxConcurrent = 1, // 最大并发上传数
    onProgress = null, // 进度回调
    onComplete = null, // 完成回调
    onError = null // 错误回调
  } = options

  // ========== 状态 ==========
  const fileInputRef = ref(null)
  const isDragging = ref(false)

  // 使用进度跟踪
  const progress = useKbUploadProgress()

  // ========== 方法 ==========

  /**
   * 触发文件选择对话框
   */
  const triggerFileSelect = () => {
    if (progress.isUploading.value) return
    fileInputRef.value?.click()
  }

  /**
   * 处理文件选择
   * @param {Event} event - 文件选择事件
   */
  const handleFileSelect = async (event) => {
    const files = event.target.files
    if (files && files.length > 0) {
      await uploadFiles(Array.from(files))
    }
    // 清空input，允许重复选择同一文件
    event.target.value = ''
  }

  /**
   * 处理文件拖放
   * @param {DragEvent} event - 拖放事件
   */
  const handleFileDrop = async (event) => {
    isDragging.value = false
    event.preventDefault()

    const files = event.dataTransfer?.files
    if (files && files.length > 0) {
      await uploadFiles(Array.from(files))
    }
  }

  /**
   * 处理拖拽悬停
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragOver = (event) => {
    event.preventDefault()
    if (event.dataTransfer?.types.includes('Files')) {
      isDragging.value = true
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  /**
   * 处理拖拽离开
   * @param {DragEvent} event - 拖拽事件
   */
  const handleDragLeave = (event) => {
    // 检查是否真的离开了拖拽区域
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX
    const y = event.clientY
    if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
      isDragging.value = false
    }
  }

  /**
   * 上传文件列表
   * @param {Array<File>} files - 文件数组
   * @param {object} uploadOptions - 上传选项
   */
  const uploadFiles = async (files, uploadOptions = {}) => {
    // 检查是否有当前知识库
    if (!kbStore.currentKb) {
      alert('请先选择一个知识库')
      return
    }

    // 验证文件
    const validation = validateFiles(files, {
      maxSize: FILE_SIZE_LIMITS.LARGE
    })

    if (!validation.valid) {
      alert('文件验证失败:\n' + validation.errors.join('\n'))
      return
    }

    // 开始上传
    progress.startUpload(files.length)

    try {
      // 顺序上传文件
      for (const file of files) {
        await uploadSingleFile(file, uploadOptions)
        progress.incrementProgress()

        // 触发进度回调
        if (onProgress) {
          onProgress({
            current: progress.currentIndex.value,
            total: progress.totalCount.value,
            percent: progress.progressPercent.value
          })
        }
      }

      // 触发完成回调
      if (onComplete) {
        onComplete({
          success: true,
          total: files.length,
          errors: progress.errors.value
        })
      }
    } catch (error) {
      // 触发错误回调
      if (onError) {
        onError(error)
      }
    } finally {
      progress.finishUpload()
    }
  }

  /**
   * 上传单个文件
   * @param {File} file - 文件对象
   * @param {object} uploadOptions - 上传选项
   */
  const uploadSingleFile = async (file, uploadOptions = {}) => {
    progress.updateCurrentFile(file)

    const defaultOptions = {
      chunking_strategy: 'llm',
      chunk_size: 800,
      chunk_overlap: 100,
      llm_mode: 'local'
    }

    const options = { ...defaultOptions, ...uploadOptions }

    try {
      await kbStore.uploadDocument(kbStore.currentKb.id, file, options)
    } catch (error) {
      const errorMsg = `上传"${file.name}"失败: ${error.message}`
      progress.addError(errorMsg)
      console.error(errorMsg, error)
    }
  }

  /**
   * 取消上传
   */
  const cancelUpload = () => {
    progress.reset()
  }

  return {
    // 状态
    fileInputRef,
    isDragging,
    progress,

    // 方法
    triggerFileSelect,
    handleFileSelect,
    handleFileDrop,
    handleDragOver,
    handleDragLeave,
    uploadFiles,
    cancelUpload
  }
}
