<template>
  <main class="fieldwatch">
    <header class="fw-topbar">
      <div class="fw-heading">
        <h1>现场巡查快报（测试）</h1>
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
            :class="{ active: alert.active, open: expandedAlert === alert.key }"
          >
            <!-- 有派发通报的记录整行可点、展开通报正文；无通报保持纯展示 -->
            <component
              :is="alert.notice ? 'button' : 'div'"
              :type="alert.notice ? 'button' : undefined"
              class="fw-alert-body"
              :aria-expanded="alert.notice ? expandedAlert === alert.key : undefined"
              @click="alert.notice && toggleAlert(alert.key)"
            >
              <div class="fw-alert-head">
                <strong>{{ alert.name }}</strong>
                <span v-if="alert.pollutant" class="fw-pollutant-tag">{{ alert.pollutant }}</span>
                <span class="fw-alert-status">{{ alert.statusText }}</span>
                <svg
                  v-if="alert.notice"
                  class="fw-alert-chevron"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </div>
              <div v-if="alert.metrics.length" class="fw-alert-metrics">
                <span v-for="metric in alert.metrics" :key="metric.label">
                  {{ metric.label }} <b>{{ metric.value }}</b><small> {{ metric.unit }}</small>
                </span>
              </div>
              <p v-if="alert.timeText" class="fw-alert-time">{{ alert.timeText }}</p>
            </component>
            <div v-if="alert.notice && expandedAlert === alert.key" class="fw-alert-notice">
              <p class="fw-alert-notice-meta">派发通报 · {{ alert.notice.time }}</p>
              <p class="fw-alert-notice-text">{{ alert.notice.text }}</p>
            </div>
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
          <span class="fw-county-hour">{{ countyHour ? `${countyHour} · ` : '' }}小时值</span>
        </header>

        <div class="fw-county-metrics" role="group" aria-label="展示指标">
          <button
            v-for="option in COUNTY_METRICS"
            :key="option.key"
            type="button"
            :class="{ on: option.key === countyMetric }"
            :aria-pressed="option.key === countyMetric"
            @click="countyMetric = option.key"
          >{{ option.label }}</button>
        </div>

        <!-- 固定升序；污染物显示单位，AQI 与首要污染物说明排序依据 -->
        <p class="fw-county-scale">{{ countyOption.unit ? `单位 ${countyOption.unit}` : '按 AQI 升序' }}</p>

        <ul class="fw-counties" :class="{ 'is-text': countyMetric === 'primary' }">
          <li v-for="county in counties" :key="county.name">
            <div class="fw-county-name">
              <strong>{{ county.name }}</strong>
              <span :style="{ color: county.levelColor }">{{ county.level }}</span>
            </div>
            <div class="fw-county-track">
              <i :style="{ width: `${county.widthPct}%`, background: county.color }"></i>
            </div>
            <span class="fw-county-value" :style="{ color: county.textColor }">{{ county.valueText }}</span>
          </li>
        </ul>
        <p class="fw-chart-note">
          河南省空气质量实时发布系统发布的区县小时值 · 颜色分级按 HJ 633-2026<span v-if="countyMetric === 'primary'"> · 首要污染物取平台发布值，优级无</span>
        </p>
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
    </template>

    <footer class="fw-footer">
      数据与对话问数同源<span v-if="store.lastFetchedAt"> · 更新于 {{ formatDateTime(store.lastFetchedAt) }}</span>
    </footer>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useBigScreenStore } from '@/stores/xuchang/bigScreen.js'
import { initDashboardAccessToken } from '@/api/xuchang/bigScreen.js'
import { aqiLevelName, formatDateTime, windDirectionLabel } from '@/components/xuchang/bigscreen/aqiLevels.js'
import {
  COUNTY_METRICS,
  buildAlertView,
  buildCountyRows,
  buildForecastRows,
  buildTrend,
  dataClock,
  dayHourLabel,
  levelColor,
  levelDisplayColor,
  levelTextColor,
  pollutantLabel,
  tintColor
} from './fieldWatchModel.js'

const store = useBigScreenStore()

