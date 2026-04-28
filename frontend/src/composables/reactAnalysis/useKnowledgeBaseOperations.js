/**
 * 知识库操作 Composable
 * 处理知识库的CRUD操作、文档上传、分块查看等
 */
import { ref, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { validateKbName, validateKbDescription, validateChunkSize, validateChunkOverlap } from '@/utils/validators'
import { KB_DEFAULTS } from '@/utils/constants'

export function useKnowledgeBaseOperations() {
  const kbStore = useKnowledgeBaseStore()

  // ========== 状态 ==========
  const kbCreateForm = ref({
    name: '',
    description: '',
    kb_type: 'private',
    chunking_strategy: 'llm',
    chunk_size: KB_DEFAULTS.CHUNK_SIZE,
    chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP
  })

  const kbEditForm = ref({
    name: '',
    description: '',
    is_default: false
  })

  const kbAdminConfirm = ref(localStorage.getItem('isAdmin') === 'true')

  const kbUploadOptions = ref({
    chunking_strategy: 'llm',
    chunk_size: KB_DEFAULTS.CHUNK_SIZE,
    chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP,
    llm_mode: 'local'
  })

  // 上传状态
  const kbIsDragging = ref(false)
  const kbIsUploading = ref(false)
  const kbUploadProgress = ref({ current: 0, total: 0 })
  const kbFileInput = ref(null)

  // ========== 计算属性 ==========

  /**
   * 当前选中的知识库
   */
  const currentKb = computed(() => kbStore.currentKb)

  /**
   * 当前文档
   */
  const currentDoc = computed(() => kbStore.currentDoc)

  /**
   * 文档分块列表
   */
  const documentChunks = computed(() => kbStore.documentChunks)

  /**
   * 知识库列表
   */
  const knowledgeBases = computed(() => kbStore.knowledgeBases)

  // ========== 知识库CRUD操作 ==========

  /**
   * 创建知识库
   */
  const handleKbCreate = async () => {
    // 验证表单
    const nameValidation = validateKbName(kbCreateForm.value.name)
    if (!nameValidation.valid) {
      alert(nameValidation.message)
      return
    }

    const descValidation = validateKbDescription(kbCreateForm.value.description)
    if (!descValidation.valid) {
      alert(descValidation.message)
      return
    }

    const sizeValidation = validateChunkSize(kbCreateForm.value.chunk_size)
    if (!sizeValidation.valid) {
      alert(sizeValidation.message)
      return
    }

    const overlapValidation = validateChunkOverlap(
      kbCreateForm.value.chunk_overlap,
      kbCreateForm.value.chunk_size
    )
    if (!overlapValidation.valid) {
      alert(overlapValidation.message)
      return
    }

    // 公共知识库需要管理员确认
    if (kbCreateForm.value.kb_type === 'public' && !kbAdminConfirm.value) {
      alert('创建公共知识库需要管理员权限，请勾选确认。')
      return
    }

    try {
      // 同步管理员标识到 localStorage
      if (kbCreateForm.value.kb_type === 'public' && kbAdminConfirm.value) {
        localStorage.setItem('isAdmin', 'true')
      } else if (!kbAdminConfirm.value) {
        localStorage.removeItem('isAdmin')
      }

      await kbStore.createKnowledgeBase(kbCreateForm.value)

      // 重置表单
      resetKbCreateForm()

      return true
    } catch (e) {
      alert('创建失败: ' + e.message)
      return false
    }
  }

  /**
   * 更新知识库
   */
  const handleKbUpdate = async () => {
    if (!currentKb.value) return false

    const nameValidation = validateKbName(kbEditForm.value.name)
    if (!nameValidation.valid) {
      alert(nameValidation.message)
      return false
    }

    const descValidation = validateKbDescription(kbEditForm.value.description)
    if (!descValidation.valid) {
      alert(descValidation.message)
      return false
    }

    try {
      await kbStore.updateKnowledgeBase(currentKb.value.id, kbEditForm.value)
      return true
    } catch (e) {
      alert('更新失败: ' + e.message)
      return false
    }
  }

  /**
   * 删除知识库
   */
  const handleDeleteKb = async () => {
    if (!currentKb.value) return false

    if (!confirm(`确定要删除知识库"${currentKb.value.name}"吗？此操作不可恢复。`)) {
      return false
    }

    try {
      await kbStore.deleteKnowledgeBase(currentKb.value.id)
      // 清除所有相关数据
      kbStore.clearCurrentDoc()
      handleKbBack()
      return true
    } catch (e) {
      alert('删除失败: ' + e.message)
      return false
    }
  }

  /**
   * 选择知识库
   */
  const selectKb = (kb) => {
    kbStore.selectKnowledgeBase(kb)
    // 初始化编辑表单
    kbEditForm.value = {
      name: kb.name,
      description: kb.description || '',
      is_default: kb.is_default
    }
  }

  /**
   * 返回知识库列表
   */
  const handleKbBack = () => {
    kbStore.currentKb = null
    kbStore.documents = []
    kbStore.clearCurrentDoc()  // 清除当前文档和分块数据
  }

  // ========== 文档操作 ==========

  /**
   * 重试文档处理
   */
  const handleKbRetry = async (docId) => {
    if (!docId || docId === 'undefined') {
      alert('文档ID无效')
      return false
    }

    if (!currentKb.value) {
      alert('请先选择知识库')
      return false
    }

    try {
      await kbStore.retryDocument(currentKb.value.id, docId)
      return true
    } catch (e) {
      alert('重试失败: ' + e.message)
      return false
    }
  }

  /**
   * 删除文档
   */
  const handleKbDeleteDoc = async (docId) => {
    if (!docId || docId === 'undefined') {
      alert('文档ID无效')
      return false
    }

    if (!currentKb.value) {
      alert('请先选择知识库')
      return false
    }

    if (!confirm('确定要删除此文档吗？')) return false

    try {
      await kbStore.deleteDocument(currentKb.value.id, docId)
      return true
    } catch (e) {
      alert('删除失败: ' + e.message)
      return false
    }
  }

  /**
   * 查看文档分块
   */
  const viewKbChunks = async (doc) => {
    if (!doc || !doc.id || doc.id === 'undefined') {
      alert('文档ID无效')
      return false
    }

    if (!currentKb.value) {
      alert('请先选择知识库')
      return false
    }

    try {
      await kbStore.fetchDocumentChunks(currentKb.value.id, doc.id)
      return true
    } catch (e) {
      alert('获取分块失败: ' + e.message)
      return false
    }
  }

  // ========== 文档上传 ==========

  /**
   * 触发文件选择对话框
   */
  const triggerKbFileInput = () => {
    if (!kbIsUploading.value) {
      kbFileInput.value?.click()
    }
  }

  /**
   * 处理文件选择
   */
  const handleKbFileSelect = async (event) => {
    const files = event.target.files
    if (files && files.length > 0) {
      await uploadFiles(files)
    }
  }

  /**
   * 上传文件
   */
  const uploadFiles = async (files) => {
    if (!currentKb.value) {
      alert('请先选择知识库')
      return
    }

    kbIsUploading.value = true
    kbUploadProgress.value = { current: 0, total: files.length }

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]

        await kbStore.uploadDocument(currentKb.value.id, file, {
          chunking_strategy: kbUploadOptions.value.chunking_strategy,
          chunk_size: kbUploadOptions.value.chunk_size,
          chunk_overlap: kbUploadOptions.value.chunk_overlap,
          llm_mode: kbUploadOptions.value.llm_mode
        })

        kbUploadProgress.value.current = i + 1
      }

      return true
    } catch (e) {
      alert('上传失败: ' + e.message)
      return false
    } finally {
      kbIsUploading.value = false
      kbUploadProgress.value = { current: 0, total: 0 }
    }
  }

  // ========== 表单重置 ==========

  /**
   * 重置创建表单
   */
  const resetKbCreateForm = () => {
    kbCreateForm.value = {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: KB_DEFAULTS.CHUNK_SIZE,
      chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP
    }
    kbAdminConfirm.value = localStorage.getItem('isAdmin') === 'true'
  }

  /**
   * 重置编辑表单
   */
  const resetKbEditForm = () => {
    kbEditForm.value = {
      name: '',
      description: '',
      is_default: false
    }
  }

  // ========== 辅助方法 ==========

  /**
   * 获取分块策略描述
   */
  const getKbStrategyDesc = (strategy) => {
    const descriptions = {
      llm: '使用LLM智能识别文档结构，适合复杂文档（较慢）',
      sentence: '按句子分块，保持语义完整，适合通用文本',
      semantic: '基于语义相似度分块，保持主题连贯',
      markdown: '按Markdown结构分块，保留标题层级',
      hybrid: '混合策略，结合多种方法优势'
    }
    return descriptions[strategy] || ''
  }

  /**
   * 获取分块类型名称
   */
  const getKbChunkTypeName = (type) => {
    const typeNames = {
      text: '文本',
      code: '代码',
      table: '表格',
      image: '图片',
      metadata: '元数据'
    }
    return typeNames[type] || type
  }

  return {
    // 状态
    kbCreateForm,
    kbEditForm,
    kbAdminConfirm,
    kbUploadOptions,
    kbIsDragging,
    kbIsUploading,
    kbUploadProgress,
    kbFileInput,

    // 计算属性
    currentKb,
    currentDoc,
    documentChunks,
    knowledgeBases,

    // 知识库CRUD
    handleKbCreate,
    handleKbUpdate,
    handleDeleteKb,
    selectKb,
    handleKbBack,

    // 文档操作
    handleKbRetry,
    handleKbDeleteDoc,
    viewKbChunks,

    // 文档上传
    triggerKbFileInput,
    handleKbFileSelect,
    uploadFiles,

    // 表单重置
    resetKbCreateForm,
    resetKbEditForm,

    // 辅助方法
    getKbStrategyDesc,
    getKbChunkTypeName
  }
}
