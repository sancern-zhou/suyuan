<template>
  <section
    class="resource-products"
    data-resource-contract="resources?presentation_type=document"
  >
    <header>
      <div>
        <h3>文件产物</h3>
        <p>对话生成的文档、图表、画板与其他文件</p>
      </div>
      <button type="button" :disabled="sessionState?.loading" @click="reload">刷新</button>
    </header>

    <FileDetailRenderer
      v-if="fileDetailResource"
      :resource="fileDetailResource"
      :group="fileDetailGroup"
      :content-url="fileDetailResource.content_url"
      @close="closeDetails"
    />
    <p v-else-if="sessionState?.loading && !products.length" class="state">正在加载文件产物...</p>
    <div v-else-if="sessionState?.error" class="state error">
      <p>{{ sessionState.error }}</p>
      <button type="button" @click="reload">重试</button>
    </div>
    <p v-else-if="!products.length" class="state">本次对话暂未产生文件</p>

    <div v-else class="product-list">
      <article v-for="group in products" :key="group.group_id" class="product">
        <button type="button" class="product-main" @click="open(group)">
          <span class="format">{{ String(group.primary.format || 'file').slice(0, 4) }}</span>
          <span class="details">
            <strong>{{ group.primary.label }}</strong>
            <small>
              {{ [String(group.primary.format || '').toUpperCase(), sizeLabel(group.primary.size_bytes), `v${group.primary.version}`].filter(Boolean).join(' · ') }}
            </small>
          </span>
        </button>
        <div v-if="group.children.length || group.versions.length > 1" class="derivatives">
          <span v-for="child in group.children" :key="child.resource_id">
            {{ derivativeLabel(child) }}
          </span>
          <span v-if="group.versions.length > 1">共 {{ group.versions.length }} 个版本</span>
        </div>
        <div class="product-actions">
          <button type="button" class="open-label" @click="open(group)">{{ targetTab(group) === 'files' ? '详情' : '打开' }}</button>
          <button
            v-if="group.primary.download_url"
            type="button"
            class="download"
            :disabled="Boolean(downloadingId)"
            @click="download(group.primary)"
          >{{ downloadingId === group.primary.resource_id ? '下载中...' : '下载' }}</button>
        </div>
      </article>
    </div>
    <p v-if="downloadError" class="download-error" role="alert">{{ downloadError }}</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { buildResourceGroups, preferredPreview, targetTab, topLevelProducts } from '@/services/resourceGroups.js'
import { downloadResource } from '@/services/resourceDownloads.js'
import { derivativeLabel } from '@/services/resourceProductLabels.js'
import FileDetailRenderer from '@/components/resources/renderers/FileDetailRenderer.vue'

const emit = defineEmits(['open-resource-tab'])
const resourceStore = useSessionResourceStore()
const downloadingId = ref('')
const downloadError = ref('')
const sessionState = computed(() => resourceStore.activeSessionState)
const products = computed(() => topLevelProducts(buildResourceGroups(sessionState.value?.resources || [])))
const explicitAttachment = computed(() => {
  if (sessionState.value?.selectionOrigin !== 'explicit' || !resourceStore.activeSessionId) return null
  const selected = resourceStore.selectedResource(resourceStore.activeSessionId)
  return selected?.role === 'attachment' ? selected : null
})
const explicitAttachmentGroup = computed(() => buildResourceGroups(sessionState.value?.resources || [])
  .find(group => group.group_id === explicitAttachment.value?.group_id) || null)
const fileDetailAttachment = computed(() => (
  explicitAttachmentGroup.value && targetTab(explicitAttachmentGroup.value) === 'files'
    ? explicitAttachment.value
    : null
))
const selectedProductGroup = computed(() => {
  if (sessionState.value?.selectionOrigin !== 'product' || !resourceStore.activeSessionId) return null
  const selected = resourceStore.selectedResource(resourceStore.activeSessionId)
  const selectedGroup = products.value.find(group => group.group_id === selected?.group_id) || null
  return selectedGroup && targetTab(selectedGroup) === 'files' ? selectedGroup : null
})
const fileDetailGroup = computed(() => explicitAttachmentGroup.value || selectedProductGroup.value)
const fileDetailResource = computed(() => (
  fileDetailAttachment.value
  || (selectedProductGroup.value ? resourceStore.selectedResource(resourceStore.activeSessionId) : null)
))

const reload = () => resourceStore.activeSessionId
  ? resourceStore.loadCatalog(resourceStore.activeSessionId)
  : null

const closeDetails = () => {
  const sessionId = resourceStore.activeSessionId
  if (!sessionId) return
  resourceStore.selectResource(sessionId, null)
  resourceStore.selectGroup(sessionId, null)
}

const open = (group) => {
  const sessionId = resourceStore.activeSessionId
  const resource = preferredPreview(group)
  if (!sessionId || !resource) return
  resourceStore.selectGroup(sessionId, group.group_id)
  resourceStore.selectResource(sessionId, resource.resource_id)
  emit('open-resource-tab', targetTab(group))
}

const download = async resource => {
  if (!resource || downloadingId.value) return
  downloadingId.value = resource.resource_id
  downloadError.value = ''
  try {
    await downloadResource(resource)
  } catch (error) {
    downloadError.value = error?.message || '下载失败'
  } finally {
    downloadingId.value = ''
  }
}

const sizeLabel = (size) => {
  const bytes = Number(size || 0)
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

</script>

<style scoped>
.resource-products { height: 100%; padding: 16px; overflow: auto; box-sizing: border-box; background: #fff; }
header, .product-main { display: flex; align-items: center; }
header { justify-content: space-between; padding-bottom: 14px; border-bottom: 1px solid #edf1f7; }
h3 { margin: 0; font-size: 16px; color: #17223b; } header p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
button { border: 0; background: transparent; color: #1976d2; cursor: pointer; font: inherit; }
.state { margin: 28px 4px; color: #64748b; text-align: center; }.error { color: #b42318; }
.product-list { display: grid; gap: 10px; padding-top: 14px; }.product { display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-rows: auto auto; border: 1px solid #e2e8f0; border-radius: 6px; }
.product-main { grid-column: 1; grid-row: 1; width: 100%; gap: 10px; padding: 10px; color: #17223b; text-align: left; }
.format { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 5px; background: #e8f1fb; color: #1b66aa; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.details { display: grid; min-width: 0; gap: 4px; }.details strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.details small, .derivatives { color: #7a8798; font-size: 11px; }
.derivatives { display: flex; grid-column: 1; grid-row: 2; flex-wrap: wrap; gap: 8px; padding: 0 10px 10px 58px; }
.product-actions { display: flex; grid-column: 2; grid-row: 1 / 3; align-items: center; gap: 2px; padding: 8px; }
.product-actions button { padding: 8px 6px; white-space: nowrap; }
.download-error { margin: 10px 4px 0; color: #b42318; font-size: 12px; }
</style>
