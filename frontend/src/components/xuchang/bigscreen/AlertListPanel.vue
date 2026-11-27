<template>
  <section class="alert-panel">
    <header class="panel-title">
      <span class="title-bar" aria-hidden="true"></span>
      <h3>站点偏离告警</h3>
      <span class="alert-count" v-if="activeCount">{{ activeCount }} 活跃</span>
    </header>

    <div v-if="alerts.length" class="alert-list">
      <div
        v-for="alert in alerts"
        :key="alert.episode_id"
        :class="['alert-item', { active: alert.status === 'active' }]"
      >
        <span class="alert-station">
          <i class="pulse" v-if="alert.status === 'active'" aria-hidden="true"></i>
          <strong>{{ alert.station_name || alert.station_id || '—' }}</strong>
          <small v-if="alert.target_pollutant">{{ alert.target_pollutant.toUpperCase() }}</small>
        </span>
        <span class="alert-meta">
          <small>峰值 {{ alert.peak_station_value ?? '—' }}<template v-if="alert.peak_deviation_ratio"> · 偏离 {{ alert.peak_deviation_ratio }}倍</template></small>
          <small>{{ formatHour(alert.last_seen_at || alert.started_at) }}</small>
        </span>
        <span :class="['alert-status', alert.status]">{{ alert.status === 'active' ? '进行中' : '已结束' }}</span>
      </div>
    </div>
    <div v-else class="empty">
      <span class="ok-dot" aria-hidden="true"></span>
      近 24 小时无站点偏离告警
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { formatHour } from './aqiLevels.js'

const props = defineProps({
  alerts: { type: Array, default: () => [] }
})

const activeCount = computed(() => props.alerts.filter(item => item.status === 'active').length)
</script>

<style lang="scss" scoped>
.alert-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;

  .title-bar {
    width: 4px;
    height: 14px;
    border-radius: 2px;
    background: #d85245;
  }
  h3 {
    margin: 0;
    font-size: 15px;
    color: #eaf6f8;
    letter-spacing: 1px;
  }
  .alert-count {
    margin-left: auto;
    padding: 2px 10px;
    border-radius: 10px;
    background: rgba(216, 82, 69, 0.2);
    color: #ff9d94;
    font-size: 12px;
  }
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
}

.alert-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  border-left: 3px solid #5b7684;

  &.active {
    border-left-color: #d85245;
    background: rgba(216, 82, 69, 0.08);
  }
}

.alert-station {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;

  strong {
    font-size: 14px;
    color: #eaf6f8;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  small {
    padding: 1px 6px;
    border-radius: 4px;
    background: rgba(63, 200, 212, 0.15);
    color: #3fc8d4;
    font-size: 11px;
  }
  .pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d85245;
    animation: pulse 1.6s ease-in-out infinite;
  }
}

.alert-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  small { font-size: 11px; color: #8ab6c2; }
}

.alert-status {
  font-size: 12px;
  color: #6f95a3;
  &.active { color: #ff9d94; }
}

.empty {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: auto;
  font-size: 13px;
  color: #6f95a3;

  .ok-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #21a366;
    box-shadow: 0 0 10px #21a366;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.35); }
}
</style>
