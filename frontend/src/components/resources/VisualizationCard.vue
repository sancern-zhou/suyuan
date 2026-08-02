<template>
  <article class="visualization-card">
    <header>
      <div class="identity">
        <strong>{{ group.primary?.label || resource.label }}</strong>
        <span>{{ formatName(resource) }} · v{{ group.primary?.version || resource.version }}</span>
      </div>
      <a
        v-if="downloadTarget?.download_url"
        :href="downloadTarget.download_url"
        :download="downloadFileName(downloadTarget)"
      >下载</a>
    </header>
    <div v-if="renderError" class="card-state error">
      <span>加载失败：{{ renderError }}</span>
      <button type="button" @click="retry">重试</button>
    </div>
    <component
      :is="rendererComponent"
      v-else
      :key="renderKey"
      class="card-content"
      :resource="resource"
      :group="group"
      :content-url="resource.content_url"
    />
  </article>
</template>

<script setup>
import { computed, defineAsyncComponent, onErrorCaptured, ref, watch } from 'vue'
import { RESOURCE_RENDERERS, rendererKey } from '@/services/resourceRendererRegistry.js'
import { downloadFileName, formatName } from '@/services/resourceDownloads.js'

const props = defineProps({
  group: { type: Object, required: true },
  resource: { type: Object, required: true }
})

const RENDERERS = Object.fromEntries(
  Object.entries(RESOURCE_RENDERERS).map(([key, loader]) => [key, defineAsyncComponent(loader)])
)
const renderError = ref('')
const retryVersion = ref(0)
const rendererComponent = computed(() => RENDERERS[rendererKey(props.resource)])
const renderKey = computed(() => (
  `${props.resource.resource_id}:${props.resource.version}:${retryVersion.value}`
))
const downloadTarget = computed(() => props.group.primary?.download_url
  ? props.group.primary
  : props.resource)

const retry = () => {
  renderError.value = ''
  retryVersion.value += 1
}

watch(() => props.resource.resource_id, () => { renderError.value = '' })
onErrorCaptured(error => {
  renderError.value = error?.message || String(error)
  return false
})
</script>

<style scoped>
.visualization-card { display: flex; min-width: 0; min-height: 360px; flex-direction: column; overflow: hidden; border: 1px solid #e1e8f0; border-radius: 10px; background: #fff; box-shadow: 0 1px 3px rgba(15, 23, 42, .06); }
header { display: flex; min-height: 52px; flex: 0 0 auto; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 12px; border-bottom: 1px solid #edf1f5; box-sizing: border-box; }
.identity { display: grid; min-width: 0; gap: 3px; }.identity strong { overflow: hidden; color: #17223b; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.identity span { color: #7a8798; font-size: 11px; }
a, button { border: 0; background: transparent; color: #1976d2; cursor: pointer; font: inherit; text-decoration: none; white-space: nowrap; }.card-content { min-height: 300px; flex: 1; }.card-state { display: grid; min-height: 300px; flex: 1; gap: 8px; place-content: center; text-align: center; }.error { color: #b42318; }
</style>
