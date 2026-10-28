<template>
  <section class="realtime-panel" aria-label="实时空气质量">
    <header class="rt-head">
      <span class="rt-bar" aria-hidden="true"></span>
      <h3>实时空气质量</h3>
      <time v-if="timeLabel">{{ timeLabel }}</time>
    </header>

    <div class="rt-hero" v-if="header">
      <div class="aqi-ring" :style="{ '--level-color': levelColor }">
        <svg viewBox="0 0 96 96" aria-hidden="true">
          <circle class="ring-track" cx="48" cy="48" r="42" />
          <circle
            class="ring-value"
            cx="48" cy="48" r="42"
            :stroke-dasharray="ringDash"
          />
        </svg>
        <div class="ring-center">
          <strong>{{ header.aqi ?? '—' }}</strong>
          <span>{{ header.quality || aqiLevelName(header.aqi) }}</span>
        </div>
      </div>
      <div class="hero-info">
        <p class="hero-place">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-5.1-7-11a7 7 0 1 1 14 0c0 5.9-7 11-7 11Z" /><circle cx="12" cy="10" r="2.6" /></svg>
          许昌市
        </p>
        <p v-if="header.primary_pollutant" class="hero-primary">首要污染物 <strong>{{ header.primary_pollutant }}</strong></p>
        <p class="hero-update">数据时间 <strong>{{ timeLabel || '—' }}</strong></p>
      </div>
    </div>

    <div class="pollutant-grid" v-if="header">
      <div class="cell" v-for="item in pollutantCells" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <div class="met-grid" v-if="header?.met">
      <div class="cell" v-for="item in metCells" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>

    <div class="minute-chip" v-if="minute?.station">
      <small>中大 5 分钟 · {{ minute.station.station_name || '—' }}</small>
      <span v-for="item in minuteCells" :key="item.label">
        <i>{{ item.label }}</i><strong>{{ item.value }}</strong>
      </span>
      <small>{{ String(minute.station?.data_time || '').slice(11, 16) }}</small>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { aqiColor, aqiLevelName, windDirectionLabel } from './aqiLevels.js'

const props = defineProps({
  header: { type: Object, default: null },
  minute: { type: Object, default: null }
})

const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const levelColor = computed(() => aqiColor(props.header?.aqi))

// AQI 圆环进度：以 300（严重）为满量程
const ringDash = computed(() => {
  const aqi = Number(props.header?.aqi)
  const ratio = Number.isFinite(aqi) ? Math.min(aqi / 300, 1) : 0
  const circumference = 2 * Math.PI * 42
  return `${(circumference * ratio).toFixed(1)} ${circumference.toFixed(1)}`
})

const timeLabel = computed(() =>
  String(props.header?.data_time || props.header?.dataTime || '')
    .replace('T', ' ')
    .slice(5, 16)
)

const pollutantCells = computed(() => [
  { label: 'PM2.5', value: fmt(props.header?.pm25) },
  { label: 'PM10', value: fmt(props.header?.pm10) },
  { label: 'SO₂', value: fmt(props.header?.so2) },
  { label: 'NO₂', value: fmt(props.header?.no2) },
  { label: 'O₃', value: fmt(props.header?.o3) },
  { label: 'CO', value: fmt(props.header?.co, 1) }
])

const metCells = computed(() => [
  { label: '温度℃', value: fmt(props.header?.met?.temperature, 1) },
  { label: '湿度%', value: fmt(props.header?.met?.humidity) },
  { label: '风向', value: windDirectionLabel(props.header?.met?.wind_direction) },
  { label: '风速m/s', value: fmt(props.header?.met?.wind_speed, 1) }
])

const minuteCells = computed(() => {
  const s = props.minute?.station || {}
  return [
    { label: 'PM2.5', value: fmt(s.pm25) },
    { label: 'PM10', value: fmt(s.pm10) },
    { label: 'SO₂', value: fmt(s.so2) },
    { label: 'NO₂', value: fmt(s.no2) },
    { label: 'O₃', value: fmt(s.o3) },
    { label: 'CO', value: fmt(s.co, 1) }
  ]
})
</script>

<style lang="scss" scoped>
.realtime-panel {
  padding: 12px 14px 10px;
  border: 1px solid rgba(63, 200, 212, 0.25);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.72);
  backdrop-filter: blur(6px);
}

.rt-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;

  .rt-bar {
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
  time {
    margin-left: auto;
    font-size: 12px;
    color: #8ab6c2;
  }
}

.rt-hero {
  display: flex;
  align-items: center;
  gap: 14px;
}

.aqi-ring {
  --level-color: #5b7684;
  position: relative;
  width: 96px;
  height: 96px;
  flex-shrink: 0;

  svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  circle {
    fill: none;
    stroke-width: 7;
  }
  .ring-track {
    stroke: rgba(255, 255, 255, 0.12);
  }
  .ring-value {
    stroke: var(--level-color);
    stroke-linecap: round;
    filter: drop-shadow(0 0 6px color-mix(in srgb, var(--level-color) 60%, transparent));
    transition: stroke-dasharray 0.6s ease;
  }

  .ring-center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;

    strong {
      font-size: 30px;
      line-height: 1;
      color: var(--level-color);
      text-shadow: 0 0 14px color-mix(in srgb, var(--level-color) 60%, transparent);
    }
    span {
      margin-top: 3px;
      font-size: 13px;
      color: #eaf6f8;
    }
  }
}

.hero-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;

  p { margin: 0; font-size: 13px; color: #8ab6c2; }
  strong { color: #eaf6f8; font-weight: 600; }

  .hero-place {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 15px;
    color: #eaf6f8;

    svg {
      width: 15px;
      height: 15px;
      fill: none;
      stroke: #3fc8d4;
      stroke-width: 1.8;
    }
  }
}

.pollutant-grid,
.met-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 10px;
}

.met-grid { grid-template-columns: repeat(4, 1fr); }

.cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 2px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);

  span { font-size: 11px; color: #8ab6c2; }
  strong { margin-top: 2px; font-size: 17px; color: #eaf6f8; }
}

.minute-chip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 10px;
  padding: 6px 10px;
  border: 1px solid rgba(63, 200, 212, 0.35);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);

  small { font-size: 11px; color: #8ab6c2; }
  small:last-child { margin-left: auto; }

  > span {
    display: inline-flex;
    align-items: baseline;
    gap: 3px;
    i { font-style: normal; font-size: 10px; color: #8ab6c2; }
    strong { font-size: 13px; color: #eaf6f8; }
  }
}
</style>
