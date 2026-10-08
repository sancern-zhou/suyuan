<template>
  <div class="management-panel skills-management-panel">
    <SkillsManagementView @close="$emit('close')" />
  </div>
</template>

<script setup>
import SkillsManagementView from '@/views/SkillsManagementView.vue'

defineEmits(['close'])
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  background: white;
}
</style>
