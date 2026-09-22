<template>
  <section class="review-evidence">
    <header class="evidence-header">
      <div class="heading">
        <span class="eyebrow">REVIEW EVIDENCE</span>
        <strong>{{ panel.station_name || '站点' }} · {{ panel.pollutant }} 审核证据</strong>
        <div class="meta">
          <span v-if="panel.working_order_code">工单号：{{ panel.working_order_code }}</span>
          <span>{{ panel.start_time || '—' }} ~ {{ panel.end_time || '—' }}</span>
        </div>
      </div>
      <span class="status-badge" :class="weatherStatusClass">{{ weatherStatusLabel }}</span>
    </header>

    <section class="chart-card">
      <div class="card-title">
        <span>污染物小时时序（含同城对比带）</span>
        <b>{{ seriesPoints.length }}</b>
      </div>
      <p class="band-note" :class="bandClass">{{ bandNote }}</p>
      <ReviewTimeSeriesChart
        v-if="seriesPoints.length"
        :series="series"
        :mark-areas="markAreas"
        :unit="unit"
        :height="320"
      />
      <p v-else class="card-empty">接口未返回污染物小时数据。</p>
    </section>

    <section class="chart-card">
      <div class="card-title"><span>气象时序（风速 / 风向 / 温湿压）</span></div>
      <JiangsuWeatherReviewChart
        v-if="weatherRows.length"
        :entry="entry"
        :weather="weather"
        :mark-areas="markAreas"
      />
      <p v-else class="card-empty">
        未获取到城市气象数据{{ panel.weather_message ? `：${panel.weather_message}` : '。' }}
      </p>
    </section>

    <p class="source-note">
      数据来源：江苏监测小时数据与城市气象取证接口，仅展示接口返回内容，不推断、不补造。
      区间标注（剔除候选）由审核结论提供时显示。
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import JiangsuWeatherReviewChart from './JiangsuWeatherReviewChart.vue'
import ReviewTimeSeriesChart from './ReviewTimeSeriesChart.vue'

const props = defineProps({ data: { type: Object, required: true } })

const payload = computed(() => props.data?.data?.work_order_review_evidence || {})
const panel = computed(() => payload.value.panel || {})
const series = computed(() => (Array.isArray(payload.value.series) ? payload.value.series : []))
const markAreas = computed(() => (Array.isArray(payload.value.mark_areas) ? payload.value.mark_areas : []))
const weather = computed(() => payload.value.weather || {})
const weatherRows = computed(() => (Array.isArray(weather.value.data) ? weather.value.data : []))
const entry = computed(() => payload.value.entry || {})
const unit = computed(() => series.value[0]?.unit || '')
const seriesPoints = computed(() => series.value[0]?.points || [])
const weatherStatusClass = computed(() => {
  const status = panel.value.weather_status
  if (status === 'success') return 'ok'
  if (status === 'partial' || status === 'empty') return 'warn'
  return 'bad'
})
const bandClass = computed(() => {
  const status = panel.value.band_status
  if (status === 'success') return 'ok'
  if (status === 'empty') return 'warn'
  return 'bad'
})
const bandNote = computed(() => {
  const status = panel.value.band_status
  const count = panel.value.band_station_count || 0
  if (status === 'success') return `同城对比：同区 ${count} 个站逐小时区间（最低/中位/最高）`
  if (status === 'empty') return `同城对比不可用：${panel.value.band_message || '同区无可比较站点'}`
  return `同城对比不可用：${panel.value.band_message || '未获取到同区站点数据'}`
})
const weatherStatusLabel = computed(() => {
  const status = panel.value.weather_status
  if (status === 'success') return '气象完整'
  if (status === 'partial') return '气象部分缺失'
  if (status === 'empty') return '无气象记录'
  return '气象不可用'
})
</script>

<style scoped>
.review-evidence { display: grid; gap: 12px; min-width: 720px; color: var(--text-1); font-family: "Microsoft YaHei", sans-serif; }
.evidence-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 16px; border-radius: 8px; background: linear-gradient(90deg, var(--color-primary-bg), var(--bg-container)); }
.heading { display: grid; gap: 5px; }
.heading .eyebrow { color: var(--color-primary); font-size: 10px; letter-spacing: 2px; }
.heading strong { font-size: 18px; }
.meta { display: flex; flex-wrap: wrap; gap: 16px; color: var(--text-2); font-size: 11px; }
.status-badge { padding: 5px 10px; border-radius: 999px; font-size: 11px; }
.status-badge.ok { background: var(--color-success-bg); color: var(--color-success); }
.status-badge.warn { background: rgba(217, 119, 6, .12); color: #d97706; }
.status-badge.bad { background: rgba(107, 114, 128, .12); color: var(--text-2); }
.chart-card { display: grid; gap: 8px; }
.card-title { display: flex; align-items: center; gap: 8px; padding-bottom: 7px; border-bottom: 1px solid rgba(17, 24, 39, .1); font-size: 13px; font-weight: 700; }
.card-title::before { width: 3px; height: 13px; border-radius: 2px; background: var(--color-primary); content: ""; }
.card-title b { margin-left: auto; padding: 1px 8px; border-radius: 999px; background: var(--color-primary-bg); color: var(--color-primary); font-size: 11px; }
.card-empty { margin: 0; padding: 14px 0; color: #6b7280; font-size: 12px; }
.band-note { margin: 0; font-size: 11px; }
.band-note.ok { color: #15803d; }
.band-note.warn { color: #d97706; }
.band-note.bad { color: #6b7280; }
.source-note { margin: 0; color: var(--text-3); font-size: 10px; line-height: 15px; }
</style>
