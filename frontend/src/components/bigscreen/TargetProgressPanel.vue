<template>
  <section class="target-panel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>年度达标态势（{{ target.year || '—' }}）</h3>
    </header>

    <template v-if="target.targets || target.official_cum">
      <div class="target-row" v-if="target.official_cum?.good_days != null">
        <div class="target-label">
          <strong>优良天数</strong>
          <small>
            官方累计 {{ target.official_cum.good_days ?? '—' }} 天（截至{{ monthLabel }}）
            <template v-if="localSegment">｜{{ localSegment.from.slice(5) }} 起本地自算 +{{ localSegment.good_days }}/{{ localSegment.days_total }} 天（未剔沙尘）</template>
          </small>
        </div>
        <div class="progress">
          <div class="progress-fill good" :style="{ width: progressPct(goodDaysCombined, target.targets?.good_days) }"></div>
          <span class="progress-text">{{ goodDaysCombined ?? '—' }} / {{ target.targets?.good_days ?? '—' }} 天</span>
        </div>
      </div>

      <div class="target-row" v-if="target.official_cum?.pm25 != null">
        <div class="target-label">
          <strong>PM2.5 年均</strong>
          <small>官方累计 {{ target.official_cum.pm25 ?? '—' }} μg/m³（截至{{ monthLabel }}）</small>
        </div>
        <div class="progress">
          <!-- 浓度越低越好：进度条语义为"距目标的余量"，满格=尚未用完目标空间 -->
          <div class="progress-fill pm25" :style="{ width: progressPct(target.official_cum.pm25, target.targets?.pm25) }"></div>
          <span class="progress-text">{{ target.official_cum.pm25 ?? '—' }} / {{ target.targets?.pm25 ?? '—' }} μg/m³</span>
        </div>
      </div>

      <div class="target-row" v-if="target.official_cum?.heavy_days != null">
        <div class="target-label">
          <strong>重污染天数</strong>
          <small>官方累计 {{ target.official_cum.heavy_days ?? '—' }} 天 · 目标 {{ target.targets?.heavy_days ?? '—' }} 天以内</small>
        </div>
        <div class="progress">
          <div class="progress-fill heavy" :style="{ width: progressPct(target.official_cum.heavy_days, target.targets?.heavy_days) }"></div>
          <span class="progress-text">{{ target.official_cum.heavy_days ?? '—' }} / {{ target.targets?.heavy_days ?? '—' }} 天</span>
        </div>
      </div>

      <div class="rank168-strip" v-if="rank168">
        <span class="strip-label">全国 168 城</span>
        <span class="strip-item">
          综合指数排名 <strong>{{ rank168.composite_rank ?? '—' }}</strong>
          <small>（{{ rank168.composite_index ?? '—' }}）</small>
        </span>
        <span class="strip-item">
          PM2.5 排名 <strong>{{ rank168.pm25_rank ?? '—' }}</strong>
          <small>（{{ rank168.pm25 ?? '—' }} μg/m³）</small>
        </span>
        <span class="strip-period">{{ rank168.period_label || '' }} · 部发布累计</span>
      </div>

      <div class="daily-strip" v-if="dailyForecasts.length">
        <span class="strip-label">未来预报</span>
        <span
          v-for="item in dailyForecasts"
          :key="item.date"
          class="strip-day"
          :style="{ borderColor: aqiColor(item.aqi) }"
        >
          <small>{{ item.date?.slice(5) }}</small>
          <strong :style="{ color: aqiColor(item.aqi) }">{{ item.aqi ?? '—' }}</strong>
          <small>{{ item.primary_pollutant || aqiLevelName(item.aqi) }}</small>
        </span>
      </div>
    </template>

    <div v-else class="empty">暂无年度目标数据</div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { aqiColor, aqiLevelName } from './aqiLevels.js'

const props = defineProps({
  target: { type: Object, default: () => ({}) },
  forecast: { type: Object, default: null },
  rank168: { type: Object, default: null }
})

const localSegment = computed(() => props.target?.local_since_official || null)
const monthLabel = computed(() => {
  const month = props.target?.official_cum?.as_of_month
  return month ? `${month.slice(5)}月` : '—'
})
const goodDaysCombined = computed(() => {
  const official = props.target?.official_cum?.good_days
  const local = localSegment.value?.good_days
  if (official == null) return null
  return local ? official + local : official
})
const dailyForecasts = computed(() => (props.forecast?.daily || []).slice(0, 5))

const progressPct = (value, target) => {
  const num = Number(value)
  const total = Number(target)
  if (!Number.isFinite(num) || !Number.isFinite(total) || total <= 0) return '0%'
  return `${Math.min(Math.max((num / total) * 100, 0), 100).toFixed(1)}%`
}
</script>

<style lang="scss" scoped>
.target-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
  overflow: hidden;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;

  .title-bar {
    width: 4px;
    height: 14px;
    border-radius: 2px;
    background: #3fc8d4;
  }
  h3 {
    margin: 0;
    font-size: 15px;
    color: #eaf6f8;
    letter-spacing: 1px;
  }
}

.target-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.target-label {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong { font-size: 14px; color: #d8ecf1; }
  small { font-size: 11px; color: #6f95a3; }
}

.progress {
  position: relative;
  height: 18px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;

  .progress-fill {
    height: 100%;
    border-radius: 9px;
    transition: width 0.6s ease;
    &.good { background: linear-gradient(90deg, #0e8a96, #21a366); }
    &.pm25 { background: linear-gradient(90deg, #116086, #3fc8d4); }
    &.heavy { background: linear-gradient(90deg, #d85245, #914c95); }
  }
  .progress-text {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-right: 8px;
    font-size: 12px;
    color: #eaf6f8;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  }
}

.rank168-strip {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 7px 10px;
  border: 1px solid rgba(229, 174, 34, 0.25);
  border-radius: 6px;
  background: rgba(229, 174, 34, 0.06);
  font-size: 12px;
  color: #c9dfe6;

  .strip-label {
    color: #e5ae22;
    letter-spacing: 1px;
    flex-shrink: 0;
  }
  .strip-item strong { font-size: 16px; color: #eaf6f8; }
  .strip-item small { color: #8ab6c2; }
  .strip-period {
    margin-left: auto;
    color: #6f95a3;
    font-size: 11px;
  }
}

.daily-strip {
  display: flex;
  align-items: stretch;
  gap: 8px;
  margin-top: auto;

  .strip-label {
    writing-mode: vertical-lr;
    font-size: 11px;
    color: #6f95a3;
    letter-spacing: 3px;
  }
  .strip-day {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 4px;
    border: 1px solid;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.03);

    small { font-size: 11px; color: #8ab6c2; }
    strong { font-size: 17px; }
  }
}

.empty {
  margin: auto;
  font-size: 13px;
  color: #6f95a3;
}
</style>
