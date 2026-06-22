<template>
  <section class="guangdong-map" aria-label="广东省空气质量总览地图">
    <div class="map-surface">
      <div class="province-outline">
        <span class="province-label">广东</span>
      </div>
      <div class="map-layer layer-city" :class="{ active: layers.city_metrics }">城市指标</div>
      <div class="map-layer layer-stations" :class="{ active: layers.stations }">站点</div>
      <div class="map-layer layer-heatmap" :class="{ active: layers.heatmap }">热力</div>
    </div>
    <div class="map-footer">
      <span>{{ focusLabel }}</span>
      <span>{{ overviewLabel }}</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  focus: {
    type: Object,
    default: null
  },
  layers: {
    type: Object,
    default: () => ({})
  }
})

const focusLabel = computed(() => {
  const cities = props.focus?.cities || []
  const stations = props.focus?.stations || []
  if (stations.length > 0) return `关注站点：${stations.join('、')}`
  if (cities.length > 0) return `关注城市：${cities.join('、')}`
  return '关注范围：全省'
})

const overviewLabel = computed(() => {
  const updatedAt = props.overview?.updated_at || props.overview?.data_time || props.overview?.timestamp
  return updatedAt ? `更新时间：${updatedAt}` : '等待地图数据'
})
</script>

<style scoped>
.guangdong-map {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  background: linear-gradient(135deg, #e7f1f0 0%, #dce8ee 48%, #f0f3ef 100%);
  color: #20313a;
}

.map-surface {
  position: relative;
  flex: 1;
  min-height: 320px;
}

.province-outline {
  position: absolute;
  inset: 13% 18% 16% 17%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgba(43, 113, 122, 0.45);
  border-radius: 44% 56% 50% 50% / 48% 38% 62% 52%;
  background:
    radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.72), transparent 28%),
    rgba(255, 255, 255, 0.28);
  box-shadow: inset 0 0 48px rgba(43, 113, 122, 0.14);
}

.province-label {
  font-size: clamp(28px, 5vw, 58px);
  font-weight: 700;
  color: rgba(32, 49, 58, 0.62);
}

.map-layer {
  position: absolute;
  max-width: 132px;
  padding: 7px 10px;
  border: 1px solid rgba(32, 49, 58, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.72);
  color: #4f6068;
  font-size: 12px;
  line-height: 1.2;
  opacity: 0.45;
  overflow-wrap: anywhere;
}

.map-layer.active {
  opacity: 1;
  border-color: rgba(17, 128, 118, 0.42);
  color: #0f6c65;
  box-shadow: 0 8px 18px rgba(29, 72, 76, 0.12);
}

.layer-city {
  top: 24%;
  left: 18%;
}

.layer-stations {
  right: 20%;
  top: 35%;
}

.layer-heatmap {
  left: 43%;
  bottom: 24%;
}

.map-footer {
  display: flex;
  gap: 14px;
  justify-content: space-between;
  padding: 10px 14px;
  border-top: 1px solid rgba(32, 49, 58, 0.12);
  background: rgba(255, 255, 255, 0.48);
  font-size: 12px;
  color: #52646c;
}

.map-footer span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
