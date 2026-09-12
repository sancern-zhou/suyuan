<template>
  <section class="smart-reports-panel">
    <header class="panel-header">
      <div><p class="eyebrow">成果中心</p><h2>智能报告</h2></div>
      <button class="icon-button" type="button" title="刷新报告" @click="loadReports">↻</button>
    </header>
    <div class="report-filters">
      <input v-model="query" type="search" placeholder="搜索报告名称" aria-label="搜索报告名称" />
      <select v-model="typeFilter" aria-label="报告类型"><option value="">全部类型</option><option v-for="type in reportTypes" :key="type" :value="type">{{ type }}</option></select>
      <select v-model="formatFilter" aria-label="文件格式"><option value="">全部格式</option><option v-for="format in formats" :key="format" :value="format">{{ format.toUpperCase() }}</option></select>
    </div>
    <p v-if="error" class="state error">{{ error }}</p>
    <p v-else-if="loading" class="state">正在加载报告…</p>
    <p v-else-if="filteredReports.length === 0" class="state">暂无匹配报告</p>
    <div v-else class="report-list">
      <button v-for="report in filteredReports" :key="report.report_id" class="report-row" type="button" @click="selected = report">
        <span class="report-main"><strong>{{ report.name }}</strong><small>{{ report.report_type }} · {{ formatDate(report.updated_at || report.created_at) }}</small></span>
        <span class="format-list"><span v-for="file in availableFiles(report)" :key="file.format" class="format-tag">{{ file.format.toUpperCase() }}</span></span>
      </button>
    </div>
    <div v-if="selected" class="report-preview" role="dialog" aria-modal="true">
      <div class="preview-header"><div><strong>{{ selected.name }}</strong><small>{{ selected.report_type }} · {{ formatDate(selected.updated_at || selected.created_at) }}</small></div><button class="icon-button" type="button" title="关闭预览" @click="selected = null">×</button></div>
      <div class="preview-actions"><button v-for="file in availableFiles(selected)" :key="file.format" type="button" @click="downloadFile(file)">下载 {{ file.format.toUpperCase() }}</button></div>
      <iframe v-if="htmlPreviewUrl" :src="htmlPreviewUrl" title="报告预览" class="preview-frame" />
      <p v-else class="state">该报告没有 HTML 预览，请下载文件查看。</p>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'

const reports = ref([])
const selected = ref(null)
const htmlPreviewUrl = ref('')
const loading = ref(false)
const error = ref('')
const query = ref('')
const typeFilter = ref('')
const formatFilter = ref('')
const formats = ['html', 'docx', 'qmd', 'pdf']
const reportTypes = computed(() => [...new Set(reports.value.map(item => item.report_type).filter(Boolean))])
const availableFiles = report => (report?.files || []).filter(file => file.available)
const htmlFile = report => availableFiles(report).find(file => file.format === 'html')
const filteredReports = computed(() => reports.value.filter(report => {
  const text = query.value.trim().toLowerCase()
  return (!text || report.name.toLowerCase().includes(text)) && (!typeFilter.value || report.report_type === typeFilter.value) && (!formatFilter.value || availableFiles(report).some(file => file.format === formatFilter.value))
}))
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'

async function loadReports() {
  loading.value = true; error.value = ''
  try {
    const response = await authFetch('/api/reports')
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '报告列表加载失败')
    reports.value = data.reports || []
  } catch (cause) { error.value = cause.message || '报告列表加载失败' } finally { loading.value = false }
}
watch(selected, async report => {
  if (htmlPreviewUrl.value) URL.revokeObjectURL(htmlPreviewUrl.value)
  htmlPreviewUrl.value = ''
  const file = htmlFile(report)
  if (!file) return
  try {
    const response = await authFetch(file.url)
    if (!response.ok) throw new Error('报告预览加载失败')
    htmlPreviewUrl.value = URL.createObjectURL(await response.blob())
  } catch (cause) { error.value = cause.message }
})
async function downloadFile(file) {
  const response = await authFetch(file.url)
  if (!response.ok) throw new Error('报告下载失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = file.name; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(loadReports)
</script>

<style scoped>
.smart-reports-panel{position:relative;height:100%;padding:24px 28px;color:#17212b;background:#f7f9fb;overflow:auto}.panel-header,.preview-header{display:flex;align-items:center;justify-content:space-between}.eyebrow{margin:0 0 4px;color:#657584;font-size:12px}.panel-header h2{margin:0;font-size:24px}.icon-button{border:1px solid #d7e0e7;background:white;color:#34495e;width:34px;height:34px;border-radius:6px;font-size:20px;cursor:pointer}.report-filters{display:grid;grid-template-columns:minmax(180px,1fr) 180px 140px;gap:10px;margin:22px 0 14px}.report-filters input,.report-filters select{height:38px;border:1px solid #d7e0e7;border-radius:6px;background:#fff;padding:0 11px;color:#263746}.report-list{border:1px solid #e0e6eb;background:white;border-radius:8px;overflow:hidden}.report-row{width:100%;display:flex;align-items:center;justify-content:space-between;gap:20px;text-align:left;padding:16px 18px;border:0;border-bottom:1px solid #edf1f4;background:#fff;cursor:pointer}.report-row:last-child{border-bottom:0}.report-row:hover{background:#f2f7fa}.report-main{display:flex;flex-direction:column;gap:6px;min-width:0}.report-main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.report-main small,.preview-header small{color:#71808d}.format-list{display:flex;gap:6px;flex-shrink:0}.format-tag{font-size:11px;color:#176b82;background:#e5f3f6;border-radius:4px;padding:4px 6px}.state{color:#71808d;padding:32px;text-align:center}.error{color:#b33a35}.report-preview{position:absolute;inset:0;background:#fff;z-index:2;display:flex;flex-direction:column;padding:20px 24px}.preview-header small{display:block;margin-top:5px}.preview-actions{display:flex;gap:8px;padding:14px 0}.preview-actions a{color:#176b82;border:1px solid #c8e0e6;border-radius:5px;padding:7px 10px;text-decoration:none;font-size:13px}.preview-frame{width:100%;flex:1;border:1px solid #dfe6eb;background:#fff}@media(max-width:700px){.smart-reports-panel{padding:18px}.report-filters{grid-template-columns:1fr}.report-row{align-items:flex-start;flex-direction:column;gap:10px}}
.preview-actions button{color:#176b82;border:1px solid #c8e0e6;border-radius:5px;padding:7px 10px;background:#fff;font-size:13px;cursor:pointer}
</style>
