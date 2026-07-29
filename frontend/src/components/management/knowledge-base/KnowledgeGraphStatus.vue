<template>
  <section class="graph-status">
    <div><strong>{{ status?.entity_count || 0 }}</strong><span>实体</span></div>
    <div><strong>{{ status?.relation_count || 0 }}</strong><span>关系</span></div>
    <div><strong>{{ candidateCount }}</strong><span>候选</span></div>
    <div><strong>{{ confirmedCount }}</strong><span>可信</span></div>
    <div><strong>{{ status?.failed_documents || 0 }}</strong><span>失败文档</span></div>
    <div><strong>{{ sceneProfileVersion }}</strong><span>场景版本</span></div>
    <div><strong>{{ schemaVersion }}</strong><span>Schema</span></div>
    <div><strong>{{ ruleVersion }}</strong><span>规则版本</span></div>
    <button type="button" @click="$emit('retry')">重试失败</button>
    <button type="button" @click="$emit('reindex')">重建索引</button>
  </section>
</template>

<script setup>
defineProps({
  status: { type: Object, default: null },
  candidateCount: { type: Number, default: 0 },
  confirmedCount: { type: Number, default: 0 },
  sceneProfileVersion: { type: Number, default: 0 },
  schemaVersion: { type: Number, default: 0 },
  ruleVersion: { type: Number, default: 0 }
})
defineEmits(['retry', 'reindex'])
</script>

<style scoped>
.graph-status { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 10px; background: #f6f8fb; border-radius: 8px; }
.graph-status div { display: grid; text-align: center; min-width: 58px; }
.graph-status span { color: #667085; font-size: 12px; }
.graph-status button { border: 1px solid #1976d2; color: #1976d2; background: white; border-radius: 4px; padding: 5px 9px; cursor: pointer; }
</style>
