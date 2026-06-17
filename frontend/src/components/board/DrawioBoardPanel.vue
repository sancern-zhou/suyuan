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
        ref="iframeRef"
        class="drawio-frame"
        :src="drawioUrl"
        title="Draw.io board"
      ></iframe>
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
          v-for="version in versionFiles"
          :key="getVersionKey(version)"
          type="button"
          class="history-item file-history-item"
          :class="{ current: !boardDirty && getVersionKey(version) === currentVersionId }"
          @click="restoreVersion(version)"
        >
          <span class="history-icon">◇</span>
          <span class="history-text">
            <span class="history-file-name">{{ getVersionName(version) }}</span>
            <span class="history-file-summary">{{ getVersionSummary(version) }}</span>
          </span>
          <span class="history-time">{{ formatTime(version.created_at || version.createdAt) }}</span>
        </button>
        <div v-if="versionFiles.length === 0" class="history-empty">
          暂无版本文件
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  getDrawioSelectionPayload,
  getDrawioSelectionPayloadFromExport,
  parseDrawioSelectedCells
} from './drawioSelection.js'

const props = defineProps({
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
  }
})

const emit = defineEmits(['xml-change', 'selection-change', 'board-snapshot-confirm', 'version-restore'])

const iframeRef = ref(null)
const iframeReady = ref(false)
const latestXml = ref(props.xml || '')
const exportingSnapshot = ref(false)
const showVersionFiles = ref(false)
let pendingExportResolver = null
let selectionProbeInterval = null
let selectionProbePending = false
let xmlSyncPending = false
let xmlSyncTimeout = null
let lastXmlSyncAt = 0

const XML_SYNC_INTERVAL_MS = 1200

const drawioUrl = computed(() => 'https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&modified=0&saveAndExit=0&noSaveBtn=1&noExitBtn=1')

const postDrawio = (action, extra = {}) => {
  const target = iframeRef.value?.contentWindow
  if (!target) return
  target.postMessage(JSON.stringify({ action, ...extra }), '*')
}

const applySelection = (selection, source = 'unknown') => {
  console.log('[drawio-board] selection updated from editor', {
    source,
    selectedCount: selection.length,
    selectedIds: selection.map((cell) => cell.id).filter(Boolean)
  })
  emit('selection-change', selection)
}

const loadXml = (xml = props.xml) => {
  if (!xml || !iframeReady.value) return
  postDrawio('load', {
    xml,
    autosave: 1
  })
}

const reloadXml = () => {
  loadXml()
}

const getVersionKey = (version = {}) => String(version.version_id || version.id || version.versionNumber || version.version_number || '')

const getVersionName = (version = {}) => {
  return version.file_name || version.fileName || version.downloadLabel || `${version.title || props.title || '画板'} v${version.version_number || version.versionNumber || ''}`.trim()
}

const getVersionSummary = (version = {}) => {
  const sourceLabel = version.source === 'agent' ? 'AI生成' : version.source === 'user_restore' ? '手动恢复' : '版本文件'
  const number = version.version_number || version.versionNumber
  return `${sourceLabel}${number ? ` · v${number}` : ''}`
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

const restoreVersion = (version = {}) => {
  const versionId = getVersionKey(version)
  if (!versionId) return
  emit('version-restore', versionId)
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
  if (typeof xml !== 'string' || xml === latestXml.value) return
  latestXml.value = xml
  console.log('[drawio-board] editor emitted XML', {
    event,
    xmlLength: xml.length
  })
  emit('xml-change', xml)
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
  const msg = parseDrawioMessage(event.data)
  if (!msg) return

  if (msg.event === 'init') {
    iframeReady.value = true
    loadXml()
    return
  }

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
  window.addEventListener('message', handleMessage)
  window.addEventListener('blur', handleWindowBlur)
  window.addEventListener('focus', handleWindowFocus)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', handleMessage)
  window.removeEventListener('blur', handleWindowBlur)
  window.removeEventListener('focus', handleWindowFocus)
  stopSelectionProbe()
  if (pendingExportResolver) {
    pendingExportResolver.reject(new Error('draw.io board panel unmounted'))
  }
})

watch(() => props.xml, (xml) => {
  if (xml === latestXml.value) return
  latestXml.value = xml || ''
  loadXml(xml)
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

.history-item:hover {
  border-color: #d8e8fb;
  background: #f8fbff;
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
