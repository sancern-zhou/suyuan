<template>
  <div v-if="primary && (primary.download_url || isQmd)" class="resource-actions">
    <button
      v-if="primary.download_url"
      type="button"
      :disabled="busy"
      @click="download(primary, 'original')"
    >
      {{ busy === 'original' ? '下载中...' : originalLabel }}
    </button>
    <template v-if="isQmd">
      <span class="divider" aria-hidden="true"></span>
      <span class="export-label">导出报告</span>
      <button type="button" :disabled="busy" @click="exportReport('html')">
        {{ busy === 'html' ? '生成中...' : 'HTML' }}
      </button>
      <button type="button" :disabled="busy" @click="exportReport('docx')">
        {{ busy === 'docx' ? '生成中...' : 'Word' }}
      </button>
      <button
        v-if="pdfRendition"
        type="button"
        :disabled="busy"
        @click="download(pdfRendition, 'pdf')"
      >
        {{ busy === 'pdf' ? '下载中...' : 'PDF' }}
      </button>
    </template>
    <span v-if="error" class="error">{{ error }}</span>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { invokeResourceAction } from '@/api/sessionResources.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { activeRendition, downloadResource, formatName } from '@/services/resourceDownloads.js'

const props = defineProps({
  group: { type: Object, default: null },
  resource: { type: Object, default: null }
})
const resourceStore = useSessionResourceStore()
const busy = ref('')
const error = ref('')
const primary = computed(() => props.group?.primary || props.resource || null)
const isQmd = computed(() => (
  primary.value?.format === 'qmd' && Boolean(primary.value?.actions?.render)
))
const originalLabel = computed(() => (
  primary.value?.relation === 'primary'
    ? `下载原始 ${formatName(primary.value)}`
    : `下载 ${formatName(primary.value)}`
))
const pdfRendition = computed(() => activeRendition(props.group, 'pdf'))

const download = async (resource, key) => {
  busy.value = key
  error.value = ''
  try {
    await downloadResource(resource)
  } catch (cause) {
    error.value = cause?.message || '下载失败'
  } finally {
    busy.value = ''
  }
}

const exportReport = async format => {
  const existing = activeRendition(props.group, format)
  if (existing) return download(existing, format)
  const sessionId = resourceStore.activeSessionId
  const actionUrl = primary.value?.actions?.render
  if (!sessionId || !actionUrl) return
  busy.value = format
  error.value = ''
  try {
    const receipt = await invokeResourceAction(actionUrl, { format })
    await resourceStore.refreshIfNewer(sessionId, receipt?.resource_version)
    const refreshed = resourceStore.sessionState(sessionId)?.resources || []
    const rendition = refreshed.find(resource => (
      resource.group_id === primary.value.group_id
      && resource.relation === 'rendition'
      && resource.format === format
      && resource.download_url
    ))
    if (!rendition) throw new Error('导出完成，但未找到下载文件')
    await downloadResource(rendition)
  } catch (cause) {
    error.value = cause?.message || '报告导出失败'
  } finally {
    busy.value = ''
  }
}
</script>

<style scoped>
.resource-actions { display: flex; min-height: 42px; align-items: center; gap: 8px; padding: 6px 12px; box-sizing: border-box; border-bottom: 1px solid #e5eaf0; background: #fff; color: #526174; font-size: 12px; }
button { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; color: #1b66aa; cursor: pointer; }
button:hover:not(:disabled) { background: #f1f6fb; }
button:disabled { cursor: wait; opacity: .6; }
.divider { width: 1px; height: 20px; margin: 0 2px; background: #e2e8f0; }
.export-label { color: #64748b; }
.error { margin-left: auto; color: #b42318; }
</style>
