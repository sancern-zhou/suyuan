<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>10 县市区官方月报</h3>
      <div class="title-right">
        <small>{{ current?.data_month || '—' }}</small>
        <div class="seg-switch">
          <button :class="{ active: scope === 'month' }" @click="scope = 'month'">当月</button>
          <button :class="{ active: scope === 'cum' }" @click="scope = 'cum'">累计</button>
        </div>
      </div>
    </header>

    <div v-if="rows.length" class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>区域</th><th>综合指数</th><th>PM2.5</th><th>PM10</th>
            <th>O₃-8h</th><th>优良天</th><th>重污染</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.region">
            <td>
              {{ row.region }}
              <span class="sub">{{ row.region_type === 'urban' ? '国家平台' : '省平台' }}</span>
            </td>
            <td>{{ fmt(row.composite_index, 2) }}</td>
            <td>{{ fmt(row.pm25, 1) }}</td>
            <td>{{ fmt(row.pm10, 1) }}</td>
            <td>{{ fmt(row.o3_8h_90, 0) }}</td>
            <td>{{ row.good_days ?? '—' }}</td>
            <td>{{ row.heavy_days ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty-hint">暂无县市区官方月报数据</div>
    <div class="caliber-note">
      官方月报（剔除沙尘）· 市辖区为国家平台、四县市为省平台数据，两平台数据源不同勿直接横比 ·
      供暖季期次无 O₃ 列
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  report: { type: Object, default: null }   // county_month_report
})

const scope = ref('month')
const current = computed(() => props.report?.[scope.value] || null)
const rows = computed(() => current.value?.rows || [])
const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.data-table td .sub { display: block; }
</style>
