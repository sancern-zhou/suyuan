<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>许昌市年度目标与实际</h3>
      <div class="title-right"><small>官方考核定版</small></div>
    </header>

    <template v-if="finalized">
      <div class="year-label">{{ finalized.year }} 年（已定版）</div>
      <div class="data-table-wrap">
        <table class="data-table target-table">
          <thead>
            <tr><th>指标</th><th>目标</th><th>实际</th><th>判定</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in targetRows" :key="row.label">
              <td>{{ row.label }}</td>
              <td>{{ row.target }}</td>
              <td>{{ row.actual }}</td>
              <td><span class="badge" :class="row.met ? 'ok' : 'fail'">{{ row.met ? '完成' : '未完成' }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <div v-else class="empty-hint">暂无年度考核定版数据</div>

    <div v-if="current" class="current-year">
      <span class="year-label">{{ current.year }} 年目标（在途）</span>
      <span class="current-targets">
        PM2.5 ≤ {{ current.pm25_target ?? '—' }} μg/m³ ·
        优良天 ≥ {{ current.good_days_target ?? '—' }} 天 ·
        重污染 ≤ {{ current.heavy_days_target ?? '—' }} 天
      </span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  target: { type: Object, default: null }   // city_year_target_official
})

const finalized = computed(() => props.target?.finalized || null)
const current = computed(() => props.target?.current || null)

const targetRows = computed(() => {
  const row = finalized.value
  if (!row) return []
  return [
    {
      label: 'PM2.5 年均 (μg/m³)',
      target: row.pm25_target ?? '—',
      actual: row.pm25 ?? '—',
      met: row.pm25 != null && row.pm25_target != null && row.pm25 <= row.pm25_target
    },
    {
      label: 'PM10 年均 (μg/m³)',
      target: row.pm10_target ?? '—',
      actual: row.pm10 ?? '—',
      met: row.pm10 != null && row.pm10_target != null && row.pm10 <= row.pm10_target
    },
    {
      label: '优良天数 (天)',
      target: `≥ ${row.good_days_target ?? '—'}`,
      actual: row.good_days ?? '—',
      met: row.good_days != null && row.good_days_target != null && row.good_days >= row.good_days_target
    },
    {
      label: '重污染天数 (天)',
      target: `≤ ${row.heavy_days_target ?? '—'}`,
      actual: row.heavy_days ?? '—',
      met: row.heavy_days != null && row.heavy_days_target != null && row.heavy_days <= row.heavy_days_target
    }
  ]
})
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.year-label {
  font-size: 12px;
  color: #e5ae22;
  margin-bottom: 6px;
}

.current-year {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(63, 200, 212, 0.18);

  .current-targets {
    display: block;
    font-size: 11px;
    color: #8ab6c2;
    line-height: 1.6;
  }
}
</style>
