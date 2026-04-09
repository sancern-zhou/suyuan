<template>
  <div class="office-panel" :class="{ 'has-content': hasOfficeDocuments, 'expanded': isExpanded }">
    <!-- Empty state -->
    <div v-if="!hasOfficeDocuments || officeDocuments.length === 0" class="empty-state">
      <p class="empty-title">暂无文档</p>
      <p class="empty-tip">编辑Word/PPT文档时，将在此处显示预览</p>
    </div>

    <!-- Panel content -->
    <template v-else>
      <!-- Document list -->
      <div class="doc-list">
        <div v-for="doc in officeDocuments" :key="doc.pdf_id || doc.file_path" class="doc-item">
          <!-- Preview mode: PDF preview (with transition animation) -->
          <div v-if="!isEditMode" class="doc-preview">
            <!-- Action buttons in top-right corner -->
            <div class="action-buttons">
              <button @click="toggleEditMode" class="action-btn edit-btn" title="编辑模式">
                ✏️ 编辑
              </button>

              <!-- Download dropdown menu -->
              <div class="download-dropdown">
                <button @click="toggleDownloadMenu" class="action-btn download-btn" title="下载文档">
                  ⬇️ 下载
                </button>
                <div v-if="showDownloadMenu" class="download-menu">
                  <button v-if="doc.doc_type === 'markdown'" @click="downloadMarkdown(doc)" class="download-item">
                    📄 下载Markdown文件
                  </button>
                  <button v-if="doc.pdf_url" @click="downloadPDF(doc)" class="download-item">
                    📄 下载PDF文件
                  </button>
                  <button
                    v-if="doc.doc_type === 'word'"
                    @click="downloadWord(doc)"
                    class="download-item"
                    :disabled="!doc.file_path || doc.file_path === ''"
                  >
                    📝 下载Word文档
                  </button>
                  <button
                    v-if="doc.doc_type === 'excel'"
                    @click="downloadExcel(doc)"
                    class="download-item"
                    :disabled="!doc.file_path || doc.file_path === ''"
                  >
                    📊 下载Excel文件
                  </button>
                </div>
              </div>
            </div>

            <!-- Loading state -->
            <div v-if="doc.loading" class="preview-loading">
              <div class="spinner"></div>
              <p>更新预览中...</p>
            </div>

            <!-- PDF preview (with fade-in animation) -->
            <div v-else-if="doc.pdf_url" class="pdf-wrapper" :class="{ 'fade-in': !doc.loading }">
              <iframe
                :src="`${doc.pdf_url}#zoom=100&toolbar=0&navpanes=0`"
                class="pdf-iframe"
                type="application/pdf"
                @load="onPdfLoaded(doc)"
              ></iframe>
            </div>

            <!-- Markdown preview -->
            <div v-else-if="doc.markdown_content && doc.doc_type === 'markdown'" class="markdown-wrapper">
              <MarkdownRenderer :content="doc.markdown_content" :streaming="false" />
            </div>

            <!-- Error state -->
            <div v-else class="preview-error">
              <p>预览加载失败</p>
            </div>
          </div>

          <!-- Edit mode: Simple edit box -->
          <div v-else class="doc-edit">
            <div class="edit-header">
              <span class="edit-hint">编辑内容（支持Markdown格式）</span>
              <button
                @click="submitEdit(doc)"
                :disabled="doc.submitting"
                class="submit-btn"
              >
                {{ doc.submitting ? '应用中...' : '✓ 应用更改' }}
              </button>
            </div>
            <textarea
              v-model="doc.editContent"
              class="edit-textarea"
              placeholder="在此编辑文档内容..."
              @input="onEditChange(doc)"
            ></textarea>
            <div v-if="doc.editMessage" class="edit-message" :class="doc.editMessage.type">
              {{ doc.editMessage.text }}
            </div>
          </div>
        </div>
      </div>

      <!-- Edit history (默认隐藏) -->
      <div class="edit-history-section">
        <div class="edit-history-header" @click="toggleHistory">
          <span class="section-title">编辑历史</span>
          <span class="history-toggle-icon">{{ showHistory ? '▼' : '▶' }}</span>
        </div>
        <div v-if="showHistory" class="history-list">
          <div
            v-for="(action, index) in editHistory.slice(-5)"
            :key="index"
            class="history-item"
          >
            <span class="history-icon">{{ getActionIcon(action.tool) }}</span>
            <span class="history-text">{{ action.summary }}</span>
            <span class="history-time">{{ formatTime(action.timestamp) }}</span>
          </div>
          <div v-if="editHistory.length === 0" class="history-empty">
            暂无编辑历史
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

const reactStore = useReactStore()
const emit = defineEmits(['submit-edit'])

