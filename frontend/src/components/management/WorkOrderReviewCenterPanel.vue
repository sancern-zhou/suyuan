<template>
  <section class="wor-panel" aria-label="故障工单审核工作台">
    <header class="wor-header">
      <div class="wor-title">
        <h3>故障工单审核</h3>
        <p>证据包拆分存储 · AI 研判 · 人工反馈 / 归档 / 退回</p>
      </div>
      <div class="wor-header-actions">
        <button type="button" class="btn btn--secondary" :disabled="listLoading" @click="loadOrders">
          <span v-if="listLoading" class="spinner spinner--sm" aria-hidden="true"></span>
          {{ listLoading ? '刷新中…' : '刷新' }}
        </button>
        <button v-if="selectedCode" type="button" class="btn btn--secondary" @click="backToList">返回列表</button>
        <button type="button" class="btn btn--text close-btn" aria-label="关闭" @click="$emit('close')">
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12" />
            <path d="M18 6L6 18" />
          </svg>
        </button>
      </div>
    </header>

    <div v-if="actionError || actionMessage" class="wor-banners">
      <p v-if="actionError" class="action-error" role="alert">{{ actionError }}</p>
      <p v-if="actionMessage" class="action-message" role="status">{{ actionMessage }}</p>
    </div>

    <!-- 列表视图 -->
    <section v-if="!selectedCode" class="wor-list-view">
      <div class="wor-toolbar">
        <input
          v-model="keyword"
          class="wor-search"
          type="search"
          placeholder="搜索工单号 / 站点 / 标题"
          aria-label="搜索工单"
          @keyup.enter="applyFilters"
        />
        <select v-model="statusFilter" class="wor-status-select" aria-label="按状态筛选" @change="applyFilters">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>

      <div v-if="listLoading && !orders.length" class="wor-state">
        <span class="spinner" aria-hidden="true"></span>
        <span>正在加载审核工单…</span>
      </div>

      <div v-else-if="!orders.length" class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 4.5h6v3H9v-3Z" />
          <path d="M9 6H6.5A1.5 1.5 0 0 0 5 7.5v12A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-12A1.5 1.5 0 0 0 17.5 6H15" />
        </svg>
        <p class="empty-title">暂无审核工单</p>
        <p class="empty-hint">在对话中对工单执行取证审核后，证据会自动归档到这里。</p>
      </div>

      <template v-else>
        <ul class="wor-order-list">
          <li v-for="order in orders" :key="order.working_order_code">
            <button type="button" class="wor-order-card" @click="openDetail(order.working_order_code)">
              <div class="order-line">
                <strong class="order-code">{{ order.working_order_code }}</strong>
                <span class="status-badge" :class="statusClass(order.status)">{{ order.status || '待审核' }}</span>
              </div>
              <div class="order-title">{{ order.title || '未命名工单' }}</div>
              <div class="order-meta">
                <span>{{ order.site_name || order.site_id || '未设置站点' }}</span>
                <span>{{ order.pollutant || '未设置污染物' }}</span>
                <span v-if="order.window_start">{{ shortTime(order.window_start) }} ~ {{ shortTime(order.window_end) }}</span>
              </div>
              <div class="order-foot">
                <span v-if="order.review_id">AI 已研判</span>
                <span>取证于 {{ formatTime(order.collected_at) }}</span>
                <span v-if="order.operations_count">操作 {{ order.operations_count }} 次</span>
              </div>
            </button>
          </li>
        </ul>
        <p class="wor-total">共 {{ total }} 条工单</p>
      </template>
    </section>

    <!-- 详情视图 -->
    <section v-else class="wor-detail-view">
      <div v-if="detailLoading" class="wor-state">
        <span class="spinner" aria-hidden="true"></span>
        <span>正在加载审核包…</span>
      </div>

      <div v-else-if="!detail" class="empty-state">
        <p class="empty-title">审核包不存在或已被清理</p>
        <p class="empty-hint">请返回列表后重新选择工单。</p>
      </div>

      <template v-else>
        <header class="detail-header">
          <div class="detail-heading">
            <strong class="order-code">{{ entry.working_order_code }}</strong>
            <h3>{{ entry.title || '故障工单审核' }}</h3>
            <p>{{ entry.site_name || entry.site_id || '未设置站点' }} · {{ entry.pollutant || '未设置污染物' }} · {{ shortTime(entry.window_start) }} ~ {{ shortTime(entry.window_end) }}</p>
          </div>
          <span class="status-badge" :class="statusClass(entry.status)">{{ entry.status || '待审核' }}</span>
        </header>

        <div class="action-bar">
          <button type="button" class="btn btn--secondary" :disabled="actionBusy" @click="openDialog('feedback')">反馈</button>
          <button type="button" class="btn btn--danger" :disabled="actionBusy" @click="openDialog('reject')">退回</button>
          <button type="button" class="btn btn--primary" :disabled="actionBusy" @click="openDialog('archive')">归档</button>
        </div>

        <div class="workbench-layout">
          <aside class="workbench-index" aria-label="审核目录">
            <div class="workbench-index-title">审核目录</div>
            <button
              v-for="section in workbenchSections"
              :key="section.key"
              type="button"
              class="workbench-index-item"
              :class="{ active: activeSectionKey === section.key }"
              @click="scrollToSection(section.key)"
            >
              <span>{{ section.index }}. {{ section.label }}</span>
              <i class="index-state" :class="section.stateClass"></i>
            </button>
          </aside>

          <main ref="sectionContent" class="workbench-content" @scroll.passive="updateActiveSection">
            <!-- AI 研判结果 -->
            <article id="wor-section-judgment" class="section-card judgment" aria-label="AI 研判结果">
              <header class="section-head">
                <h4>AI 研判结果</h4>
                <span v-if="judgment?.judged_at" class="muted">{{ formatTime(judgment.judged_at) }}</span>
              </header>
              <div v-if="!judgment" class="source-empty">尚未提交 AI 研判。在对话中要求审核该工单并提交结论后，这里会展示研判结果。</div>
              <template v-else>
                <div class="judgment-chips">
                  <span class="chip" :class="decisionChipClass">结论：{{ decisionText }}</span>
                  <span v-for="(impact, index) in dataImpactChips" :key="index" class="chip neutral">{{ impact }}</span>
                </div>
                <MarkdownRenderer v-if="judgment.comment" :content="judgment.comment" :streaming="false" />
                <table v-if="judgment.checks?.length" class="evidence-table">
                  <thead><tr><th>核验项</th><th>结论</th><th>依据</th><th>范围</th></tr></thead>
                  <tbody>
                    <tr v-for="(check, index) in judgment.checks" :key="index">
                      <td>{{ check.name }}</td>
                      <td><span class="chip" :class="check.status === 'pass' ? 'ok' : (check.status === 'fail' ? 'bad' : 'neutral')">{{ checkStatusLabel(check.status) }}</span></td>
                      <td class="basis-cell">{{ check.basis }}</td>
                      <td>{{ checkScopeLabel(check.scope) }}</td>
                    </tr>
                  </tbody>
                </table>
              </template>
            </article>

            <!-- 证据数据 -->
            <article
              v-for="source in evidenceSections"
              :id="`wor-section-${source.key}`"
              :key="source.key"
              class="section-card"
              aria-label="证据数据"
            >
              <header class="section-head">
                <h4>{{ source.label }}</h4>
                <span class="source-meta" :class="`st-${source.status}`">
                  {{ sourceStatusLabel(source.status) }}<template v-if="source.recordCount != null"> · {{ source.recordCount }} 条</template>
                </span>
              </header>
              <p v-if="source.summary" class="source-summary">{{ source.summary }}</p>

              <template v-if="source.key === 'work_order'">
                <div v-if="woFacts.length" class="fact-grid">
                  <div v-for="fact in woFacts" :key="fact.label" class="fact-item">
                    <span>{{ fact.label }}</span>
                    <strong>{{ fact.value }}</strong>
                  </div>
                </div>
                <p v-else class="source-empty">未获取到工单信息（未提供工单号）。</p>

                <div v-for="device in deviceSections" :key="device.key" class="sub-section">
                  <h5>{{ device.label }}</h5>
                  <div class="fact-grid">
                    <div v-for="fact in device.entries" :key="fact.label" class="fact-item">
                      <span>{{ fact.label }}</span>
                      <strong>{{ fact.value }}</strong>
                    </div>
                  </div>
                </div>

                <div v-if="woSteps.length" class="sub-section">
                  <h5>流程节点</h5>
                  <ol class="step-list">
                    <li v-for="(step, index) in woSteps" :key="index">
                      <span class="step-dot" :class="`st-${step.statusKey}`"></span>
                      <strong>{{ step.name }}</strong>
                      <em>{{ step.statusText }}</em>
                      <small v-if="step.time">{{ shortTime(step.time) }}</small>
                    </li>
                  </ol>
                </div>

                <div v-if="woDetails.length" class="sub-section">
                  <h5>处置过程（{{ woDetails.length }} 条）</h5>
                  <ol class="history-list">
                    <li v-for="(item, index) in woDetails" :key="index">
                      <strong>{{ item.step ? `${item.step} · ${item.user || '平台记录'}` : (item.user || '平台记录') }}</strong>
                      <span>{{ item.content || '—' }}</span>
                      <small v-if="item.time">{{ formatTime(item.time) }}</small>
                    </li>
                  </ol>
                </div>

                <div v-if="woAttachments.length" class="sub-section">
                  <h5>附件（{{ woAttachments.length }}）</h5>
                  <div class="attachment-grid">
                    <figure v-for="att in woAttachments" :key="att.index" :class="{ failed: att.status !== 'success' }">
                      <button
                        v-if="att.isImage && att.url"
                        type="button"
                        class="attachment-thumb"
                        @click="previewUrl = att.url"
                      >
                        <img :src="att.url" :alt="att.name" loading="lazy" />
                      </button>
                      <a v-else-if="att.status === 'success' && att.url" class="attachment-file" :href="att.url" :download="att.name">{{ att.name }}</a>
                      <span v-else class="attachment-file muted">{{ att.name }}（{{ att.status }}）</span>
                      <figcaption>
                        {{ att.name }}
                        <em v-if="att.size">{{ Math.round(att.size / 1024) }} KB</em>
                      </figcaption>
                    </figure>
                  </div>
                </div>
              </template>

              <template v-else-if="source.key === 'station_hour'">
                <ReviewTimeSeriesChart v-if="chartSeries.length" :series="chartSeries" :mark-areas="markAreas" :unit="unit" :height="300" />
                <p v-else class="source-empty">该来源暂无小时数据。</p>
              </template>

              <template v-else-if="source.key === 'weather'">
                <JiangsuWeatherReviewChart v-if="weatherRows.length" :entry="weatherEntry" :weather="weatherPayload" :mark-areas="markAreas" />
                <p v-else class="source-empty">未获取到城市气象数据。</p>
              </template>

              <template v-else-if="source.key === 'qc'">
                <div v-if="qcTasks.length" class="qc-task-list">
                  <article v-for="(task, index) in qcTasks" :key="task.rId || index" class="qc-task-card">
                    <header class="qc-task-head">
                      <div class="qc-task-title">
                        <strong>{{ task.qcType || task.task_type_name || '质控任务' }}</strong>
                        <span class="muted">{{ task.poll || entry.pollutant }} · {{ task.sStart || task.rStart || '—' }}</span>
                      </div>
                      <span class="chip" :class="qcResultClass(task)">{{ qcResultText(task) }}</span>
                    </header>
                    <div class="qc-task-actions">
                      <button
                        v-if="task.detail"
                        type="button"
                        class="link-btn"
                        @click="toggleQcDetail(task.rId || index)"
                      >
                        {{ expandedQcKeys.includes(task.rId || index) ? '收起详情' : '展开详情 / 质控曲线' }}
                      </button>
                      <span v-else-if="task.detail_status === 'failed'" class="muted">详情获取失败{{ task.detail_error ? `：${task.detail_error}` : '' }}</span>
                    </div>
                    <div v-if="task.detail && expandedQcKeys.includes(task.rId || index)" class="qc-task-detail">
                      <QcTaskDetailPanel :data="{ data: { qc_task_detail: task.detail } }" />
                    </div>
                  </article>
                </div>
                <p v-else class="source-empty">该时间窗内无{{ entry.pollutant || '目标污染物' }}质控任务。</p>
              </template>

              <template v-else-if="source.key === 'env_power'">
                <div v-if="source.rows.length" class="table-scroll">
                  <table class="evidence-table">
                    <thead><tr><th v-for="col in source.columns" :key="col.key">{{ col.label }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in source.rows" :key="rowIndex">
                        <td v-for="col in source.columns" :key="col.key">{{ row[col.key] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="source-empty">{{ envEmptyHint }}</p>
              </template>

              <template v-else-if="source.columns.length">
                <div class="table-scroll">
                  <table class="evidence-table">
                    <thead><tr><th v-for="col in source.columns" :key="col.key">{{ col.label }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in visibleRows(source)" :key="rowIndex">
                        <td v-for="col in source.columns" :key="col.key">{{ row[col.key] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <button
                  v-if="source.rows.length > TABLE_ROW_LIMIT"
                  type="button"
                  class="link-btn"
                  @click="toggleSourceRows(source.key)"
                >
                  {{ expandedSourceKeys.includes(source.key) ? '收起' : `展开全部 ${source.rows.length} 条` }}
                </button>
                <p v-if="source.truncatedNote" class="truncated-note">{{ source.truncatedNote }}</p>
              </template>

              <p v-else-if="source.rows.length" class="source-empty">该来源数据暂不支持在此预览，请在对话中查看完整证据。</p>
              <p v-else class="source-empty">该来源暂无数据。</p>
            </article>

            <!-- 操作记录 -->
            <article id="wor-section-operations" class="section-card" aria-label="操作记录">
              <header class="section-head">
                <h4>操作记录</h4>
                <span v-if="operations.length" class="muted">{{ operations.length }} 条</span>
              </header>
              <div v-if="!operations.length" class="source-empty">暂无操作记录。</div>
              <ol v-else class="history-list">
                <li v-for="(op, index) in operations" :key="index">
                  <strong>{{ operationActionLabel(op.action, op.label) }}</strong>
                  <span>{{ op.comment || '无意见' }}</span>
                  <small>{{ op.actor?.username || '系统' }} · {{ formatTime(op.at) }}</small>
                </li>
              </ol>
            </article>
          </main>
        </div>
      </template>
    </section>

    <!-- 操作对话框 -->
    <div v-if="dialog.visible" class="dialog-mask" @click.self="closeDialog" @keydown.esc="closeDialog">
      <div class="dialog" role="dialog" aria-modal="true" :aria-label="dialogTitle">
        <header class="dialog-head"><h4>{{ dialogTitle }}</h4></header>
        <div class="dialog-body">
          <p class="dialog-hint">{{ dialogHint }}</p>
          <textarea ref="dialogTextarea" v-model="dialog.comment" rows="4" placeholder="填写意见（退回时必填）"></textarea>
          <label v-if="dialog.action === 'archive' && hasExclusions" class="dialog-check">
            <input v-model="dialog.intervalsConfirmed" type="checkbox" />
            已核验数据剔除区间与合理性
          </label>
        </div>
        <footer class="dialog-actions">
          <button type="button" class="btn btn--secondary" @click="closeDialog">取消</button>
          <button
            type="button"
            class="btn"
            :class="dialog.action === 'reject' ? 'btn--danger' : 'btn--primary'"
            :disabled="actionBusy || (dialog.action === 'reject' && !dialog.comment.trim())"
            @click="submitDialog"
          >
            <span v-if="actionBusy" class="spinner spinner--sm" aria-hidden="true"></span>
            {{ actionBusy ? '提交中…' : '确认' }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 附件图片放大预览 -->
    <div v-if="previewUrl" class="dialog-mask image-mask" @click.self="previewUrl = null">
      <img class="preview-image" :src="previewUrl" alt="附件预览" @click="previewUrl = null" />
      <button type="button" class="ghost-btn close-btn preview-close" aria-label="关闭预览" @click="previewUrl = null">✕</button>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import JiangsuWeatherReviewChart from '@/components/visualization/JiangsuWeatherReviewChart.vue'
import QcTaskDetailPanel from '@/components/visualization/QcTaskDetailPanel.vue'
import ReviewTimeSeriesChart from '@/components/visualization/ReviewTimeSeriesChart.vue'
import {
  getWorkOrderReview,
  getWorkOrderReviewSource,
  fetchWorkOrderReviewAttachmentUrl,
  listWorkOrderReviews,
  submitWorkOrderReviewOperation,
} from '@/services/jiangsuWorkOrderReviewApi.js'
import {
  TABLE_PREFERRED_COLUMNS,
  checkScopeLabel,
  checkStatusLabel,
  columnLabel,
  dataImpactLabel,
  decisionLabelOf,
  operationActionLabel,
  sourceStatusLabel,
  woDetailLabel,
  workflowStatusLabel,
  WO_FIELD_ORDER,
  DEVICE_SECTION_LABELS,
  DETAIL_TIME_KEYS,
  DETAIL_USER_KEYS,
  DETAIL_CONTENT_KEYS,
  DETAIL_STEP_KEYS,
} from '@/services/jiangsuWorkOrderReviewLabels.js'

const props = defineProps({
  workspaceCommand: { type: Object, default: null },
})
defineEmits(['close'])

const SECTION_LABELS = {
  work_order: '工单信息',
  station_hour: '污染物小时时序',
  band: '同城对比带',
  weather: '气象时序',
  alarms: '站房设备告警',
  env_power: '站房动环历史',
  qc: '质控任务清单',
}
const SOURCE_TABLE_FIELDS = {
  band: 'band',
  alarms: 'alarm_logs',
  env_power: 'table_rows',
  qc: 'qc_tasks',
}

const orders = ref([])
const statuses = ref([])
const total = ref(0)
const listLoading = ref(false)
const keyword = ref('')
const statusFilter = ref('')

const selectedCode = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const sourceCache = ref({})
const actionBusy = ref(false)
const actionError = ref('')
const actionMessage = ref('')
const dialog = reactive({ visible: false, action: '', comment: '', intervalsConfirmed: false })
const dialogTextarea = ref(null)

const entry = computed(() => detail.value?.entry || {})
const index = computed(() => detail.value?.index || {})
const judgment = computed(() => index.value.judgment || null)
const operations = computed(() => index.value.operations || [])
const unit = computed(() => sourceCache.value.station_hour?.data?.unit || 'μg/m³')

function tableRows(key) {
  const data = sourceCache.value[key]?.data || {}
  const field = SOURCE_TABLE_FIELDS[key]
  return field ? (data[field] || []) : []
}

function tableColumns(key, rows) {
  if (!rows.length) return []
  const keys = Object.keys(rows[0] || {})
  const preferred = TABLE_PREFERRED_COLUMNS[key] || []
  const ordered = [
    ...preferred.filter(name => keys.includes(name)),
    ...keys.filter(name => !preferred.includes(name)),
  ]
  return ordered
    .map(name => ({ key: name, label: columnLabel(name) }))
    .filter(column => column.label)
    .slice(0, 12)
}

const evidenceSections = computed(() => {
  const sources = index.value.sources || {}
  return Object.keys(SECTION_LABELS)
    .filter(key => sources[key])
    .map(key => {
      const rows = tableRows(key)
      return {
        key,
        label: SECTION_LABELS[key],
        status: sources[key].status || 'skipped',
        recordCount: sources[key].record_count,
        summary: sources[key].summary || '',
        truncatedNote: sources[key].truncated ? '索引未含全部行，完整数据在分文件中' : '',
        rows,
        columns: tableColumns(key, rows),
      }
    })
})

const chartSeries = computed(() => {
  const data = sourceCache.value.station_hour?.data || {}
  const target = (data.points || []).map(point => ({ time: point.time, value: point.value }))
  if (!target.length) return []
  const series = [{ name: `${data.pollutant || entry.value.pollutant || 'PM10'}（本站）`, unit: data.unit || 'μg/m³', color: '#2f86e0', points: target }]
  const pm25 = data.pm25_points || []
  if (pm25.length) series.push({ name: 'PM2.5（对照）', unit: data.unit || 'μg/m³', color: '#9b8cff', points: pm25 })
  const band = sourceCache.value.band?.data?.band || []
  if (band.length) {
    const pick = key => band.filter(row => row[key] != null).map(row => ({ time: row.time, value: row[key] }))
    const overlays = [['min', '同城最低', '#94a3b8'], ['median', '同城中位', '#61d394'], ['max', '同城最高', '#f6bd4a']]
    overlays.forEach(([key, name, color]) => {
      const points = pick(key)
      if (points.length) series.push({ name, unit: data.unit || 'μg/m³', color, points })
    })
  }
  return series
})
const markAreas = computed(() => index.value.mark_areas || [])
const weatherRows = computed(() => sourceCache.value.weather?.data?.rows || [])
const weatherPayload = computed(() => ({
  start: entry.value.window_start,
  end: entry.value.window_end,
  data: weatherRows.value,
}))
const weatherEntry = computed(() => {
  const data = sourceCache.value.station_hour?.data || {}
  const points = (data.points || []).map(point => ({ time: point.time, value: point.value }))
  return {
    title: `${entry.value.pollutant || ''} 与气象时序`,
    unit: data.unit || 'μg/m³',
    series: points.length ? [{ name: `${data.pollutant || entry.value.pollutant}（本站）`, points }] : [],
  }
})

const workOrderData = computed(() => sourceCache.value.work_order?.data || {})
const sectionContent = ref(null)
const activeSectionKey = ref('judgment')
const expandedQcKeys = ref([])
const expandedSourceKeys = ref([])
const TABLE_ROW_LIMIT = 20

function toggleQcDetail(key) {
  expandedQcKeys.value = expandedQcKeys.value.includes(key)
    ? expandedQcKeys.value.filter(item => item !== key)
    : [...expandedQcKeys.value, key]
}

function toggleSourceRows(key) {
  expandedSourceKeys.value = expandedSourceKeys.value.includes(key)
    ? expandedSourceKeys.value.filter(item => item !== key)
    : [...expandedSourceKeys.value, key]
}

function visibleRows(source) {
  if (expandedSourceKeys.value.includes(source.key)) return source.rows
  return source.rows.slice(0, TABLE_ROW_LIMIT)
}

// 质控任务：只保留目标污染物任务，展示合格结果并可展开质控曲线
const qcTasks = computed(() => {
  const tasks = sourceCache.value.qc?.data?.qc_tasks || []
  return tasks.map(task => {
    const detailTask = task.detail?.task || {}
    return {
      ...task,
      poll: task.target_pollutant || task.poll || detailTask.poll,
      qcType: task.qcType || detailTask.qc_type,
      qc_result: detailTask.qc_result || task.qc_result || task.result,
      task_status_label: detailTask.task_status_label,
      detail: task.detail || null,
    }
  })
})

function qcResultText(task) {
  const result = String(task.qc_result || '').trim()
  if (!result) return task.task_status_label || '结果未知'
  if (/合格|pass|normal|success/i.test(result)) return '合格'
  if (/不合格|异常|fail|ng/i.test(result)) return '不合格'
  return result
}

function qcResultClass(task) {
  const result = String(task.qc_result || '').trim()
  if (/合格|pass|normal|success/i.test(result) && !/不合格/i.test(result)) return 'ok'
  if (result) return 'bad'
  return 'neutral'
}

const envEmptyHint = computed(() => {
  const source = index.value.sources?.env_power || {}
  if (source.status === 'skipped') return source.summary || '无动环类告警，未抓取动环历史。'
  return '窗口内无动环异常记录（正常逐时数据已过滤，不参与研判）。'
})

const workbenchSections = computed(() => {
  const sources = index.value.sources || {}
  const entries = [
    { key: 'judgment', label: 'AI 研判结果', state: judgment.value ? 'ok' : 'empty' },
    ...Object.keys(SECTION_LABELS)
      .filter(key => sources[key])
      .map(key => ({
        key,
        label: SECTION_LABELS[key],
        state: sources[key].status === 'success' ? 'ok' : (sources[key].status === 'skipped' ? 'empty' : 'warn'),
      })),
    { key: 'operations', label: '操作记录', state: operations.value.length ? 'ok' : 'empty' },
  ]
  return entries.map((item, position) => ({ ...item, index: position + 1, stateClass: item.state }))
})

function scrollToSection(key) {
  activeSectionKey.value = key
  const container = sectionContent.value
  const target = document.getElementById(`wor-section-${key}`)
  if (!container || !target) return
  const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top
  container.scrollTo({ top: Math.max(0, container.scrollTop + offset), behavior: 'smooth' })
}

function updateActiveSection() {
  const container = sectionContent.value
  if (!container) return
  const sections = [...container.querySelectorAll('[id^="wor-section-"]')]
  const containerTop = container.getBoundingClientRect().top
  const current = sections.filter(section => section.getBoundingClientRect().top <= containerTop + 8).at(-1) || sections[0]
  if (current?.id) activeSectionKey.value = current.id.replace('wor-section-', '')
}

const attachmentUrls = ref({})
const previewUrl = ref(null)

function scalarFacts(source, excludeKeys = []) {
  if (!source || typeof source !== 'object') return []
  return Object.entries(source)
    .filter(([key, value]) => !excludeKeys.includes(key)
      && value != null && value !== '' && ['string', 'number', 'boolean'].includes(typeof value))
    .map(([key, value]) => ({ key, label: woDetailLabel(key), value: String(value) }))
    .filter(item => item.label)
}

// 源平台详单结构：data.order（清单条目）+ data.wo（详单主表）；主表优先，清单补缺
const woFacts = computed(() => {
  const data = workOrderData.value
  const merged = { ...(data.order || {}), ...(data.wo || {}) }
  return scalarFacts(merged)
    .sort((left, right) => {
      const leftIndex = WO_FIELD_ORDER.indexOf(left.key)
      const rightIndex = WO_FIELD_ORDER.indexOf(right.key)
      if (leftIndex >= 0 || rightIndex >= 0) {
        return (leftIndex < 0 ? WO_FIELD_ORDER.length : leftIndex)
          - (rightIndex < 0 ? WO_FIELD_ORDER.length : rightIndex)
      }
      return left.label.localeCompare(right.label, 'zh-Hans')
    })
    .slice(0, 32)
})

const deviceSections = computed(() => Object.entries(DEVICE_SECTION_LABELS)
  .map(([key, label]) => ({ key, label, entries: scalarFacts(workOrderData.value[key]).slice(0, 12) }))
  .filter(section => section.entries.length))

const woSteps = computed(() => {
  const steps = workOrderData.value.workFlowInfo?.stepList || []
  return steps
    .map(step => {
      const status = workflowStatusLabel(step?.status)
      return {
        name: step?.taskName || step?.name || '—',
        statusText: status.text,
        statusKey: status.key,
        time: step?.createTime || step?.finishTime || '',
      }
    })
    .filter(step => step.name !== '—' || step.time)
})

const woDetails = computed(() => (workOrderData.value.details || [])
  .map(row => {
    if (!row || typeof row !== 'object') return null
    const pick = keys => keys.map(key => row[key]).find(value => value != null && value !== '') || ''
    return {
      time: pick(DETAIL_TIME_KEYS),
      user: pick(DETAIL_USER_KEYS),
      content: pick(DETAIL_CONTENT_KEYS),
      step: pick(DETAIL_STEP_KEYS),
    }
  })
  .filter(item => item && (item.content || item.time || item.user || item.step)))

const woAttachments = computed(() => (workOrderData.value.attachments || [])
  .map((attachment, index) => {
    const name = String(attachment?.fileName || `附件 ${index + 1}`)
    const type = String(attachment?.content_type || '')
    const isImage = type.startsWith('image/')
      || /\.(png|jpe?g|gif|bmp|webp)$/i.test(name)
    return {
      index,
      name,
      type,
      status: attachment?.download_status || 'pending',
      isImage,
      size: attachment?.size_bytes || 0,
      url: attachmentUrls.value[index] || null,
    }
  }))

function releaseAttachmentUrls() {
  Object.values(attachmentUrls.value).forEach(url => URL.revokeObjectURL(url))
  attachmentUrls.value = {}
  previewUrl.value = null
}

async function loadAttachmentUrls(code) {
  releaseAttachmentUrls()
  const attachments = workOrderData.value.attachments || []
  if (!attachments.length) return
  const urls = {}
  await Promise.all(attachments.map(async (attachment, index) => {
    if (attachment?.download_status !== 'success') return
    try {
      urls[index] = await fetchWorkOrderReviewAttachmentUrl(code, index)
    } catch {
      // 单个附件加载失败不阻断整体展示，卡片显示原始状态
    }
  }))
  attachmentUrls.value = urls
}

const decisionText = computed(() => judgment.value?.decision_label || decisionLabelOf(judgment.value?.decision))
const decisionChipClass = computed(() => {
  const decision = String(judgment.value?.decision || '').toLowerCase()
  if (decision === 'pass' || decision === 'confirm') return 'ok'
  if (decision === 'reject' || decision === 'needs_evidence') return 'bad'
  return 'neutral'
})
const dataImpactChips = computed(() => (judgment.value?.data_impact || [])
  .map(item => {
    const impact = dataImpactLabel(item.decision)
    const pollutant = String(item.pollutant || '').trim()
    return pollutant ? `${pollutant} ${impact}` : impact
  })
  .filter(Boolean))
const hasExclusions = computed(() => (judgment.value?.data_impact || [])
  .some(item => ['exclude', 'partial_exclude'].includes(String(item.decision || ''))))

const dialogTitle = computed(() => ({ feedback: '反馈意见', reject: '退回工单审核', archive: '归档审核结论' }[dialog.action] || '工单操作'))
const dialogHint = computed(() => ({
  feedback: '反馈将记录到操作历史；涉及结论修正时建议同步在对话中发起增量复审。',
  reject: '退回后如存在 AI 审核记录，会触发以退回意见为基准的增量复审。',
  archive: '归档表示人工确认通过，证据包与审核记录将定格。',
}[dialog.action] || ''))

const statusClass = status => ({
  '已归档': 'st-ok',
  '待归档': 'st-info',
  '已退回': 'st-bad',
  '待补证': 'st-warn',
  '处置中': 'st-warn',
  '待审核': 'st-info',
}[status] || 'st-info')

function pad(value) {
  return String(value).padStart(2, '0')
}

function shortTime(value) {
  const text = String(value || '')
  return text.length >= 16 ? text.slice(5, 16) : text
}

function formatTime(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (!Number.isFinite(parsed.getTime())) return String(value).slice(0, 16)
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

async function loadOrders() {
  listLoading.value = true
  actionError.value = ''
  try {
    const payload = await listWorkOrderReviews({
      keyword: keyword.value || undefined,
      status: statusFilter.value || undefined,
      limit: 100,
    })
    orders.value = payload.orders || []
    statuses.value = payload.statuses || []
    total.value = payload.total || orders.value.length
  } catch (error) {
    actionError.value = error.message
  } finally {
    listLoading.value = false
  }
}

function applyFilters() {
  loadOrders()
}

async function loadSource(code, name) {
  if (sourceCache.value[name]) return
  try {
    const payload = await getWorkOrderReviewSource(code, name)
    sourceCache.value = { ...sourceCache.value, [name]: payload }
  } catch {
    sourceCache.value = { ...sourceCache.value, [name]: { source: name, data: null } }
  }
}

async function openDetail(code) {
  selectedCode.value = code
  detail.value = null
  sourceCache.value = {}
  releaseAttachmentUrls()
  expandedQcKeys.value = []
  expandedSourceKeys.value = []
  activeSectionKey.value = 'judgment'
  actionError.value = ''
  actionMessage.value = ''
  detailLoading.value = true
  try {
    detail.value = await getWorkOrderReview(code)
    await Promise.all(Object.keys(SECTION_LABELS).map(name => loadSource(code, name)))
    await loadAttachmentUrls(code)
  } catch (error) {
    detail.value = null
    actionError.value = error.message
  } finally {
    detailLoading.value = false
  }
}

function backToList() {
  selectedCode.value = null
  detail.value = null
  releaseAttachmentUrls()
  loadOrders()
}

function openDialog(action) {
  dialog.action = action
  dialog.comment = ''
  dialog.intervalsConfirmed = false
  dialog.visible = true
  actionError.value = ''
  actionMessage.value = ''
}

function closeDialog() {
  dialog.visible = false
}

async function submitDialog() {
  actionBusy.value = true
  actionError.value = ''
  try {
    await submitWorkOrderReviewOperation(selectedCode.value, {
      action: dialog.action,
      comment: dialog.comment.trim(),
      intervalsConfirmed: dialog.intervalsConfirmed,
    })
    dialog.visible = false
    actionMessage.value = { feedback: '反馈已记录。', reject: '已退回。', archive: '已归档。' }[dialog.action]
    detail.value = await getWorkOrderReview(selectedCode.value)
  } catch (error) {
    actionError.value = error.message
  } finally {
    actionBusy.value = false
  }
}

watch(() => dialog.visible, visible => {
  if (visible) nextTick(() => dialogTextarea.value?.focus())
})

watch(() => props.workspaceCommand, command => {
  const code = command?.working_order_code
  if (!code) return
  if (code === selectedCode.value && detail.value) return
  openDetail(String(code))
}, { immediate: true })

loadOrders()
</script>

<style scoped>
.wor-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-muted);
  color: var(--text-1);
  font-size: var(--text-size-sm);
}

.wor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: var(--panel-header-h);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border-1);
  background: var(--bg-container);
}

.wor-title h3 {
  margin: 0;
  font-size: var(--text-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-title);
  color: var(--text-1);
}

.wor-title p {
  margin: 2px 0 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.wor-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* 按钮：默认 / hover / active / disabled 四态 + focus-visible */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: var(--control-h-md);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
  line-height: var(--line-height-compact);
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--transition-base), background var(--transition-base), border-color var(--transition-base);
}

.btn:hover:not(:disabled) {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.btn:disabled {
  background: var(--bg-disabled);
  border-color: var(--border-3);
  color: var(--text-disabled);
  cursor: not-allowed;
}

.btn--primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--bg-container);
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: var(--bg-container);
}

.btn--primary:active:not(:disabled) {
  background: var(--color-primary-active);
  border-color: var(--color-primary-active);
}

.btn--danger {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: var(--bg-container);
}

.btn--danger:hover:not(:disabled) {
  background: var(--color-danger-hover);
  border-color: var(--color-danger-hover);
  color: var(--bg-container);
}

.btn--text {
  padding: 0 var(--space-2);
  border-color: transparent;
  background: transparent;
  color: var(--text-2);
}

.btn--text:hover:not(:disabled) {
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border-color: transparent;
}

.close-btn .icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
}

.wor-banners {
  display: grid;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4) 0;
}

