<template>
  <main class="bigscreen-viewport">
    <div class="bigscreen-stage" ref="stageEl" :style="{ transform: `scale(${scale})` }">
      <ScreenHeader
        :header="store.header"
        :data-cutoff-hour="store.snapshot?.data_cutoff_hour || ''"
        :generated-at="store.snapshot?.generated_at || ''"
        :loading="store.loading"
        :error="store.error"
      />

      <div class="screen-body">
        <div class="column column-left">
          <RankingPanel
            title="河南 18 城市小时排名"
            :rows="store.cityHourRank?.rows || []"
            :data-time="store.cityHourRank?.data_time"
            name-key="city"
          />
          <RankingPanel
            title="许昌县市区小时排名"
            :rows="store.countyHourRank?.rows || []"
            :data-time="store.countyHourRank?.data_time"
            name-key="county"
          />
        </div>

        <div class="column column-center">
          <FocusCarouselPanel
            :assets="store.assets"
            :asset-url="store.assetUrl"
            class="center-carousel"
          >
            <StationMapPanel :stations="store.stations" :alerts="store.alerts" />
          </FocusCarouselPanel>
          <TrendPanel :trend="store.cityTrend" :forecast="store.forecast" />
        </div>

        <div class="column column-right">
          <AlertListPanel :alerts="store.alerts" />
          <TargetProgressPanel :target="store.yearTarget || {}" :forecast="store.forecast" />
        </div>
      </div>

      <BroadcastTicker :items="store.broadcast" />
    </div>
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import ScreenHeader from '@/components/bigscreen/ScreenHeader.vue'
import RankingPanel from '@/components/bigscreen/RankingPanel.vue'
import TrendPanel from '@/components/bigscreen/TrendPanel.vue'
import TargetProgressPanel from '@/components/bigscreen/TargetProgressPanel.vue'
import AlertListPanel from '@/components/bigscreen/AlertListPanel.vue'
import StationMapPanel from '@/components/bigscreen/StationMapPanel.vue'
import FocusCarouselPanel from '@/components/bigscreen/FocusCarouselPanel.vue'
import BroadcastTicker from '@/components/bigscreen/BroadcastTicker.vue'
import { useBigScreenStore } from '@/stores/bigScreen.js'

const DESIGN_WIDTH = 1920
const DESIGN_HEIGHT = 1080

const store = useBigScreenStore()
const stageEl = ref(null)
const scale = ref(1)

const applyScale = () => {
  scale.value = Math.min(
    window.innerWidth / DESIGN_WIDTH,
    window.innerHeight / DESIGN_HEIGHT
  )
}

onMounted(() => {
  applyScale()
  window.addEventListener('resize', applyScale)
  store.startPolling()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', applyScale)
  store.stopPolling()
})
</script>

<style lang="scss" scoped>
.bigscreen-viewport {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #04141f;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
}

.bigscreen-stage {
  flex-shrink: 0;
  width: 1920px;
  height: 1080px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 18px 14px;
  transform-origin: center center;
  color: #d8ecf1;
  background:
    radial-gradient(1200px 500px at 18% -8%, rgba(17, 96, 134, 0.35), transparent 65%),
    radial-gradient(1000px 480px at 88% 108%, rgba(14, 138, 150, 0.22), transparent 65%),
    #051a28;
}

.screen-body {
  flex: 1;
  display: grid;
  grid-template-columns: 372px 1fr 396px;
  gap: 12px;
  min-height: 0;
}

.column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.column-left {
  :first-child { flex: 5; }
  :last-child { flex: 4; }
}

.column-center {
  .center-carousel { flex: 3; }
  :last-child { flex: 2; }
}

.column-right {
  :first-child { flex: 4; }
  :last-child { flex: 3; }
}
</style>
