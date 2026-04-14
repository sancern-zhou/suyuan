/**
 * 知识库上传进度跟踪 Composable
 * 跟踪文件上传进度和状态
 */
import { ref, computed } from 'vue'

export function useKbUploadProgress() {
  // ========== 状态 ==========
  const isUploading = ref(false)
  const currentFile = ref(null)
  const currentIndex = ref(0)
  const totalCount = ref(0)
  const errors = ref([])

  // ========== 计算属性 ==========

  /**
   * 上传进度百分比
   */
  const progressPercent = computed(() => {
    if (totalCount.value === 0) return 0
    return Math.round((currentIndex.value / totalCount.value) * 100)
  })

  /**
   * 进度文本
   */
  const progressText = computed(() => {
    if (!isUploading.value) return ''
    return `正在上传 ${currentIndex.value}/${totalCount.value}`
  })

  /**
   * 是否有错误
   */
  const hasErrors = computed(() => errors.value.length > 0)

  // ========== 方法 ==========

  /**
   * 开始上传
   * @param {number} total - 总文件数
   */
  const startUpload = (total) => {
    isUploading.value = true
    totalCount.value = total
    currentIndex.value = 0
    errors.value = []
  }

  /**
   * 更新当前文件
   * @param {File} file - 当前文件
   */
  const updateCurrentFile = (file) => {
    currentFile.value = file?.name || ''
  }

  /**
   * 增加进度
   */
  const incrementProgress = () => {
    currentIndex.value++
  }

  /**
   * 添加错误
   * @param {string} error - 错误信息
   */
  const addError = (error) => {
    errors.value.push(error)
  }

  /**
   * 完成上传
   */
  const finishUpload = () => {
    isUploading.value = false
    currentFile.value = null
  }

  /**
   * 重置状态
   */
  const reset = () => {
    isUploading.value = false
    currentFile.value = null
    currentIndex.value = 0
    totalCount.value = 0
    errors.value = []
  }

  return {
    // 状态
    isUploading,
    currentFile,
    currentIndex,
    totalCount,
    errors,

    // 计算属性
    progressPercent,
    progressText,
    hasErrors,

    // 方法
    startUpload,
    updateCurrentFile,
    incrementProgress,
    addError,
    finishUpload,
    reset
  }
}
