<template>
  <div class="office-panel" :class="{ 'has-content': hasOfficeDocuments, 'expanded': isExpanded }">
    <!-- Empty state -->
    <div v-if="!hasOfficeDocuments || officeDocuments.length === 0" class="empty-state">
      <p class="empty-title">暂无文档</p>
      <p class="empty-tip">触发文件预览后，将在此处显示预览</p>
    </div>

    <!-- Panel content -->
    <template v-else>
      <!-- Active document preview -->
      <div class="doc-list">
        <div v-for="doc in activeDocumentList" :key="getDocumentKey(doc)" class="doc-item">
          <!-- Preview mode: PDF preview (with transition animation) -->
          <div v-if="!isEditMode" class="doc-preview">
            <!-- Action buttons in top-right corner -->
            <div v-if="!isExcelDoc(doc)" class="action-buttons">
              <button
                v-if="isEditableDoc(doc)"
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
                  <button v-if="doc.doc_type === 'html_artifact' && !isDiagramDocument(doc)" @click="downloadHtmlArtifact(doc)" class="download-item">
                    下载 HTML 文件
                  </button>
                  <button
                    v-for="file in getRelatedDownloadFiles(doc)"
                    :key="file.key"
                    @click="downloadRelatedFile(file)"
                    class="download-item"
                  >
                    {{ getRelatedDownloadLabel(file) }}
                  </button>
                  <button v-if="doc.file_path && doc.generator === 'present_artifact'" @click="downloadOriginalFile(doc)" class="download-item">
                    下载原文件
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

            <!-- Excel preview/edit surface -->
            <div v-if="isExcelDoc(doc)" class="excel-wrapper">
              <ExcelOnlineEditor
                :doc="doc"
                :session-id="props.sessionId"
                @saved="handleOfficeDocumentSaved"
              />
            </div>

            <!-- Loading state -->
            <div v-else-if="doc.loading" class="preview-loading">
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

            <!-- Native presentation preview -->
            <div v-else-if="doc.ppt_preview" class="ppt-wrapper">
              <div v-if="getPptPages(doc).length > 0" class="ppt-preview-content">
                <div class="ppt-toolbar">
                  <button
                    type="button"
                    class="ppt-nav-btn"
                    :disabled="presentationPageIndex <= 0"
                    @click="changePresentationPage(doc, -1)"
                  >
                    上一页
                  </button>
                  <span class="ppt-page-count">
                    {{ presentationPageIndex + 1 }} / {{ getPptPages(doc).length }}
                  </span>
                  <button
                    type="button"
                    class="ppt-nav-btn"
                    :disabled="presentationPageIndex >= getPptPages(doc).length - 1"
                    @click="changePresentationPage(doc, 1)"
                  >
                    下一页
                  </button>
                </div>
                <div class="ppt-slide-stage">
                  <img
                    v-if="getActivePptPage(doc)?.image_url"
                    :src="getActivePptPage(doc).image_url"
                    :alt="`幻灯片 ${getActivePptPage(doc).slide || presentationPageIndex + 1}`"
                    class="ppt-slide-image"
                    @load="onPdfLoaded(doc)"
                  />
                  <p v-else class="ppt-slide-error">当前幻灯片缺少预览图片</p>
                </div>
              </div>
              <div v-else class="preview-error">
                <p>演示文稿没有可用的分页预览</p>
              </div>
            </div>

            <!-- HTML/Image preview (iframe displays HTML pages and browser-renderable media URLs) -->
            <div v-else-if="doc.html_url" class="html-wrapper">
              <iframe
                :src="doc.html_url"
                :key="doc.html_url"
                class="html-iframe"
                type="text/html"
                @load="onPdfLoaded(doc)"
              ></iframe>
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

          <!-- Edit mode: DOCX online editor -->
          <div v-else class="doc-edit">
            <DocxOnlineEditor
              :doc="doc"
              :session-id="props.sessionId"
              @cancel="cancelEditMode"
              @saved="handleDocxSaved"
            />
          </div>
        </div>
      </div>

      <!-- File history (默认隐藏) -->
      <div class="file-history-section">
        <div class="file-history-header" @click="toggleFileHistory">
          <span class="section-title">文件历史</span>
          <span class="history-toggle-icon">{{ showFileHistory ? '▼' : '▶' }}</span>
        </div>
        <div v-if="showFileHistory" class="history-list">
          <button
            v-for="doc in fileHistory"
            :key="getDocumentKey(doc)"
            type="button"
            class="history-item file-history-item"
            :class="{ active: getDocumentKey(doc) === activeDocumentId }"
            @click="selectDocument(doc)"
          >
            <span class="history-icon">{{ getDocIcon(doc.doc_type) }}</span>
            <span class="history-text">
              <span class="history-file-name">{{ doc.file_name || getFileName(doc.file_path) }}</span>
              <span v-if="doc.last_action?.summary" class="history-file-summary">{{ doc.last_action.summary }}</span>
            </span>
            <span class="history-time">{{ formatTime(doc.last_action?.timestamp || doc.timestamp) }}</span>
          </button>
          <div v-if="fileHistory.length === 0" class="history-empty">
            暂无文件历史
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
import { authFetch } from '@/auth/http.js'
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import DocxOnlineEditor from '@/components/DocxOnlineEditor.vue'
import ExcelOnlineEditor from '@/components/ExcelOnlineEditor.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { normalizeArtifactUrl, normalizeRelatedArtifactFiles } from '@/utils/artifactRelatedFiles'
import { getPresentationPreviewPages } from '@/services/sessionDocumentResources.js'

