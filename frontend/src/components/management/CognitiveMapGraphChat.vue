<template>
  <section class="graph-chat-panel">
    <div class="graph-chat-header">
      <strong>对话编辑</strong>
      <span>{{ currentMap?.name || '未选择地图' }}</span>
    </div>

    <div class="graph-chat-messages">
      <div
        v-for="message in graphMessages"
        :key="message.id"
        class="graph-chat-message"
        :class="`message-${message.type}`"
      >
        <span class="message-role">{{ roleLabel(message.type) }}</span>
        <p>{{ message.content }}</p>
      </div>
      <div v-if="graphMessages.length === 0" class="graph-chat-empty">
        选择图中实体或关系后，可直接描述要合并、修正或删除的内容。
      </div>
    </div>

    <form class="graph-chat-input" @submit.prevent="sendGraphMessage">
      <textarea
        v-model="draft"
        :disabled="store.modeStates.graph?.isAnalyzing"
        rows="3"
        placeholder="例如：把零漂和零点漂移合并，保留零点漂移这个名称"
      ></textarea>
      <button type="submit" :disabled="!canSend">
        {{ store.modeStates.graph?.isAnalyzing ? '处理中' : '发送' }}
      </button>
    </form>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useReactStore } from '@/stores/reactStore'

const props = defineProps({
  currentMap: { type: Object, default: null },
  selectedGraphItem: { type: Object, default: null },
  entities: { type: Array, default: () => [] },
  relations: { type: Array, default: () => [] }
})

const emit = defineEmits(['graph-updated'])

const store = useReactStore()
const draft = ref('')

const graphMessages = computed(() => {
  const state = store.modeStates.graph
  return (state?.messages || []).filter(message => (
    message.type === 'user' || message.type === 'agent' || message.type === 'final'
  ))
})

const canSend = computed(() => (
  !!props.currentMap?.id &&
  draft.value.trim().length > 0 &&
  !store.modeStates.graph?.isAnalyzing
))

const selectedItemPayload = () => {
  const item = props.selectedGraphItem
  if (!item?.kind || !item?.raw) return null
  const raw = item.raw
  return {
    kind: item.kind,
    id: item.kind === 'relation'
      ? raw.relation_id || raw.id
      : raw.entity_id || raw.id,
    name: item.kind === 'relation'
      ? `${raw.source_name || raw.source_entity_id || ''} -> ${raw.relation_type || raw.type || ''} -> ${raw.target_name || raw.target_entity_id || ''}`.trim()
      : raw.name || raw.canonical_name || ''
  }
}

const buildGraphMapContext = () => ({
  active_map_id: props.currentMap?.id || null,
  active_map_name: props.currentMap?.name || '',
  selected_item: selectedItemPayload(),
  visible_entity_ids: props.entities
    .map(entity => entity.entity_id || entity.id)
    .filter(Boolean)
    .slice(0, 200),
  visible_relation_ids: props.relations
    .map(relation => relation.relation_id || relation.id)
    .filter(Boolean)
    .slice(0, 200),
  entity_count: props.entities.length,
  relation_count: props.relations.length
})

const roleLabel = (type) => {
  if (type === 'user') return '用户'
  if (type === 'final' || type === 'agent') return 'Graph'
  return type
}

const sendGraphMessage = async () => {
  if (!canSend.value) return
  const query = draft.value.trim()
  draft.value = ''
  await store.analyze(query, {
    agentMode: 'graph',
    mapContext: buildGraphMapContext(),
    skipAutoFollowup: true
  })
  emit('graph-updated')
}
</script>

<style scoped>
.graph-chat-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 320px;
}

.graph-chat-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.graph-chat-header span {
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-chat-messages {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 160px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px;
  background: #f8fafc;
}

.graph-chat-message {
  display: grid;
  gap: 4px;
  font-size: 13px;
}

.message-role {
  color: #475569;
  font-weight: 600;
}

.graph-chat-message p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
}

.graph-chat-empty {
  color: #64748b;
  font-size: 13px;
}

.graph-chat-input {
  display: grid;
  gap: 8px;
}

.graph-chat-input textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px;
  font-size: 13px;
}

.graph-chat-input button {
  justify-self: end;
  border: 1px solid #2563eb;
  border-radius: 6px;
  background: #2563eb;
  color: white;
  padding: 6px 14px;
  cursor: pointer;
}

.graph-chat-input button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
