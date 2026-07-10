<template>
  <div class="knowledge-graph-tab">
    <KnowledgeGraphStatus
      :status="store.graphStatus"
      :candidate-count="candidateCount"
      :confirmed-count="confirmedCount"
      @retry="retryFailed"
      @reindex="reindex"
    />
    <div class="graph-summary">
      <h4>知识库关系视图</h4>
      <p v-if="!store.graphEntities.length">当前知识库暂无图谱事实，上传或替换文档后会自动增量完善。</p>
      <ul v-else>
        <li v-for="link in graphLinks.slice(0, 30)" :key="link.id || `${link.source}-${link.target}`">
          {{ entityName(link.source) }} — {{ link.value }} → {{ entityName(link.target) }}
        </li>
      </ul>
    </div>
    <KnowledgeGraphReview
      :entities="store.graphEntities"
      @update="updateReview"
      @merge="mergeEntities"
    />
    <CognitiveMapGraphChat
      :knowledge-base-id="kbId"
      :entities="store.graphEntities"
      :relations="store.graphRelations"
      @graph-updated="reload"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import * as api from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { buildGraphLinks } from '../cognitiveMapGraphLinks'
import KnowledgeGraphReview from './KnowledgeGraphReview.vue'
import KnowledgeGraphStatus from './KnowledgeGraphStatus.vue'
import CognitiveMapGraphChat from '../CognitiveMapGraphChat.vue'

const props = defineProps({ kbId: { type: String, required: true } })
const store = useKnowledgeBaseStore()
const candidateCount = computed(() => store.graphEntities.filter(item => item.review_status === 'candidate').length)
const confirmedCount = computed(() => store.graphEntities.filter(item => ['confirmed', 'published'].includes(item.review_status)).length)
const graphLinks = computed(() => buildGraphLinks({
  relations: store.graphRelations,
  nodeIds: new Set(store.graphEntities.map(item => item.id)),
  relationColorByType: new Map(),
  isRelationTypeHidden: () => false,
  formatRelationType: value => value,
  showRelationLabels: true
}))
const entityName = id => store.graphEntities.find(item => item.id === id)?.name || id
const reload = () => store.loadGraph(props.kbId)
const updateReview = async (entity, reviewStatus) => {
  await api.updateKnowledgeGraphEntity(props.kbId, entity.id, { review_status: reviewStatus })
  await reload()
}
const mergeEntities = async (source, target) => {
  await api.mergeKnowledgeGraphEntities(props.kbId, source.id, target.id)
  await reload()
}
const retryFailed = async () => { await api.retryFailedKnowledgeGraph(props.kbId); await reload() }
const reindex = async () => { await api.reindexKnowledgeGraph(props.kbId); await reload() }
onMounted(reload)
watch(() => props.kbId, reload)
</script>

<style scoped>
.knowledge-graph-tab { display: grid; gap: 14px; }
.graph-summary { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; max-height: 260px; overflow: auto; }
.graph-summary h4 { margin: 0 0 8px; }
</style>