const reactStore = useReactStore()

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
const showFileHistory = ref(false)
const showDownloadMenu = ref(false)
const activeDocumentId = ref(null)
const presentationPageIndex = ref(0)
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

const officeDocuments = computed(() => {
  return (reactStore.officeDocumentHistory || [])
    .filter(doc => doc?.pdf_preview || doc?.markdown_preview || doc?.html_preview || doc?.svg_preview || doc?.spreadsheet_preview || doc?.ppt_preview || doc?.pdf_url || doc?.html_url || doc?.svg_url || doc?.markdown_content || isExcelPath(doc?.file_path || doc?.path || doc?.file_name))
    .map(normalizeDocument)
})

const activeDocument = computed(() => {
  if (officeDocuments.value.length === 0) {
    return null
  }
  return officeDocuments.value.find(doc => getDocumentKey(doc) === activeDocumentId.value)
    || officeDocuments.value.find(doc => doc.is_current)
    || officeDocuments.value[officeDocuments.value.length - 1]
})

const activeDocumentList = computed(() => {
  return activeDocument.value ? [activeDocument.value] : []
})

const fileHistory = computed(() => {
  return officeDocuments.value.slice().reverse()
})

function getDocumentKey(doc) {
  return doc?.version_id || doc?.pdf_id || doc?.html_id || doc?.file_path || doc?.svg_url || doc?.file_name || ''
}

function getDocumentSignature(doc) {
  if (!doc) return ''
  return [
    getDocumentKey(doc),
    doc.html_url,
    doc.svg_url,
    doc.pdf_url,
    doc.preview_version,
    doc.timestamp
  ].filter(Boolean).join('|')
}

function selectDocument(doc) {
  const key = getDocumentKey(doc)
  if (!key) return
  activeDocumentId.value = key
  presentationPageIndex.value = 0
  isEditMode.value = false
  showDownloadMenu.value = false
}

