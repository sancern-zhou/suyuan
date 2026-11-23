<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>许昌市统计与全省排名</h3>
      <div class="title-right">
        <div class="seg-switch">
          <button :class="{ active: scope === 'month' }" @click="scope = 'month'">当月</button>
          <button :class="{ active: scope === 'year' }" @click="scope = 'year'">当年累计</button>
        </div>
      </div>
    </header>

    <div v-if="localStat" class="stat-grid">
      <div class="stat-cell"><span>PM2.5</span><strong>{{ fmt(localStat.pm25, 1) }}</strong></div>
      <div class="stat-cell"><span>PM10</span><strong>{{ fmt(localStat.pm10, 1) }}</strong></div>
      <div class="stat-cell"><span>优良天</span><strong>{{ localStat.good_days ?? '—' }}<small>/{{ localStat.days_total ?? '—' }}天</small></strong></div>
      <div class="stat-cell"><span>优良率%</span><strong>{{ fmt(localStat.good_days_ratio, 1) }}</strong></div>
    </div>
    <div v-else class="empty-hint">暂无本地统计数据</div>
    <div class="caliber-note">
      截至 {{ stats?.as_of || '—' }}（{{ scope === 'month' ? '本月1日起' : '本年1月1日起' }}）· {{ localStat?.caliber || '本地日值自算' }}
    </div>

    <div class="rank-block" v-if="provinceRows.length">
      <div class="rank-head">
        <span>全省 19 市(区)官方排名 · {{ provinceData?.data_month || '—' }}{{ scope === 'year' ? ' 累计' : ' 当月' }}</span>
        <button class="rank-toggle" @click="showAllCities = !showAllCities">
          {{ showAllCities ? '收起' : '展开全部城市' }}
        </button>
      </div>
      <div v-if="displayProvinceRows.length" class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr><th>排名</th><th>城市</th><th>综合指数</th><th>PM2.5</th><th>PM10</th><th>优良天</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="row in displayProvinceRows"
              :key="row.region"
              :class="{ highlight: row.region === '许昌市' }"
            >
              <td>{{ row.rank ?? '—' }}</td>
              <td>{{ row.region }}</td>
              <td>{{ fmt(row.composite_index, 2) }}</td>
              <td>{{ fmt(row.pm25, 1) }}</td>
              <td>{{ fmt(row.pm10, 0) }}</td>
              <td>{{ row.good_days ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-hint">暂无许昌市排名数据</div>
      <div class="caliber-note">河南省环境空气质量月报（官方发布口径）· 综合指数升序，#1 为最优</div>
    </div>
    <div v-else class="empty-hint">暂无全省官方月报排名</div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  stats: { type: Object, default: null },       // city_period_stats
  province: { type: Object, default: null }     // province_city_ranking
})

const scope = ref('month')
const showAllCities = ref(false)
const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const localStat = computed(() => (scope.value === 'month' ? props.stats?.month : props.stats?.year))
const provinceData = computed(() => (scope.value === 'month' ? props.province?.month : props.province?.cum))
const provinceRows = computed(() => provinceData.value?.rows || [])
const displayProvinceRows = computed(() =>
  showAllCities.value
    ? provinceRows.value
    : provinceRows.value.filter(row => row.region === '许昌市')
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

  .rank-toggle {
    padding: 0;
    border: none;
    background: transparent;
    color: #3fc8d4;
    font-size: 11px;
    white-space: nowrap;
    cursor: pointer;

    &:hover { color: #d8ecf1; }
  }
}
</style>
