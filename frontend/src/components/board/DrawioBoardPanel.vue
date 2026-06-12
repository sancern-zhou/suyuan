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
      <div
        v-if="selectedCellsForAiEdit.length > 0"
        class="ai-edit-indicator"
        aria-live="polite"
      >
        <span class="ai-edit-icon">AI</span>
        <span class="ai-edit-text">AI编辑</span>
        <span class="ai-edit-target">{{ selectedCellsLabel }}</span>
      </div>

      <iframe
        ref="iframeRef"
        class="drawio-frame"
        :src="drawioUrl"
        title="Draw.io board"
      ></iframe>
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
  }
})

const emit = defineEmits(['xml-change', 'selection-change', 'board-snapshot-confirm'])

const iframeRef = ref(null)
const iframeReady = ref(false)
const latestXml = ref(props.xml || '')
const exportingSnapshot = ref(false)
const selectedCellsForAiEdit = ref([])
let pendingExportResolver = null
let selectionProbeInterval = null
let selectionProbePending = false

const drawioUrl = computed(() => 'https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&saveAndExit=0&noSaveBtn=1&noExitBtn=1')

const selectedCellsLabel = computed(() => {
  const selected = selectedCellsForAiEdit.value
  if (selected.length === 1) {
    return selected[0]?.value || selected[0]?.id || '已选中模块'
  }
  return `已选中 ${selected.length} 项`
})

const postDrawio = (action, extra = {}) => {
  const target = iframeRef.value?.contentWindow
  if (!target) return
  target.postMessage(JSON.stringify({ action, ...extra }), '*')
}

const applySelection = (selection, source = 'unknown') => {
  selectedCellsForAiEdit.value = selection
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

const probeDrawioSelection = () => {
  if (!iframeReady.value || selectionProbePending || pendingExportResolver) return

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
}

const startSelectionProbe = () => {
  if (!iframeReady.value) return
  probeDrawioSelection()
  if (selectionProbeInterval) return

  selectionProbeInterval = window.setInterval(() => {
    if (document.activeElement !== iframeRef.value) {
      stopSelectionProbe()
      return
    }
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
    latestXml.value = msg.xml
    console.log('[drawio-board] editor emitted XML', {
      event: msg.event,
      xmlLength: msg.xml.length
    })
    emit('xml-change', msg.xml)
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

.ai-edit-indicator {
  position: absolute;
  top: 12px;
  left: 50%;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  max-width: min(420px, calc(100% - 32px));
  min-height: 34px;
  padding: 6px 10px;
  border: 1px solid #b7d6ff;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 6px 18px rgba(45, 67, 97, 0.16);
  color: #1f3b57;
  font-size: 12px;
  gap: 7px;
  pointer-events: none;
  transform: translateX(-50%);
}

.ai-edit-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: #1976D2;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

.ai-edit-text {
  flex: 0 0 auto;
  font-weight: 700;
}

.ai-edit-target {
  min-width: 0;
  overflow: hidden;
  color: #526173;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawio-frame {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 0;
  background: #fff;
}
</style>