function normalizeDocument(doc) {
  const filePath = doc.file_path || doc.path || doc.pdf_preview?.pdf_path || doc.svg_preview?.svg_path
  const fileName = doc.file_name || (filePath ? filePath.split(/[/\\]/).pop() : 'unknown')
  const svgPreviewUrl = getSvgPreviewUrl(doc)
  const htmlPreviewUrl = doc.html_url || withPreviewVersion(doc.html_preview?.html_url, doc.html_preview?.preview_version) || svgPreviewUrl
  const pptPreview = doc.ppt_preview
    ? {
        ...doc.ppt_preview,
        pages: getPresentationPreviewPages(doc.ppt_preview).map(page => ({
          ...page,
          image_url: normalizeArtifactUrl(page.image_url)
        }))
      }
    : undefined
  return {
    doc_type: doc.doc_type || getDocType(doc.generator, doc.markdown_preview, doc.html_preview, filePath, doc.file_type || doc.svg_preview?.file_type),
    document_id: doc.document_id,
    version_id: doc.version_id,
    revision: doc.revision,
    is_current: doc.is_current,
    file_name: fileName,
    file_path: filePath,
    generator: doc.generator,
    pdf_url: normalizeArtifactUrl(doc.pdf_url || doc.pdf_preview?.pdf_url),
    pdf_id: doc.pdf_id || doc.pdf_preview?.pdf_id,
    spreadsheet_preview: doc.spreadsheet_preview,
    ppt_preview: pptPreview,
    html_url: normalizeArtifactUrl(htmlPreviewUrl),
    html_id: doc.html_id || doc.html_preview?.html_id,
    svg_url: normalizeArtifactUrl(svgPreviewUrl),
    svg_preview: doc.svg_preview,
    preview_version: doc.preview_version || doc.html_preview?.preview_version,
    related_files: doc.related_files,
    artifacts: doc.artifacts,
    refs: doc.refs,
    assets: doc.assets,
    metadata: doc.metadata,
    markdown_content: doc.markdown_content || doc.markdown_preview?.content,
    loading: doc.loading || false,
    sharing: doc.sharing || false,
    editContent: doc.editContent || '',
    submitting: doc.submitting || false,
    editMessage: doc.editMessage || null,
    timestamp: doc.timestamp,
    last_action: doc.last_action || {
      tool: doc.generator,
      summary: doc.summary,
      timestamp: doc.timestamp || new Date()
    }
  }
}

function getPptPages(doc) {
  return Array.isArray(doc?.ppt_preview?.pages) ? doc.ppt_preview.pages : []
}

function getActivePptPage(doc) {
  const pages = getPptPages(doc)
  if (pages.length === 0) return null
  const index = Math.min(Math.max(presentationPageIndex.value, 0), pages.length - 1)
  return pages[index]
}

function changePresentationPage(doc, delta) {
  const pages = getPptPages(doc)
  if (pages.length === 0) return
  presentationPageIndex.value = Math.min(
    Math.max(presentationPageIndex.value + delta, 0),
    pages.length - 1
  )
}

function getSvgPreviewUrl(doc) {
  const directUrl = doc.svg_url || doc.svg_preview?.svg_url
  if (directUrl) {
    return directUrl
  }

  const svgFile = getRelatedDownloadFiles(doc).find(file => {
    const format = String(file.format || '').toLowerCase()
    return format === 'svg' || format === 'drawio_svg'
  })

  return svgFile?.url || ''
}

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

watch(officeDocuments, (docs, oldDocs = []) => {
  if (docs.length === 0) {
    activeDocumentId.value = null
    presentationPageIndex.value = 0
    return
  }
  const latestDoc = docs[docs.length - 1]
  const previousLatestDoc = oldDocs[oldDocs.length - 1]
  const latestChanged = getDocumentSignature(latestDoc) !== getDocumentSignature(previousLatestDoc)
  const activeStillExists = docs.some(doc => getDocumentKey(doc) === activeDocumentId.value)
  if (!activeStillExists || docs.length > oldDocs.length || latestChanged) {
    activeDocumentId.value = getDocumentKey(latestDoc)
    presentationPageIndex.value = 0
  }
}, { immediate: true })

