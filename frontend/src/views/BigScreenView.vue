<template>
  <main ref="viewportEl" class="bigscreen-viewport" :class="{ 'is-embedded': embedded }">
    <StationMapPanel
      class="map-layer"
      :stations="store.stations"
      :alerts="store.alerts"
    />

    <ScreenHeader
      :header="store.header"
      :minute="store.minute"
      :data-cutoff-hour="store.snapshot?.data_cutoff_hour || ''"
      :generated-at="store.snapshot?.generated_at || ''"
      :loading="store.loading"
      :error="store.error"
    />

    <button
      class="panel-handle handle-left"
      :class="{ open: leftOpen }"
      type="button"
      :title="leftOpen ? '收起数据面板' : '展开数据面板'"
      @click="leftOpen = !leftOpen"
    >{{ leftOpen ? '‹' : '›' }}</button>

    <aside v-show="leftOpen" class="side-panel panel-left">
      <RealtimePanel :header="store.header" :minute="store.minute" />
      <TrendPanel :trend="store.cityTrend" :forecast="store.forecast" />
      <RankingPanel
        title="国控站实时排名"
        name-key="station_name"
        :rows="nationalRows"
        :data-time="nationalTime"
        highlight=""
      />
    </aside>

    <button
      class="panel-handle handle-right"
      :class="{ open: rightOpen }"
      type="button"
      :title="rightOpen ? '收起数据面板' : '展开数据面板'"
      @click="rightOpen = !rightOpen"
    >{{ rightOpen ? '›' : '‹' }}</button>

    <aside v-show="rightOpen" class="side-panel panel-right">
      <DataQualityBar :quality="store.quality" />
      <AlertListPanel :alerts="store.alerts" />
      <TargetProgressPanel
        :target="store.yearTarget || {}"
        :forecast="store.forecast"
        :rank168="store.rank168"
      />
    </aside>

    <BroadcastTicker :items="store.broadcast" />
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ScreenHeader from '@/components/bigscreen/ScreenHeader.vue'
import RealtimePanel from '@/components/bigscreen/RealtimePanel.vue'
import TrendPanel from '@/components/bigscreen/TrendPanel.vue'
import RankingPanel from '@/components/bigscreen/RankingPanel.vue'
import TargetProgressPanel from '@/components/bigscreen/TargetProgressPanel.vue'
import AlertListPanel from '@/components/bigscreen/AlertListPanel.vue'
import StationMapPanel from '@/components/bigscreen/StationMapPanel.vue'
import DataQualityBar from '@/components/bigscreen/DataQualityBar.vue'
import BroadcastTicker from '@/components/bigscreen/BroadcastTicker.vue'
import { useBigScreenStore } from '@/stores/bigScreen.js'
import { initDashboardAccessToken } from '@/api/bigScreen.js'

const props = defineProps({
  embedded: { type: Boolean, default: false }
})

const store = useBigScreenStore()
const viewportEl = ref(null)
const leftOpen = ref(true)
const rightOpen = ref(true)

// 国控站行映射为排名表字段（RankingPanel 期望 nameKey/aqi/pm25/quality/primary）
const nationalRows = computed(() =>
  (store.stations?.national || [])
    .filter(item => item.aqi != null && Number.isFinite(Number(item.aqi)))
    .sort((a, b) => a.aqi - b.aqi)
    .map((item, index) => ({
      station_name: item.station_name,
      aqi: item.aqi,
      pm25: item.pm25,
      quality: item.quality,
      primary: item.primary,
      rank: index + 1
    }))
)

const nationalTime = computed(() => {
  const rows = store.stations?.national || []
  return String(rows[0]?.data_time || '').replace('T', ' ').slice(0, 16)
})

onMounted(() => {
  initDashboardAccessToken()
  store.startPolling()
})

onBeforeUnmount(() => {
  store.stopPolling()
})
</script>

<style lang="scss" scoped>
.bigscreen-viewport {
  position: fixed;
  inset: 0;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  background: #04141f;
}

.bigscreen-viewport.is-embedded {
  position: absolute;
}

.map-layer {
  position: absolute;
  inset: 0;
}

.side-panel {
  position: absolute;
  top: 64px;
  bottom: 44px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 380px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: rgba(63, 200, 212, 0.35) transparent;
  padding-bottom: 4px;
}

.panel-left { left: 12px; }
.panel-right { right: 12px; }

/* 自由高度滚动容器内，ECharts 面板需固定高度防止塌陷 */
.side-panel {
  :deep(.trend-panel),
  :deep(.ranking-panel) {
    height: 250px;
    flex-shrink: 0;
  }

  :deep(.alert-panel) {
    max-height: 320px;
    flex-shrink: 0;
  }

  /* 卫星底图上提升面板遮蔽度，保证文字可读 */
  :deep(section) {
    background: rgba(6, 30, 44, 0.82);
    backdrop-filter: blur(8px);
  }
}

.panel-handle {
  position: absolute;
  top: 50%;
  z-index: 210;
  width: 20px;
  height: 64px;
  border: 1px solid rgba(63, 200, 212, 0.4);
  background: rgba(7, 41, 59, 0.85);
  color: #3fc8d4;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  backdrop-filter: blur(4px);
  transition: all 0.2s;

  &:hover { background: rgba(63, 200, 212, 0.25); }
}

.handle-left {
  left: 0;
  border-left: none;
  border-radius: 0 8px 8px 0;
  transition: left 0.25s ease;

  &.open { left: 392px; }
}

.handle-right {
  right: 0;
  border-right: none;
  border-radius: 8px 0 0 8px;
  transition: right 0.25s ease;

  &.open { right: 392px; }
}
</style>