.action-error {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-danger);
}

.action-message {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-success);
}

.wor-list-view,
.wor-detail-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-3) var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.wor-detail-view {
  overflow: hidden;
}

/* 审核工作台：左侧目录 + 右侧分节内容（参照智能事件） */
.workbench-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin: 0 calc(var(--space-4) * -1) calc(var(--space-5) * -1);
  background: var(--bg-muted);
}

.workbench-index {
  flex: 0 0 176px;
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 0 var(--space-2) var(--space-3) 0;
}

.workbench-index-title {
  margin: 0 0 var(--space-2);
  padding: var(--space-3) 0 var(--space-2) var(--space-3);
  color: var(--text-1);
  font-size: var(--text-size-base);
  font-weight: var(--font-weight-semibold);
}

.workbench-index-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  min-height: 36px;
  border: 0;
  border-left: 3px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  padding: var(--space-2) var(--space-3);
  text-align: left;
  font-size: var(--text-size-sm);
  font-family: inherit;
  transition: background 0.15s ease, color 0.15s ease;
}

.workbench-index-item:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.workbench-index-item.active {
  border-left-color: var(--color-primary);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.index-state {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-disabled);
}

.index-state.ok { background: var(--color-success); }
.index-state.warn { background: var(--color-warning, #d7a84e); }
.index-state.empty { background: var(--text-disabled); }

.workbench-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 var(--space-4) var(--space-5) 0;
}

/* 质控任务卡片 */
.qc-task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.qc-task-card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
}

