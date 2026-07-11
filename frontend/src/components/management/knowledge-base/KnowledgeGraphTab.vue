<template>
  <div ref="workbench" class="knowledge-graph-tab">
    <KnowledgeGraphStatus :status="store.graphStatus" :candidate-count="candidateCount" :confirmed-count="confirmedCount" @retry="retryFailed" @reindex="reindex" />
    <KnowledgeGraphToolbar
      :entity-types="entityTypes" :relation-types="relationTypes"
      :selected-entity-types="[...selectedEntityTypes]" :selected-relation-types="[...selectedRelationTypes]"
      :show-labels="showRelationLabels" :include-history="includeHistory"
      :loaded-entities="store.graphProgress.loadedEntities" :loaded-relations="store.graphProgress.loadedRelations"
      :entity-total="store.graphProgress.entityTotal" :relation-total="store.graphProgress.relationTotal"
      :loading="store.graphLoading" :layouting="layouting"
      @search="search" @entity-filter="toggleEntityType" @relation-filter="toggleRelationType"
      @labels="showRelationLabels=$event" @history="changeHistory" @fit="canvas?.fitView()"
      @layout="canvas?.relayout()" @fullscreen="fullscreen" @refresh="reload"
    />
    <p v-if="loadError" class="error">{{ loadError }} <button @click="reload">重试</button></p>
    <p v-if="mergeSource" class="merge-notice">请选择要合并到的目标实体：{{ mergeSource.name }} <button @click="mergeSource=null">取消</button></p>
    <div class="graph-workbench">
      <KnowledgeGraphCanvas ref="canvas" :nodes="visibleGraph.nodes" :edges="visibleGraph.edges" :show-relation-labels="showRelationLabels"
        @node-click="selectEntity" @relation-click="selectRelation" @canvas-click="selected=null"
        @layout-start="layouting=true" @layout-end="layouting=false" />
      <KnowledgeGraphDetailPanel v-if="selected" :kb-id="kbId" :selected="selected" @close="selected=null"
        @confirm="setReview($event, 'confirmed')" @reject="setReview($event, 'rejected')" @save="saveFact"
        @begin-merge="mergeSource=$event" @delete="deleteFact" @open-document-chunk="$emit('open-document-chunk', $event)" />
    </div>
    <KnowledgeGraphReview :entities="store.graphEntities" @update="updateReview" @merge="mergeEntities" />
    <CognitiveMapGraphChat :knowledge-base-id="kbId" :entities="store.graphEntities" :relations="store.graphRelations" @graph-updated="reload" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as api from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { filterGraphData, findEntityMatches, toG6Data } from './knowledgeGraphData.js'
import CognitiveMapGraphChat from '../CognitiveMapGraphChat.vue'
import KnowledgeGraphCanvas from './KnowledgeGraphCanvas.vue'
import KnowledgeGraphDetailPanel from './KnowledgeGraphDetailPanel.vue'
import KnowledgeGraphReview from './KnowledgeGraphReview.vue'
import KnowledgeGraphStatus from './KnowledgeGraphStatus.vue'
import KnowledgeGraphToolbar from './KnowledgeGraphToolbar.vue'

const props = defineProps({ kbId: { type: String, required: true } })
defineEmits(['open-document-chunk'])
const store = useKnowledgeBaseStore(); const canvas = ref(null); const workbench = ref(null)
const includeHistory = ref(false); const showRelationLabels = ref(true); const selectedEntityTypes = ref(new Set()); const selectedRelationTypes = ref(new Set())
const selected = ref(null); const mergeSource = ref(null); const layouting = ref(false); const loadError = ref('')
let buildPoller = null; let lastBuildStatus = null
const candidateCount = computed(() => store.graphEntities.filter(item => item.review_status === 'candidate').length)
const confirmedCount = computed(() => store.graphEntities.filter(item => ['confirmed', 'published'].includes(item.review_status)).length)
const fullGraph = computed(() => toG6Data(store.graphEntities, store.graphRelations))
const visibleGraph = computed(() => filterGraphData(fullGraph.value, { entityTypes: selectedEntityTypes.value, relationTypes: selectedRelationTypes.value }))
const entityTypes = computed(() => [...new Set(store.graphEntities.map(item => item.entity_type))].sort())
const relationTypes = computed(() => [...new Set(store.graphRelations.map(item => item.relation_type))].sort())

