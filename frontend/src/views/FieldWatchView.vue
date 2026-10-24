<template>
  <main class="fieldwatch">
    <header class="fw-header">
      <div>
        <h1>现场巡查快报</h1>
        <p>许昌市大气环境管控 · 移动端</p>
      </div>
      <span class="fw-status" :class="{ stale: store.error }">
        <i aria-hidden="true"></i>{{ store.error ? '刷新异常' : formatHour(store.snapshot?.data_cutoff_hour) }}
      </span>
    </header>

    <section class="fw-now" v-if="store.header">
      <div class="fw-aqi" :style="{ '--level-color': aqiColor(store.header.aqi) }">
        <strong>{{ store.header.aqi ?? '—' }}</strong>
        <span>{{ store.header.quality || aqiLevelName(store.header.aqi) }}</span>
      </div>
      <div class="fw-city">
        <strong>许昌市</strong>
        <small v-if="store.header.primary_pollutant">首要 {{ store.header.primary_pollutant }}</small>
        <small>PM2.5 {{ fmt(store.header.pm25) }} · PM10 {{ fmt(store.header.pm10) }} · O3 {{ fmt(store.header.o3) }}</small>
      </div>
      <div class="fw-met" v-if="store.header.met">
        <small>{{ windDirectionLabel(store.header.met.wind_direction) }}风 {{ fmt(store.header.met.wind_speed) }}km/h</small>
        <small>{{ fmt(store.header.met.temperature) }}℃ · 湿度{{ fmt(store.header.met.humidity) }}%</small>
      </div>
    </section>

    <section class="fw-section" aria-label="告警列表">
      <h2>告警与任务派发</h2>
      <div v-if="store.alerts.length" class="fw-alerts">
        <div
          v-for="alert in store.alerts"
          :key="alert.episode_id"
          :class="['fw-alert', { active: alert.status === 'active' }]"
        >
          <div class="fw-alert-head">
            <strong>{{ alert.station_name || alert.station_id }}</strong>
            <span :class="['fw-alert-status', alert.status]">{{ alert.status === 'active' ? '进行中' : '已结束' }}</span>
          </div>
          <p class="fw-alert-meta">
            <span v-if="alert.target_pollutant">{{ alert.target_pollutant.toUpperCase() }}</span>
            <span v-if="alert.peak_station_value">峰值 {{ alert.peak_station_value }}</span>
            <span v-if="alert.peak_deviation_ratio">偏离 {{ alert.peak_deviation_ratio }}倍</span>
            <span>{{ formatHour(alert.last_seen_at || alert.started_at) }}</span>
            <span v-if="alert.hot" class="fw-hot">实时</span>
          </p>
        </div>
      </div>
      <div v-else class="fw-empty">
        <span class="ok-dot" aria-hidden="true"></span>近 24 小时无站点偏离告警
      </div>
    </section>

    <section class="fw-section" aria-label="全县区实况">
      <h2>区县实况</h2>
      <div class="fw-counties">
        <div
          v-for="county in store.stations.counties"
          :key="county.station_name"
          class="fw-county"
          :style="{ borderColor: aqiColor(county.aqi) }"
        >
          <strong>{{ county.station_name }}</strong>
          <span :style="{ color: aqiColor(county.aqi) }">{{ county.aqi ?? '—' }}</span>
          <small>{{ county.quality || aqiLevelName(county.aqi) }}</small>
        </div>
      </div>
    </section>

    <section class="fw-section" aria-label="任务播报">
      <h2>任务播报</h2>
      <div v-if="store.broadcast.length" class="fw-broadcast">
        <div v-for="item in store.broadcast" :key="`${item.time}-${item.task_name}`" class="fw-broadcast-item">
          <small>{{ formatDateTime(item.time).slice(5, 16) }} · {{ item.task_name }}</small>
          <p>{{ item.text }}</p>
        </div>
      </div>
      <div v-else class="fw-empty">暂无播报</div>
    </section>

    <footer class="fw-footer">
      <button type="button" @click="store.refresh()">手动刷新</button>
      <small>数据与对话问数同源 · {{ formatDateTime(store.lastFetchedAt) }}</small>
    </footer>
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useBigScreenStore } from '@/stores/bigScreen.js'
import { aqiColor, aqiLevelName, formatDateTime, formatHour, windDirectionLabel } from '@/components/bigscreen/aqiLevels.js'

const store = useBigScreenStore()

const fmt = (value, digits = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(digits) : '—'
}

onMounted(() => store.startPolling())
onBeforeUnmount(() => store.stopPolling())
</script>

<style lang="scss" scoped>
.fieldwatch {
  max-width: 560px;
  margin: 0 auto;
  padding: 14px 14px 28px;
  color: #d8ecf1;
  background:
    radial-gradient(600px 280px at 20% -5%, rgba(17, 96, 134, 0.4), transparent 70%),
    #051a28;
  min-height: 100vh;
}

.fw-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;

  h1 {
    margin: 0;
    font-size: 20px;
    letter-spacing: 1px;
  }
  p { margin: 4px 0 0; font-size: 12px; color: #3fc8d4; }

  .fw-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #21a366;
    i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    &.stale { color: #e5ae22; }
  }
}

.fw-now {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 10px;
  background: rgba(7, 41, 59, 0.55);
  margin-bottom: 16px;
}

.fw-aqi {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 74px;
  height: 74px;
  border: 1px solid var(--level-color, #5b7684);
  border-radius: 10px;

  strong { font-size: 28px; color: var(--level-color, #5b7684); }
  span { font-size: 13px; }
}

.fw-city {
  display: flex;
  flex-direction: column;
  gap: 2px;
  strong { font-size: 16px; }
  small { color: #8ab6c2; font-size: 12px; }
}

.fw-met {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  small { color: #8ab6c2; font-size: 12px; }
}

.fw-section {
  margin-bottom: 18px;

  h2 {
    margin: 0 0 8px;
    font-size: 14px;
    color: #3fc8d4;
    letter-spacing: 1px;
  }
}

.fw-alerts {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fw-alert {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border-left: 3px solid #5b7684;

  &.active {
    border-left-color: #d85245;
    background: rgba(216, 82, 69, 0.1);
  }
}

.fw-alert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;

  strong { font-size: 15px; }
  .fw-alert-status {
    font-size: 12px;
    color: #6f95a3;
    &.active { color: #ff9d94; }
  }
}

.fw-alert-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0 0;
  font-size: 12px;
  color: #8ab6c2;

  .fw-hot {
    padding: 0 6px;
    border-radius: 4px;
    background: rgba(229, 174, 34, 0.2);
    color: #e5ae22;
  }
}

.fw-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  font-size: 13px;
  color: #6f95a3;

  .ok-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #21a366;
  }
}

.fw-counties {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
}

.fw-county {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  border: 1px solid;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);

  strong { font-size: 13px; }
  span { font-size: 19px; font-weight: 700; }
  small { font-size: 11px; color: #8ab6c2; }
}

.fw-broadcast {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fw-broadcast-item {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);

  small { color: #6f95a3; font-size: 12px; }
  p { margin: 4px 0 0; font-size: 13px; line-height: 1.5; }
}

.fw-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: 8px;

  button {
    padding: 8px 26px;
    border: 1px solid rgba(63, 200, 212, 0.35);
    border-radius: 20px;
    background: rgba(63, 200, 212, 0.12);
    color: #3fc8d4;
    font-size: 14px;
  }
  small { color: #6f95a3; font-size: 11px; }
}
</style>
