<template>
  <div class="management-panel social-platform-panel">
    <div class="panel-header">
      <h3>社交平台管理</h3>
    </div>
    <div class="panel-embedded-content">
      <SocialAccountsView />
    </div>
  </div>
</template>

<script setup>
import SocialAccountsView from '@/views/SocialAccountsView.vue'

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
  border-bottom: 1px solid var(--border-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-primary);
  background: white;
  color: var(--color-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover {
  background: var(--color-primary);
  color: white;
}

.panel-embedded-content {
  height: calc(100% - 60px);
  overflow-y: auto;
}

</style>
