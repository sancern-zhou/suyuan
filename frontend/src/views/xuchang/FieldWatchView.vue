<template>
  <main class="fieldwatch">
    <header class="fw-topbar">
      <div class="fw-heading">
        <h1>现场巡查快报</h1>
        <p>许昌市大气环境管控 · {{ todayLine }}</p>
      </div>
      <button
        class="fw-refresh"
        type="button"
        :class="{ spinning: store.loading }"
        :disabled="store.loading"
        aria-label="刷新数据"
        @click="store.refresh()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M23 4v6h-6" />
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
      </button>
    </header>

    <p class="fw-dataline" :class="{ error: store.error }" aria-live="polite">
      <i aria-hidden="true"></i>{{ statusText }}
    </p>

    <!-- 首屏加载：骨架保持版面结构，避免白屏后内容突然跳动 -->
    <div v-if="!store.snapshot && store.loading" class="fw-skeletons" aria-label="正在加载">
      <div v-for="n in 3" :key="n" class="fw-card fw-skeleton"></div>
    </div>

    <section v-else-if="!store.snapshot && store.error" class="fw-card fw-load-error">
      <p>{{ store.error }}</p>
      <button type="button" @click="store.refresh()">重新加载</button>
    </section>

    <template v-else>
      <section v-if="store.header" class="fw-card fw-hero" aria-label="实时空气质量">
        <div class="fw-hero-main">
          <div class="fw-aqi">
            <span class="fw-aqi-label">AQI</span>
            <strong :style="{ color: levelDisplayColor(store.header.aqi) }">{{ store.header.aqi ?? '—' }}</strong>
          </div>
          <div class="fw-hero-side">
            <span class="fw-level" :style="levelPillStyle(store.header.aqi)">
              {{ store.header.quality || aqiLevelName(store.header.aqi) }}
            </span>
            <span v-if="store.header.primary_pollutant" class="fw-primary">
              首要污染物 {{ pollutantLabel(store.header.primary_pollutant) }}
            </span>
          </div>
        </div>

        <div class="fw-block-caption">
          <span>六项污染物</span>
          <small>μg/m³，CO 为 mg/m³</small>
        </div>
        <div class="fw-pollutants">
          <div v-for="item in pollutants" :key="item.label" class="fw-pollutant">
            <strong>{{ item.value }}</strong>
            <span>{{ item.label }}</span>
          </div>
        </div>

        <div v-if="store.header.met" class="fw-met">
          <span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
              <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" />
            </svg>
            {{ windDirectionLabel(store.header.met.wind_direction) }}风 {{ fmt(store.header.met.wind_speed) }} km/h
          </span>
          <span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
              <path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z" />
            </svg>
            {{ fmt(store.header.met.temperature) }}℃
          </span>
          <span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z" />
            </svg>
            湿度 {{ fmt(store.header.met.humidity) }}%
          </span>
        </div>
      </section>

      <section v-if="trend" class="fw-card" aria-label="近24小时趋势">
        <header class="fw-card-head">
          <h2>近 24 小时趋势</h2>
          <span>AQI · 逐小时</span>
        </header>
        <svg
          class="fw-trend"
          :viewBox="`0 0 ${trend.width} ${trend.height}`"
          role="img"
          aria-label="近24小时逐小时AQI柱状图"
        >
          <g v-for="line in trend.grid" :key="line.value">
            <line
              :x1="26" :x2="trend.width - 4" :y1="line.y" :y2="line.y"
              :stroke="line.dashed ? '#e2d9b6' : '#eef0f3'"
              :stroke-dasharray="line.dashed ? '4 4' : undefined"
            />
            <text x="0" :y="line.y + 3" class="fw-axis">{{ line.value }}</text>
          </g>
          <line :x1="26" :x2="trend.width - 4" :y1="trend.baseline" :y2="trend.baseline" stroke="#e7eaee" />
          <rect
            v-for="(bar, index) in trend.bars"
            :key="index"
            :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height"
            :fill="bar.color" rx="2"
          />
          <text
            v-for="tick in trend.ticks"
            :key="tick.x"
            :x="tick.x" :y="trend.height - 6" text-anchor="middle" class="fw-axis"
          >{{ tick.label }}</text>
        </svg>
        <p class="fw-chart-note">虚线为 AQI 100（良与轻度污染分界）· 缺测小时留空</p>
      </section>

      <section class="fw-card" aria-label="告警与任务派发">
        <header class="fw-card-head">
          <h2>告警与派发</h2>
          <span :class="{ 'fw-attention': activeAlertCount > 0 }">{{ alertSummary }}</span>
        </header>
        <ul v-if="alerts.length" class="fw-alerts">
          <li
            v-for="alert in alerts"
            :key="alert.key"
            class="fw-alert"
            :class="{ active: alert.active }"
          >
            <div class="fw-alert-head">
              <strong>{{ alert.name }}</strong>
              <span v-if="alert.pollutant" class="fw-pollutant-tag">{{ alert.pollutant }}</span>
              <span class="fw-alert-status">{{ alert.statusText }}</span>
            </div>
            <div v-if="alert.metrics.length" class="fw-alert-metrics">
              <span v-for="metric in alert.metrics" :key="metric.label">
                {{ metric.label }} <b>{{ metric.value }}</b><small> {{ metric.unit }}</small>
              </span>
            </div>
            <p v-if="alert.timeText" class="fw-alert-time">{{ alert.timeText }}</p>
          </li>
        </ul>
        <p v-else class="fw-clear">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="m8 12 2.6 2.6L16 9" />
          </svg>
          近 24 小时无站点偏离告警
        </p>
      </section>

      <section v-if="counties.length" class="fw-card" aria-label="区县实况">
        <header class="fw-card-head">
          <h2>区县实况</h2>
          <span>按 AQI 降序</span>
        </header>
        <ul class="fw-counties">
          <li v-for="county in counties" :key="county.name">
            <div class="fw-county-name">
              <strong>{{ county.name }}</strong>
              <span :style="{ color: county.textColor }">{{ county.level }}</span>
            </div>
            <div class="fw-county-track">
              <i :style="{ width: `${county.widthPct}%`, background: county.color }"></i>
            </div>
            <span class="fw-county-aqi" :style="{ color: county.textColor }">{{ county.aqiText }}</span>
          </li>
        </ul>
      </section>

      <section v-if="forecast.length" class="fw-card" aria-label="空气质量预报">
        <header class="fw-card-head">
          <h2>未来 {{ forecast.length }} 天预报</h2>
          <span>AQI 区间</span>
        </header>
        <ul class="fw-forecast">
          <li v-for="day in forecast" :key="day.key">
            <div class="fw-forecast-day">
              <strong>{{ day.weekday }}</strong>
              <span>{{ day.dateLabel }}</span>
            </div>
            <div class="fw-forecast-band">
              <div class="fw-forecast-track">
                <i :style="{ left: `${day.leftPct}%`, width: `${day.widthPct}%`, background: day.color }"></i>
              </div>
              <small v-if="day.primary">首要 {{ day.primary }}</small>
            </div>
            <div class="fw-forecast-value">
              <strong>{{ day.rangeText }}</strong>
              <span :style="{ color: day.textColor }">{{ day.level }}</span>
            </div>
          </li>
        </ul>
      </section>

      <section class="fw-card" aria-label="任务播报">
        <header class="fw-card-head">
          <h2>任务播报</h2>
          <span v-if="store.broadcast.length">{{ store.broadcast.length }} 条</span>
        </header>
        <ol v-if="store.broadcast.length" class="fw-feed">
          <li v-for="(item, index) in store.broadcast" :key="`${item.time}-${item.task_name}`" :class="{ latest: index === 0 }">
            <div class="fw-feed-head">
              <strong>{{ item.task_name }}</strong>
              <time>{{ shortDateTime(item.time) }}</time>
            </div>
            <p>{{ item.text }}</p>
          </li>
        </ol>
        <p v-else class="fw-empty">暂无播报</p>
      </section>
    </template>

    <footer class="fw-footer">
      数据与对话问数同源<span v-if="store.lastFetchedAt"> · 更新于 {{ formatDateTime(store.lastFetchedAt) }}</span>
    </footer>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useBigScreenStore } from '@/stores/xuchang/bigScreen.js'
