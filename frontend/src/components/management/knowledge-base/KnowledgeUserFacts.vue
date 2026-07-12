<template>
  <section class="facts-card">
    <h3>直接录入业务事实</h3>
    <div class="fact-input"><textarea v-model="text" rows="2" placeholder="例如：企业A的主要噪声源是1号空压机" /><button :disabled="!text.trim() || busy" @click="parse">解析事实</button></div>
    <article v-if="draft" class="preview">
      <p><strong>{{ draft.structured_fact.subject.name }}</strong> —{{ draft.structured_fact.relation_type }}→ <strong>{{ draft.structured_fact.object.name }}</strong></p>
      <div v-for="decision in ambiguous" :key="decision.local_id" class="resolution">
        <label>{{ decision.canonical_name }} 存在歧义
          <select v-model="resolutions[decision.local_id]"><option value="">请选择已有实体</option><option v-for="candidate in decision.candidates" :key="candidate.entity_id" :value="candidate.entity_id">{{ candidate.name }}（{{ candidate.entity_type }}）</option></select>
        </label>
      </div>
      <button :disabled="ambiguous.some(item => !resolutions[item.local_id])" @click="confirm">确认并加入可信图谱</button>
      <button class="plain" @click="draft=null">取消</button>
    </article>
    <ul><li v-for="fact in facts" :key="fact.id"><span>{{ fact.raw_text }}</span><small>用户确认事实 · {{ fact.review_status }}</small></li></ul>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import * as api from '@/api/knowledgeBase'
const props = defineProps({ kbId: { type: String, required: true } })
const emit = defineEmits(['changed'])
const text = ref(''); const draft = ref(null); const facts = ref([]); const busy = ref(false); const resolutions = reactive({})
const ambiguous = computed(() => (draft.value?.entity_link_decisions || []).filter(item => item.action === 'ambiguous'))
async function load() { facts.value = (await api.listKnowledgeUserFacts(props.kbId)).facts || [] }
async function parse() { busy.value = true; try { draft.value = await api.parseKnowledgeUserFact(props.kbId, text.value.trim()); Object.keys(resolutions).forEach(key => delete resolutions[key]) } finally { busy.value = false } }
async function confirm() { await api.confirmKnowledgeUserFact(props.kbId, draft.value.id, resolutions); draft.value = null; text.value = ''; await load(); emit('changed') }
onMounted(load)
</script>

<style scoped>
.facts-card { padding: 16px; border: 1px solid #dce3ea; border-radius: 8px; background: #fff; display: grid; gap: 10px; }
.fact-input { display: flex; gap: 8px; }.fact-input textarea { flex: 1; padding: 8px; }.preview { padding: 10px; background: #f2fdf5; border-radius: 6px; }
.resolution label { display: grid; gap: 5px; } select { padding: 7px; } ul { list-style: none; padding: 0; display: grid; gap: 6px; } li { display: flex; justify-content: space-between; gap: 12px; } small { color: #027a48; }
button { padding: 7px 12px; border: 0; border-radius: 5px; background: #027a48; color: white; }.plain { background: transparent; color: #475467; }
</style>
