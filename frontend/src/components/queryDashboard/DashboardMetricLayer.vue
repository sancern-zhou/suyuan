<template>
  <section class="metric-layer" aria-label="广东省空气质量指标">
    <div class="metric-header">
      <div>
        <h2>广东空气质量</h2>
        <p>{{ statusText }}</p>
      </div>
      <button type="button" class="source-button" @click="$emit('open-sources')">
        数据源
      </button>
    </div>

    <div class="metric-grid">
      <article v-for="metric in metrics" :key="metric.key" class="metric-card">
        <span class="metric-label">{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <span class="metric-note">{{ metric.note }}</span>
      </article>
    </div>

    <p v-if="displayError" class="metric-error">{{ displayError }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  }
})

defineEmits(['open-sources'])

const pick = (...values) => {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value
  }
  return '--'
}

const formatValue = (value, suffix = '') => {
  const normalized = pick(value)
  if (normalized === '--') return normalized
  const text = String(normalized)
  return suffix && !text.endsWith(suffix) ? `${text}${suffix}` : text
}

const moduleFor = (key, legacyKey) => props.overview?.modules?.[key] ||
  props.overview?.[key] ||
  props.overview?.[legacyKey] ||
  {}

const moduleErrorText = (module) => {
  if (!module?.error) return ''
  if (typeof module.error === 'string') return module.error
  return module.error.message || JSON.stringify(module.error)
}

const moduleStatusText = (module) => {
  const statusMap = {
    idle: '待加载',
    loading: '加载中',
    success: '已更新',
    partial: '部分更新',
    error: '异常',
    stale: '旧数据'
  }
  return statusMap[module?.status] || module?.status || '未知状态'
}

const summaryValue = (summary, keys, suffix = '') => {
  for (const key of keys) {
    if (summary?.[key] !== undefined && summary?.[key] !== null && summary?.[key] !== '') {
      return formatValue(summary[key], suffix)
    }
  }
  return '--'
}

const moduleValue = (module, keys, suffix = '') => {
  const summarized = summaryValue(module?.summary, keys, suffix)
  if (summarized !== '--') return summarized
  return summaryValue(module, keys, suffix)
}

const recordCountValue = (module) => {
  const count = module?.summary?.record_count ?? module?.record_count
  if (count !== undefined && count !== null && count !== '') return `${count}条`
  const fallbackCount = Array.isArray(module?.cities)
    ? module.cities.length
    : Array.isArray(module?.stations)
      ? module.stations.length
      : null
  return fallbackCount !== null ? `${fallbackCount}条` : '--'
}

const statusText = computed(() => {
  if (props.loading) return '模块状态：加载中'
  const statuses = metrics.value.map((metric) => metric.status).filter(Boolean)
  if (props.error || statuses.includes('error')) return '模块状态：数据异常'
  if (statuses.includes('partial') || statuses.includes('stale')) return '模块状态：部分可用'
  if (statuses.includes('success')) return '模块状态：已连接'
  return '模块状态：等待数据'
})

const displayError = computed(() => {
  if (props.error) return props.error
  const errors = metrics.value
    .map((metric) => metric.error)
    .filter(Boolean)
  return errors.join('；')
})

const metrics = computed(() => {
  const realtime = moduleFor('realtime', 'current')
  const month = moduleFor('month_to_date', 'month')
  const year = moduleFor('year_to_date', 'year')

  return [
    {
      key: 'realtime',
      label: '实时数据',
      value: moduleValue(realtime, ['aqi', 'avg_aqi', 'value']) !== '--'
        ? moduleValue(realtime, ['aqi', 'avg_aqi', 'value'])
        : recordCountValue(realtime),
      note: `状态：${moduleStatusText(realtime)}`,
      status: realtime.status,
      error: moduleErrorText(realtime)
    },
    {
      key: 'month',
      label: '本月累计',
      value: moduleValue(month, ['good_rate', 'excellent_rate', 'rate'], '%') !== '--'
        ? moduleValue(month, ['good_rate', 'excellent_rate', 'rate'], '%')
        : recordCountValue(month),
      note: `状态：${moduleStatusText(month)}`,
      status: month.status,
      error: moduleErrorText(month)
    },
    {
      key: 'year',
      label: '年度累计',
      value: moduleValue(year, ['good_rate', 'compliance_rate', 'rate'], '%') !== '--'
        ? moduleValue(year, ['good_rate', 'compliance_rate', 'rate'], '%')
        : recordCountValue(year),
      note: `状态：${moduleStatusText(year)}`,
      status: year.status,
      error: moduleErrorText(year)
    }
  ]
})
</script>

<style scoped>
.metric-layer {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid rgba(32, 49, 58, 0.1);
  background: rgba(255, 255, 255, 0.94);
}

.metric-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

h2,
p {
  margin: 0;
}

h2 {
  font-size: 18px;
  color: #20313a;
}

.metric-header p {
  margin-top: 4px;
  color: #667781;
  font-size: 12px;
}

.source-button {
  flex: 0 0 auto;
  min-width: 70px;
  max-width: 120px;
  padding: 7px 10px;
  border: 1px solid rgba(17, 128, 118, 0.28);
  border-radius: 6px;
  background: #f7fbfa;
  color: #0f6c65;
  cursor: pointer;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(32, 49, 58, 0.1);
  border-radius: 8px;
  background: #ffffff;
}

.metric-label,
.metric-note {
  color: #667781;
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

strong {
  color: #20313a;
  font-size: 24px;
  line-height: 1.1;
  overflow-wrap: anywhere;
}

.metric-error {
  color: #b42318;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
