<template>
  <main class="mobile-map-view">
    <StationMapPanel :stations="store.stations" :alerts="store.alerts" compact />
    <div class="map-status" :class="{ error: store.error }">
      <i></i>
      <span>{{ store.error || (store.loading && !store.snapshot ? '实时地图加载中…' : '站点实时数据') }}</span>
      <time v-if="dataTime">{{ dataTime }}</time>
    </div>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import StationMapPanel from '@/components/xuchang/bigscreen/StationMapPanel.vue'
import { useBigScreenStore } from '@/stores/xuchang/bigScreen.js'
import { initDashboardAccessToken } from '@/api/xuchang/bigScreen.js'

const store = useBigScreenStore()
const dataTime = computed(() => {
  const value = store.snapshot?.latest_station_time || store.snapshot?.data_cutoff_hour || ''
  return String(value).replace('T', ' ').slice(5, 16)
})

onMounted(() => {
  initDashboardAccessToken()
  store.startPolling()
})
onBeforeUnmount(() => store.stopPolling())
</script>

<style lang="scss" scoped>
.mobile-map-view {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #04141f;
}

.map-status {
  position: absolute;
  top: 58px;
  left: 12px;
  z-index: 220;
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: calc(100% - 24px);
  padding: 5px 9px;
  border: 1px solid rgba(63, 200, 212, 0.25);
  border-radius: 5px;
  background: rgba(7, 41, 59, 0.85);
  color: #c9dfe6;
  font-size: 11px;
  pointer-events: none;
  backdrop-filter: blur(4px);

  i {
    width: 6px;
    height: 6px;
    flex: none;
    border-radius: 50%;
    background: #4fd695;
  }

  time { color: #8ab6c2; white-space: nowrap; }
  &.error { color: #ff9d94; }
  &.error i { background: #ff9d94; }
}
</style>
