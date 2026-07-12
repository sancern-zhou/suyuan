<template>
  <section class="scene-card">
    <h3>建立当前场景的业务认知</h3>
    <p>描述这个知识库要解决的问题，系统将结合代表性文档自动发现业务对象和逻辑。</p>
    <label>
      场景目标
      <textarea v-model="goal" rows="4" placeholder="例如：分析工业企业噪声投诉、监测结果与整改措施之间的关系" />
    </label>
    <label>
      希望回答的问题（每行一个，可选）
      <textarea v-model="questionsText" rows="4" placeholder="某企业有哪些主要噪声源？" />
    </label>
    <p v-if="!hasRepresentativeDocument" class="warning">请先上传并完成处理至少一份代表性文档。</p>
    <button :disabled="!canDiscover || loading" @click="discover">
      {{ loading ? '正在分析…' : '分析代表性文档' }}
    </button>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'

const props = defineProps({ kbId: { type: String, required: true } })
const emit = defineEmits(['discovered'])
const store = useKnowledgeBaseStore()
const goal = ref('')
const questionsText = ref('')
const loading = computed(() => store.sceneLoading)
const hasRepresentativeDocument = computed(() =>
  store.documents.some(item => ['completed', 'partial'].includes(item.ingestion_status || item.status) && Number(item.chunk_count) > 0)
)
const canDiscover = computed(() => hasRepresentativeDocument.value && goal.value.trim().length >= 5)

async function discover() {
  const profile = await store.discoverKnowledgeScene(props.kbId, {
    scene_goal: goal.value.trim(),
    desired_questions: questionsText.value.split('\n').map(item => item.trim()).filter(Boolean)
  })
  emit('discovered', profile)
}
</script>

<style scoped>
.scene-card { padding: 18px; border: 1px solid #dce3ea; border-radius: 8px; background: #fff; display: grid; gap: 14px; }
label { display: grid; gap: 6px; font-weight: 600; }
textarea { padding: 10px; border: 1px solid #cfd8e3; border-radius: 6px; resize: vertical; font: inherit; }
.warning { color: #b54708; }
button { width: fit-content; padding: 9px 16px; border: 0; border-radius: 6px; background: #2563eb; color: white; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
</style>
