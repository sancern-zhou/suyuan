<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>10 县市区年度目标与实际</h3>
      <div class="title-right">
        <div class="seg-switch">
          <button
            v-for="year in years"
            :key="year"
            :class="{ active: selectedYear === year }"
            @click="selectedYear = year"
          >{{ year }}</button>
        </div>
      </div>
    </header>

    <div v-if="rows.length" class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>区域</th>
            <th>PM2.5 实际/目标</th>
            <th>优良天 实际/目标</th>
            <th>重污染 实际/目标</th>
            <th>考核</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.region">
            <td>
              {{ row.region }}
              <span class="sub">{{ row.region_type === 'urban' ? '国家平台' : '省平台' }}</span>
            </td>
            <td>
              {{ fmt(row.pm25, 0) }}/{{ fmt(row.pm25_target, 0) }}
              <span class="badge" :class="row.pm25_completed === '是' ? 'ok' : 'fail'">{{ row.pm25_completed || '—' }}</span>
            </td>
            <td>
              {{ row.good_days ?? '—' }}/{{ row.good_days_target ?? '—' }}
              <span class="badge" :class="row.good_days_completed === '是' ? 'ok' : 'fail'">{{ row.good_days_completed || '—' }}</span>
            </td>
            <td>
              {{ row.heavy_days ?? '—' }}/{{ row.heavy_days_target ?? '—' }}
              <span class="badge" :class="row.heavy_days_completed === '是' ? 'ok' : 'fail'">{{ row.heavy_days_completed || '—' }}</span>
            </td>
            <td><span class="badge" :class="allMet(row) ? 'ok' : 'fail'">{{ allMet(row) ? '全达标' : '未全达标' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty-hint">暂无县市区年度考核数据</div>
    <div class="caliber-note">官方考核定版 · 重污染天剔沙尘口径 · 县市区年度目标唯一来源</div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  data: { type: Object, default: null }   // county_year_targets
})

const years = computed(() => props.data?.years || [])
const selectedYear = ref(years.value[0] || null)
watch(years, list => {
  if (!list.includes(selectedYear.value)) selectedYear.value = list[0] || null
})

const rows = computed(() => props.data?.by_year?.[String(selectedYear.value)] || [])
const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}
const allMet = row =>
  row.pm25_completed === '是' && row.good_days_completed === '是' && row.heavy_days_completed === '是'
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.data-table td .badge { margin-left: 4px; }
.data-table td .sub { display: block; }
</style>
