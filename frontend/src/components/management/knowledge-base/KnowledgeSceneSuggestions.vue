<template>
  <section v-if="suggestions.length || loading" class="scene-suggestions">
    <header><strong>场景模型改进建议</strong><span>接受后生成待确认草稿，不会直接修改当前 Schema</span></header>
    <p v-if="loading">加载建议中...</p>
    <article v-for="item in suggestions" :key="item.id">
      <div>
        <strong>{{ item.suggestion_type === 'business_logic' ? '业务逻辑' : '业务对象' }}：{{ title(item) }}</strong>
        <p>{{ item.payload.statement || item.payload.description || '抽取中发现了当前场景模型未覆盖的内容。' }}</p>
        <small v-if="item.evidence?.length">证据：{{ evidenceLabel(item.evidence) }}</small>
      </div>
      <div class="actions">
        <button :disabled="busyId === item.id" @click="accept(item)">接受并创建草稿</button>
        <button :disabled="busyId === item.id" class="secondary" @click="reject(item)">忽略</button>
      </div>
    </article>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { acceptKnowledgeSceneSuggestion, listKnowledgeSceneSuggestions, rejectKnowledgeSceneSuggestion } from '@/api/knowledgeBase'

const props = defineProps({ kbId: { type: String, required: true } })
const emit = defineEmits(['accepted', 'changed'])
const suggestions = ref([])
const loading = ref(false)
const busyId = ref('')
const error = ref('')
const title = item => item.payload.name || item.payload.statement || item.payload.key || '未命名建议'
const evidenceLabel = evidence => evidence.map(item => item.filename || item.document_id || item.chunk_id).filter(Boolean).join('、')

async function load() {
  loading.value = true; error.value = ''
  try { suggestions.value = (await listKnowledgeSceneSuggestions(props.kbId)).suggestions || [] }
  catch (reason) { error.value = reason.message || '建议加载失败' }
  finally { loading.value = false }
}
async function accept(item) {
  busyId.value = item.id; error.value = ''
  try { const profile = await acceptKnowledgeSceneSuggestion(props.kbId, item.id); emit('accepted', profile) }
  catch (reason) { error.value = reason.message || '接受建议失败' }
  finally { busyId.value = ''; await load() }
}
async function reject(item) {
  busyId.value = item.id; error.value = ''
  try { await rejectKnowledgeSceneSuggestion(props.kbId, item.id); emit('changed') }
  catch (reason) { error.value = reason.message || '忽略建议失败' }
  finally { busyId.value = ''; await load() }
}
onMounted(load)
watch(() => props.kbId, load)
</script>

<style scoped>
.scene-suggestions { display: grid; gap: 8px; padding: 12px; border: 1px solid #f0c36d; border-radius: 8px; background: #fffaf0; }.scene-suggestions header { display: flex; justify-content: space-between; gap: 12px; }.scene-suggestions header span, small { color: #667085; }.scene-suggestions article { display: flex; justify-content: space-between; gap: 16px; padding-top: 8px; border-top: 1px solid #f3dfb8; }.scene-suggestions p { margin: 4px 0; }.actions { display: flex; gap: 6px; align-items: center; }.actions button { white-space: nowrap; }.secondary { background: white; }.error { color: #b42318; }
</style>
