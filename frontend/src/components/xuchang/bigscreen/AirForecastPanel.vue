<template>
  <section class="screen-card">
    <header class="screen-card-title">
      <span class="title-bar"></span>
      <h3>空气质量预报</h3>
      <div class="title-right"><small>未来 5 日 · 每日更新</small></div>
    </header>

    <div v-if="daily.length" class="aq-daily">
      <div
        v-for="item in daily"
        :key="item.date"
        class="aq-day"
        :style="{ borderColor: aqiColor(item.aqi) }"
      >
        <span class="aq-date">{{ item.date?.slice(5) }}</span>
        <strong :style="{ color: aqiColor(item.aqi) }">{{ item.min_aqi ?? '—' }}~{{ item.max_aqi ?? '—' }}</strong>
        <span class="aq-level" :style="{ color: aqiColor(item.aqi) }">{{ aqiLevelName(item.aqi) }}</span>
        <span class="aq-primary">{{ item.primary_pollutant || '—' }}</span>
      </div>
    </div>
    <div v-else class="empty-hint">暂无空气质量日预报</div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { aqiColor, aqiLevelName } from './aqiLevels.js'

const props = defineProps({
  forecast: { type: Object, default: null }   // forecast_72h
})

const daily = computed(() => (props.forecast?.daily || []).slice(0, 5))
</script>

<style lang="scss" scoped>
@import './panelCommon.scss';

.aq-daily {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;

  .aq-day {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 8px 2px;
    border: 1px solid;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.03);
    min-width: 0;

    .aq-date { font-size: 11px; color: #8ab6c2; }
    strong { font-size: 16px; white-space: nowrap; }
    .aq-level { font-size: 12px; }
    .aq-primary {
      font-size: 10px;
      color: #8ab6c2;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}
</style>
