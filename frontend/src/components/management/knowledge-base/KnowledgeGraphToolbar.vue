<template>
  <section class="graph-toolbar">
    <input v-model="query" placeholder="搜索实体" @keyup.enter="$emit('search', query)" />
    <button @click="$emit('search', query)">定位</button>
    <details><summary>实体类型</summary><label v-for="type in entityTypes" :key="type"><input type="checkbox" :checked="selectedEntityTypes.includes(type)" @change="toggle('entity-filter', type, $event.target.checked)" />{{ type }}</label></details>
    <details><summary>关系类型</summary><label v-for="type in relationTypes" :key="type"><input type="checkbox" :checked="selectedRelationTypes.includes(type)" @change="toggle('relation-filter', type, $event.target.checked)" />{{ type }}</label></details>
    <label><input type="checkbox" :checked="showLabels" @change="$emit('labels', $event.target.checked)" />关系标签</label>
    <label><input type="checkbox" :checked="includeHistory" @change="$emit('history', $event.target.checked)" />历史数据</label>
    <button @click="$emit('fit')">适应</button><button @click="$emit('layout')">重新布局</button><button @click="$emit('fullscreen')">全屏</button><button @click="$emit('refresh')">刷新</button>
    <span class="counts">实体 {{ loadedEntities }}/{{ entityTotal }} · 关系 {{ loadedRelations }}/{{ relationTotal }} <em v-if="loading">加载中</em><em v-else-if="layouting">布局中</em></span>
  </section>
</template>

<script setup>
import { ref } from 'vue'
defineProps({
  entityTypes: { type: Array, default: () => [] }, relationTypes: { type: Array, default: () => [] },
  selectedEntityTypes: { type: Array, default: () => [] }, selectedRelationTypes: { type: Array, default: () => [] },
  showLabels: { type: Boolean, default: true }, includeHistory: { type: Boolean, default: false },
  loadedEntities: { type: Number, default: 0 }, loadedRelations: { type: Number, default: 0 },
  entityTotal: { type: Number, default: 0 }, relationTotal: { type: Number, default: 0 },
  loading: Boolean, layouting: Boolean
})
const emit = defineEmits(['search', 'entity-filter', 'relation-filter', 'labels', 'fit', 'layout', 'fullscreen', 'history', 'refresh'])
const query = ref('')
const toggle = (event, type, checked) => emit(event, { type, checked })
</script>

<style scoped>
.graph-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.graph-toolbar input[type='text'], .graph-toolbar > input { min-width: 180px; padding: 6px 8px; }
.graph-toolbar button { padding: 6px 9px; cursor: pointer; }
details { position: relative; } details[open] { padding: 5px; border: 1px solid #ddd; } details label { display: block; white-space: nowrap; }
.counts { margin-left: auto; color: #667085; font-size: 12px; } em { margin-left: 6px; color: #1976d2; font-style: normal; }
</style>
