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
              <button
                v-if="!['notebook', 'report', 'html_artifact'].includes(doc.doc_type)"
                @click="toggleEditMode"
                class="action-btn edit-btn"
                title="编辑模式"
              >
                <svg class="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
                  <path d="m13.5 8.5 2 2" />
                </svg>
                <span>编辑</span>
              </button>
              <button
                v-if="['report', 'html_artifact'].includes(doc.doc_type)"
                @click="doc.doc_type === 'html_artifact' ? handleHtmlArtifactShare(doc) : handleReportShare(doc)"
                class="action-btn share-btn"
                title="生成分享链接"
                :disabled="doc.sharing"
              >
                <span v-if="doc.sharing">生成中...</span>
                <template v-else>
                  <svg class="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 16V4" />
                    <path d="m7 9 5-5 5 5" />
                    <path d="M5 16v2.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V16" />
                  </svg>
                  <span>分享</span>
                </template>
              </button>

              <!-- Download dropdown menu -->
              <div class="download-dropdown">
                <button @click="toggleDownloadMenu" class="action-btn download-btn" title="下载文档">
                  <svg class="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 4v12" />
                    <path d="m7 11 5 5 5-5" />
                    <path d="M5 20h14" />
                  </svg>
                  <span>下载</span>
                </button>
                <div v-if="showDownloadMenu" class="download-menu">
                  <button v-if="doc.doc_type === 'report'" @click="downloadReportFormat(doc, 'qmd')" class="download-item">
                    下载 QMD 源文件
                  </button>
                  <button v-if="doc.doc_type === 'report'" @click="downloadReportFormat(doc, 'docx')" class="download-item">
                    下载 Word 文档
                  </button>
                  <button v-if="doc.doc_type === 'html_artifact'" @click="downloadHtmlArtifact(doc)" class="download-item">
                    下载 HTML 文件
                  </button>
                  <button v-if="doc.doc_type === 'markdown'" @click="downloadMarkdown(doc)" class="download-item">
                    下载 Markdown 文件
                  </button>
                  <button v-if="doc.pdf_url" @click="downloadPDF(doc)" class="download-item">
                    下载 PDF 文件
                  </button>
                  <button
                    v-if="doc.doc_type === 'word'"
                    @click="downloadWord(doc)"
                    class="download-item"
                    :disabled="!doc.file_path || doc.file_path === ''"
                  >
                    下载 Word 文档
                  </button>
                  <button
                    v-if="doc.doc_type === 'ppt'"
                    @click="downloadPPT(doc)"
                    class="download-item"
                    :disabled="!doc.file_path || doc.file_path === ''"
                  >
                    下载 PPT 文件
                  </button>
                  <button
                    v-if="doc.doc_type === 'excel'"
                    @click="downloadExcel(doc)"
                    class="download-item"
                    :disabled="!doc.file_path || doc.file_path === ''"
                  >
                    下载 Excel 文件
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

            <!-- HTML preview (Notebook/Quarto报告/HTML展示页使用iframe显示) -->
            <div v-else-if="['notebook', 'report', 'html_artifact'].includes(doc.doc_type) && doc.html_url" class="notebook-wrapper">
              <iframe
                :src="doc.html_url"
                :key="doc.html_url"
                class="notebook-iframe"
                type="text/html"
                @load="onPdfLoaded(doc)"
              ></iframe>
            </div>

            <!-- Notebook with share button (如果有file_path) -->
            <div v-else-if="doc.doc_type === 'notebook' && doc.file_path" class="notebook-with-share">
              <div class="notebook-actions">
                <button
                  @click="handleNotebookShare(doc)"
                  class="share-button"
                  :disabled="doc.sharing"
                >
                  <span v-if="doc.sharing">生成中...</span>
                  <span v-else>分享报告</span>
                </button>
              </div>
              <div class="notebook-placeholder">
                <p>📝 Notebook文件：{{ doc.file_name }}</p>
                <p class="hint">点击"分享报告"生成可分享的HTML链接</p>
              </div>
            </div>

            <!-- Markdown preview -->
            <div v-else-if="doc.markdown_content && ['markdown', 'report'].includes(doc.doc_type)" class="markdown-wrapper">
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

    <transition name="share-toast">
      <div
        v-if="shareToast.visible"
        class="share-toast"
        :class="shareToast.type"
        role="status"
        aria-live="polite"
      >
        <div class="share-toast-indicator" aria-hidden="true"></div>
        <div class="share-toast-content">
          <div class="share-toast-title">{{ shareToast.title }}</div>
          <div v-if="shareToast.message" class="share-toast-message">{{ shareToast.message }}</div>
          <div v-if="shareToast.link" class="share-toast-link" :title="shareToast.link">
            {{ shareToast.link }}
          </div>
          <div v-if="shareToast.link" class="share-toast-actions">
            <button type="button" @click="copyShareToastLink">复制链接</button>
            <a :href="shareToast.link" target="_blank" rel="noopener noreferrer">打开</a>
          </div>
        </div>
        <button type="button" class="share-toast-close" @click="hideShareToast" aria-label="关闭提示">x</button>
      </div>
    </transition>
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
const shareToast = ref({
  visible: false,
  type: 'success',
  title: '',
  message: '',
  link: ''
})
let shareToastTimer = null

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
  if (shareToastTimer) {
    clearTimeout(shareToastTimer)
  }
})