const props = defineProps({
  history: {
    type: Array,
    default: () => []
  },
  sessionId: {
    type: String,
    default: null
  }
})

// 状态
const isEditMode = ref(false)
const isExpanded = ref(true)
const showHistory = ref(false)
const showDownloadMenu = ref(false)
const officeDocuments = ref([])
const editHistory = ref([])
const refreshTimeouts = ref(new Map())

// 点击外部关闭下载菜单
function handleClickOutside(event) {
  // 检查点击是否在下载菜单或按钮之外
  if (showDownloadMenu.value) {
    const downloadDropdown = event.target.closest('.download-dropdown')
    if (!downloadDropdown) {
      showDownloadMenu.value = false
    }
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

const hasOfficeDocuments = computed(() => {
  return officeDocuments.value.length > 0
})

// 监听 store.lastOfficeDocument，直接更新文档列表
watch(() => reactStore.lastOfficeDocument, (doc) => {
  if (!doc?.pdf_preview && !doc?.markdown_preview) return

  console.log('[OfficeDocumentPanel] 收到office_document事件:', {
    generator: doc.generator,
    pdf_id: doc.pdf_preview?.pdf_id,
    has_markdown_preview: !!doc.markdown_preview,
    file_path: doc.file_path
  })

  const filePath = doc.file_path
  const fileName = filePath ? filePath.split(/[/\\]/).pop() : 'unknown'

  // 查找现有文档
  const existingDoc = officeDocuments.value.find(d =>
    d.file_path === filePath || d.file_name === fileName
  )

  if (existingDoc) {
    // 更新现有文档
    if (doc.pdf_preview && existingDoc.pdf_id !== doc.pdf_preview.pdf_id) {
      console.log('[OfficeDocumentPanel] 更新现有文档PDF:', fileName)
      existingDoc.pdf_url = doc.pdf_preview.pdf_url
      existingDoc.pdf_id = doc.pdf_preview.pdf_id
      existingDoc.file_path = filePath
      triggerPdfRefresh(existingDoc)
    }
    // 更新markdown内容
    if (doc.markdown_preview) {
      existingDoc.markdown_content = doc.markdown_preview.content
      existingDoc.file_path = filePath
    }
  } else {
    // 添加新文档
    console.log('[OfficeDocumentPanel] 添加新文档:', fileName)
    officeDocuments.value.push({
      doc_type: getDocType(doc.generator, doc.markdown_preview, filePath),
      file_name: fileName,
      file_path: filePath,
      pdf_url: doc.pdf_preview?.pdf_url,
      pdf_id: doc.pdf_preview?.pdf_id,
      markdown_content: doc.markdown_preview?.content,
      loading: false,
      editContent: '',
      submitting: false,
      editMessage: null,
      last_action: {
        tool: doc.generator,
        summary: doc.summary,
        timestamp: doc.timestamp || new Date()
      }
    })
  }

  // 添加到编辑历史
  editHistory.value.push({
    tool: doc.generator,
    summary: doc.summary,
    timestamp: doc.timestamp || new Date()
  })
}, { immediate: true })

// Trigger PDF refresh animation
function triggerPdfRefresh(doc) {
  const key = doc.pdf_id || doc.file_path

  // 清除之前的定时器
  if (refreshTimeouts.value.has(key)) {
    clearTimeout(refreshTimeouts.value.get(key))
  }

  // 设置loading状态
  doc.loading = true

  // 设置新的定时器
  const timeoutId = setTimeout(() => {
    doc.loading = false
    refreshTimeouts.value.delete(key)
  }, 100)

  refreshTimeouts.value.set(key, timeoutId)
}

// PDF load complete callback
function onPdfLoaded(doc) {
  // Additional load completion logic can be added here
}

// Toggle edit mode
function toggleEditMode() {
  isEditMode.value = !isEditMode.value
}

// Toggle download menu
function toggleDownloadMenu() {
  showDownloadMenu.value = !showDownloadMenu.value
}

// Download PDF file
function downloadPDF(doc) {
  if (!doc.pdf_url) {
    console.error('[OfficeDocumentPanel] PDF URL not available')
    showDownloadMenu.value = false
    return
  }

  try {
    // 创建下载链接
    const link = document.createElement('a')
    link.href = doc.pdf_url
    link.download = `${doc.file_name || 'document'}.pdf`
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    console.log('[OfficeDocumentPanel] PDF download started:', doc.file_name)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] PDF download failed:', error)
  }
}

// Download Word document
async function downloadWord(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] Word file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    // 调用后端API下载Word文档
    const response = await fetch('/api/office/download-word', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: doc.file_path
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    // 获取文件名
    const contentDisposition = response.headers.get('Content-Disposition')
    let fileName = doc.file_name || 'document.docx'
    if (contentDisposition) {
      const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match && match[1]) {
        fileName = match[1].replace(/['"]/g, '')
      }
    }

    // 下载文件
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    console.log('[OfficeDocumentPanel] Word download started:', fileName)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Word download failed:', error)
  }
}

// Download Markdown file
function downloadMarkdown(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] Markdown file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    // 使用通用文件下载API（类似PDF的简单方式）
    const fileUrl = `/api/file/${encodeURIComponent(doc.file_path)}`

    // 创建下载链接
    const link = document.createElement('a')
    link.href = fileUrl
    link.download = doc.file_name || 'document.md'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    console.log('[OfficeDocumentPanel] Markdown download started:', doc.file_name)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Markdown download failed:', error)
  }
}