async function reload() { loadError.value = ''; try { await store.loadGraph(props.kbId, { includeHistory: includeHistory.value }) } catch (error) { loadError.value = error.message || '图谱加载失败' } }
function toggleSet(target, { type, checked }) { const next = new Set(target.value); checked ? next.add(type) : next.delete(type); target.value = next }
const toggleEntityType = event => toggleSet(selectedEntityTypes, event); const toggleRelationType = event => toggleSet(selectedRelationTypes, event)
const changeHistory = value => { includeHistory.value = value; reload() }
function search(query) { const id = findEntityMatches(fullGraph.value, query)[0]; if (id) canvas.value?.focusNode(id) }
function rawEntity(id) { return store.graphEntities.find(item => String(item.id) === String(id)) }
function rawRelation(id) { return store.graphRelations.find(item => String(item.id) === String(id)) }
async function selectEntity(id) {
  const entity = rawEntity(id); if (!entity) return
  if (mergeSource.value) { if (entity.id !== mergeSource.value.id && window.confirm(`确认将 ${mergeSource.value.name} 合并到 ${entity.name}？`)) await mergeEntities(mergeSource.value, entity); mergeSource.value = null; return }
  selected.value = { kind: 'entity', raw: entity }
}
function selectRelation(id) { const relation = rawRelation(id); if (relation) selected.value = { kind: 'relation', raw: relation } }
async function setReview(item, review_status) { await (item.kind === 'entity' ? api.updateKnowledgeGraphEntity(props.kbId, item.raw.id, { review_status }) : api.updateKnowledgeGraphRelation(props.kbId, item.raw.id, { review_status })); await reload(); selected.value = null }
async function saveFact({ selected: item, payload }) { await (item.kind === 'entity' ? api.updateKnowledgeGraphEntity(props.kbId, item.raw.id, payload) : api.updateKnowledgeGraphRelation(props.kbId, item.raw.id, payload)); await reload(); selected.value = null }
async function deleteFact(item) { await (item.kind === 'entity' ? api.deleteKnowledgeGraphEntity(props.kbId, item.raw.id) : api.deleteKnowledgeGraphRelation(props.kbId, item.raw.id)); await reload(); selected.value = null }
const updateReview = (entity, status) => setReview({ kind: 'entity', raw: entity }, status)
async function mergeEntities(source, target) { await api.mergeKnowledgeGraphEntities(props.kbId, source.id, target.id); await reload(); selected.value = null }
const retryFailed = async () => { await api.retryFailedKnowledgeGraph(props.kbId); await reload() }; const reindex = async () => { await api.reindexKnowledgeGraph(props.kbId); await reload() }
const fullscreen = () => workbench.value?.requestFullscreen?.()
async function pollBuild() {
  try { const task = await api.getKnowledgeGraphBuild(props.kbId); const status = task?.status; if (lastBuildStatus && ['queued', 'running'].includes(lastBuildStatus) && status && !['queued', 'running'].includes(status)) await reload(); lastBuildStatus = status } catch {}
}
onMounted(() => { reload(); buildPoller = setInterval(pollBuild, 2500) })
onUnmounted(() => clearInterval(buildPoller))
watch(() => props.kbId, () => { selected.value = null; mergeSource.value = null; selectedEntityTypes.value = new Set(); selectedRelationTypes.value = new Set(); lastBuildStatus = null; reload() })
</script>

<style scoped>
.knowledge-graph-tab { display: grid; gap: 12px; }.graph-workbench { display: flex; gap: 12px; align-items: stretch; }.graph-workbench > :first-child { flex: 1; min-width: 0; }.error { color: #b42318; }.merge-notice { padding: 8px; background: #fff6df; border-radius: 6px; }
.knowledge-graph-tab:fullscreen { background: #f7f9fc; padding: 14px; overflow: auto; }
@media (max-width: 900px) { .graph-workbench { display: grid; } }
</style>
