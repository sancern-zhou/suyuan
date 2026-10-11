<template>
  <section class="inline-chart-card">
    <header><span>{{ resource.label || '交互图表' }}</span><button @click="expanded = !expanded">{{ expanded ? '收起' : '全屏查看' }}</button></header>
    <div :class="{ fullscreen: expanded }">
      <button v-if="expanded" class="close-chart" @click="expanded = false">关闭图表</button>
      <ChartResourceRenderer :resource="resource" :content-url="resource.content_url" />
    </div>
  </section>
</template>
<script setup>
import { ref } from 'vue'
import ChartResourceRenderer from './resources/renderers/ChartResourceRenderer.vue'
defineProps({ resource: { type: Object, required: true } })
const expanded = ref(false)
</script>
<style scoped>
.inline-chart-card { width: 100%; min-width: 0; box-sizing: border-box; margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: white; }
.inline-chart-card :deep(.chart) { padding: 4px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; font-size: 13px; }
button { border: 0; background: transparent; color: #2878ff; cursor: pointer; white-space: nowrap; }
.fullscreen { position: fixed; inset: 0; z-index: 2000; background: white; overflow: auto; padding-top: 40px; }
.close-chart { position: fixed; top: 12px; right: 18px; z-index: 2001; }
</style>
