<template>
  <div class="dashboard-card" @click="$emit('click')">
    <div class="card-header">
      <div class="header-decoration left"></div>
      <span v-if="icon" class="card-icon">{{ icon }}</span>
      <h4 class="card-title">{{ title }}</h4>
      <div class="header-decoration right"></div>
    </div>
    <div class="card-body">
      <slot></slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    default: ''
  },
  icon: {
    type: String,
    default: ''
  }
})

defineEmits(['click'])
</script>

<style lang="scss" scoped>
.dashboard-card {
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.card-header {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
  position: relative;
}

.header-decoration {
  display: none;
}

.card-icon {
  font-size: 18px;
}

.card-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
  letter-spacing: 1px;
  flex: 1;
}

.card-body {
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  /* 移除最小高度限制，让内容自适应 */
  /* min-height: 0; - 已存在，允许内容收缩 */
}
</style>
