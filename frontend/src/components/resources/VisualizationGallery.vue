<template>
  <section :class="['visualization-gallery', { 'full-bleed-gallery': fullBleedSingleItem }]">
    <p v-if="!orderedItems.length" class="empty">暂无可视化产物</p>
    <div v-else :class="['gallery-grid', { 'full-bleed-grid': fullBleedSingleItem }]">
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
import { computed, ref, watch } from 'vue'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { visualizationGalleryItems } from '@/services/visualizationGallery.js'
import { isFaultWorkOrderReviewVisual } from '@/services/visualizationTypes.js'
import VisualizationCard from './VisualizationCard.vue'

const resourceStore = useSessionResourceStore()
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
const fullBleedSingleItem = computed(() => (
  orderedItems.value.length === 1 && isFaultWorkOrderReviewVisual(orderedItems.value[0]?.resource)
))

watch(
  () => [resourceStore.activeSessionId, items.value.map(item => item.group.group_id).join('|')],
  ([sessionId]) => {
    const ids = items.value.map(item => item.group.group_id)
    if (initializedSessionId.value !== sessionId) {
      initializedSessionId.value = sessionId || ''
      seenGroups = new Set(ids)
      groupOrder = new Map(ids.map((id, index) => [id, index]))
      nextGroupOrder = ids.length
      return
    }
    const added = ids.filter(id => !seenGroups.has(id))
    added.forEach(id => {
      seenGroups.add(id)
      groupOrder.set(id, nextGroupOrder)
      nextGroupOrder += 1
    })
  },
  { immediate: true }
)
</script>

<style scoped>
.visualization-gallery { height: 100%; min-height: 0; padding: 12px; overflow-x: hidden; overflow-y: auto; box-sizing: border-box; background: #f7f9fc; overflow-anchor: none; }
.visualization-gallery.full-bleed-gallery { padding: 0; overflow: hidden; background: transparent; }
.gallery-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }.empty { display: grid; min-height: 240px; margin: 0; place-content: center; color: #64748b; }
.gallery-grid.full-bleed-grid { height: 100%; min-height: 0; gap: 0; }
</style>
