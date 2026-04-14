/**
 * Office文档处理 Composable
 * 处理Office文档的预览、编辑和提交
 */
import { ref, computed, watch } from 'vue'

export function useOfficeDocumentHandler(store, options = {}) {
  const {
    onEditSubmit = null,
    onPreviewChange = null
  } = options

  // ========== 状态 ==========
  const isEditing = ref(false)
  const isSubmitting = ref(false)
  const currentDocument = ref(null)
  const editContent = ref('')
  const panelRef = ref(null)

  // ========== 计算属性 ==========

  /**
   * 最新的Office文档
   */
  const latestDocument = computed(() => store.lastOfficeDocument)

  /**
   * 是否有Office文档
   */
  const hasDocument = computed(() => {
    return !!(
      latestDocument.value?.pdf_preview ||
      latestDocument.value?.markdown_preview
    )
  })

  /**
   * PDF预览数据
   */
  const pdfPreview = computed(() => {
    return latestDocument.value?.pdf_preview || null
  })

  /**
   * Markdown预览数据
   */
  const markdownPreview = computed(() => {
    return latestDocument.value?.markdown_preview || null
  })

  /**
   * 文档类型
   */
  const documentType = computed(() => {
    const doc = latestDocument.value
    if (!doc) return null

    if (doc.file_path) {
      const ext = doc.file_path.split('.').pop().toLowerCase()
      if (['doc', 'docx'].includes(ext)) return 'word'
      if (['xls', 'xlsx'].includes(ext)) return 'excel'
      if (['ppt', 'pptx'].includes(ext)) return 'powerpoint'
    }

    return 'unknown'
  })

  // ========== 监听器 ==========

  /**
   * 监听文档变化
   */
  watch(latestDocument, (doc) => {
    if (doc && onPreviewChange) {
      onPreviewChange(doc)
    }
  }, { immediate: true })

  // ========== 方法 ==========

  /**
   * 开始编辑文档
   */
  const startEditing = () => {
    if (!currentDocument.value) {
      currentDocument.value = latestDocument.value
    }

    // 初始化编辑内容
    if (markdownPreview.value) {
      editContent.value = markdownPreview.value.content || ''
    }

    isEditing.value = true
  }

  /**
   * 取消编辑
   */
  const cancelEdit = () => {
    isEditing.value = false
    editContent.value = ''
    currentDocument.value = null
  }

  /**
   * 提交编辑
   * @param {object} editData - 编辑数据
   */
  const submitEdit = async (editData) => {
    if (!editData || !editData.file_path) {
      console.error('[Office文档] 缺少必要参数')
      return { success: false, error: '缺少必要参数' }
    }

    isSubmitting.value = true

    try {
      const response = await fetch('/api/office/apply-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_path: editData.file_path,
          content: editData.content || editContent.value,
          doc_type: editData.doc_type || documentType.value,
          session_id: store.currentState.sessionId || ''
        })
      })

      const result = await response.json()

      if (result.success) {
        console.log('[Office文档] 编辑已提交:', result.message)
        cancelEdit()

        if (onEditSubmit) {
          onEditSubmit(result)
        }

        return { success: true, data: result }
      } else {
        console.error('[Office文档] 提交失败:', result.message)
        return { success: false, error: result.message }
      }
    } catch (error) {
      console.error('[Office文档] 提交编辑失败:', error)
      return { success: false, error: error.message }
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 重新加载文档
   */
  const reloadDocument = () => {
    // 文档更新会通过SSE推送自动更新
    console.log('[Office文档] 等待服务器推送更新')
  }

  /**
   * 下载文档
   * @param {string} filePath - 文件路径
   */
  const downloadDocument = async (filePath) => {
    try {
      const response = await fetch(`/api/office/download?path=${encodeURIComponent(filePath)}`)

      if (!response.ok) {
        throw new Error('下载失败')
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filePath.split('/').pop()
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('[Office文档] 下载失败:', error)
      throw error
    }
  }

  /**
   * 获取文档图标
   * @param {string} type - 文档类型
   * @returns {string} 图标类名
   */
  const getDocumentIcon = (type) => {
    const iconMap = {
      word: 'icon-word',
      excel: 'icon-excel',
      powerpoint: 'icon-powerpoint',
      pdf: 'icon-pdf',
      unknown: 'icon-file'
    }
    return iconMap[type] || iconMap.unknown
  }

  /**
   * 格式化文件大小
   * @param {number} bytes - 字节数
   * @returns {string} 格式化后的大小
   */
  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  }

  /**
   * 清除文档
   */
  const clearDocument = () => {
    store.setLastOfficeDocument(null)
    currentDocument.value = null
    editContent.value = ''
    isEditing.value = false
  }

  return {
    // 状态
    isEditing,
    isSubmitting,
    currentDocument,
    editContent,
    panelRef,

    // 计算属性
    latestDocument,
    hasDocument,
    pdfPreview,
    markdownPreview,
    documentType,

    // 方法
    startEditing,
    cancelEdit,
    submitEdit,
    reloadDocument,
    downloadDocument,
    getDocumentIcon,
    formatFileSize,
    clearDocument
  }
}
