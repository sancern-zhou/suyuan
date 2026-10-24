<template>
  <header class="screen-header">
    <div class="brand">
      <h1>许昌市大气环境管控数据大屏</h1>
      <p class="brand-sub">空气质量 · 排名 · 告警 · 达标态势</p>
    </div>

    <div class="now-block" v-if="header">
      <div class="aqi-block" :style="{ '--level-color': aqiColor(header.aqi) }">
        <span class="aqi-value">{{ header.aqi ?? '—' }}</span>
        <span class="aqi-level">{{ header.quality || aqiLevelName(header.aqi) }}</span>
        <span class="aqi-primary" v-if="header.primary_pollutant">首要 {{ header.primary_pollutant }}</span>
      </div>
      <div class="pollutant-grid">
        <div class="pollutant"><span>PM2.5</span><strong>{{ fmt(header.pm25) }}</strong></div>
        <div class="pollutant"><span>PM10</span><strong>{{ fmt(header.pm10) }}</strong></div>
        <div class="pollutant"><span>O3</span><strong>{{ fmt(header.o3) }}</strong></div>
        <div class="pollutant"><span>NO2</span><strong>{{ fmt(header.no2) }}</strong></div>
        <div class="pollutant"><span>SO2</span><strong>{{ fmt(header.so2) }}</strong></div>
        <div class="pollutant"><span>CO</span><strong>{{ fmt(header.co, 1) }}</strong></div>
      </div>
      <div class="met-grid" v-if="header.met">
        <div class="met"><span>气温</span><strong>{{ fmt(header.met.temperature) }}℃</strong></div>
        <div class="met"><span>湿度</span><strong>{{ fmt(header.met.humidity) }}%</strong></div>
        <div class="met"><span>风向</span><strong>{{ windDirectionLabel(header.met.wind_direction) }}</strong></div>
        <div class="met"><span>风速</span><strong>{{ fmt(header.met.wind_speed) }}km/h</strong></div>
      </div>
    </div>

    <div class="meta-block">
      <p>数据截止 <strong>{{ formatDateTime(dataCutoffHour) }}</strong></p>
      <p>快照生成 <strong>{{ formatDateTime(generatedAt) }}</strong></p>
      <p class="status-line" :class="{ stale: error }">
        <i aria-hidden="true"></i>{{ error ? '数据刷新异常，展示最近一次快照' : (loading ? '正在刷新…' : '运行正常') }}
      </p>
    </div>
  </header>
</template>

<script setup>
import { aqiColor, aqiLevelName, formatDateTime, windDirectionLabel } from './aqiLevels.js'

defineProps({
  header: { type: Object, default: null },
  dataCutoffHour: { type: String, default: '' },
  generatedAt: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}
</script>

<style lang="scss" scoped>
.screen-header {
  display: grid;
  grid-template-columns: 300px 1fr 250px;
  align-items: center;
  gap: 18px;
  padding: 14px 24px 12px;
  border-bottom: 1px solid rgba(63, 200, 212, 0.25);
  background: linear-gradient(180deg, rgba(7, 41, 59, 0.9), rgba(7, 41, 59, 0.35));
}

.brand {
  h1 {
    margin: 0;
    font-size: 27px;
    letter-spacing: 2px;
    color: #eaf6f8;
  }
  .brand-sub {
    margin: 6px 0 0;
    font-size: 13px;
    letter-spacing: 6px;
    color: #3fc8d4;
  }
}

.now-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 26px;
}

.aqi-block {
  --level-color: #5b7684;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 128px;
  height: 104px;
  border-radius: 10px;
  background: radial-gradient(circle at 50% 30%, rgba(255, 255, 255, 0.08), transparent 70%);
  border: 1px solid var(--level-color);

  .aqi-value {
    font-size: 42px;
    font-weight: 700;
    line-height: 1;
    color: var(--level-color);
    text-shadow: 0 0 18px color-mix(in srgb, var(--level-color) 60%, transparent);
  }
  .aqi-level {
    margin-top: 6px;
    font-size: 16px;
    color: #eaf6f8;
  }
  .aqi-primary {
    margin-top: 2px;
    font-size: 12px;
    color: #8ab6c2;
  }
}

.pollutant-grid,
.met-grid {
  display: grid;
  gap: 8px 18px;
}

.pollutant-grid {
  grid-template-columns: repeat(3, minmax(64px, auto));

  .pollutant {
    display: flex;
    flex-direction: column;
    align-items: center;
    span { font-size: 12px; color: #8ab6c2; }
    strong { font-size: 20px; color: #eaf6f8; }
  }
}

.met-grid {
  grid-template-columns: repeat(2, minmax(84px, auto));

  .met {
    display: flex;
    align-items: baseline;
    gap: 8px;
    span { font-size: 12px; color: #8ab6c2; }
    strong { font-size: 16px; color: #d8ecf1; }
  }
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: #8ab6c2;

  strong { color: #d8ecf1; font-weight: 600; }

  .status-line {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #21a366;

    i {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 8px currentColor;
    }
    &.stale { color: #e5ae22; }
  }
}
</style>
