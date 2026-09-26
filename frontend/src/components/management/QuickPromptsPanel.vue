<template>
  <div class="management-panel quick-prompts-panel">
    <QuickPromptsManagementView />
  </div>
</template>

<script setup>
import QuickPromptsManagementView from '@/views/QuickPromptsManagementView.vue'

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
