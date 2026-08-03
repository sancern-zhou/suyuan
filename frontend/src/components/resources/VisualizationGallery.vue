<template>
  <section ref="galleryRef" class="visualization-gallery">
    <div class="gallery-heading">
      <div>
        <strong>全部可视化</strong>
        <span>{{ orderedItems.length }} 项 · 按生成顺序排列</span>
      </div>
      <button
        v-if="newCount > 0"
        type="button"
        class="new-visuals"
        aria-live="polite"
        @click="showLatest"
      >新增 {{ newCount }} 项，查看最新</button>
    </div>
    <p v-if="!orderedItems.length" class="empty">暂无可视化产物</p>
    <div v-else class="gallery-grid">
      <VisualizationCard
        v-for="item in orderedItems"
        :key="item.group.group_id"
        :group="item.group"
        :resource="item.resource"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { visualizationGalleryItems } from '@/services/visualizationGallery.js'
import VisualizationCard from './VisualizationCard.vue'

const resourceStore = useSessionResourceStore()
const galleryRef = ref(null)
const newCount = ref(0)
const initializedSessionId = ref('')
let seenGroups = new Set()
let groupOrder = new Map()
let nextGroupOrder = 0

const explicitVisualId = computed(() => {
  const state = resourceStore.activeSessionState
  if (state?.selectionOrigin !== 'explicit' || !resourceStore.activeSessionId) return ''
  return resourceStore.selectedResource(resourceStore.activeSessionId)?.resource_id || ''
})
const items = computed(() => visualizationGalleryItems(
  resourceStore.activeSessionState?.resources || [],
  explicitVisualId.value
))
const orderedItems = computed(() => [...items.value].sort((left, right) => (
  (groupOrder.get(left.group.group_id) ?? Number.MAX_SAFE_INTEGER)
  - (groupOrder.get(right.group.group_id) ?? Number.MAX_SAFE_INTEGER)
)))

watch(
  () => [resourceStore.activeSessionId, items.value.map(item => item.group.group_id).join('|')],
  ([sessionId]) => {
    const ids = items.value.map(item => item.group.group_id)
    if (initializedSessionId.value !== sessionId) {
      initializedSessionId.value = sessionId || ''
      seenGroups = new Set(ids)
      groupOrder = new Map(ids.map((id, index) => [id, index]))
      nextGroupOrder = ids.length
      newCount.value = 0
      return
    }
    const added = ids.filter(id => !seenGroups.has(id))
    added.forEach(id => {
      seenGroups.add(id)
      groupOrder.set(id, nextGroupOrder)
      nextGroupOrder += 1
    })
    if (added.length) newCount.value += added.length
  },
  { immediate: true }
)

const showLatest = async () => {
  newCount.value = 0
  await nextTick()
  galleryRef.value?.scrollTo({ top: galleryRef.value.scrollHeight, behavior: 'smooth' })
}
</script>

<style scoped>
.visualization-gallery { height: 100%; min-height: 0; padding: 12px; overflow-x: hidden; overflow-y: auto; box-sizing: border-box; background: #f7f9fc; overflow-anchor: none; }
.gallery-heading { position: sticky; z-index: 5; top: -12px; display: flex; min-height: 52px; align-items: center; justify-content: space-between; gap: 12px; margin: -12px -12px 12px; padding: 9px 12px; border-bottom: 1px solid #e1e8f0; background: rgba(255, 255, 255, .96); backdrop-filter: blur(6px); }
.gallery-heading > div { display: grid; gap: 2px; }.gallery-heading strong { color: #17223b; font-size: 14px; }.gallery-heading span { color: #7a8798; font-size: 11px; }.new-visuals { padding: 6px 10px; border: 1px solid #cfe2f7; border-radius: 999px; background: #edf6ff; color: #1769aa; cursor: pointer; font: inherit; font-size: 12px; white-space: nowrap; }
.gallery-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }.empty { display: grid; min-height: 240px; margin: 0; place-content: center; color: #64748b; }
</style>
