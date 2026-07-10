<template>
  <section class="graph-review">
    <div class="filters">
      <button v-for="status in ['candidate', 'confirmed', 'rejected']" :key="status" :class="{ active: filter === status }" @click="filter = status">
        {{ status }}
      </button>
    </div>
    <div v-for="entity in visibleEntities" :key="entity.id" class="review-row">
      <span>{{ entity.name }}</span><small>{{ entity.entity_type }}</small>
      <button v-if="entity.review_status !== 'confirmed'" @click="$emit('update', entity, 'confirmed')">确认</button>
      <button v-if="entity.review_status !== 'rejected'" @click="$emit('update', entity, 'rejected')">拒绝</button>
      <button @click="selectMerge(entity)">merge</button>
    </div>
    <p v-if="mergeSource">已选择 {{ mergeSource.name }}，点击另一个实体执行合并。</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ entities: { type: Array, default: () => [] } })
const emit = defineEmits(['update', 'merge'])
const filter = ref('candidate')
const mergeSource = ref(null)
const visibleEntities = computed(() => props.entities.filter(item => item.review_status === filter.value))
const selectMerge = entity => {
  if (!mergeSource.value) mergeSource.value = entity
  else if (mergeSource.value.id !== entity.id) {
    emit('merge', mergeSource.value, entity)
    mergeSource.value = null
  }
}
</script>

<style scoped>
.filters, .review-row { display: flex; gap: 8px; align-items: center; }
.filters { margin: 12px 0; }
.filters .active { background: #1976d2; color: white; }
.review-row { padding: 8px 0; border-bottom: 1px solid #eee; }
.review-row span { flex: 1; }
button { cursor: pointer; }
</style>