.qc-task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.qc-task-title {
  display: grid;
  gap: 2px;
}

.qc-task-title strong {
  font-size: var(--text-size-sm);
  color: var(--text-1);
}

.link-btn {
  align-self: flex-start;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  padding: 0;
  font-size: var(--text-size-sm);
  font-family: inherit;
}

.link-btn:hover {
  text-decoration: underline;
}

.qc-task-detail {
  border-top: 1px dashed var(--border-2);
  padding-top: var(--space-3);
}

.wor-toolbar {
  display: flex;
  gap: var(--space-2);
}

.wor-search {
  flex: 1;
  min-height: var(--control-h-md);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
}

.wor-search::placeholder {
  color: var(--text-3);
}

.wor-search:hover {
  border-color: var(--color-primary-hover);
}

.wor-search:focus {
  outline: none;
  border-color: var(--color-primary);
}

.wor-search:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.wor-status-select {
  min-height: var(--control-h-md);
  padding: 0 var(--space-2);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
}

.wor-status-select:hover {
  border-color: var(--color-primary-hover);
}

.wor-status-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.wor-status-select:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.wor-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-7) var(--space-3);
  color: var(--text-3);
  font-size: var(--text-size-sm);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-primary-bg-hover);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: wor-spin 0.8s linear infinite;
}

