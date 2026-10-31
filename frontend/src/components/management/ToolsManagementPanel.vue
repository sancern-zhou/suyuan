<template>
  <div class="management-panel tools-management-panel">
    <ToolsManagementView @close="$emit('close')" />
  </div>
</template>

<script setup>
import ToolsManagementView from '@/views/ToolsManagementView.vue'

defineEmits(['close'])
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  background: white;
}
</style>
