<template>
  <section class="rules-card">
    <h3>业务规则</h3>
    <div class="rule-input"><textarea v-model="text" rows="2" placeholder="用自然语言补充一条业务规则" /><button :disabled="!text.trim() || busy" @click="parse">解析规则</button></div>
    <article v-if="draft" class="preview">
      <strong>系统理解：{{ draft.structured_rule.summary }}</strong>
      <p v-if="draft.structured_rule.conditions?.length">适用条件：{{ draft.structured_rule.conditions.join('；') }}</p>
      <div><button @click="confirm">确认规则</button><button class="plain" @click="draft=null">取消</button></div>
    </article>
    <ul><li v-for="rule in rules" :key="rule.id"><span>{{ rule.structured_rule.summary }}</span><small>v{{ rule.version }} · {{ rule.status }}</small><button class="plain danger" @click="archive(rule)">归档</button></li></ul>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import * as api from '@/api/knowledgeBase'
const props = defineProps({ kbId: { type: String, required: true }, ruleVersion: { type: Number, default: 0 } })
const emit = defineEmits(['changed'])
const text = ref(''); const draft = ref(null); const rules = ref([]); const busy = ref(false)
async function load() { rules.value = (await api.listKnowledgeBusinessRules(props.kbId)).rules || [] }
async function parse() { busy.value = true; try { draft.value = await api.parseKnowledgeBusinessRule(props.kbId, text.value.trim()) } finally { busy.value = false } }
async function confirm() { await api.confirmKnowledgeBusinessRule(props.kbId, draft.value.id, props.ruleVersion + 1); draft.value = null; text.value = ''; await load(); emit('changed') }
async function archive(rule) { if (window.confirm('归档后，该规则不再影响后续抽取。是否继续？')) { await api.archiveKnowledgeBusinessRule(props.kbId, rule.id); await load() } }
onMounted(load)
</script>

<style scoped>
.rules-card { padding: 16px; border: 1px solid #dce3ea; border-radius: 8px; background: #fff; display: grid; gap: 10px; }
.rule-input { display: flex; gap: 8px; }.rule-input textarea { flex: 1; padding: 8px; }.preview { padding: 10px; background: #f0f7ff; border-radius: 6px; }
ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; } li { display: flex; align-items: center; gap: 10px; } li span { flex: 1; } small { color: #667085; }
button { padding: 7px 12px; border: 0; border-radius: 5px; background: #2563eb; color: white; }.plain { background: transparent; color: #475467; }.danger { color: #b42318; }
</style>
