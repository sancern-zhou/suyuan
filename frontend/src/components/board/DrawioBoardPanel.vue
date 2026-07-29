<template>
  <div class="drawio-board-panel">
    <div class="board-toolbar">
      <div class="board-title" :title="title || '画板'">{{ title || '画板' }}</div>
      <div class="board-actions">
        <button type="button" class="board-btn" @click="reloadXml">重新加载</button>
        <button
          type="button"
          class="board-btn"
          :disabled="exportingSnapshot"
          @click="downloadBoardImage"
        >
          导出图片
        </button>
        <button
          type="button"
          class="board-btn"
          :disabled="exportingSnapshot"
          @click="confirmBoardSnapshot"
        >
          {{ exportingSnapshot ? '正在附图...' : '对话附图' }}
        </button>
        <button type="button" class="board-btn" @click="downloadDrawio">下载 Draw.io</button>
      </div>
    </div>

    <div class="drawio-canvas-shell">
      <iframe
        :key="editorInstanceKey"
        ref="iframeRef"
        class="drawio-frame"
        :src="drawioUrl"
        title="Draw.io board"
      ></iframe>
      <div v-if="readOnly" class="board-readonly-overlay" role="status">
        Agent 正在处理画板，当前暂不可编辑
      </div>
    </div>

    <div class="file-history-section">
      <button type="button" class="file-history-header" @click="showVersionFiles = !showVersionFiles">
        <span class="section-title">版本文件</span>
        <span class="history-toggle-icon">{{ showVersionFiles ? '▼' : '▶' }}</span>
      </button>
      <div v-if="showVersionFiles" class="history-list">
        <div v-if="boardDirty" class="history-dirty">
          当前画布有手动修改，后续 AI 将基于当前画布内容。
        </div>
        <button
          v-for="version in acceptedVersions"
          :key="getVersionKey(version)"
          type="button"
          class="history-item file-history-item"
          :class="{ current: getVersionKey(version) === displayedVersionId }"
          :disabled="previewLoading"
          @click="previewVersion(version)"
        >
          <span class="history-icon">◇</span>
          <span class="history-text">
            <span class="history-file-name">{{ getVersionName(version) }}</span>
            <span class="history-file-summary">{{ getVersionSummary(version) }}</span>
          </span>
          <span class="history-time">{{ formatTime(version.created_at || version.createdAt) }}</span>
        </button>
        <div v-if="previewError" class="history-error" role="alert">
          {{ previewError }}
        </div>
        <div v-if="acceptedVersions.length === 0" class="history-empty">
          暂无版本文件
        </div>
        <button
          v-if="qualityAttempts.length > 0"
          type="button"
          class="quality-attempts-toggle"
          @click="showQualityAttempts = !showQualityAttempts"
        >
          {{ showQualityAttempts ? '收起' : '查看' }}质量核查过程（{{ qualityAttempts.length }}）
        </button>
        <div v-if="showQualityAttempts" class="quality-attempts">
          <div
            v-for="version in qualityAttempts"
            :key="getVersionKey(version)"
            class="quality-attempt"
          >
            <AuthenticatedImage
              v-if="version.screenshotUrl"
              :source="version.screenshotUrl"
              :alt="`${getVersionName(version)} 核查截图`"
              class="quality-thumbnail"
            />
            <div class="quality-attempt-body">
              <span>{{ getVersionName(version) }}</span>
              <span class="quality-status" :class="`status-${version.qualityStatus || 'pending'}`">
                {{ getQualityLabel(version) }}
              </span>
              <span class="quality-summary">{{ getQualitySummary(version) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AuthenticatedImage from '@/components/AuthenticatedImage.vue'
import { loadBoardVersionXml } from '@/api/board.js'
import {
  getDrawioSelectionPayload,
  getDrawioSelectionPayloadFromExport,
  parseDrawioSelectedCells
} from './drawioSelection.js'
import {
  BoardSyncError,
  createDrawioBoardBridge,
  createDrawioBoardLoader,
  registerActiveDrawioBoardExporter
} from './drawioBoardBridge.js'

const props = defineProps({
  boardId: {
    type: String,
    default: ''
  },
  xml: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    default: ''
  },
  versionFiles: {
    type: Array,
    default: () => []
  },
  currentVersionId: {
    type: String,
    default: null
  },
  boardDirty: {
    type: Boolean,
    default: false
  },
  readOnly: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['xml-change', 'selection-change', 'board-snapshot-confirm'])

const iframeRef = ref(null)
const iframeReady = ref(false)
const editorInstanceKey = ref(0)
const latestXml = ref(props.xml || '')
const previewVersionId = ref('')
const previewXml = ref('')
const previewSelection = ref([])
const previewLoading = ref(false)
const previewError = ref('')
const exportingSnapshot = ref(false)
const showVersionFiles = ref(false)
const showQualityAttempts = ref(false)
let pendingExportResolver = null
let selectionProbeInterval = null
let selectionProbePending = false
let xmlSyncPending = false
let xmlSyncTimeout = null
let lastXmlSyncAt = 0
let unregisterBoardExporter = null
let previewRequestId = 0
let editorLoadPromise = null
let pendingEditorRestart = null

const XML_SYNC_INTERVAL_MS = 1200
const DRAWIO_URL = 'https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&modified=0&saveAndExit=0&noSaveBtn=1&noExitBtn=1'
const DRAWIO_ORIGIN = new URL(DRAWIO_URL).origin

const drawioUrl = computed(() => DRAWIO_URL)
const acceptedVersions = computed(() => props.versionFiles.filter(version => (
  version.visibleInHistory !== false &&
  (version.lifecycleStatus || version.lifecycle_status || 'accepted') === 'accepted'
)))
const qualityAttempts = computed(() => props.versionFiles.filter(version => (
  (version.lifecycleStatus || version.lifecycle_status) !== 'accepted'
)))
const displayedVersionId = computed(() => previewVersionId.value || String(props.currentVersionId || ''))

const boardBridge = createDrawioBoardBridge({
  getTargetWindow: () => iframeRef.value?.contentWindow || null,
  allowedOrigin: DRAWIO_ORIGIN
})

const boardLoader = createDrawioBoardLoader({
  getTargetWindow: () => iframeRef.value?.contentWindow || null,
  allowedOrigin: DRAWIO_ORIGIN
})

const postDrawio = (action, extra = {}) => {
  const target = iframeRef.value?.contentWindow
  if (!target) return
  target.postMessage(JSON.stringify({ action, ...extra }), DRAWIO_ORIGIN)
}

const applySelection = (selection, source = 'unknown') => {
  console.log('[drawio-board] selection updated from editor', {
    source,
    selectedCount: selection.length,
    selectedIds: selection.map((cell) => cell.id).filter(Boolean)
  })
  if (previewVersionId.value) {
    previewSelection.value = selection
    return
  }
  emit('selection-change', selection)
}

const loadXml = async (xml = previewVersionId.value ? previewXml.value : props.xml, required = false) => {
  if (!xml) return false
  if (!iframeReady.value && required) {
    throw new BoardSyncError('board_editor_not_ready', '画板编辑器尚未就绪')
  }
  if (!iframeReady.value) return false
  const loadRequest = boardLoader.loadXml(xml, { autosave: previewVersionId.value ? 0 : 1 })
  editorLoadPromise = loadRequest
  try {
    await loadRequest
    return true
  } catch (error) {
    if (required) throw error
    if (!['board_load_superseded', 'board_context_changed', 'board_editor_unmounted'].includes(error?.code)) {
      console.error('[drawio-board] failed to load XML into editor', error)
    }
    return false
  } finally {
    if (editorLoadPromise === loadRequest) editorLoadPromise = null
  }
}

const settleEditorRestart = (request, kind, value) => {
  if (pendingEditorRestart !== request) return
  pendingEditorRestart = null
  if (editorLoadPromise === request.promise) editorLoadPromise = null
  request[kind](value)
}

const cancelEditorRestart = (code) => {
  if (!pendingEditorRestart) return
  const request = pendingEditorRestart
  settleEditorRestart(
    request,
    request.required ? 'reject' : 'resolve',
    request.required ? new BoardSyncError(code) : false
  )
}

const restartEditor = (xml, required = false) => {
  boardBridge.cancel('board_editor_restarting')
  boardLoader.cancel('board_editor_restarting')
  cancelEditorRestart('board_load_superseded')
  iframeReady.value = false
  stopSelectionProbe()

  let resolveRequest
  let rejectRequest
  const promise = new Promise((resolve, reject) => {
    resolveRequest = resolve
    rejectRequest = reject
  })
  const request = {
    xml,
    required,
    autosave: previewVersionId.value ? 0 : 1,
    resolve: resolveRequest,
    reject: rejectRequest,
    promise
  }
  pendingEditorRestart = request
  editorLoadPromise = promise
  editorInstanceKey.value += 1
  return promise
}

const reloadXml = () => {
  void restartEditor(previewVersionId.value ? previewXml.value : props.xml)
}

const getVersionKey = (version = {}) => String(version.version_id || version.id || version.versionNumber || version.version_number || '')

const showCurrentVersion = async () => {
  const requestId = ++previewRequestId
  previewVersionId.value = ''
  previewXml.value = ''
  previewSelection.value = []
  previewError.value = ''
  previewLoading.value = true
  latestXml.value = props.xml || ''
  try {
    await restartEditor(props.xml, true)
  } catch (error) {
    if (requestId !== previewRequestId) return
    console.error('[drawio-board] failed to reload current version', error)
    previewError.value = '当前版本加载失败，请稍后重试'
  } finally {
    if (requestId === previewRequestId) previewLoading.value = false
  }
}

const previewVersion = async (version = {}) => {
  const versionId = getVersionKey(version)
  if (!versionId) return
  if (versionId === String(props.currentVersionId || '')) {
    await showCurrentVersion()
    return
  }

  boardBridge.cancel('board_version_preview_started')
  const requestId = ++previewRequestId
  previewLoading.value = true
  previewError.value = ''
  try {
    const xml = await loadBoardVersionXml(props.boardId, versionId, version)
    if (requestId !== previewRequestId) return
    previewVersionId.value = versionId
    previewXml.value = xml
    previewSelection.value = []
    latestXml.value = xml
    stopSelectionProbe()
    await restartEditor(xml, true)
    if (requestId !== previewRequestId) return
  } catch (error) {
    if (requestId !== previewRequestId) return
    console.error('[drawio-board] failed to preview board version', { versionId, error })
    await showCurrentVersion()
    previewError.value = '版本加载失败，请稍后重试'
  } finally {
    if (requestId === previewRequestId) previewLoading.value = false
  }
}

const getVersionName = (version = {}) => {
  return version.file_name || version.fileName || version.downloadLabel || `${version.title || props.title || '画板'} v${version.version_number || version.versionNumber || ''}`.trim()
}

const getVersionSummary = (version = {}) => {
  const sourceLabel = version.source === 'agent' ? 'AI生成' : version.source === 'user_restore' ? '手动恢复' : '版本文件'
  const number = version.version_number || version.versionNumber
  return `${sourceLabel}${number ? ` · v${number}` : ''}`
}

const getQualityLabel = (version = {}) => {
  const labels = { passed: '通过', warning: '有警告', failed: '未通过', pending: '待核查' }
  return labels[version.qualityStatus || version.quality_status] || '待核查'
}

const getQualitySummary = (version = {}) => {
  const report = version.qualityReport || version.quality_report || {}
  const errors = Array.isArray(report.errors) ? report.errors.length : Number(report.error_count || 0)
  const warnings = Array.isArray(report.warnings) ? report.warnings.length : Number(report.warning_count || 0)
  if (!errors && !warnings) return '未发现结构或视觉问题'
  return `${errors} 个错误 · ${warnings} 个警告`
}

const formatTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getActiveXml = () => latestXml.value || props.xml || ''

const sanitizeFileName = (name) => {
  return String(name || 'diagram')
    .replace(/[\\/:*?"<>|]+/g, '_')
    .trim() || 'diagram'
}

const downloadDrawio = () => {
  const blob = new Blob([getActiveXml()], { type: 'application/xml' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${sanitizeFileName(props.title)}.drawio`
  link.click()
  URL.revokeObjectURL(url)
}

const downloadDataUrl = (dataUrl, filename) => {
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = filename
  link.click()
}

const dataUrlToFile = (dataUrl, filename) => {
  if (!dataUrl || typeof dataUrl !== 'string' || !dataUrl.startsWith('data:')) {
    throw new Error('draw.io export did not return a data URL')
  }

  const [meta, data] = dataUrl.split(',')
  const mime = meta.match(/^data:([^;]+);base64$/)?.[1] || 'image/png'
  const bytes = atob(data || '')
  const buffer = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i += 1) {
    buffer[i] = bytes.charCodeAt(i)
  }

  return new File([buffer], filename, { type: mime })
}

const getExportDataUrl = (msg) => {
  const value = msg?.data || msg?.image || msg?.url || ''
  if (typeof value !== 'string') return ''
  if (value.startsWith('data:')) return value
  if (value.startsWith('iVBOR') || value.startsWith('/9j/')) {
    return `data:image/png;base64,${value}`
  }
  return ''
}

const getExportXml = (msg) => {
  const value = msg?.xml || msg?.data || ''
  if (typeof value !== 'string') return ''
  const trimmed = value.trim()
  if (!trimmed.startsWith('<mxfile') && !trimmed.startsWith('<mxGraphModel')) return ''
  return value
}

const applyEditorXml = (xml, event = 'sync') => {
  if (previewVersionId.value) {
    latestXml.value = xml
    return
  }
  if (typeof xml !== 'string' || xml === latestXml.value) return
  latestXml.value = xml
  console.log('[drawio-board] editor emitted XML', {
    event,
    xmlLength: xml.length
  })
  emit('xml-change', xml)
}

const exportCurrentXml = async () => {
  if (previewLoading.value && !editorLoadPromise) {
    throw new BoardSyncError('board_editor_not_ready', '画板工作版本正在加载，请稍后重试')
  }
  if (editorLoadPromise) await editorLoadPromise
  if (!iframeReady.value) {
    throw new BoardSyncError('board_editor_not_ready', '画板编辑器尚未就绪')
  }
  const exportPreviewVersionId = previewVersionId.value
  const exportPreviewRequestId = previewRequestId
  const exportBoardId = props.boardId
  const xml = await boardBridge.exportCurrentXml()
  if (
    exportPreviewRequestId !== previewRequestId ||
    exportBoardId !== props.boardId ||
    exportPreviewVersionId !== previewVersionId.value
  ) {
    throw new BoardSyncError('board_version_conflict', '画板工作版本已切换，请重新发送')
  }
  xmlSyncPending = false
  clearXmlSyncTimeout()
  if (exportPreviewVersionId) {
    latestXml.value = xml
  } else {
    applyEditorXml(xml, 'pre-send-sync')
  }
  return xml
}

const confirmWorkingVersionCommit = ({ xml } = {}) => {
  if (!previewVersionId.value) return
  emit('selection-change', previewSelection.value)
  previewRequestId += 1
  previewVersionId.value = ''
  previewXml.value = ''
  previewSelection.value = []
  previewError.value = ''
  latestXml.value = xml || latestXml.value
}

const exportBoardImage = () => {
  if (!iframeReady.value) {
    return Promise.reject(new Error('draw.io editor is not ready'))
  }

  if (pendingExportResolver) {
    pendingExportResolver.reject(new Error('draw.io export is already pending'))
    pendingExportResolver = null
  }

  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      pendingExportResolver = null
      reject(new Error('draw.io export timed out'))
    }, 8000)

    pendingExportResolver = {
      resolve: (dataUrl) => {
        window.clearTimeout(timeoutId)
        pendingExportResolver = null
        resolve(dataUrl)
      },
      reject: (error) => {
        window.clearTimeout(timeoutId)
        pendingExportResolver = null
        reject(error)
      }
    }

    postDrawio('export', {
      format: 'png',
      xml: getActiveXml()
    })
  })
}

const clearXmlSyncTimeout = () => {
  if (xmlSyncTimeout) {
    window.clearTimeout(xmlSyncTimeout)
    xmlSyncTimeout = null
  }
}

const syncDrawioXml = (force = false) => {
  if (previewVersionId.value) return
  if (!iframeReady.value || xmlSyncPending || selectionProbePending || pendingExportResolver) return

  const now = Date.now()
  if (!force && now - lastXmlSyncAt < XML_SYNC_INTERVAL_MS) return

  xmlSyncPending = true
  lastXmlSyncAt = now
  clearXmlSyncTimeout()
  xmlSyncTimeout = window.setTimeout(() => {
    xmlSyncPending = false
    xmlSyncTimeout = null
  }, 2500)

  postDrawio('export', {
    format: 'xml'
  })
}

const probeDrawioSelection = () => {
  if (!iframeReady.value || selectionProbePending || xmlSyncPending || pendingExportResolver) return

  selectionProbePending = true
  postDrawio('export', {
    format: 'json',
    selection: true,
    allPages: false
  })
}

const stopSelectionProbe = () => {
  if (selectionProbeInterval) {
    window.clearInterval(selectionProbeInterval)
    selectionProbeInterval = null
  }
  selectionProbePending = false
  xmlSyncPending = false
  clearXmlSyncTimeout()
}

const startSelectionProbe = () => {
  if (!iframeReady.value) return
  syncDrawioXml(true)
  probeDrawioSelection()
  if (selectionProbeInterval) return

  selectionProbeInterval = window.setInterval(() => {
    if (document.activeElement !== iframeRef.value) {
      stopSelectionProbe()
      return
    }
    syncDrawioXml()
    probeDrawioSelection()
  }, 700)
}

const downloadBoardImage = async () => {
  exportingSnapshot.value = true
  try {
    const dataUrl = await exportBoardImage()
    downloadDataUrl(dataUrl, `${sanitizeFileName(props.title || 'drawio-board')}.png`)
  } catch (error) {
    console.error('[drawio-board] failed to export board image', error)
  } finally {
    exportingSnapshot.value = false
  }
}

const confirmBoardSnapshot = async () => {
  exportingSnapshot.value = true
  try {
    const dataUrl = await exportBoardImage()
    const filename = `${sanitizeFileName(props.title || 'drawio-board')}.png`
    const file = dataUrlToFile(dataUrl, filename)
    emit('board-snapshot-confirm', {
      file,
      dataUrl,
      filename,
      title: props.title || '画板',
      xmlLength: getActiveXml().length,
      confirmedAt: new Date().toISOString()
    })
  } catch (error) {
    console.error('[drawio-board] failed to confirm board snapshot', error)
  } finally {
    exportingSnapshot.value = false
  }
}

const parseDrawioMessage = (data) => {
  if (!data) return null
  if (typeof data === 'object') return data
  if (typeof data !== 'string') return null

  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

const handleMessage = (event) => {
  const target = iframeRef.value?.contentWindow
  if (!target || event.source !== target || event.origin !== DRAWIO_ORIGIN) return
  if (boardBridge.handleMessage(event)) return
  const msg = parseDrawioMessage(event.data)
  if (!msg) return

  if (msg.event === 'init') {
    iframeReady.value = true
    if (pendingEditorRestart) {
      const request = pendingEditorRestart
      const loadRequest = boardLoader.loadXml(request.xml, { autosave: request.autosave })
      loadRequest.then(
        (result) => settleEditorRestart(request, 'resolve', result),
        (error) => settleEditorRestart(request, request.required ? 'reject' : 'resolve', request.required ? error : false)
      )
      return
    }
    void loadXml()
    return
  }

  if (boardLoader.handleMessage(event)) return

  if (msg.event === 'export') {
    if (xmlSyncPending) {
      const xml = getExportXml(msg)
      if (xml) {
        xmlSyncPending = false
        clearXmlSyncTimeout()
        applyEditorXml(xml, 'xml-export')
        return
      }
    }

    if (msg.format === 'json' && selectionProbePending) {
      selectionProbePending = false
      const selectionIds = getDrawioSelectionPayloadFromExport(msg)
      const selection = parseDrawioSelectedCells(latestXml.value || props.xml, selectionIds)
      applySelection(selection, 'selection-export')
      return
    }

    const dataUrl = getExportDataUrl(msg)
    if (pendingExportResolver && dataUrl) {
      pendingExportResolver.resolve(dataUrl)
    } else if (pendingExportResolver) {
      pendingExportResolver.reject(new Error('draw.io export response did not contain PNG data'))
    }
    return
  }

  if ((msg.event === 'save' || msg.event === 'autosave') && typeof msg.xml === 'string') {
    applyEditorXml(msg.xml, msg.event)
    return
  }

  if (msg.event === 'select' || msg.event === 'selection') {
    const selection = parseDrawioSelectedCells(latestXml.value || props.xml, getDrawioSelectionPayload(msg))
    console.log('[drawio-board] editor emitted selection', {
      event: msg.event,
      selectedCount: selection.length,
      selectedIds: selection.map((cell) => cell.id).filter(Boolean)
    })
    applySelection(selection, msg.event)
  }
}

const handleWindowBlur = () => {
  window.setTimeout(() => {
    if (document.activeElement === iframeRef.value) {
      startSelectionProbe()
    }
  }, 0)
}

const handleWindowFocus = () => {
  if (document.activeElement !== iframeRef.value) {
    stopSelectionProbe()
  }
}

onMounted(() => {
  unregisterBoardExporter = registerActiveDrawioBoardExporter(
    exportCurrentXml,
    confirmWorkingVersionCommit,
    () => previewVersionId.value || props.currentVersionId || null
  )
  window.addEventListener('message', handleMessage)
  window.addEventListener('blur', handleWindowBlur)
  window.addEventListener('focus', handleWindowFocus)
})

onBeforeUnmount(() => {
  unregisterBoardExporter?.()
  unregisterBoardExporter = null
  boardBridge.cancel('board_editor_unmounted')
  boardLoader.cancel('board_editor_unmounted')
  cancelEditorRestart('board_editor_unmounted')
  window.removeEventListener('message', handleMessage)
  window.removeEventListener('blur', handleWindowBlur)
  window.removeEventListener('focus', handleWindowFocus)
  stopSelectionProbe()
  if (pendingExportResolver) {
    pendingExportResolver.reject(new Error('draw.io board panel unmounted'))
  }
})

defineExpose({ exportCurrentXml })

watch(() => props.xml, (xml) => {
  if (previewVersionId.value) return
  if (xml === latestXml.value) return
  latestXml.value = xml || ''
  void restartEditor(xml)
})

watch(() => props.currentVersionId, (versionId) => {
  if (previewVersionId.value && previewVersionId.value === String(versionId || '')) {
    void showCurrentVersion()
  }
})

watch(() => props.boardId, () => {
  boardBridge.cancel('board_context_changed')
  boardLoader.cancel('board_context_changed')
  void showCurrentVersion()
})
</script>

<style scoped>
.drawio-board-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #fff;
}

.board-toolbar {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 48px;
  padding: 8px 10px;
  border-bottom: 1px solid #edf1f7;
  background: #fff;
}

.board-title {
  min-width: 0;
  overflow: hidden;
  color: #263445;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
}

.board-btn {
  min-height: 30px;
  padding: 5px 9px;
  border: 1px solid #d7e1ec;
  border-radius: 6px;
  background: #fff;
  color: #526173;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
}

.board-btn:hover {
  border-color: #b8d4f0;
  background: #f5f9fd;
  color: #1976D2;
}

.drawio-canvas-shell {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
}

.board-readonly-overlay {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(248, 250, 252, 0.68);
  color: #43536a;
  font-size: 14px;
  font-weight: 600;
  backdrop-filter: blur(1px);
}

.file-history-section {
  flex: 0 0 auto;
  padding: 10px 12px;
  border-top: 1px solid #edf1f7;
  background: #fafafa;
}

.file-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
  user-select: none;
}

.section-title {
  color: #526173;
  font-size: 13px;
  font-weight: 600;
}

.history-toggle-icon {
  color: #7a8796;
  font-size: 12px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  max-height: 150px;
  overflow: auto;
}

.history-item {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: #fff;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.history-item:hover:not(:disabled) {
  border-color: #d8e8fb;
  background: #f8fbff;
}

.history-item:disabled {
  cursor: wait;
  opacity: 0.68;
}

.history-item.current {
  border-color: #90caf9;
  background: #eef6ff;
}

.history-empty {
  padding: 10px;
  color: #98a4b3;
  font-size: 12px;
  text-align: center;
}

.history-dirty {
  padding: 7px 8px;
  border: 1px solid #f0d79b;
  border-radius: 4px;
  background: #fff8e6;
  color: #8a6420;
  font-size: 12px;
}

.history-error {
  padding: 7px 8px;
  border: 1px solid #ffcdd2;
  border-radius: 4px;
  background: #fff5f5;
  color: #b3261e;
  font-size: 12px;
}

.quality-attempts-toggle {
  padding: 5px 2px;
  border: 0;
  background: transparent;
  color: #607d9b;
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.quality-attempts {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quality-attempt {
  display: flex;
  gap: 8px;
  padding: 6px;
  border: 1px solid #e5eaf0;
  border-radius: 5px;
  background: #fff;
}

.quality-thumbnail {
  width: 68px;
  height: 44px;
  border-radius: 3px;
  object-fit: contain;
  background: #f4f6f8;
}

.quality-attempt-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
  color: #4a596b;
  font-size: 11px;
}

.quality-status {
  align-self: flex-start;
  padding: 1px 5px;
  border-radius: 8px;
  background: #edf2f7;
}

.quality-status.status-passed { background: #e8f5e9; color: #2e7d32; }
.quality-status.status-warning { background: #fff3e0; color: #a15c00; }
.quality-status.status-failed { background: #ffebee; color: #b3261e; }
.quality-summary { color: #7b8796; }

.history-icon {
  flex: 0 0 auto;
  color: #1976D2;
  font-size: 14px;
}

.history-text {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  color: #333;
}

.history-file-name,
.history-file-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-file-summary {
  margin-top: 2px;
  color: #7b8796;
  font-size: 11px;
}

.history-time {
  flex: 0 0 auto;
  color: #999;
  font-size: 11px;
}

.drawio-frame {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 0;
  background: #fff;
}
</style>
