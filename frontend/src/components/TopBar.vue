<template>
  <div class="topbar">
    <div class="left">
      <!-- 标题已移除 -->
    </div>

    <div class="right">
      <!-- 状态指示 -->
      <div v-if="status === 'running'" class="status-indicator">
        <span class="spinner"></span>
        <span>分析中...</span>
      </div>

      <!-- 调试开关 -->
      <button
        class="debug-toggle"
        :class="{ active: debugEnabled }"
        @click="$emit('toggle-debug')"
        :title="debugEnabled ? '关闭调试模式' : '开启调试模式'"
      >
        调试 {{ debugEnabled ? '开启' : '关闭' }}
      </button>

      <!-- 成果报告 -->
      <button
        v-if="hasReport"
        class="report-btn"
        @click="$emit('open-report')"
        title="查看完整分析报告"
      >
        成果报告
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  status: {
    type: String,
    default: 'idle'
  },
  debugEnabled: {
    type: Boolean,
    default: false
  },
  hasReport: {
    type: Boolean,
    default: false
  }
})

defineEmits(['toggle-debug', 'open-report'])
</script>

<style lang="scss" scoped>
.topbar {
  height: 60px;
  background: white;
  border-bottom: 1px solid var(--border-1);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  flex-shrink: 0;
}

.left h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-2);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-2);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.debug-toggle,
.report-btn {
  padding: 8px 16px;
  border: 1px solid var(--border-2);
  background: white;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.debug-toggle:hover,
.report-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.debug-toggle.active {
  background: #FFF3E0;
  border-color: var(--color-warning);
  color: #F57C00;
}
</style>