// 监听 sessionId 变化，切换会话时清空文档列表
watch(() => props.sessionId, (newSessionId, oldSessionId) => {
  if (newSessionId && newSessionId !== oldSessionId) {
    // 如果store中没有新的office document，说明是切换到空会话，需要清空
    // 如果store中有新的office document，会在lastOfficeDocument的watch中处理，这里不清空
    if (!reactStore.lastOfficeDocument) {
      activeDocumentId.value = null
      presentationPageIndex.value = 0
      showFileHistory.value = false
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

function cancelEditMode() {
  isEditMode.value = false
}

function cancelEdit() {
  cancelEditMode()
}

function handleDocxSaved(document) {
  handleOfficeDocumentSaved(document)
}

function handleOfficeDocumentSaved(document) {
  reactStore.recordOfficeDocument(document)
  activeDocumentId.value = getDocumentKey(document)
  isEditMode.value = false
  showDownloadMenu.value = false
}

// Toggle download menu
function toggleDownloadMenu() {
  showDownloadMenu.value = !showDownloadMenu.value
}

function isEditableDoc(doc) {
  if (doc.generator === 'present_artifact' || ['report', 'html_artifact'].includes(doc.doc_type)) {
    return false
  }
  const filePath = String(doc.file_path || doc.file_name || '').toLowerCase()
  return doc.doc_type === 'word' && filePath.endsWith('.docx')
}

function isExcelDoc(doc) {
  return doc?.doc_type === 'excel' || isExcelPath(doc?.file_path || doc?.file_name)
}

function isExcelPath(path) {
  return /\.(xlsx|xls)$/i.test(String(path || ''))
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

    const response = await authFetch(downloadUrl)
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
    const response = await authFetch('/api/office/download-word', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: doc.file_path,
        file_name: doc.file_name || 'document.docx'
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
    const response = await authFetch('/api/office/download-ppt', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: doc.file_path,
        file_name: doc.file_name || 'document.pptx'
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

  const response = await authFetch(`/api/reports/${encodeURIComponent(reportId)}/render/${format}`, {
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

    const response = await authFetch(`/api/reports/${encodeURIComponent(reportId)}/download/${format}`)
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
    const response = await authFetch(`/api/html-artifacts/${encodeURIComponent(artifactId)}/download/html`)
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

function getRelatedDownloadFiles(doc) {
  return normalizeRelatedArtifactFiles({
    artifact: {
      related_files: doc.related_files,
      artifacts: doc.artifacts,
      assets: doc.assets
    },
    refs: doc.refs
  })
}

function getRelatedDownloadLabel(file) {
  const format = String(file.format || '').toLowerCase()
  if (format === 'drawio') return '下载 Draw.io 源文件（可继续编辑）'
  if (format === 'drawio_svg' || format === 'svg') return '下载 SVG 矢量图'
  if (format === 'png') return '下载 PNG 图片'
  return file.downloadLabel || '下载附件'
}

function isDiagramDocument(doc) {
  return doc?.generator === 'create_diagram_artifact' ||
    doc?.metadata?.artifact_kind === 'diagram' ||
    doc?.refs?.drawio ||
    getRelatedDownloadFiles(doc).some(file => file.format === 'drawio')
}

function downloadRelatedFile(file) {
  if (!file?.file_path && !file?.url) {
    console.error('[OfficeDocumentPanel] Related file not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const fileUrl = normalizeArtifactUrl(file.url || `/api/file/${encodeURIComponent(file.file_path)}`)
    const link = document.createElement('a')
    link.href = fileUrl
    link.download = file.file_path?.replace(/\\/g, '/').split('/').pop() || file.downloadLabel || 'artifact'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Related file download failed:', error)
  }
}

function downloadOriginalFile(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] Original file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const fileUrl = normalizeArtifactUrl(`/api/file/${encodeURIComponent(doc.file_path)}`)
    const link = document.createElement('a')
    link.href = fileUrl
    link.download = doc.file_name || 'artifact'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Original file download failed:', error)
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
    const fileUrl = normalizeArtifactUrl(`/api/file/${encodeURIComponent(doc.file_path)}`)

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
async function downloadExcel(doc) {
  if (!doc.file_path || doc.file_path === '') {
    console.error('[OfficeDocumentPanel] Excel file path not available')
    showDownloadMenu.value = false
    return
  }

  try {
    const response = await authFetch('/api/office/download-excel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: doc.file_path,
        file_name: doc.file_name || 'document.xlsx'
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const fileName = getResponseFilename(response, doc.file_name || 'document.xlsx')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    console.log('[OfficeDocumentPanel] Excel download started:', fileName)
    showDownloadMenu.value = false
  } catch (error) {
    console.error('[OfficeDocumentPanel] Excel download failed:', error)
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
  if (['html', 'image'].includes(explicitType)) {
    return explicitType
  }
  if (explicitType === 'pdf') {
    return 'pdf'
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
    } else if (['html', 'htm'].includes(ext)) {
      return 'html'
    } else if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) {
      return 'image'
    } else if (ext === 'pdf') {
      return 'pdf'
    }
  }

  return 'unknown'
}

function getDocIcon(docType) {
  const icons = { word: '📝', ppt: '📊', excel: '📈', unknown: '📄' }
  return icons[docType] || icons.unknown
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function toggleFileHistory() {
  showFileHistory.value = !showFileHistory.value
}

// 【新增】从历史数据加载文档列表（用于历史对话恢复）
function loadDocuments(documents) {
  if (!documents || !Array.isArray(documents) || documents.length === 0) {
    console.log('[OfficeDocumentPanel] 无历史文档需要加载')
    return
  }

  console.log('[OfficeDocumentPanel] 开始加载历史文档，数量:', documents.length)

  if (typeof reactStore.setOfficeDocumentHistory === 'function') {
    reactStore.setOfficeDocumentHistory(documents)
  }

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
    const response = await authFetch(`/api/reports/${encodeURIComponent(reportId)}/share/html`, {
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
    const response = await authFetch(`/api/html-artifacts/${encodeURIComponent(artifactId)}/share`, {
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

.excel-wrapper {
  width: 100%;
  flex: 1;
  min-height: 720px;
  box-sizing: border-box;
}

.pdf-iframe {
  width: 100%;
  height: 750px;
  border: none;
  transition: height 0.3s ease;
}

.ppt-wrapper {
  width: 100%;
  min-height: 600px;
  background: #eef1f5;
}

.ppt-preview-content {
  min-height: 600px;
  display: flex;
  flex-direction: column;
}

.ppt-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 10px 12px;
  background: #fff;
  border-bottom: 1px solid #e5e9ef;
}

.ppt-nav-btn {
  padding: 6px 14px;
  border: 1px solid #d9e0e8;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  cursor: pointer;

  &:hover:not(:disabled) {
    border-color: #1976d2;
    color: #1976d2;
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

.ppt-page-count {
  min-width: 72px;
  text-align: center;
  color: #526173;
  font-size: 13px;
}

.ppt-slide-stage {
  flex: 1;
  min-height: 540px;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

.ppt-slide-image {
  display: block;
  max-width: 100%;
  max-height: calc(100vh - 170px);
  object-fit: contain;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.14);
}

.ppt-slide-error {
  color: #8a94a3;
}

.html-wrapper {
  width: 100%;
  flex: 1;
  min-height: 600px;
  display: flex;
  flex-direction: column;
}

.html-iframe {
  width: 100%;
  flex: 1;
  border: none;
  display: block;
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
  height: calc(100vh - 100px);
  min-height: 560px;
  overflow: hidden;
}

.file-history-section {
  padding: 12px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.file-history-header {
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
  border: 1px solid transparent;
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
  width: 100%;

  &:hover {
    background: #f8fbff;
    border-color: #d8e8fb;
  }

  &.active {
    background: #eef6ff;
    border-color: #90caf9;
  }
}

.history-empty {
  padding: 12px;
  text-align: center;
  color: #999;
  font-size: 12px;
}

.history-icon { flex: 0 0 auto; font-size: 14px; }
.history-text { display: flex; flex: 1; flex-direction: column; min-width: 0; color: #333; }
.history-file-name,
.history-file-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-file-summary { margin-top: 2px; color: #7b8796; font-size: 11px; }
.history-time { flex: 0 0 auto; color: #999; font-size: 11px; }

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
