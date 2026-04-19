<template>
  <div class="management-panel skills-management-panel">
    <div class="panel-header">
      <h3>技能管理</h3>
      <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
    </div>
    <div class="panel-embedded-content">
      <SkillsManagementView />
    </div>
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
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover {
  background: #1976d2;
  color: white;
}

.panel-embedded-content {
  height: calc(100% - 60px);
  overflow-y: auto;
}
</style>
