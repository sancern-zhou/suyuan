<template>
  <aside v-if="selected" class="graph-detail-panel">
    <header><strong>{{ title }}</strong><button @click="$emit('close')">×</button></header>
    <template v-if="!editing">
      <dl><template v-for="(value, key) in summary" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl>
      <div class="actions">
        <button @click="$emit('confirm', selected)">确认</button>
        <button @click="reject">拒绝</button>
        <button @click="beginEdit">编辑</button>
        <button v-if="selected.kind === 'entity'" @click="$emit('begin-merge', selected.raw)">合并</button>
        <button class="danger" @click="remove">删除</button>
      </div>
    </template>
    <form v-else @submit.prevent="save">
      <label v-if="selected.kind === 'entity'">名称<input v-model="form.name" required /></label>
      <label v-if="selected.kind === 'entity'">规范名称<input v-model="form.canonicalName" /></label>
      <label v-if="selected.kind === 'entity'">别名（逗号分隔）<input v-model="form.aliasesText" /></label>
      <label>类型<input v-model="form.type" required /></label>
      <label>描述<textarea v-model="form.description" /></label>
      <label>属性 JSON<textarea v-model="form.attributesText" /></label>
      <div class="actions"><button type="submit">保存</button><button type="button" @click="editing=false">取消</button></div>
      <p v-if="formError" class="error">{{ formError }}</p>
    </form>
    <section class="evidence">
      <h4>来源证据</h4><p v-if="loading">加载中...</p><p v-else-if="evidenceError" class="error">{{ evidenceError }}</p><p v-else-if="!mentions.length">暂无证据</p>
      <article v-for="mention in mentions" :key="mention.id" :class="{ stale: mention.stale }">
        <strong>{{ mention.filename }} · 分块 {{ mention.chunk_index + 1 }}</strong>
        <p>{{ mention.evidence_text || mention.content }}</p>
        <small>confidence: {{ mention.confidence ?? '-' }} · extractor: {{ mention.extractor_name }}</small>
        <button :disabled="mention.stale" @click="$emit('open-document-chunk', { documentId: mention.document_id, chunkId: mention.chunk_id })">{{ mention.stale ? '证据已失效' : '查看原文' }}</button>
      </article>
    </section>
  </aside>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { getKnowledgeGraphEntityMentions, getKnowledgeGraphRelationMentions } from '@/api/knowledgeBase'

const props = defineProps({ kbId: { type: String, required: true }, selected: { type: Object, default: null } })
const emit = defineEmits(['close', 'confirm', 'reject', 'save', 'begin-merge', 'delete', 'open-document-chunk'])
const mentions = ref([]); const loading = ref(false); const evidenceError = ref(''); const editing = ref(false); const formError = ref('')
const form = reactive({ name: '', canonicalName: '', aliasesText: '', type: '', description: '', attributesText: '{}' })
let controller = null
const title = computed(() => props.selected?.raw?.name || props.selected?.raw?.relation_type || '图谱详情')
const summary = computed(() => {
  const raw = props.selected?.raw || {}
  return props.selected?.kind === 'entity'
    ? { 类型: raw.entity_type, 状态: raw.review_status, 别名: (raw.aliases || []).join('、'), 描述: raw.description || '-', Mention: raw.mention_count || 0 }
    : { 关系: raw.relation_type, 状态: raw.review_status, 描述: raw.description || '-', Mention: raw.mention_count || 0 }
})
function beginEdit() {
  const raw = props.selected.raw
  Object.assign(form, { name: raw.name || '', canonicalName: raw.canonical_name || '', aliasesText: (raw.aliases || []).join(', '), type: raw.entity_type || raw.relation_type || '', description: raw.description || '', attributesText: JSON.stringify(raw.attributes || {}, null, 2) })
  editing.value = true; formError.value = ''
}
function save() {
  try {
    const attributes = JSON.parse(form.attributesText || '{}')
    const payload = props.selected.kind === 'entity'
      ? { name: form.name, canonical_name: form.canonicalName || null, aliases: form.aliasesText.split(',').map(value => value.trim()).filter(Boolean), entity_type: form.type, description: form.description, attributes }
      : { relation_type: form.type, description: form.description, attributes }
    emit('save', { selected: props.selected, payload }); editing.value = false
  } catch { formError.value = '属性必须是合法 JSON' }
}
const reject = () => { if (window.confirm('确认拒绝该事实？')) emit('reject', props.selected) }
const remove = () => { if (window.confirm('确认删除该事实？删除将按归档处理。')) emit('delete', props.selected) }
async function loadEvidence() {
  controller?.abort(); controller = new AbortController(); mentions.value = []; evidenceError.value = ''
  if (!props.selected) return
  loading.value = true
  try {
    const data = props.selected.kind === 'entity'
      ? await getKnowledgeGraphEntityMentions(props.kbId, props.selected.raw.id, { signal: controller.signal })
      : await getKnowledgeGraphRelationMentions(props.kbId, props.selected.raw.id, { signal: controller.signal })
    mentions.value = data.mentions || []
  } catch (error) { if (error?.name !== 'AbortError') evidenceError.value = error.message || '证据加载失败' }
  finally { loading.value = false }
}
watch(() => [props.kbId, props.selected?.kind, props.selected?.raw?.id], loadEvidence, { immediate: true })
onUnmounted(() => controller?.abort())
</script>

<style scoped>
.graph-detail-panel { width: 360px; max-height: 68vh; overflow: auto; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; background: #fff; }
header { display: flex; justify-content: space-between; } dl { display: grid; grid-template-columns: 80px 1fr; gap: 6px; } dt { color: #667085; } dd { margin: 0; }
.actions { display: flex; gap: 7px; flex-wrap: wrap; margin: 12px 0; } button { cursor: pointer; } .danger, .error { color: #b42318; }
form label { display: grid; gap: 4px; margin: 8px 0; } textarea { min-height: 70px; }
.evidence article { border-top: 1px solid #eee; padding: 10px 0; } .evidence article.stale { opacity: .6; } .evidence p { white-space: pre-wrap; }
</style>
