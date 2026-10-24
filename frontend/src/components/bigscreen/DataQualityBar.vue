<template>
  <section class="quality-bar" aria-label="站点在线情况">
    <span class="bar-title">站点在线</span>
    <span class="bar-item" v-if="siteText">{{ siteText }}</span>
    <span class="bar-item" v-if="townText">{{ townText }}</span>
    <span v-if="!siteText && !townText" class="bar-empty">暂无在线数据</span>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { formatHour } from './aqiLevels.js'

const props = defineProps({
  quality: { type: Object, default: null }
})

const siteText = computed(() => {
  const site = props.quality?.site_hour
  if (!site || site.online == null) return ''
  return `县级站 ${site.online}${formatHour(site.data_time) ? ` · ${formatHour(site.data_time)}` : ''}`
})

const townText = computed(() => {
  const town = props.quality?.town_hour
  if (!town || town.online == null) return ''
  const caliberTag = town.caliber === 'src' ? '（原始口径）' : ''
  return `乡镇站 ${town.online}/${town.total ?? '—'}${caliberTag}`
})
</script>

<style lang="scss" scoped>
.quality-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 14px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
  font-size: 12px;
  color: #c9dfe6;
  flex-shrink: 0;

  .bar-title {
    color: #3fc8d4;
    letter-spacing: 1px;
    flex-shrink: 0;
  }
  .bar-item strong { color: #eaf6f8; }
  .bar-empty { color: #6f95a3; }
}
</style>
