<template>
  <section v-if="chart.kind === 'spec'" class="inline-chart-card">
    <header><span>{{ chart.resource.label || '交互图表' }}</span><button type="button" @click.stop="expanded = !expanded">{{ expanded ? '收起' : '全屏查看' }}</button></header>
    <div :class="{ fullscreen: expanded }">
      <button v-if="expanded" type="button" class="close-chart" @click.stop="expanded = false">关闭图表</button>
      <ChartResourceRenderer :resource="chart.resource" :content-url="chart.url" />
    </div>
  </section>
  <span v-else class="md-image-wrapper inline-chart-image">
    <AuthenticatedImage :source="chart.url" :alt="chart.resource.label || '图表'" class="md-external-image"
      @resolved="imageStatus = $event ? 'ready' : 'loading'" @error="imageStatus = 'error'" />
    <span v-if="imageStatus === 'loading'">图表加载中…</span>
    <span v-else-if="imageStatus === 'error'">图表加载失败</span>
    <span v-else-if="chart.resource.label" class="md-image-caption">{{ chart.resource.label }}</span>
  </span>
</template>
<script setup>
import { ref } from 'vue'
import AuthenticatedImage from './AuthenticatedImage.vue'
import ChartResourceRenderer from './resources/renderers/ChartResourceRenderer.vue'
defineProps({ chart: { type: Object, required: true } })
const expanded = ref(false)
const imageStatus = ref('loading')
</script>
<style scoped>
.inline-chart-card { width: 100%; min-width: 0; box-sizing: border-box; margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: white; }
.inline-chart-card :deep(.chart) { padding: 4px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; font-size: 13px; }
button { border: 0; background: transparent; color: #2878ff; cursor: pointer; white-space: nowrap; }
.fullscreen { position: fixed; inset: 0; z-index: 2000; background: white; overflow: auto; padding-top: 40px; }
.close-chart { position: fixed; top: 12px; right: 18px; z-index: 2001; }
</style>
