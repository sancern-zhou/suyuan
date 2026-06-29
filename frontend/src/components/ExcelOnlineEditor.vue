<template>
  <div class="excel-editor">
    <div class="excel-toolbar">
      <div class="sheet-tabs" role="tablist" aria-label="工作表">
        <button
          v-for="name in sheetNames"
          :key="name"
          type="button"
          class="sheet-tab"
          :class="{ active: name === activeSheetName }"
          @click="selectSheet(name)"
        >
          {{ name }}
        </button>
      </div>
      <div class="toolbar-actions">
        <button type="button" class="toolbar-btn" :disabled="loading || saving || downloading || !props.doc?.file_path" @click="downloadWorkbook">
          {{ downloading ? '下载中...' : '下载' }}
        </button>
        <button type="button" class="toolbar-btn" :disabled="loading || saving" @click="reloadWorkbook">
          重新加载
        </button>
        <button type="button" class="toolbar-btn primary" :disabled="loading || saving || !workbook" @click="saveWorkbook">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="excel-state">加载表格中...</div>
    <div v-else-if="errorMessage" class="excel-state error">{{ errorMessage }}</div>
    <div v-else class="sheet-container">
      <table class="sheet-table">
        <thead>
          <tr>
            <th class="corner-cell"></th>
            <th v-for="column in columnHeaders" :key="column" class="column-header">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in sheetRows" :key="rowIndex">
            <th class="row-header">{{ rowIndex + 1 }}</th>
            <td v-for="(cell, colIndex) in row" :key="`${rowIndex}-${colIndex}`">
              <input
                class="cell-input"
                :value="cell"
                @input="updateCell(rowIndex, colIndex, $event.target.value)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="statusMessage" class="excel-status" :class="statusType">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import * as XLSX from 'xlsx'
import { downloadExcelFile, openExcelForEditing, saveEditedExcel } from '@/services/excelOnlineEditorApi'

