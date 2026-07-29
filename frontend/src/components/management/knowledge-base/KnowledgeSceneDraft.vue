<template>
  <section class="scene-draft">
    <header>
      <div><h3>确认系统对业务场景的理解</h3><p>{{ profile.scene_goal }}</p></div>
      <button :disabled="loading" @click="confirm">{{ loading ? '保存中…' : '确认并启用图谱构建' }}</button>
    </header>
    <h4>业务对象</h4>
    <div class="object-grid">
      <article v-for="(item, index) in objects" :key="item.key">
        <input v-model="item.name" aria-label="业务对象名称" />
        <textarea v-model="item.description" rows="2" aria-label="业务对象说明" />
        <button class="text-button" @click="objects.splice(index, 1)">删除</button>
      </article>
    </div>
    <h4>业务逻辑</h4>
    <div v-for="(item, index) in logic" :key="item.key" class="logic-row">
      <input v-model="item.statement" aria-label="业务逻辑" />
      <select v-model="item.policy" aria-label="逻辑约束">
        <option value="required">必须满足</option><option value="allowed">允许出现</option><option value="forbidden">禁止抽取</option>
      </select>
      <button class="text-button" @click="logic.splice(index, 1)">删除</button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'

const props = defineProps({ kbId: { type: String, required: true }, profile: { type: Object, required: true } })
const emit = defineEmits(['confirmed'])
const store = useKnowledgeBaseStore()
const objects = ref([]); const logic = ref([])
const loading = computed(() => store.sceneLoading)
watch(() => props.profile, value => {
  objects.value = structuredClone(value.business_objects || [])
  logic.value = structuredClone(value.business_logic || [])
}, { immediate: true })

async function confirm() {
  const result = await store.confirmKnowledgeScene(props.kbId, props.profile.id, {
    business_objects: objects.value,
    business_logic: logic.value,
    ignored_content: props.profile.ignored_content || []
  })
  emit('confirmed', result)
}
</script>

<style scoped>
.scene-draft { padding: 18px; border: 1px solid #dce3ea; border-radius: 8px; background: #fff; display: grid; gap: 12px; }
header { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.object-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
article, .logic-row { border: 1px solid #e4e9ef; border-radius: 6px; padding: 10px; display: grid; gap: 8px; }
.logic-row { grid-template-columns: 1fr 130px auto; }
input, textarea, select { padding: 8px; border: 1px solid #cfd8e3; border-radius: 5px; font: inherit; }
header button { padding: 9px 14px; border: 0; border-radius: 6px; background: #2563eb; color: white; }
.text-button { border: 0; background: none; color: #b42318; width: fit-content; }
</style>