.spinner--sm {
  width: 12px;
  height: 12px;
}

@keyframes wor-spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-7) var(--space-4);
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  fill: none;
  stroke: var(--text-disabled);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.empty-title {
  margin: 0;
  font-size: var(--text-size-base);
  color: var(--text-2);
}

.empty-hint {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.wor-order-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.wor-order-card {
  width: 100%;
  display: grid;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  background: var(--bg-container);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}

.wor-order-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-2);
}

.wor-order-card:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.order-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.order-code {
  font-family: var(--font-mono);
  font-size: var(--text-size-xs);
  color: var(--text-2);
}

.order-title {
  font-size: var(--text-size-base);
  color: var(--text-1);
}

.order-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--text-size-xs);
  color: var(--text-2);
}

.order-foot {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.wor-total {
  margin: 0;
  text-align: center;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

/* 状态徽章（规范 §6.3） */
.status-badge {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-size-xs);
}

.st-ok { background: var(--color-success-bg); color: var(--color-success); }
.st-info { background: var(--color-primary-bg); color: var(--color-primary); }
.st-warn { background: var(--color-warning-bg); color: var(--color-warning-text); }
.st-bad { background: var(--color-danger-bg); color: var(--color-danger); }

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.detail-heading h3 {
  margin: var(--space-1) 0;
  font-size: var(--text-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-1);
}

.detail-heading p {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.action-bar {
  display: flex;
  gap: var(--space-2);
}

.section-card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  background: var(--bg-container);
}

.section-card.judgment {
  border-left: 3px solid var(--color-primary);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.section-head h4 {
  margin: 0;
  font-size: var(--text-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-1);
}

.source-meta {
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.source-meta.st-success,
.source-meta.st-pass { color: var(--color-success); }
.source-meta.st-failed,
.source-meta.st-empty { color: var(--color-danger); }
.source-meta.st-partial,
.source-meta.st-unavailable { color: var(--color-warning-text); }

.source-summary {
  margin: 0;
  font-size: var(--text-size-sm);
  color: var(--text-2);
}

.source-empty {
  margin: 0;
  font-size: var(--text-size-sm);
  color: var(--text-3);
}

.muted {
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.judgment-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-size-xs);
  background: var(--bg-muted);
  color: var(--text-2);
}

.chip.ok { background: var(--color-success-bg); color: var(--color-success); }
.chip.bad { background: var(--color-danger-bg); color: var(--color-danger); }
.chip.neutral { background: var(--bg-muted); color: var(--text-2); }

.fact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-1);
}