import { initDashboardAccessToken } from '@/api/xuchang/bigScreen.js'
import { aqiColor, aqiLevelName, formatDateTime, formatHour, windDirectionLabel } from '@/components/xuchang/bigscreen/aqiLevels.js'
import {
  buildAlertView,
  buildCountyRows,
  buildForecastRows,
  buildTrend,
  levelDisplayColor,
  levelTextColor,
  pollutantLabel,
  shortDateTime,
  tintColor
} from './fieldWatchModel.js'

const store = useBigScreenStore()

const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const statusText = computed(() => {
  if (store.error) return store.snapshot ? '刷新异常，显示上次数据' : '数据加载失败'
  return `数据截至 ${formatHour(store.snapshot?.latest_station_time || store.snapshot?.data_cutoff_hour)}`
})

const todayLine = computed(() => {
  const now = new Date()
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][now.getDay()]
  return `${now.getMonth() + 1}月${now.getDate()}日 ${weekday}`
})

const levelPillStyle = aqi => ({
  color: levelTextColor(aqi),
  background: tintColor(aqiColor(aqi))
})

const pollutants = computed(() => {
  const header = store.header || {}
  return [
    { label: 'PM2.5', value: fmt(header.pm25) },
    { label: 'PM10', value: fmt(header.pm10) },
    { label: 'O3', value: fmt(header.o3) },
    { label: 'SO2', value: fmt(header.so2) },
    { label: 'NO2', value: fmt(header.no2) },
    { label: 'CO', value: fmt(header.co, 1) }
  ]
})

