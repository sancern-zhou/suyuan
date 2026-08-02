<template>
  <div class="excel-editor">
    <div class="excel-toolbar">
      <div class="sheet-tabs" role="tablist" aria-label="工作表">
        <button
          v-for="name in sheetNames"
          :key="name"
          type="button"
          role="tab"
          class="sheet-tab"
          :class="{ active: name === activeSheetName }"
          :aria-selected="name === activeSheetName"
          @click="selectSheet(name)"
        >{{ name }}</button>
      </div>
      <div class="toolbar-actions">
        <button type="button" :disabled="loading || saving" @click="loadWorkbook">重新加载</button>
        <button
          v-if="resource.actions?.save"
          type="button"
          class="primary"
          :disabled="loading || saving || !workbook"
          @click="saveWorkbook"
        >{{ saving ? '保存中...' : '保存' }}</button>
      </div>
    </div>

    <div v-if="loading" class="excel-state">正在加载表格...</div>
    <div v-else-if="error" class="excel-state error">{{ error }}</div>
    <div v-else class="sheet-container">
      <table class="sheet-table">
        <thead>
          <tr>
            <th class="corner-cell"></th>
            <th v-for="column in columnHeaders" :key="column" class="column-header">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
            <th class="row-header">{{ rowIndex + 1 }}</th>
            <td v-for="(cell, columnIndex) in row" :key="`${rowIndex}-${columnIndex}`">
              <input
                class="cell-input"
                :value="cell"
                :disabled="saving"
                @input="updateCell(rowIndex, columnIndex, $event.target.value)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="status" class="excel-status" :class="statusType">{{ status }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import * as XLSX from 'xlsx'
import { authFetch } from '@/auth/http.js'
import { coerceSpreadsheetCell, saveSpreadsheetResource } from '@/services/spreadsheetResourceApi.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'

const props = defineProps({
  resource: { type: Object, required: true },
  group: { type: Object, default: null },
  contentUrl: { type: String, required: true }
})

const resourceStore = useSessionResourceStore()
const workbook = ref(null)
const activeSheetName = ref('')
const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const status = ref('')
const statusType = ref('success')

const sheetNames = computed(() => workbook.value?.SheetNames || [])
const columnHeaders = computed(() => {
  const width = Math.max(1, ...rows.value.map(row => row.length))
  return Array.from({ length: width }, (_, index) => XLSX.utils.encode_col(index))
})

const normalizeRows = sourceRows => {
  const visible = sourceRows.length ? sourceRows : [['']]
  const width = Math.max(1, ...visible.map(row => row.length))
  return visible.map(row => {
    const next = Array.from(row)
    while (next.length < width) next.push('')
    return next
  })
}

const loadActiveSheet = () => {
  const sheet = workbook.value?.Sheets?.[activeSheetName.value]
  rows.value = sheet
    ? normalizeRows(XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false, defval: '' }))
    : [['']]
}

const loadWorkbook = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await authFetch(props.contentUrl)
    if (!response.ok) throw new Error(`加载失败（HTTP ${response.status}）`)
    workbook.value = XLSX.read(await response.arrayBuffer(), {
      type: 'array',
      cellDates: true,
      cellStyles: true
    })
    activeSheetName.value = workbook.value.SheetNames[0] || ''
    loadActiveSheet()
  } catch (cause) {
    error.value = cause?.message || '加载表格失败'
  } finally {
    loading.value = false
  }
}

const selectSheet = name => {
  activeSheetName.value = name
  loadActiveSheet()
}

const updateCell = (rowIndex, columnIndex, value) => {
  const nextRows = rows.value.map(row => row.slice())
  nextRows[rowIndex][columnIndex] = value
  rows.value = nextRows
  const sheet = workbook.value?.Sheets?.[activeSheetName.value]
  if (!sheet) return
  const address = XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex })
  sheet[address] = coerceSpreadsheetCell(sheet[address], value)
  const range = sheet['!ref'] ? XLSX.utils.decode_range(sheet['!ref']) : { s: { r: 0, c: 0 }, e: { r: 0, c: 0 } }
  range.e.r = Math.max(range.e.r, rowIndex)
  range.e.c = Math.max(range.e.c, columnIndex)
  sheet['!ref'] = XLSX.utils.encode_range(range)
}

const saveWorkbook = async () => {
  if (!workbook.value || !props.resource.actions?.save) return
  saving.value = true
  status.value = ''
  error.value = ''
  try {
    const bookType = props.resource.format === 'xls' ? 'xls' : 'xlsx'
    workbook.value.Workbook ||= {}
    workbook.value.Workbook.CalcPr = {
      ...(workbook.value.Workbook.CalcPr || {}),
      calcMode: 'auto',
      fullCalcOnLoad: true,
      forceFullCalc: true
    }
    const bytes = XLSX.write(workbook.value, { type: 'array', bookType })
    const receipt = await saveSpreadsheetResource(props.resource, bytes)
    const sessionId = resourceStore.activeSessionId
    await resourceStore.refreshIfNewer(sessionId, receipt.resource_version)
    const next = resourceStore.sessionState(sessionId)?.resources.find(item => (
      item.group_id === props.resource.group_id
      && item.relation === 'primary'
      && item.status === 'active'
    ))
    if (next) {
      resourceStore.selectGroup(sessionId, next.group_id)
      resourceStore.selectResource(sessionId, next.resource_id)
    }
    statusType.value = 'success'
    status.value = '已保存为最新版本'
  } catch (cause) {
    statusType.value = 'error'
    status.value = cause?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadWorkbook)
watch(() => props.contentUrl, loadWorkbook)
</script>

<style scoped>
.excel-editor { display: flex; height: 100%; min-height: 0; flex-direction: column; background: #fff; }
.excel-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 112px 8px 12px; border-bottom: 1px solid #d8deea; background: #f7f9fc; }
.sheet-tabs, .toolbar-actions { display: flex; gap: 6px; }.sheet-tabs { min-width: 0; overflow-x: auto; }
button { min-height: 30px; padding: 5px 10px; border: 1px solid #cfd7e6; border-radius: 5px; background: #fff; color: #334155; cursor: pointer; white-space: nowrap; }
button:disabled { cursor: wait; opacity: .55; }.sheet-tab.active { border-color: #2374d5; background: #eef6ff; color: #145ca8; }.primary { border-color: #2374d5; background: #2374d5; color: #fff; }
.sheet-container { min-height: 0; flex: 1; overflow: auto; }.sheet-table { min-width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 13px; }
.corner-cell, .column-header, .row-header { position: sticky; z-index: 1; border: 1px solid #d8deea; background: #eef2f7; color: #475569; font-weight: 600; }.column-header { top: 0; width: 140px; min-width: 140px; height: 28px; }.row-header { left: 0; width: 46px; min-width: 46px; height: 30px; text-align: center; }.corner-cell { top: 0; left: 0; z-index: 2; width: 46px; }
td { width: 140px; min-width: 140px; height: 30px; padding: 0; border: 1px solid #e2e8f0; }.cell-input { width: 100%; height: 30px; padding: 4px 8px; box-sizing: border-box; border: 0; outline: 0; background: #fff; font: inherit; }.cell-input:focus { box-shadow: inset 0 0 0 2px #2374d5; }
.excel-state { display: grid; min-height: 0; flex: 1; place-content: center; color: #64748b; }.error, .excel-status.error { color: #b42318; }.excel-status { padding: 7px 12px; border-top: 1px solid #d8deea; color: #15803d; font-size: 12px; }
</style>