.fact-item {
  display: grid;
  gap: 2px;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
}

.fact-item span {
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.fact-item strong {
  font-size: var(--text-size-sm);
  color: var(--text-1);
  word-break: break-all;
}

.table-scroll {
  overflow-x: auto;
}

/* 卡片内数据表：规范 §6.4 无边框紧凑变体 */
.evidence-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-size-sm);
}

.evidence-table th,
.evidence-table td {
  padding: var(--space-2);
  text-align: left;
  vertical-align: top;
  color: var(--text-1);
  border-bottom: 1px solid var(--border-1);
}

.evidence-table th {
  background: var(--bg-muted);
  color: var(--text-2);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.evidence-table tbody tr:last-child td {
  border-bottom: 0;
}

.basis-cell {
  max-width: 420px;
}

.truncated-note {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-warning-text);
}

.history-list {
  margin: 0;
  padding-left: var(--space-5);
  display: grid;
  gap: var(--space-1);
  font-size: var(--text-size-sm);
  color: var(--text-1);
}

.history-list small {
  color: var(--text-3);
}

/* 对话框（规范 §4.4） */
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: var(--space-4);
  background: rgba(15, 23, 42, 0.38);
}

.dialog {
  width: min(520px, 100%);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--bg-container);
  box-shadow: var(--shadow-3);
}