// Download Excel file
function downloadExcel(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] Excel file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    // 使用通用文件下载API
    const fileUrl = `/api/file/${encodeURIComponent(doc.file_path)}`

    // 创建下载链接
    const link = document.createElement('a')
    link.href = fileUrl
    link.download = doc.file_name || 'document.xlsx'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    console.log('[OfficeDocumentPanel] Excel download started:', doc.file_name)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Excel download failed:', error)
  }
}

// Cancel edit
function cancelEdit() {
  isEditMode.value = false
  // Clear edit content
  officeDocuments.value.forEach(doc => {
    doc.editContent = ''
    doc.editMessage = null
  })
}

// Edit content change
function onEditChange(doc) {
  // Clear previous message
  if (doc.editMessage) {
    doc.editMessage = null
  }
}

// Submit edit
async function submitEdit(doc) {
  if (!doc.editContent || doc.editContent.trim() === '') {
    doc.editMessage = { type: 'error', text: '请输入编辑内容' }
    return
  }

  doc.submitting = true

  try {
    // Trigger parent component to handle edit submission
    emit('submit-edit', {
      file_path: doc.file_path,
      content: doc.editContent,
      doc_type: doc.doc_type
    })

    // Switch back to preview mode after edit
    isEditMode.value = false
    doc.editContent = ''
    doc.editMessage = null
  } catch (error) {
    doc.editMessage = { type: 'error', text: '提交失败：' + error.message }
  } finally {
    doc.submitting = false
  }
}

function getDocType(generator, markdownPreview, filePath) {
  // 先根据 generator 判断
  if (['word_edit', 'find_replace_word', 'accept_word_changes'].includes(generator)) {
    return 'word'
  } else if (['add_ppt_slide'].includes(generator)) {
    return 'ppt'
  } else if (markdownPreview) {
    return 'markdown'
  }

  // 如果 generator 无法判断，根据文件扩展名判断
  if (filePath) {
    const ext = filePath.toLowerCase().split('.').pop()
    if (['doc', 'docx'].includes(ext)) {
      return 'word'
    } else if (['ppt', 'pptx'].includes(ext)) {
      return 'ppt'
    } else if (['xls', 'xlsx'].includes(ext)) {
      return 'excel'
    } else if (['md', 'markdown'].includes(ext)) {
      return 'markdown'
    }
  }

  return 'unknown'
}

function getDocIcon(docType) {
  const icons = { word: '📝', ppt: '📊', unknown: '📄' }
  return icons[docType] || icons.unknown
}