const trend = computed(() => buildTrend(store.cityTrend?.rows))
const alerts = computed(() => store.alerts.map(buildAlertView))
const activeAlertCount = computed(() => alerts.value.filter(item => item.active).length)
const alertSummary = computed(() => {
  if (activeAlertCount.value > 0) return `${activeAlertCount.value} 项进行中`
  return alerts.value.length ? `${alerts.value.length} 条记录` : ''
})
const counties = computed(() => buildCountyRows(store.stations.counties))
const forecast = computed(() => buildForecastRows(store.forecast?.daily))

onMounted(() => {
  initDashboardAccessToken()
  store.startPolling()
})
onBeforeUnmount(() => store.stopPolling())
</script>

<style lang="scss">
/* 快报是独立整页，不保留主工作区的固定高度/裁剪，滚动交给 WebView 文档层。 */
#app:has(.fieldwatch) {
  height: auto;
  min-height: 100vh;
  overflow: visible;
  background: #f4f5f7;
}
</style>

<style lang="scss" scoped>
.fieldwatch {
  max-width: 600px;
  margin: 0 auto;
  padding: 14px 14px 26px;
  color: #16181d;
  background: #f4f5f7;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  /* 使用 WebView 原生文档滚动；嵌套 overflow 容器滑动后会被该机型的合成层清空。 */
  min-height: 100vh;
}

.fw-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 0;

  h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.2px;
  }
  p { margin: 4px 0 0; font-size: 12px; color: #8a8f99; }
}