.dialog-head {
  display: flex;
  align-items: center;
  min-height: var(--panel-header-h);
  padding: 0 var(--space-6);
  border-bottom: 1px solid var(--border-1);
}

.dialog-head h4 {
  margin: 0;
  font-size: var(--text-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-1);
}

.dialog-body {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-6);
}

.dialog-hint {
  margin: 0;
  font-size: var(--text-size-sm);
  line-height: var(--line-height-body);
  color: var(--text-2);
}

.dialog textarea {
  width: 100%;
  box-sizing: border-box;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
  line-height: var(--line-height-body);
  resize: vertical;
}

.dialog textarea::placeholder {
  color: var(--text-3);
}

.dialog textarea:hover {
  border-color: var(--color-primary-hover);
}

.dialog textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.dialog textarea:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.dialog-check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-size-sm);
  color: var(--text-1);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6) var(--space-6);
}

/* 工单信息子区块（源平台详单结构） */
.sub-section {
  display: grid;
  gap: 6px;
  border-top: 1px dashed var(--border-1, #e2e8f1);
  padding-top: 8px;
}

.sub-section h5 {
  margin: 0;
  font-size: 12px;
  color: var(--text-2);
  font-weight: 600;
}

.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-1);
}

.step-list li small {
  margin-left: auto;
  color: var(--text-3);
}

