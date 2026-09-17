<template>
  <section class="qc-task-detail">
    <header class="qc-header">
      <div class="qc-heading">
        <span class="eyebrow">QUALITY CONTROL</span>
        <strong>{{ task.station_name || '站点' }} · {{ pollText }}</strong>
        <div class="qc-meta">
          <span>站点编码：{{ task.station_code || '—' }}</span>
          <span>唯一编码：{{ task.unique_code || '—' }}</span>
          <span>{{ task.start_time || '—' }} ~ {{ task.end_time || '—' }}</span>
        </div>
      </div>
      <div class="qc-verdict" :class="resultClass">
        <span class="verdict-label">质控结果</span>
        <strong>{{ task.qc_result || '—' }}</strong>
        <small>{{ task.task_status_label || '状态未返回' }}</small>
      </div>
    </header>

    <div class="qc-metrics">
      <article>
        <span>质控类型</span>
        <strong>{{ task.task_type_name || task.qc_type || '—' }}</strong>
      </article>
      <article>
        <span>响应浓度</span>
        <strong>{{ valueText(task.relevant_value) }}</strong>
      </article>
      <article>
        <span>相对误差</span>
        <strong>{{ relativeErrorText }}</strong>
      </article>
      <article>
        <span>零气 / 标气流量</span>
        <strong>{{ flowText }}</strong>
      </article>
    </div>

    <section class="qc-card">
      <div class="card-title"><span>任务执行步骤</span><b>{{ steps.length }}</b></div>
      <div v-if="steps.length" class="steps-strip">
        <article
          v-for="(step, index) in steps"
          :key="`${step.name}-${index}`"
          class="step-card"
          :class="stepClass(step.status)"
        >
          <header class="step-name">{{ step.name || `步骤 ${index + 1}` }}</header>
          <ul v-if="step.actions.length" class="step-items">
            <li v-for="(action, actionIndex) in step.actions" :key="`${action.name}-${actionIndex}`">
              <span class="item-label">
                <i v-if="action.status === 1" class="item-flag running"></i>
                <i v-else-if="action.status === 2" class="item-flag done">✓</i>
                {{ action.name || '检查项' }}
              </span>
              <span class="item-value">{{ actionValue(action) }}</span>
            </li>
          </ul>
          <p v-else class="step-card-empty">无检查项</p>
          <footer class="step-status">
            <span class="status-dot" :class="stepClass(step.status)">{{ stepStatusSymbol(step.status) }}</span>
            <em>{{ stepStatusText(step.status) }}</em>
          </footer>
        </article>
      </div>
      <p v-else class="card-empty">接口未返回任务步骤。</p>
    </section>

    <div class="qc-columns">
      <section class="qc-card">
        <div class="card-title"><span>结果项</span><b>{{ resultValues.length }}</b></div>
        <div v-if="resultValues.length" class="value-group">
          <div v-for="(row, index) in resultValues" :key="`r-${index}`" class="value-row">
            <span>{{ row.name || '结果' }}</span>
            <b>{{ row.value || '—' }}</b>
          </div>
        </div>
        <p v-else class="card-empty">接口未返回结果项。</p>
      </section>

      <section class="qc-card">
        <div class="card-title"><span>计算数据项</span><b>{{ dataValues.length }}</b></div>
        <div v-if="dataValues.length" class="value-group">
          <div v-for="(row, index) in dataValues" :key="`d-${index}`" class="value-row">
            <span>{{ row.name || '数据' }}</span>
            <b>{{ row.value || '—' }}</b>
          </div>
        </div>
        <p v-else class="card-empty">接口未返回计算数据项。</p>
      </section>
    </div>

    <section class="qc-card">
      <div class="card-title"><span>质控监测曲线</span><b>{{ curve.length }}</b></div>
      <div v-if="hasCurve" ref="chartRef" class="qc-chart"></div>
      <p v-else-if="curve.length" class="card-empty">监测值均为无效标记（-99/-999），无可绘制曲线。</p>
      <p v-else class="card-empty">接口未返回监测曲线数据。</p>
    </section>

    <section class="qc-card">
      <div class="card-title"><span>质控日志</span><b>{{ runLogs.length }}</b></div>
      <div v-if="runLogs.length" class="log-table">
        <div class="log-head">
          <span>时间</span><span>类型</span><span>日志信息</span>
        </div>
        <div v-for="(log, index) in runLogs" :key="`log-${index}`" class="log-row">
          <span>{{ log.record_time || '—' }}</span>
          <span>{{ log.target || '—' }}</span>
          <span :title="log.message">{{ log.message || '—' }}</span>
        </div>
      </div>
      <p v-else class="card-empty">接口未返回质控日志。</p>
    </section>

    <p class="qc-source">
      数据来源：江苏运维平台质控历史接口（任务状态 / 运行日志 / 监测曲线），仅展示接口返回内容，不推断、不补造。
      更新于 {{ updateTimeText }}
    </p>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { DataZoomComponent, GridComponent, MarkAreaComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([DataZoomComponent, GridComponent, MarkAreaComponent, TooltipComponent, LineChart, CanvasRenderer])

const props = defineProps({ data: { type: Object, required: true } })

const payload = computed(() => props.data?.data?.qc_task_detail || {})
const task = computed(() => payload.value.task || {})
const steps = computed(() => (Array.isArray(payload.value.steps) ? payload.value.steps : []))
const resultValues = computed(() => (Array.isArray(payload.value.result_values) ? payload.value.result_values : []))
const dataValues = computed(() => (Array.isArray(payload.value.data_values) ? payload.value.data_values : []))
const runLogs = computed(() => (Array.isArray(payload.value.run_logs) ? payload.value.run_logs : []))
const curve = computed(() => (Array.isArray(payload.value.curve) ? payload.value.curve : []))

const pollText = computed(() => {
  const poll = String(task.value.poll || '').trim()
  const qcType = String(task.value.qc_type || '').trim()
  return [poll, qcType].filter(Boolean).join(' ') || '质控任务'
})
const resultClass = computed(() => {
  const result = String(task.value.qc_result || '')
  if (result.includes('不合格')) return 'failed'
  if (result.includes('合格')) return 'passed'
  return 'unknown'
})
const relativeErrorText = computed(() => {
  const value = task.value.inaccuracy
  return isMeaningful(value) ? `${(Number(value) * 100).toFixed(2)}%` : '—'
})
const flowText = computed(() => {
  const zero = task.value.zero_air_flow
  const span = task.value.std_air_flow
  if (zero == null && span == null) return '—'
  return `${zero ?? '—'} / ${span ?? '—'}`
})
const updateTimeText = computed(() => {
  const raw = payload.value.updated_at
  const date = raw ? new Date(raw) : null
  if (!date || Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { hour12: false })
})
const hasCurve = computed(() => chartPoints.value.length > 0)

// 平台用 -99 / -999 标记无效观测值，展示与绘图前统一过滤。
const isMeaningful = value => {
  const number = Number(value)
  return Number.isFinite(number) && number > -90
}

const valueText = value => {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (Number.isFinite(number)) return isMeaningful(number) ? String(number) : '—'
  return String(value)
}
const stepStatusText = status => {
  if (status === 0) return '待执行'
  if (status === 1) return '执行中'
  if (status === 2) return '已完成'
  if (status === 3) return '已中止'
  if (status === 4) return '中止中'
  return status == null ? '状态未提供' : '未知'
}
const stepStatusSymbol = status => {
  if (status === 1) return '◌'
  if (status === 2) return '✓'
  if (status === 3) return '✕'
  if (status === 4) return '−'
  return '○'
}
const actionValue = action => {
  if (action.value) return action.value
  if (action.status === 2) return '已完成'
  if (action.status === 1) return '进行中'
  return '—'
}
const stepClass = status => {
  if (status === 2) return 'done'
  if (status === 1) return 'active'
  if (status === 3 || status === 4) return 'aborted'
  return 'pending'
}

const parseTime = value => {
  const raw = String(value || '').trim()
  if (!raw) return null
  const timestamp = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'))
  return Number.isFinite(timestamp) ? timestamp : null
}
const formatTime = value => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = number => String(number).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const chartPoints = computed(() => curve.value
  .map(point => [parseTime(point.time_point), Number(point.value)])
  .filter(point => Number.isFinite(point[0]) && isMeaningful(point[1])))
const curveUnit = computed(() => {
  const unit = curve.value.find(point => point.unit)?.unit
  if (unit) return unit
  return String(task.value.poll || '').toUpperCase() === 'CO' ? 'ppm' : 'ppb'
})
const qcWindow = computed(() => {
  const start = parseTime(task.value.start_time)
  const end = parseTime(task.value.end_time)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null
  return [start, end]
})

const chartRef = ref(null)
let chart = null
let resizeObserver = null

const renderChart = () => {
  if (!chartRef.value || !chartPoints.value.length) return
  if (!chart) chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  const window = qcWindow.value
  chart.setOption({
    animationDuration: 240,
    color: ['#2f86e0'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      textStyle: { color: '#111827', fontSize: 11 },
      formatter: params => {
        const rows = Array.isArray(params) ? params : [params]
        const value = rows[0]?.value?.[1]
        const time = rows[0]?.value?.[0]
        return `${formatTime(time)}<br/>${rows[0]?.marker || ''}监测值：${Number.isFinite(value) ? value : '-'} ${curveUnit.value}`
      }
    },
    grid: { top: 20, right: 18, bottom: 42, left: 48, containLabel: true },
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisLine: { lineStyle: { color: 'rgba(17, 24, 39, .24)' } },
      axisTick: { show: false },
      axisLabel: { color: '#111827', fontSize: 10, formatter: formatTime }
    },
    yAxis: {
      type: 'value',
      name: curveUnit.value,
      nameTextStyle: { color: '#111827', fontSize: 10 },
      axisLabel: { color: '#111827', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(17, 24, 39, .12)' } }
    },
    dataZoom: [{ type: 'inside', filterMode: 'none' }],
    series: [{
      name: '监测值',
      type: 'line',
      smooth: 0.2,
      showSymbol: chartPoints.value.length <= 40,
      symbolSize: 4,
      connectNulls: false,
      data: chartPoints.value,
      markArea: window
        ? {
            silent: true,
            itemStyle: { color: 'rgba(47, 134, 224, .1)' },
            data: [[{ xAxis: window[0] }, { xAxis: window[1] }]]
          }
        : undefined
    }]
  }, true)
}

watch(chartPoints, () => nextTick(renderChart), { deep: true })

onMounted(() => {
  renderChart()
  if (chartRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  } else {
    window.addEventListener('resize', renderChart)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', renderChart)
  chart?.dispose()
})
</script>

<style scoped>
.qc-task-detail { display: grid; gap: 12px; min-width: 720px; color: #111827; font-family: "Microsoft YaHei", sans-serif; }
.qc-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 16px; border-radius: 8px; background: linear-gradient(90deg, rgba(47, 134, 224, .12), rgba(47, 134, 224, .03)); }
.qc-heading { display: grid; gap: 5px; }
.qc-heading .eyebrow { color: #2f86e0; font-size: 10px; letter-spacing: 2px; }
.qc-heading strong { font-size: 19px; }
.qc-meta { display: flex; flex-wrap: wrap; gap: 16px; color: #4b5563; font-size: 11px; }
.qc-verdict { display: grid; gap: 2px; min-width: 120px; padding: 8px 16px; border-radius: 8px; text-align: center; }
.qc-verdict .verdict-label { font-size: 10px; letter-spacing: 1px; }
.qc-verdict strong { font-size: 20px; }
.qc-verdict small { font-size: 10px; opacity: .8; }
.qc-verdict.passed { background: rgba(21, 128, 61, .1); color: #15803d; }
.qc-verdict.failed { background: rgba(185, 28, 28, .1); color: #b91c1c; }
.qc-verdict.unknown { background: rgba(107, 114, 128, .1); color: #4b5563; }
.qc-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.qc-metrics article { display: grid; gap: 6px; padding: 10px 12px; border-radius: 6px; background: #f6f8fb; }
.qc-metrics span { color: #6b7280; font-size: 11px; }
.qc-metrics strong { font-size: 15px; }
.qc-columns { display: grid; grid-template-columns: repeat(2, minmax(240px, 1fr)); gap: 12px; }
.qc-card { display: grid; gap: 10px; align-content: start; }
.card-title { display: flex; align-items: center; gap: 8px; padding-bottom: 7px; border-bottom: 1px solid rgba(17, 24, 39, .1); color: #111827; font-size: 13px; font-weight: 700; }
.card-title::before { width: 3px; height: 13px; border-radius: 2px; background: #2f86e0; content: ""; }
.card-title b { margin-left: auto; padding: 1px 8px; border-radius: 999px; background: rgba(47, 134, 224, .12); color: #2f86e0; font-size: 11px; }
.card-empty { margin: 0; padding: 12px 0; color: #6b7280; font-size: 12px; }
.steps-strip { display: flex; gap: 10px; padding: 2px 2px 8px; overflow-x: auto; }
.step-card { display: grid; grid-template-rows: auto 1fr auto; flex: 1 0 230px; min-width: 230px; max-width: 280px; border-radius: 6px; background: #f6f8fb; overflow: hidden; }
.step-name { padding: 7px 10px; color: #fff; font-size: 12px; font-weight: 700; text-align: center; background: linear-gradient(90deg, #2f86e0, #57a8ef); }
.step-card.aborted .step-name { background: linear-gradient(90deg, #b91c1c, #d95757); }
.step-card.pending .step-name { background: linear-gradient(90deg, #9ca3af, #b6bdc7); }
.step-items { display: grid; gap: 5px; max-height: 232px; margin: 0; padding: 8px; list-style: none; overflow: auto; }
.step-items li { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 6px; border-radius: 4px; background: #fff; font-size: 11px; }
.item-label { display: inline-flex; align-items: center; gap: 5px; min-width: 0; color: #374151; }
.item-flag { display: inline-grid; width: 14px; height: 14px; place-content: center; border-radius: 50%; color: #fff; font-size: 9px; font-style: normal; }
.item-flag.done { background: #52c51a; }
.item-flag.running { border: 2px solid rgba(255, 176, 55, .35); border-top-color: #ffb037; background: transparent; }
.item-value { flex: none; max-width: 46%; padding: 0 5px; border-radius: 4px; background: rgba(47, 134, 224, .1); color: #2f86e0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-card-empty { margin: 0; padding: 12px; color: #9ca3af; font-size: 11px; text-align: center; }
.step-status { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 6px; background: #eef2f7; }
.status-dot { display: inline-grid; width: 22px; height: 22px; place-content: center; border-radius: 50%; background: #9ca3af; color: #fff; font-size: 12px; }
.status-dot.done { background: #52c51a; }
.status-dot.active { background: #2f86e0; }
.status-dot.aborted { background: #b91c1c; }
.status-dot.pending { background: #9ca3af; }
.step-status em { color: #4b5563; font-size: 10px; font-style: normal; }
.value-group { display: grid; gap: 0; }
.value-row { display: flex; justify-content: space-between; gap: 10px; padding: 5px 2px; border-bottom: 1px dashed rgba(17, 24, 39, .1); font-size: 12px; }
.value-row:last-child { border-bottom: 0; }
.value-row b { color: #111827; }
.qc-chart { width: 100%; height: 260px; }
.log-table { display: grid; gap: 0; max-height: 320px; overflow: auto; }
.log-head, .log-row { display: grid; grid-template-columns: minmax(120px, 140px) minmax(90px, 120px) minmax(0, 1fr); gap: 10px; padding: 5px 6px; font-size: 11px; }
.log-head { position: sticky; top: 0; z-index: 1; background: #f3f4f6; border-radius: 4px; color: #4b5563; font-weight: 700; }
.log-row { border-bottom: 1px dashed rgba(17, 24, 39, .08); color: #374151; }
.log-row:last-child { border-bottom: 0; }
.log-row span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qc-source { margin: 0; color: #9ca3af; font-size: 10px; line-height: 15px; }
@media (max-width: 980px) {
  .qc-columns { grid-template-columns: 1fr; }
  .qc-metrics { grid-template-columns: repeat(2, 1fr); }
}
</style>
