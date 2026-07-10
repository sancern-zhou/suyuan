<template>
  <section class="graph-chat-panel">
    <div class="graph-chat-body">
      <ReActMessageList
        v-if="graphMessages.length"
        class="graph-chat-message-list"
        :messages="graphMessages"
        :show-reflexion="false"
        :reflexion-count="0"
        :use-markdown="true"
        assistant-mode="graph"
        :selected-message-id="null"
        :visualization-panel-ref="null"
        :has-more-messages="false"
        :total-message-count="graphMessages.length"
        :loading-more="false"
        :hide-welcome="true"
      />
      <div v-else class="graph-chat-empty">
        <h3>用对话修正当前图谱</h3>
        <p>选择图中实体或关系后，可以直接描述要合并、修正、删除或补充的内容。</p>
        <div class="graph-chat-examples">
          <button type="button" @click="fillExample('把零漂和零点漂移合并，保留零点漂移这个名称')">合并重复实体</button>
          <button type="button" @click="fillExample('删除这条错误关系，并说明原因')">删除错误关系</button>
          <button type="button" @click="fillExample('为当前实体补充与运维检查项的关系')">补充关联关系</button>
        </div>
      </div>
    </div>

    <form class="graph-chat-composer" @submit.prevent="sendGraphMessage">
      <div class="graph-chat-context">
        <span>{{ selectedContextText }}</span>
        <strong>{{ entities.length }} 实体 / {{ relations.length }} 关系</strong>
      </div>
      <div class="graph-chat-input-shell">
        <textarea
          v-model="draft"
          :disabled="isGraphAnalyzing"
          rows="2"
          placeholder="描述要对当前图谱执行的修改，例如合并实体、修正关系、删除错误节点"
          @keydown.enter.exact.prevent="sendGraphMessage"
        ></textarea>
        <div class="graph-chat-input-footer">
          <span>{{ knowledgeBaseId ? '将携带当前知识库和选中对象上下文' : '请先选择知识库' }}</span>
          <button class="graph-chat-send" type="submit" :disabled="!canSend">
            {{ isGraphAnalyzing ? '处理中' : '发送' }}
          </button>
        </div>
      </div>
    </form>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import { useReactStore } from '@/stores/reactStore'

const props = defineProps({
  knowledgeBaseId: { type: String, default: '' },
  selectedGraphItem: { type: Object, default: null },
  entities: { type: Array, default: () => [] },
  relations: { type: Array, default: () => [] }
})

const emit = defineEmits(['graph-updated'])

const store = useReactStore()
const draft = ref('')

const graphState = computed(() => {
  const sessionId = store.activeSessionByMode.graph
  return (sessionId && store.sessionStates[sessionId]) || store.modeStates.graph
})

const graphMessages = computed(() => {
  return (graphState.value?.messages || []).filter(message => (
    message.type === 'user' || message.type === 'agent' || message.type === 'final'
  ))
})

const isGraphAnalyzing = computed(() => !!store.modeStates.graph?.isAnalyzing)

const canSend = computed(() => (
  !!props.knowledgeBaseId &&
  draft.value.trim().length > 0 &&
  !isGraphAnalyzing.value
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
  knowledge_base_id: props.knowledgeBaseId || null,
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

const selectedContextText = computed(() => {
  const item = selectedItemPayload()
  if (!item) return '未选中图谱对象'
  return item.kind === 'relation' ? `当前关系：${item.name}` : `当前实体：${item.name || item.id}`
})

const fillExample = (text) => {
  if (isGraphAnalyzing.value) return
  draft.value = text
}

const sendGraphMessage = async () => {
  if (!canSend.value) return
  const query = draft.value.trim()
  draft.value = ''
  await store.analyze(query, {
    agentMode: 'graph',
    mapContext: buildGraphMapContext(),
    skipAutoFollowup: true,
    preserveCurrentMode: true
  })
  emit('graph-updated')
}
</script>

<style scoped>
.graph-chat-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.graph-chat-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.graph-chat-message-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.graph-chat-message-list :deep(.welcome-message) {
  display: none;
}

.graph-chat-message-list :deep(.message-wrapper) {
  max-width: 100%;
}

.graph-chat-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 28px;
  text-align: center;
  color: #64748b;
}

.graph-chat-empty h3 {
  margin: 0;
  color: #24324a;
  font-size: 18px;
}

.graph-chat-empty p {
  max-width: 360px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.graph-chat-examples {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.graph-chat-examples button {
  padding: 6px 10px;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  background: #fff;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
}

.graph-chat-examples button:hover {
  border-color: #93c5fd;
  color: #1d4ed8;
}

.graph-chat-composer {
  position: sticky;
  bottom: 0;
  z-index: 2;
  flex: 0 0 auto;
  padding: 12px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
  box-shadow: 0 -8px 18px rgba(15, 23, 42, 0.06);
}

.graph-chat-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
}

.graph-chat-context span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-chat-context strong {
  flex: 0 0 auto;
  color: #475569;
  font-weight: 600;
}

.graph-chat-input-shell {
  border: 1px solid #d9e2ef;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.graph-chat-input-shell:focus-within {
  border-color: #93c5fd;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.graph-chat-input-shell textarea {
  width: 100%;
  min-height: 54px;
  max-height: 140px;
  resize: none;
  border: 0;
  padding: 11px 12px 6px;
  color: #111827;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  outline: none;
}

.graph-chat-input-shell textarea:disabled {
  background: #f8fafc;
  color: #94a3b8;
  cursor: not-allowed;
}

.graph-chat-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 8px 8px 12px;
  color: #94a3b8;
  font-size: 12px;
}

.graph-chat-send {
  flex: 0 0 auto;
  min-width: 64px;
  min-height: 30px;
  border: 1px solid #2563eb;
  border-radius: 6px;
  background: #2563eb;
  color: white;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.graph-chat-send:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