.step-list li em {
  font-style: normal;
  font-size: 11px;
  color: var(--text-3);
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #b6c2d2;
  flex: none;
}

.step-dot.st-ok {
  background: #1e7f46;
}

.step-dot.st-info {
  background: #2563c4;
}

.attachment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.attachment-grid figure {
  margin: 0;
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: var(--text-3);
}

.attachment-grid figure.failed {
  opacity: 0.6;
}

.attachment-thumb {
  width: 100%;
  height: 104px;
  padding: 0;
  border: 1px solid var(--border-1, #e2e8f1);
  border-radius: 6px;
  overflow: hidden;
  background: #f6f8fb;
  cursor: zoom-in;
}

.attachment-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.attachment-file {
  font-size: 12px;
  color: #2563c4;
  text-decoration: none;
  word-break: break-all;
}

.attachment-file.muted {
  color: var(--text-3);
}

.attachment-grid figcaption {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  word-break: break-all;
}

.attachment-grid figcaption em {
  font-style: normal;
  flex: none;
}

.image-mask {
  z-index: calc(var(--z-modal) + 1);
}

.preview-image {
  max-width: min(92vw, 1200px);
  max-height: 86vh;
  border-radius: 8px;
  box-shadow: var(--shadow-3);
  cursor: zoom-out;
}

.preview-close {
  position: fixed;
  top: 16px;
  right: 20px;
  background: #fff;
}
</style>