.fw-refresh {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid #e7eaee;
  border-radius: 50%;
  background: #fff;
  color: #007aff;
  cursor: pointer;

  svg { width: 18px; height: 18px; }
  &:active { background: #f0f4fa; }
  &:disabled { opacity: 0.7; }
  &.spinning svg { animation: fw-spin 1s linear infinite; }
}

@keyframes fw-spin {
  to { transform: rotate(360deg); }
}

.fw-dataline {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 10px 2px 14px;
  font-size: 11px;
  color: #8a8f99;

  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #21a366;
  }
  &.error { color: #b4741a; }
  &.error i { background: #e5ae22; }
}

.fw-card {
  margin-bottom: 12px;
  padding: 16px;
  border: 1px solid #eceef1;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04);
}

.fw-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;

  h2 { margin: 0; font-size: 15px; font-weight: 650; }
  span { font-size: 11px; color: #8a8f99; }
  .fw-attention { color: #c8402f; }
}

/* ---- 实时空气质量 ---- */
.fw-hero-main {
  display: flex;
  align-items: center;
  gap: 18px;
}

.fw-aqi {
  display: flex;
  flex-direction: column;

  .fw-aqi-label { font-size: 11px; color: #8a8f99; letter-spacing: 1px; }
  strong {
    font-size: 54px;
    font-weight: 650;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
  }
}

.fw-hero-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;

  .fw-level {
    align-self: flex-start;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
  }
  .fw-primary { font-size: 12px; color: #4a5058; }
}

.fw-block-caption {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f1f4;
  font-size: 12px;
  color: #4a5058;

  small { font-size: 10px; color: #a6abb4; }
}

.fw-pollutants {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 8px;
  margin-top: 12px;
}

.fw-pollutant {
  display: flex;
  flex-direction: column;
  gap: 3px;

  strong { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
  span { font-size: 11px; color: #8a8f99; }
}

.fw-met {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f1f4;

  > span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: #4a5058;
  }
  svg { width: 14px; height: 14px; color: #8a8f99; }
}

/* ---- 趋势图 ---- */
.fw-trend {
  display: block;
  width: 100%;
  height: auto;
}

.fw-axis {
  font-size: 9px;
  fill: #a6abb4;
}

.fw-chart-note {
  margin: 6px 0 0;
  font-size: 10px;
  color: #a6abb4;
}

/* ---- 告警 ---- */
.fw-alerts {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.fw-alert {
  padding: 12px;
  border: 1px solid #eef0f3;
  border-radius: 10px;
  background: #fafbfc;

  &.active {
    border-color: #f2d6cf;
    background: #fdf6f4;
  }
}

.fw-alert-head {
  display: flex;
  align-items: center;
  gap: 8px;

  strong { font-size: 14px; font-weight: 600; }
  .fw-alert-status { margin-left: auto; font-size: 11px; color: #8a8f99; }
  .active & .fw-alert-status { color: #c8402f; }
}

.fw-pollutant-tag {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef0f3;
  font-size: 10px;
  color: #4a5058;
}

.fw-alert-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 8px;
  font-size: 12px;
  color: #8a8f99;

  b {
    font-weight: 600;
    color: #16181d;
    font-variant-numeric: tabular-nums;
  }
  small { font-size: 10px; }
}

.fw-alert-time {
  margin: 8px 0 0;
  font-size: 11px;
  color: #8a8f99;
}

.fw-clear {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 13px;
  color: #4a5058;

  svg { width: 18px; height: 18px; color: #21a366; }
}

/* ---- 区县实况 ---- */
.fw-counties {
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: grid;
    grid-template-columns: 74px 1fr 34px;
    align-items: center;
    column-gap: 12px;
    padding: 9px 0;

    & + li { border-top: 1px solid #f4f5f7; }
  }
}

.fw-county-name {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong { font-size: 13px; font-weight: 500; }
  span { font-size: 10px; }
}

.fw-county-track {
  height: 5px;
  border-radius: 3px;
  background: #f0f1f4;
  overflow: hidden;

  i { display: block; height: 100%; border-radius: 3px; }
}

.fw-county-aqi {
  font-size: 17px;
  font-weight: 650;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ---- 预报 ---- */
.fw-forecast {
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: grid;
    grid-template-columns: 52px 1fr 64px;
    align-items: center;
    column-gap: 12px;
    padding: 10px 0;

    & + li { border-top: 1px solid #f4f5f7; }
  }
}

.fw-forecast-day {
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong { font-size: 13px; font-weight: 500; }
  span { font-size: 10px; color: #8a8f99; }
}

.fw-forecast-track {
  position: relative;
  height: 5px;
  border-radius: 3px;
  background: #f0f1f4;

  i {
    position: absolute;
    top: 0;
    height: 100%;
    border-radius: 3px;
  }
}

.fw-forecast-band small {
  display: block;
  margin-top: 5px;
  font-size: 10px;
  color: #a6abb4;
}

.fw-forecast-value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;

  strong { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
  span { font-size: 10px; }
}

/* ---- 任务播报：时间线 ---- */
.fw-feed {
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    position: relative;
    padding: 0 0 16px 16px;

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 5px;
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #c9cdd4;
    }
    &::after {
      content: '';
      position: absolute;
      left: 3px;
      top: 16px;
      bottom: 0;
      width: 1px;
      background: #eceef1;
    }
    &:last-child { padding-bottom: 2px; }
    &:last-child::after { display: none; }
    &.latest::before { background: #007aff; }
  }
}

.fw-feed-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;

  strong { font-size: 13px; font-weight: 600; }
  time { font-size: 11px; color: #8a8f99; white-space: nowrap; }
}

.fw-feed p {
  margin: 5px 0 0;
  font-size: 13px;
  line-height: 1.65;
  color: #4a5058;
}

.fw-empty {
  margin: 0;
  font-size: 12px;
  color: #8a8f99;
}

/* ---- 首屏状态与页脚 ---- */
.fw-skeleton {
  height: 120px;
  animation: fw-pulse 1.4s ease-in-out infinite;

  &:first-child { height: 220px; }
}

@keyframes fw-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.fw-load-error {
  text-align: center;

  p { margin: 6px 0 12px; font-size: 13px; color: #4a5058; }
  button {
    padding: 8px 24px;
    border: none;
    border-radius: 8px;
    background: #007aff;
    color: #fff;
    font-size: 13px;
  }
}

.fw-footer {
  margin-top: 4px;
  text-align: center;
  font-size: 11px;
  color: #a6abb4;
}
</style>