const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const statusText = computed(() => {
  if (store.error) return store.snapshot ? '刷新异常，显示上次数据' : '数据加载失败'
  return `数据截至 ${dataClock(store.snapshot?.latest_station_time || store.snapshot?.data_cutoff_hour)}`
})

const todayLine = computed(() => {
  const now = new Date()
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][now.getDay()]
  return `${now.getMonth() + 1}月${now.getDate()}日 ${weekday}`
})

const levelPillStyle = aqi => ({
  color: levelTextColor(aqi),
  background: tintColor(levelColor(aqi))
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
// 告警记录点击展开派发通报：同时只展开一条，再点同一条收起；
// 状态只在本页存活，快照轮询刷新不收起已展开的行
const expandedAlert = ref(null)
const toggleAlert = key => {
  expandedAlert.value = expandedAlert.value === key ? null : key
}
// 区县实况固定升序；指标只在本页存活，重新进入回到 AQI
const countyMetric = ref('aqi')
const countyOption = computed(() => COUNTY_METRICS.find(item => item.key === countyMetric.value) || COUNTY_METRICS[0])
const counties = computed(() => buildCountyRows(store.stations.counties, { metric: countyOption.value.key }))
// 快照里各区县同属最新可用小时；旧快照未带时间时不显示
const countyHour = computed(() => dayHourLabel((store.stations.counties || []).find(item => item?.data_time)?.data_time))
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

/* 整行点击区（有通报时渲染为 button）：占满 li、还原排版由外层控制 */
.fw-alert-body {
  display: block;
  width: 100%;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;

  &:focus-visible {
    outline: 2px solid #007aff;
    outline-offset: 2px;
  }
}

.fw-alert-chevron {
  flex: none;
  width: 14px;
  height: 14px;
  color: #a6abb4;
  transition: transform 0.18s ease;
}

.fw-alert.open .fw-alert-chevron {
  transform: rotate(180deg);
}

/* 展开的通报正文：确定性渲染的纯文本，保留换行 */
.fw-alert-notice {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e2e5ea;
}

.fw-alert-notice-meta {
  margin: 0 0 4px;
  font-size: 10px;
  color: #a6abb4;
}

.fw-alert-notice-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #4a5058;
  white-space: pre-line;
  word-break: break-word;
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
/* 数据时段是这张卡片的关键信息，比卡片头的辅助说明更重 */
.fw-card-head .fw-county-hour {
  font-size: 12px;
  font-weight: 600;
  color: #4a5058;
  font-variant-numeric: tabular-nums;
}

/* 手机竖屏内容宽约 300px，8 个指标放不下一行：按可用宽度自动折行（360px 宽为 4+4），
   不用横向滚动容器；最小列宽保证「首要污染物」五个字放得下 */
.fw-county-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(66px, 1fr));
  gap: 6px;
  margin-bottom: 8px;

  button {
    padding: 7px 0;
    border: 1px solid #e7eaee;
    border-radius: 8px;
    background: #fff;
    font-family: inherit;
    font-size: 12px;
    white-space: nowrap;
    color: #4a5058;
    cursor: pointer;

    &.on {
      border-color: #007aff;
      background: #007aff;
      color: #fff;
      font-weight: 600;
    }
  }
}

/* 宽屏排成一行：7 个短标签均分，末列按「首要污染物」的实际宽度 */
@media (min-width: 556px) {
  .fw-county-metrics { grid-template-columns: repeat(7, minmax(0, 1fr)) max-content; }
}

.fw-county-scale {
  margin: 0 0 4px;
  font-size: 11px;
  color: #8a8f99;
  text-align: right;
}

.fw-counties {
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: grid;
    grid-template-columns: 74px 1fr 40px;
    align-items: center;
    column-gap: 10px;
    padding: 9px 0;

    & + li { border-top: 1px solid #f4f5f7; }
  }

  /* 首要污染物一列显示的是名称（如 PM2.5）：数值列加宽、字号略小 */
  &.is-text {
    li { grid-template-columns: 74px 1fr 52px; }
    .fw-county-value { font-size: 14px; }
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

.fw-county-value {
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
