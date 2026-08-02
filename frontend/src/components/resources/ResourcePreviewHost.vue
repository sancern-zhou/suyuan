<template>
  <section class="resource-preview-host">
    <p v-if="state?.loading && !resource" class="state">正在加载资源...</p>
    <div v-else-if="state?.error && !resource" class="state error">
      <p>{{ state.error }}</p>
      <button type="button" @click="retry">重试</button>
    </div>
    <div v-else-if="renderError" class="state error">
      <p>资源预览失败：{{ renderError }}</p>
      <button type="button" @click="renderError = ''">重试</button>
    </div>
    <p v-else-if="!resource" class="state">请选择一个文件产物</p>
    <div v-else class="preview-layout">
      <ResourcePreviewActions
        :group="group"
        :resource="resource"
        :floating="target === 'document' && resource.renderer !== 'spreadsheet'"
      />
      <component
        :is="rendererComponent"
        :key="`${resource.group_id}:${resource.renderer}`"
        class="preview-content"
        :resource="resource"
        :group="group"
        :content-url="resource.content_url"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, onErrorCaptured, ref } from 'vue'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { buildResourceGroups, preferredPreview, targetTab, topLevelProducts } from '@/services/resourceGroups.js'
import { rendererKey, RESOURCE_RENDERERS } from '@/services/resourceRendererRegistry.js'
import ResourcePreviewActions from './ResourcePreviewActions.vue'

const RENDERER_COMPONENTS = Object.fromEntries(
  Object.entries(RESOURCE_RENDERERS).map(([key, loader]) => [key, defineAsyncComponent(loader)])
)

const resourceStore = useSessionResourceStore()
const props = defineProps({
  target: { type: String, default: '' }
})
const renderError = ref('')
const state = computed(() => resourceStore.activeSessionState)
const allGroups = computed(() => buildResourceGroups(state.value?.resources || []))
const groups = computed(() => topLevelProducts(allGroups.value))
const selected = computed(() => resourceStore.activeSessionId
  ? resourceStore.selectedResource(resourceStore.activeSessionId)
  : null)
const explicitAttachment = computed(() => (
  state.value?.selectionOrigin === 'explicit' && selected.value?.role === 'attachment'
    ? selected.value
    : null
))
const group = computed(() => {
  if (explicitAttachment.value) {
    const attachmentGroup = allGroups.value.find(
      item => item.group_id === explicitAttachment.value.group_id
    ) || null
    if (
      attachmentGroup
      && (!props.target || targetTab(attachmentGroup) === props.target)
    ) return attachmentGroup
  }
  const selectedGroup = groups.value.find(item => item.group_id === selected.value?.group_id)
  if (selectedGroup && (!props.target || targetTab(selectedGroup) === props.target)) return selectedGroup
  return groups.value.find(item => !props.target || targetTab(item) === props.target) || null
})
const resource = computed(() => {
  if (explicitAttachment.value) return preferredPreview(group.value) || explicitAttachment.value
  if (selected.value && selected.value.group_id === group.value?.group_id) return selected.value
  return preferredPreview(group.value)
})
const rendererComponent = computed(() => {
  if (!resource.value) return null
  return RENDERER_COMPONENTS[rendererKey(resource.value)]
})

const retry = () => resourceStore.activeSessionId
  ? resourceStore.loadCatalog(resourceStore.activeSessionId)
  : null

onErrorCaptured((error) => {
  renderError.value = error?.message || String(error)
  return false
})
</script>

<style scoped>
.resource-preview-host { height: 100%; min-height: 0; background: #fff; }.preview-layout { position: relative; display: flex; height: 100%; min-height: 0; flex-direction: column; }.preview-content { min-height: 0; flex: 1; }.state { display: grid; height: 100%; margin: 0; place-content: center; color: #64748b; text-align: center; }.error { color: #b42318; }.state button { border: 0; background: transparent; color: #1976d2; cursor: pointer; }
</style>
