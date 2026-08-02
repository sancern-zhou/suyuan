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
      <header v-if="target === 'document'" class="document-toolbar">
        <label class="document-picker">
          <span class="sr-only">选择文档</span>
          <select :value="group?.group_id || ''" @change="selectDocument">
            <option
              v-for="item in documentGroups"
              :key="item.group_id"
              :value="item.group_id"
            >{{ item.primary?.label || preferredPreview(item)?.label }}</option>
          </select>
        </label>
        <div class="document-meta">
          <span>{{ String(group?.primary?.format || resource.format || '').toUpperCase() }}</span>
          <span>v{{ group?.primary?.version || resource.version }}</span>
          <span v-if="isLatestVersion" class="latest">最新版本</span>
        </div>
        <ResourcePreviewActions
          :group="group"
          :resource="resource"
          compact
        />
      </header>
      <ResourcePreviewActions
        v-else
        :group="group"
        :resource="resource"
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
import { confirmResourcePreviewLeave } from '@/services/resourcePreviewLeaveGuard.js'

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
const documentGroups = computed(() => {
  const documents = groups.value.filter(item => targetTab(item) === 'document')
  if (explicitAttachment.value) {
    const attachmentGroup = allGroups.value.find(item => item.group_id === explicitAttachment.value.group_id)
    if (attachmentGroup && targetTab(attachmentGroup) === 'document'
      && !documents.some(item => item.group_id === attachmentGroup.group_id)) {
      return [attachmentGroup, ...documents]
    }
  }
  return documents
})
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
const isLatestVersion = computed(() => (
  Number(group.value?.primary?.version || resource.value?.version || 0)
  === Math.max(...(group.value?.versions || [Number(resource.value?.version || 0)]))
))

const selectDocument = async event => {
  const groupId = event?.target?.value || ''
  const sessionId = resourceStore.activeSessionId
  const nextGroup = documentGroups.value.find(item => item.group_id === groupId)
  const nextResource = preferredPreview(nextGroup)
  if (!sessionId || !nextGroup || !nextResource) return
  if (!await confirmResourcePreviewLeave()) {
    if (event?.target) event.target.value = group.value?.group_id || ''
    return
  }
  resourceStore.selectGroup(sessionId, nextGroup.group_id)
  resourceStore.selectResource(sessionId, nextResource.resource_id, 'document-picker')
}

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
.document-toolbar { position: relative; z-index: 10; display: flex; min-height: 52px; flex: 0 0 auto; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid #e5eaf0; box-sizing: border-box; background: #fff; }.document-picker { min-width: 0; flex: 1; }.document-picker select { width: 100%; min-height: 34px; padding: 5px 30px 5px 9px; overflow: hidden; border: 1px solid #d5dde8; border-radius: 6px; background: #fff; color: #17223b; font: inherit; text-overflow: ellipsis; }.document-meta { display: flex; align-items: center; gap: 5px; color: #64748b; font-size: 11px; white-space: nowrap; }.document-meta span { padding: 3px 6px; border-radius: 999px; background: #f1f5f9; }.document-meta .latest { background: #eaf7ee; color: #15803d; }.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 900px) { .document-meta { display: none; } }
</style>