const props = defineProps({
  doc: {
    type: Object,
    required: true
  },
  sessionId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['saved'])

const workbook = ref(null)
const activeSheetName = ref('')
const sheetRows = ref([])
const loading = ref(false)
const saving = ref(false)
const downloading = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const statusType = ref('info')

const sheetNames = computed(() => workbook.value?.SheetNames || [])
const columnHeaders = computed(() => {
  const maxColumns = Math.max(1, ...sheetRows.value.map(row => row.length))
  return Array.from({ length: maxColumns }, (_, index) => XLSX.utils.encode_col(index))
})

onMounted(loadWorkbook)

watch(() => props.doc?.file_path, () => {
  loadWorkbook()
})

async function loadWorkbook() {
  if (!props.doc?.file_path) {
    errorMessage.value = '缺少 Excel 文件路径'
    return
  }

  loading.value = true
  errorMessage.value = ''
  statusMessage.value = ''

  try {
    const buffer = await openExcelForEditing(props.doc.file_path)
    workbook.value = XLSX.read(buffer, { type: 'array', cellDates: true })
    activeSheetName.value = workbook.value.SheetNames[0] || ''
    loadActiveSheetRows()
  } catch (error) {
    errorMessage.value = error.message || '打开 Excel 文档失败'
  } finally {
    loading.value = false
  }
}

function reloadWorkbook() {
  loadWorkbook()
}

async function downloadWorkbook() {
  if (!props.doc?.file_path) {
    return
  }

  downloading.value = true
  statusMessage.value = ''

  try {
    const { blob, fileName } = await downloadExcelFile(props.doc.file_path, {
      fallbackFileName: props.doc.file_name || 'document.xlsx',
      fileName: props.doc.file_name || 'document.xlsx'
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error) {
    statusType.value = 'error'
    statusMessage.value = error.message || '下载 Excel 文档失败'
  } finally {
    downloading.value = false
  }
}

function selectSheet(name) {
  activeSheetName.value = name
  loadActiveSheetRows()
}

function loadActiveSheetRows() {
  const sheet = workbook.value?.Sheets?.[activeSheetName.value]
  if (!sheet) {
    sheetRows.value = [['']]
    return
  }
  const rows = XLSX.utils.sheet_to_json(sheet, {
    header: 1,
    raw: false,
    defval: ''
  })
  sheetRows.value = normalizeRows(rows)
}

function normalizeRows(rows) {
  const visibleRows = rows.length > 0 ? rows : [['']]
  const maxColumns = Math.max(1, ...visibleRows.map(row => row.length))
  return visibleRows.map(row => {
    const nextRow = Array.from(row)
    while (nextRow.length < maxColumns) {
      nextRow.push('')
    }
    return nextRow
  })
}

function updateCell(rowIndex, colIndex, value) {
  const nextRows = sheetRows.value.map(row => row.slice())
  nextRows[rowIndex][colIndex] = value
  sheetRows.value = nextRows
}

async function saveWorkbook() {
  if (!workbook.value || !activeSheetName.value) {
    return
  }

  saving.value = true
  statusMessage.value = ''
  errorMessage.value = ''

  try {
    workbook.value.Sheets[activeSheetName.value] = XLSX.utils.aoa_to_sheet(sheetRows.value)
    const fileType = getWorkbookType(props.doc.file_name || props.doc.file_path)
    const buffer = XLSX.write(workbook.value, { type: 'array', bookType: fileType })
    const document = await saveEditedExcel({
      filePath: props.doc.file_path,
      sessionId: props.sessionId || '',
      fileName: props.doc.file_name || `workbook.${fileType}`,
      buffer
    })
    statusType.value = 'success'
    statusMessage.value = '已保存'
    emit('saved', document)
  } catch (error) {
    statusType.value = 'error'
    statusMessage.value = error.message || '保存 Excel 文档失败'
  } finally {
    saving.value = false
  }
}

function getWorkbookType(fileName) {
  return String(fileName || '').toLowerCase().endsWith('.xls') ? 'xls' : 'xlsx'
}
</script>

<style scoped>
.excel-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #fff;
}

.excel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #d8deea;
  background: #f7f9fc;
}

.sheet-tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  min-width: 0;
}

.sheet-tab,
.toolbar-btn {
  min-height: 30px;
  border: 1px solid #cfd7e6;
  background: #fff;
  color: #334155;
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}

.sheet-tab.active {
  border-color: #2374d5;
  color: #145ca8;
  background: #eef6ff;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.toolbar-btn.primary {
  background: #2374d5;
  color: #fff;
  border-color: #2374d5;
}

.toolbar-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.sheet-container {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.sheet-table {
  border-collapse: collapse;
  min-width: 100%;
  table-layout: fixed;
  font-size: 13px;
}

.corner-cell,
.column-header,
.row-header {
  background: #eef2f7;
  color: #475569;
  border: 1px solid #d8deea;
  font-weight: 600;
}

.corner-cell,
.row-header {
  width: 48px;
  min-width: 48px;
}

.column-header {
  width: 140px;
  min-width: 140px;
  height: 28px;
}

.row-header {
  height: 30px;
  text-align: center;
}

td {
  border: 1px solid #e2e8f0;
  width: 140px;
  min-width: 140px;
  height: 30px;
  padding: 0;
}

.cell-input {
  width: 100%;
  height: 30px;
  border: none;
  outline: none;
  padding: 4px 8px;
  box-sizing: border-box;
  font: inherit;
  background: #fff;
}

.cell-input:focus {
  box-shadow: inset 0 0 0 2px #2374d5;
}

.excel-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
}

.excel-state.error,
.excel-status.error {
  color: #b91c1c;
}

.excel-status {
  padding: 8px 12px;
  border-top: 1px solid #d8deea;
  font-size: 12px;
  color: #475569;
}

.excel-status.success {
  color: #15803d;
}
</style>