function getActionIcon(tool) {
  const icons = {
    word_edit: '✏️',
    find_replace_word: '🔍',
    accept_word_changes: '✅',
    add_ppt_slide: '➕',
    unpack_office: '📦',
    pack_office: '📦',
    recalc_excel: '📊'
  }
  return icons[tool] || '⚙️'
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function toggleHistory() {
  showHistory.value = !showHistory.value
}

// 【新增】从历史数据加载文档列表（用于历史对话恢复）
function loadDocuments(documents) {
  if (!documents || !Array.isArray(documents) || documents.length === 0) {
    console.log('[OfficeDocumentPanel] 无历史文档需要加载')
    return
  }

  console.log('[OfficeDocumentPanel] 开始加载历史文档，数量:', documents.length)

  documents.forEach((doc, index) => {
    // 检查是否有有效的预览数据（PDF或Markdown）
    if ((!doc.pdf_preview && !doc.markdown_preview) || !doc.file_path) {
      console.warn('[OfficeDocumentPanel] 跳过无效文档:', index, doc)
      return
    }

    const filePath = doc.file_path
    const fileName = filePath ? filePath.split(/[/\\]/).pop() : 'unknown'

    // 检查是否已存在
    const existingDoc = officeDocuments.value.find(d =>
      d.file_path === filePath || d.file_name === fileName
    )

    if (!existingDoc) {
      // 添加新文档（不触发动画，因为这是历史数据）
      console.log('[OfficeDocumentPanel] 加载历史文档:', index + 1, fileName)
      officeDocuments.value.push({
        doc_type: getDocType(doc.generator, doc.markdown_preview),
        file_name: fileName,
        file_path: filePath,
        pdf_url: doc.pdf_preview?.pdf_url,
        pdf_id: doc.pdf_preview?.pdf_id,
        markdown_content: doc.markdown_preview?.content,
        loading: false,
        editContent: '',
        submitting: false,
        editMessage: null,
        last_action: {
          tool: doc.generator,
          summary: doc.summary,
          timestamp: doc.timestamp || new Date()
        }
      })
    }
  })

  console.log('[OfficeDocumentPanel] 历史文档加载完成，当前总数:', officeDocuments.value.length)
}

function getFileName(path) {
  if (!path) return '未命名文档'
  return path.split(/[/\\]/).pop() || '未命名文档'
}

defineExpose({
  hasOfficeDocuments,
  isEditMode,
  cancelEdit,
  loadDocuments  // 【新增】暴露loadDocuments方法
})
</script>

<style lang="scss" scoped>
.office-panel {
  width: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-left: 1px solid #f0f0f0;
  max-height: none !important;
  overflow: visible !important;
  flex-shrink: 0;
}

.doc-list {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.doc-item {
  border: none;
  padding: 0;
  background: #fff;
}

.doc-preview {
  margin: 0;
  border: none;
  min-height: 720px;
  position: relative;
  overflow: hidden;
}

.action-buttons {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 8px;
  z-index: 10;
}

.action-btn {
  padding: 6px 16px;
  border: 1px solid #1976d2;
  background: #1976d2;
  color: white;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  white-space: nowrap;

  &:hover {
    background: #1565c0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
  }
}

.download-dropdown {
  position: relative;
}

.download-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  min-width: 160px;
  z-index: 100;
  overflow: hidden;
}

.download-item {
  width: 100%;
  padding: 10px 16px;
  border: none;
  background: white;
  text-align: left;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #333;

  &:hover:not(:disabled) {
    background: #f5f5f5;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &:not(:last-child) {
    border-bottom: 1px solid #f0f0f0;
  }
}

.office-panel.expanded .doc-preview {
  min-height: calc(100vh - 120px);
}

.preview-loading,
.preview-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #999;
  min-height: 300px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e0e0;
  border-top-color: #3498db;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.pdf-wrapper {
  width: 100%;
  height: 750px;
  opacity: 0;
  transition: opacity 0.3s ease-in-out;

  &.fade-in {
    opacity: 1;
  }
}

.office-panel.expanded .pdf-wrapper {
  height: calc(100vh - 100px);
}

.pdf-iframe {
  width: 100%;
  height: 750px;
  border: none;
  transition: height 0.3s ease;
}

.markdown-wrapper {
  width: 100%;
  min-height: 750px;
  padding: 20px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}

.office-panel.expanded .pdf-iframe {
  height: calc(100vh - 100px);
}

// Edit mode styles
.doc-edit {
  margin: 12px 0;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafafa;
}

.edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fff;
  border-radius: 6px 6px 0 0;
}

.edit-hint {
  font-size: 12px;
  color: #666;
}

.submit-btn {
  padding: 4px 12px;
  border: none;
  background: #1976d2;
  color: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: #1565c0;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.edit-textarea {
  width: 100%;
  min-height: 200px;
  padding: 12px;
  border: none;
  border-radius: 0 0 6px 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;

  &:focus {
    outline: none;
    background: #fff;
  }
}

.edit-message {
  padding: 8px 12px;
  margin-top: 8px;
  border-radius: 4px;
  font-size: 12px;

  &.error {
    background: #ffebee;
    color: #c62828;
  }

  &.success {
    background: #e8f5e9;
    color: #2e7d32;
  }
}

.edit-history-section {
  padding: 12px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.edit-history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
  padding: 4px 0;
}

.history-toggle-icon {
  font-size: 12px;
  color: #666;
  transition: transform 0.2s;
}

.section-title { font-size: 13px; font-weight: 600; color: #666; margin-bottom: 0; }

.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #fff;
  border-radius: 4px;
  font-size: 12px;
}

.history-empty {
  padding: 12px;
  text-align: center;
  color: #999;
  font-size: 12px;
}

.history-icon { font-size: 14px; }
.history-text { flex: 1; color: #333; }
.history-time { color: #999; font-size: 11px; }

.empty-state {
  gap: 6px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
  padding: 40px 20px;
}

.empty-title { font-size: 16px; font-weight: 500; color: #666; margin: 0 0 8px 0; }
.empty-tip { font-size: 13px; margin: 0; }
</style>
