<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>县市区排名</h3>
      <div class="title-right">
        <div class="seg-switch">
          <button :class="{ active: scope === 'realtime' }" @click="scope = 'realtime'">实时</button>
          <button :class="{ active: scope === 'daily' }" @click="scope = 'daily'">昨日日报</button>
        </div>
      </div>
    </header>

    <!-- 实时/日报统一排名表（与全省城市排名同构）：点击表头因子切换排序（默认 AQI） -->
    <div class="rank-block" v-if="rankRows.length">
      <div class="rank-head">
        <span>{{ rankTitle }}</span>
      </div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>县市区</th>
              <th
                v-for="factor in FACTORS"
                :key="factor.key"
                class="sortable"
                :class="{ active: sortKey === factor.key }"
                @click="sortKey = factor.key"
              >{{ factor.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sortedDisplayRows" :key="row.county">
              <td>{{ rowRank(row) ?? '—' }}</td>
              <td>{{ row.county }}</td>
              <td v-for="factor in FACTORS" :key="factor.key">{{ fmt(row[factor.key], factor.digits) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="caliber-note">
        点击 AQI/PM2.5/PM10/O3 切换排序（升序，#1 为最优） ·
        {{ scope === 'realtime' ? '河南省实时发布 · O3 为小时值' : '河南省日发布 · O3 为 O3-8h 滑动值' }}
      </div>
    </div>
    <div v-else class="empty-hint">{{ scope === 'realtime' ? '暂无县市区实时排名' : '暂无县市区日报排名' }}</div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  countyHourRank: { type: Object, default: null },  // county_hour_rank（10 县市区实时排名）
  countyDayRank: { type: Object, default: null }    // county_day_rank（10 县市区日排名）
})

const FACTORS = [
  { key: 'aqi', label: 'AQI', digits: 0 },
  { key: 'pm25', label: 'PM2.5', digits: 1 },
  { key: 'pm10', label: 'PM10', digits: 0 },
  { key: 'o3', label: 'O3', digits: 1 }
]

const scope = ref('realtime')
const sortKey = ref('aqi')
const fmt = (value, digits = 0) => {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

// ssfb 平台小时戳为时段结束时刻（DataTime 19:00 = 18:00→19:00 时段均值），
// 展示按数据所属时段标注：19:00 → "25日 18-19时"（跨零点 00:00 → 前一日 "23-24时"）。
const formatRankWindow = (iso) => {
  const match = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):/)
  if (!match) return iso || '—'
  const end = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]))
  if (Number.isNaN(end.getTime())) return iso
  const start = new Date(end.getTime() - 3600 * 1000)
  const endHour = end.getHours() === 0 ? 24 : end.getHours()
  return `${start.getDate()}日 ${start.getHours()}-${endHour}时`
}

// 两个数据源归一为同构行：aqi/pm25/pm10/o3 值 + 分因子排名（rank_*）
// 实时（SsfbCountyHourRank）O3 为小时值，日报（SsfbCountyDayRank）O3 为 O3-8h
const normalizeRow = (row) => ({
  county: row.county,
  aqi: row.aqi,
  pm25: row.pm25,
  pm10: row.pm10,
  o3: row.o3 ?? row.o3_8h,
  rank_aqi: row.rank ?? row.rank_aqi ?? null,
  rank_pm25: row.rank_pm25 ?? null,
  rank_pm10: row.rank_pm10 ?? null,
  rank_o3: row.rank_o3 ?? null
})

const rankRows = computed(() => {
  const source = scope.value === 'realtime' ? props.countyHourRank?.rows : props.countyDayRank?.rows
  return (source || []).map(normalizeRow)
})
const sortedDisplayRows = computed(() => {
  const key = sortKey.value
  return [...rankRows.value].sort((a, b) => {
    const av = Number(a[key])
    const bv = Number(b[key])
    const aOk = Number.isFinite(av)
    const bOk = Number.isFinite(bv)
    if (aOk && bOk) return av - bv
    if (aOk) return -1
    if (bOk) return 1
    return 0
  })
})
const rowRank = row => row[`rank_${sortKey.value}`]

const rankTitle = computed(() =>
  scope.value === 'realtime'
    ? `许昌 9 县市区实时排名 · ${formatRankWindow(props.countyHourRank?.data_time)}`
    : `许昌 9 县市区日报排名 · ${(props.countyDayRank?.data_date || '').slice(0, 10) || '—'}`
)
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.rank-block { margin-top: 12px; }

.rank-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11px;
  color: #8ab6c2;
}

.data-table {
  th.sortable {
    cursor: pointer;
    user-select: none;
    color: #8ab6c2;

    &:hover { color: #d8ecf1; }

    &.active { color: #3fc8d4; }
  }
}
</style>
