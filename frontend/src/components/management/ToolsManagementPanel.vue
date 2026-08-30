<template>
  <div class="management-panel tools-management-panel">
    <ToolsManagementView />
  </div>
</template>

<script setup>
import ToolsManagementView from '@/views/ToolsManagementView.vue'

defineEmits(['close'])
</script>

<style scoped>
.management-panel {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  background: white;
}
</style>
