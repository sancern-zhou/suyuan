<template>
  <header class="screen-header">
    <div class="brand">
      <h1>许昌市大气环境管控数据大屏</h1>
      <p class="brand-sub">空气质量 · 排名 · 告警 · 达标态势</p>
    </div>

    <div class="minute-chip" v-if="minute?.station">
      <small>中大 5 分钟 · {{ minute.station.station_name || '—' }}</small>
      <div class="minute-grid">
        <span v-for="item in minuteCells" :key="item.label">
          <i>{{ item.label }}</i><strong>{{ item.value }}</strong>
        </span>
      </div>
      <small>{{ String(minute.station?.data_time || '').slice(11, 16) }}</small>
    </div>

    <div class="meta-block">
      <p>数据截止 <strong>{{ formatDateTime(dataCutoffHour) }}</strong></p>
      <p class="status-line" :class="{ stale: error }">
        <i aria-hidden="true"></i>{{ error ? '数据刷新异常，展示最近一次快照' : (loading ? '正在刷新…' : '运行正常') }}
      </p>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { formatDateTime } from './aqiLevels.js'

const props = defineProps({
  header: { type: Object, default: null },
  minute: { type: Object, default: null },
  dataCutoffHour: { type: String, default: '' },
  generatedAt: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

const fmtVal = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

const minuteCells = computed(() => {
  const s = props.minute?.station || {}
  return [
    { label: 'PM2.5', value: fmtVal(s.pm25) },
    { label: 'PM10', value: fmtVal(s.pm10) },
    { label: 'SO₂', value: fmtVal(s.so2) },
    { label: 'NO₂', value: fmtVal(s.no2) },
    { label: 'O₃', value: fmtVal(s.o3) },
    { label: 'CO', value: fmtVal(s.co, 1) }
  ]
})
</script>

<style lang="scss" scoped>
.screen-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 220;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 20px 8px;
  background: linear-gradient(180deg, rgba(4, 20, 31, 0.85), rgba(4, 20, 31, 0.25) 80%, transparent);
  pointer-events: none;

  > * { pointer-events: auto; }
}

.brand {
  h1 {
    margin: 0;
    font-size: 22px;
    letter-spacing: 2px;
    color: #eaf6f8;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
  }
  .brand-sub {
    margin: 3px 0 0;
    font-size: 11px;
    letter-spacing: 5px;
    color: #3fc8d4;
  }
}

.minute-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding: 5px 10px;
  border: 1px solid rgba(63, 200, 212, 0.4);
  border-radius: 6px;
  background: rgba(7, 41, 59, 0.8);

  small { font-size: 10px; color: #8ab6c2; }
}

.minute-grid {
  display: grid;
  grid-template-columns: repeat(6, auto);
  gap: 2px 8px;

  > span {
    display: inline-flex;
    align-items: baseline;
    gap: 3px;
    i { font-style: normal; font-size: 10px; color: #8ab6c2; }
    strong { font-size: 12px; color: #d8ecf1; }
  }
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: #8ab6c2;
  text-align: right;

  strong { color: #d8ecf1; font-weight: 600; }

  .status-line {
    display: flex;
    align-items: center;
    justify-content: flex-end;
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