const hasOfficeDocuments = computed(() => {
  return officeDocuments.value.length > 0
})

function withPreviewVersion(url, version) {
  if (!url || !version) {
    return url
  }
  try {
    const separator = url.includes('?') ? '&' : '?'
    return `${url}${separator}v=${encodeURIComponent(version)}`
  } catch (error) {
    return url
  }
}

// 监听 store.lastOfficeDocument，直接更新文档列表
watch(() => reactStore.lastOfficeDocument, (doc, oldDoc) => {
  if (!doc?.pdf_preview && !doc?.markdown_preview && !doc?.html_preview) {
    return
  }

  const filePath = doc.file_path
  const fileName = filePath ? filePath.split(/[/\\]/).pop() : 'unknown'

  // 检测是否切换到了不同的文档（会话切换）
  if (oldDoc?.file_path && oldDoc.file_path !== filePath) {
    officeDocuments.value = []
    editHistory.value = []
    showHistory.value = false
    isEditMode.value = false
  }

  // 查找现有文档
  const existingDoc = officeDocuments.value.find(d =>
    d.file_path === filePath || d.file_name === fileName
  )

  if (existingDoc) {
    // 更新现有文档
    if (doc.pdf_preview && existingDoc.pdf_id !== doc.pdf_preview.pdf_id) {
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
    // 更新 Notebook HTML预览
    if (doc.html_preview) {
      existingDoc.html_url = withPreviewVersion(doc.html_preview.html_url, doc.html_preview.preview_version)
      existingDoc.html_id = doc.html_preview.html_id
      existingDoc.preview_version = doc.html_preview.preview_version
      existingDoc.file_path = filePath
      existingDoc.doc_type = getDocType(doc.generator, doc.markdown_preview, doc.html_preview, filePath, doc.file_type)
      existingDoc.loading = false
    }
  } else {
    // 添加新文档
    const newDoc = {
      doc_type: getDocType(doc.generator, doc.markdown_preview, doc.html_preview, filePath, doc.file_type),
      file_name: fileName,
      file_path: filePath,
      pdf_url: doc.pdf_preview?.pdf_url,
      pdf_id: doc.pdf_preview?.pdf_id,
      html_url: withPreviewVersion(doc.html_preview?.html_url, doc.html_preview?.preview_version),
      html_id: doc.html_preview?.html_id,
      preview_version: doc.html_preview?.preview_version,
      markdown_content: doc.markdown_preview?.content,
      loading: false,
      sharing: false,
      editContent: '',
      submitting: false,
      editMessage: null,
      last_action: {
        tool: doc.generator,
        summary: doc.summary,
        timestamp: doc.timestamp || new Date()
      }
    }

    officeDocuments.value.push(newDoc)
  }

  // 添加到编辑历史
  editHistory.value.push({
    tool: doc.generator,
    summary: doc.summary,
    timestamp: doc.timestamp || new Date()
  })
}, { immediate: true })

// 监听 sessionId 变化，切换会话时清空文档列表
watch(() => props.sessionId, (newSessionId, oldSessionId) => {
  if (newSessionId && newSessionId !== oldSessionId) {
    // 如果store中没有新的office document，说明是切换到空会话，需要清空
    // 如果store中有新的office document，会在lastOfficeDocument的watch中处理，这里不清空
    if (!reactStore.lastOfficeDocument) {
      officeDocuments.value = []
      editHistory.value = []
      showHistory.value = false
      isEditMode.value = false
    }
  }
})

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

function getResponseFilename(response, fallback) {
  const contentDisposition = response.headers.get('Content-Disposition')
  if (!contentDisposition) {
    return fallback
  }

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1])
    } catch (error) {
      console.warn('[OfficeDocumentPanel] Failed to decode filename*:', error)
    }
  }

  const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
  if (match?.[1]) {
    return match[1].replace(/['"]/g, '')
  }

  return fallback
}

// Download PDF file
async function downloadPDF(doc) {
  if (!doc.pdf_url) {
    console.error('[OfficeDocumentPanel] PDF URL not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const baseName = doc.file_name
      ? doc.file_name.replace(/\.[^.]+$/, '')
      : 'document'
    const fileName = `${baseName}.pdf`
    const downloadUrl = doc.pdf_id
      ? `/api/office/pdf/${encodeURIComponent(doc.pdf_id)}/download?filename=${encodeURIComponent(fileName)}`
      : doc.pdf_url

    const response = await fetch(downloadUrl)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    console.log('[OfficeDocumentPanel] PDF download started:', fileName)
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

    const fileName = getResponseFilename(response, doc.file_name || 'document.docx')

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

// Download PowerPoint document
async function downloadPPT(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] PPT file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const response = await fetch('/api/office/download-ppt', {
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

    const fileName = getResponseFilename(response, doc.file_name || 'document.pptx')

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    console.log('[OfficeDocumentPanel] PPT download started:', fileName)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] PPT download failed:', error)
  }
}

function getReportId(doc) {
  if (doc.html_id) {
    return doc.html_id
  }
  if (doc.html_url) {
    const match = doc.html_url.match(/\/api\/reports\/([^/]+)\/html/)
    if (match?.[1]) {
      return decodeURIComponent(match[1])
    }
  }
  if (doc.file_path) {
    const normalized = doc.file_path.replace(/\\/g, '/')
    const match = normalized.match(/\/reports\/([^/]+)\/report\.qmd$/)
    if (match?.[1]) {
      return match[1]
    }
  }
  return null
}

function getHtmlArtifactId(doc) {
  if (doc.html_id) {
    return doc.html_id
  }
  if (doc.html_url) {
    const match = doc.html_url.match(/\/api\/html-artifacts\/([^/?#]+)\/html/)
    if (match?.[1]) {
      return decodeURIComponent(match[1])
    }
  }
  if (doc.file_path) {
    const normalized = doc.file_path.replace(/\\/g, '/')
    const match = normalized.match(/\/html_artifacts\/([^/]+)\/index\.html$/)
    if (match?.[1]) {
      return match[1]
    }
  }
  return null
}

async function ensureReportFormat(reportId, format) {
  if (format !== 'docx') {
    return
  }

  const response = await fetch(`/api/reports/${encodeURIComponent(reportId)}/render/${format}`, {
    method: 'POST'
  })
  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.json()
      detail = payload.detail || payload.message || ''
    } catch (error) {
      detail = await response.text()
    }
    throw new Error(detail || `生成 ${format.toUpperCase()} 失败`)
  }
}

async function downloadReportFormat(doc, format) {
  const reportId = getReportId(doc)
  if (!reportId) {
    console.error('[OfficeDocumentPanel] Report ID not available')
    showDownloadMenu.value = false
    return
  }

  try {
    await ensureReportFormat(reportId, format)

    const response = await fetch(`/api/reports/${encodeURIComponent(reportId)}/download/${format}`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const fallbackNames = {
      qmd: 'report.qmd',
      docx: 'report.docx'
    }
    const fileName = getResponseFilename(response, fallbackNames[format] || `report.${format}`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    console.log('[OfficeDocumentPanel] Report download started:', reportId, format)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Report download failed:', error)
    alert(`下载报告失败：${error.message}`)
  }
}

async function downloadHtmlArtifact(doc) {
  const artifactId = getHtmlArtifactId(doc)
  if (!artifactId) {
    console.error('[OfficeDocumentPanel] HTML artifact ID not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const response = await fetch(`/api/html-artifacts/${encodeURIComponent(artifactId)}/download/html`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const fileName = getResponseFilename(response, 'index.html')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] HTML artifact download failed:', error)
    alert(`下载HTML展示页失败：${error.message}`)
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

function getDocType(generator, markdownPreview, htmlPreview, filePath, fileType) {
  const explicitType = fileType || htmlPreview?.file_type
  if (explicitType === 'html_artifact') {
    return 'html_artifact'
  }
  if (['report', 'html_report', 'quarto_report'].includes(explicitType)) {
    return 'report'
  }
  if (explicitType === 'notebook') {
    return 'notebook'
  }

  // 先根据 generator 判断
  if (generator === 'quarto_report' || filePath?.endsWith('report.qmd')) {
    return 'report'
  } else if (generator === 'create_html_artifact' || filePath?.includes('/html_artifacts/')) {
    return 'html_artifact'
  } else if (['word_edit', 'find_replace_word', 'accept_word_changes'].includes(generator)) {
    return 'word'
  } else if (['add_ppt_slide'].includes(generator)) {
    return 'ppt'
  } else if (filePath?.endsWith('.ipynb')) {
    return 'notebook'
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
    } else if (['md', 'markdown', 'qmd'].includes(ext)) {
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
    // 检查是否有有效的预览数据（PDF、Markdown或HTML）
    if ((!doc.pdf_preview && !doc.markdown_preview && !doc.html_preview) || !doc.file_path) {
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
        doc_type: getDocType(doc.generator, doc.markdown_preview, doc.html_preview, filePath, doc.file_type),
        file_name: fileName,
        file_path: filePath,
        pdf_url: doc.pdf_preview?.pdf_url,
        pdf_id: doc.pdf_preview?.pdf_id,
        html_url: withPreviewVersion(doc.html_preview?.html_url, doc.html_preview?.preview_version),
        html_id: doc.html_preview?.html_id,
        preview_version: doc.html_preview?.preview_version,
        markdown_content: doc.markdown_preview?.content,
        loading: false,
        sharing: false,
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

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

function showShareToast({ type = 'success', title, message = '', link = '', duration = 5200 }) {
  if (shareToastTimer) {
    clearTimeout(shareToastTimer)
  }

  shareToast.value = {
    visible: true,
    type,
    title,
    message,
    link
  }

  if (duration > 0) {
    shareToastTimer = setTimeout(() => {
      hideShareToast()
    }, duration)
  }
}

function hideShareToast() {
  if (shareToastTimer) {
    clearTimeout(shareToastTimer)
    shareToastTimer = null
  }
  shareToast.value.visible = false
}

async function showGeneratedShareLink(shareLink) {
  try {
    await copyTextToClipboard(shareLink)
    showShareToast({
      type: 'success',
      title: '分享链接已生成',
      message: '链接已自动复制到剪贴板。',
      link: shareLink
    })
  } catch (error) {
    console.warn('[OfficeDocumentPanel] 分享链接复制失败:', error)
    showShareToast({
      type: 'warning',
      title: '分享链接已生成',
      message: '自动复制失败，可在这里手动复制。',
      link: shareLink,
      duration: 0
    })
  }
}

async function copyShareToastLink() {
  if (!shareToast.value.link) {
    return
  }

  try {
    await copyTextToClipboard(shareToast.value.link)
    showShareToast({
      type: 'success',
      title: '链接已复制',
      message: '分享链接已复制到剪贴板。',
      link: shareToast.value.link
    })
  } catch (error) {
    console.warn('[OfficeDocumentPanel] 手动复制分享链接失败:', error)
    showShareToast({
      type: 'warning',
      title: '复制失败',
      message: '请选中链接后手动复制。',
      link: shareToast.value.link,
      duration: 0
    })
  }
}

// 处理Quarto报告分享
async function handleReportShare(doc) {
  const reportId = getReportId(doc)
  if (!reportId) {
    showShareToast({
      type: 'error',
      title: '无法分享',
      message: '缺少报告ID。'
    })
    return
  }

  doc.sharing = true

  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(reportId)}/share/html`, {
      method: 'POST'
    })
    const result = await response.json()

    if (!response.ok || !result.success) {
      throw new Error(result.detail || '生成分享链接失败')
    }

    const shareLink = `${window.location.origin}${result.share_url}`
    await showGeneratedShareLink(shareLink)
  } catch (error) {
    console.error('[OfficeDocumentPanel] 生成报告分享链接失败:', error)
    showShareToast({
      type: 'error',
      title: '生成分享链接失败',
      message: error.message
    })
  } finally {
    doc.sharing = false
  }
}

// 处理HTML展示页分享
async function handleHtmlArtifactShare(doc) {
  const artifactId = getHtmlArtifactId(doc)
  if (!artifactId) {
    showShareToast({
      type: 'error',
      title: '无法分享',
      message: '缺少HTML展示页ID。'
    })
    return
  }

  doc.sharing = true

  try {
    const response = await fetch(`/api/html-artifacts/${encodeURIComponent(artifactId)}/share`, {
      method: 'POST'
    })
    const result = await response.json()

    if (!response.ok || !result.success) {
      throw new Error(result.detail || '生成分享链接失败')
    }

    const shareLink = `${window.location.origin}${result.share_url}`
    await showGeneratedShareLink(shareLink)
  } catch (error) {
    console.error('[OfficeDocumentPanel] 生成HTML展示页分享链接失败:', error)
    showShareToast({
      type: 'error',
      title: '生成分享链接失败',
      message: error.message
    })
  } finally {
    doc.sharing = false
  }
}

// 处理Notebook分享
async function handleNotebookShare(doc) {
  if (!doc.file_path) {
    showShareToast({
      type: 'error',
      title: '无法分享',
      message: '缺少Notebook文件路径。'
    })
    return
  }

  doc.sharing = true

  try {
    // 调用后端API生成分享HTML
    const response = await fetch('/api/tools/execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        tool: 'generate_shareable_notebook',
        parameters: {
          notebook_path: doc.file_path
        }
      })
    })

    const result = await response.json()

    if (result.success) {
      const shareLink = result.data.share_link
      await showGeneratedShareLink(shareLink)
    } else {
      showShareToast({
        type: 'error',
        title: '生成分享链接失败',
        message: result.summary || '未知错误'
      })
    }
  } catch (error) {
    console.error('[OfficeDocumentPanel] 生成分享链接失败:', error)
    showShareToast({
      type: 'error',
      title: '生成分享链接失败',
      message: error.message
    })
  } finally {
    doc.sharing = false
  }
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
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.doc-list {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 0;
}

.doc-item {
  border: none;
  padding: 0;
  background: #fff;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.doc-preview {
  margin: 0;
  border: none;
  min-height: 720px;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 6px 12px;
  border: 1px solid #d8deea;
  background: rgba(255, 255, 255, 0.94);
  color: #526173;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(31, 45, 68, 0.12);
  white-space: nowrap;

  &:hover {
    color: #1976d2;
    border-color: #90caf9;
    background: #fff;
    box-shadow: 0 6px 16px rgba(31, 45, 68, 0.16);
  }
}

.btn-icon {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: 0 0 auto;
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
  border: 1px solid #d8deea;
  border-radius: 8px;
  box-shadow: 0 8px 22px rgba(31, 45, 68, 0.16);
  min-width: 168px;
  z-index: 100;
  overflow: hidden;
}

.download-item {
  width: 100%;
  padding: 10px 14px;
  border: none;
  background: white;
  text-align: left;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #526173;

  &:hover:not(:disabled) {
    background: #f8fbff;
    color: #1976d2;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &:not(:last-child) {
    border-bottom: 1px solid #f0f0f0;
  }
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

.notebook-wrapper {
  width: 100%;
  flex: 1;
  min-height: 600px;
  display: flex;
  flex-direction: column;
}

.notebook-iframe {
  width: 100%;
  flex: 1;
  border: none;
  display: block;
}

.notebook-with-share {
  padding: 20px;
  text-align: center;
  background: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin: 12px;
}

.notebook-actions {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
}

.notebook-placeholder {
  padding: 40px 20px;
  background: white;
  border-radius: 8px;
  border: 2px dashed #e0e0e0;
}

.notebook-placeholder p {
  margin: 10px 0;
  color: #666;
  font-size: 14px;
}

.notebook-placeholder .hint {
  color: #999;
  font-size: 13px;
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
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8a96a8;
  padding: 40px 20px;
  text-align: center;
}

.empty-title { font-size: 15px; font-weight: 500; color: #526173; margin: 0; }
.empty-tip { font-size: 13px; margin: 0; line-height: 1.6; color: #8a96a8; }

.share-toast {
  position: absolute;
  top: 56px;
  right: 12px;
  z-index: 120;
  display: grid;
  grid-template-columns: 4px minmax(0, 1fr) auto;
  gap: 12px;
  width: min(420px, calc(100% - 24px));
  padding: 12px;
  border: 1px solid #d8deea;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 14px 38px rgba(31, 45, 68, 0.18);
  color: #243044;
}

.share-toast.success .share-toast-indicator { background: #19a06b; }
.share-toast.warning .share-toast-indicator { background: #d08a00; }
.share-toast.error .share-toast-indicator { background: #d14343; }

.share-toast-indicator {
  width: 4px;
  border-radius: 999px;
}

.share-toast-content {
  min-width: 0;
}

.share-toast-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.share-toast-message {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: #5e6b7c;
}

.share-toast-link {
  margin-top: 8px;
  padding: 7px 9px;
  border: 1px solid #e3e8f2;
  border-radius: 6px;
  background: #f7f9fc;
  color: #2c5f9e;
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-toast-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.share-toast-actions button,
.share-toast-actions a,
.share-toast-close {
  border: 1px solid #d8deea;
  background: #fff;
  color: #526173;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.share-toast-actions button,
.share-toast-actions a {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 5px 10px;
  text-decoration: none;
}

.share-toast-actions button:hover,
.share-toast-actions a:hover,
.share-toast-close:hover {
  color: #1976d2;
  border-color: #90caf9;
  background: #f8fbff;
}

.share-toast-close {
  width: 26px;
  height: 26px;
  padding: 0;
  line-height: 1;
}

.share-toast-enter-active,
.share-toast-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.share-toast-enter-from,
.share-toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
