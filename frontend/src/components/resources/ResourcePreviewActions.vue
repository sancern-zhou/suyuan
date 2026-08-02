<template>
  <div
    v-if="primary && (primary.download_url || isQmd)"
    ref="actionsRef"
    :class="['resource-actions', { floating, compact }]"
  >
    <button
      v-if="floating || compact"
      type="button"
      class="download-trigger"
      aria-haspopup="menu"
      :aria-expanded="menuOpen"
      @click="menuOpen = !menuOpen"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" />
      </svg>
      <span>下载</span>
      <svg class="chevron" viewBox="0 0 16 16" aria-hidden="true">
        <path d="m4 6 4 4 4-4" />
      </svg>
    </button>

    <div
      v-if="(!floating && !compact) || menuOpen"
      :class="floating || compact ? 'download-menu' : 'action-list'"
      :role="floating || compact ? 'menu' : null"
    >
      <button
        v-if="primary.download_url"
        type="button"
        :role="floating || compact ? 'menuitem' : null"
        :disabled="Boolean(busy)"
        @click="download(primary)"
      >
        {{ busy === primary.resource_id ? '下载中...' : originalLabel }}
      </button>
      <template v-if="isQmd">
        <span class="divider" aria-hidden="true"></span>
        <button
          type="button"
          :role="floating || compact ? 'menuitem' : null"
          :disabled="Boolean(busy)"
          @click="exportReport('html')"
        >
          {{ busy === 'html' ? '生成中...' : (floating || compact ? '导出 HTML' : 'HTML') }}
        </button>
        <button
          type="button"
          :role="floating || compact ? 'menuitem' : null"
          :disabled="Boolean(busy)"
          @click="exportReport('docx')"
        >
          {{ busy === 'docx' ? '生成中...' : (floating || compact ? '导出 Word' : 'Word') }}
        </button>
        <button
          v-if="pdfRendition"
          type="button"
          :role="floating || compact ? 'menuitem' : null"
          :disabled="Boolean(busy)"
          @click="download(pdfRendition)"
        >
          {{ busy === pdfRendition.resource_id ? '下载中...' : (floating || compact ? '下载 PDF' : 'PDF') }}
        </button>
      </template>
      <span v-if="error" class="error" role="alert">{{ error }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { invokeResourceAction } from '@/api/sessionResources.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { activeRendition, downloadResource, formatName } from '@/services/resourceDownloads.js'

const props = defineProps({
  group: { type: Object, default: null },
  resource: { type: Object, default: null },
  floating: { type: Boolean, default: false },
  compact: { type: Boolean, default: false }
})
const resourceStore = useSessionResourceStore()
const busy = ref('')
const error = ref('')
const menuOpen = ref(false)
const actionsRef = ref(null)
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

const closeMenu = () => {
  menuOpen.value = false
}

const download = async resource => {
  if (!resource || busy.value) return
  busy.value = resource.resource_id
  error.value = ''
  try {
    await downloadResource(resource)
    closeMenu()
  } catch (cause) {
    error.value = cause?.message || '下载失败'
  } finally {
    busy.value = ''
  }
}

const handleDocumentPointerDown = event => {
  if (menuOpen.value && !actionsRef.value?.contains(event.target)) closeMenu()
}

const handleDocumentKeydown = event => {
  if (event.key === 'Escape') closeMenu()
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})

watch(() => props.resource?.resource_id, closeMenu)

const exportReport = async format => {
  const existing = activeRendition(props.group, format)
  if (existing) return download(existing)
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
.resource-actions { position: relative; min-height: 42px; box-sizing: border-box; border-bottom: 1px solid #e5eaf0; background: #fff; color: #526174; font-size: 12px; }
.action-list { display: flex; min-height: 42px; align-items: center; gap: 8px; padding: 6px 12px; box-sizing: border-box; }
.resource-actions.floating { position: absolute; z-index: 20; top: 64px; right: 12px; min-height: 0; border: 0; background: transparent; }
.resource-actions.compact { min-height: 0; border: 0; background: transparent; }
button, a { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; color: #1b66aa; cursor: pointer; font: inherit; text-decoration: none; }
button:hover:not(:disabled), a:hover { background: #f1f6fb; }
button:disabled { cursor: wait; opacity: .6; }
.download-trigger { min-height: 34px; border-color: #c3d2e2; border-radius: 7px; box-shadow: 0 2px 8px rgba(15, 23, 42, .12); font-weight: 500; }
.download-trigger svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.download-trigger .chevron { width: 12px; height: 12px; }
.download-menu { position: absolute; z-index: 30; top: calc(100% + 6px); right: 0; display: flex; width: max-content; min-width: 168px; flex-direction: column; gap: 4px; padding: 6px; border: 1px solid #d9e2ec; border-radius: 8px; background: #fff; box-shadow: 0 10px 28px rgba(15, 23, 42, .16); }
.download-menu button, .download-menu a { width: 100%; justify-content: flex-start; box-sizing: border-box; border-color: transparent; color: #334155; text-align: left; white-space: nowrap; }
.download-menu button:hover:not(:disabled), .download-menu a:hover { border-color: #d8e9fb; color: #1b66aa; }
.divider { width: 1px; height: 20px; margin: 0 2px; background: #e2e8f0; }
.error { margin-left: auto; color: #b42318; }
.download-menu .divider { width: 100%; height: 1px; margin: 2px 0; }
.download-menu .error { max-width: 220px; margin: 2px 8px; line-height: 1.4; }
</style>
