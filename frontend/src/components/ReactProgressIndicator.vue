<template>
  <div class="react-progress-indicator">
    <div class="progress-header">
      <span class="status-text">{{ statusText }}</span>
      <span class="progress-percent">{{ progress }}%</span>
    </div>
    <div class="progress-bar">
      <div
        class="progress-fill"
        :style="{ width: progress + '%' }"
        :class="{ 'is-complete': isComplete }"
      ></div>
    </div>
    <div class="progress-details">
      <span>迭代 {{ iterations }}/{{ maxIterations }}</span>
      <span v-if="isError" class="error-text">分析出现错误</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  isComplete: {
    type: Boolean,
    default: false
  },
  isError: {
    type: Boolean,
    default: false
  },
  iterations: {
    type: Number,
    default: 0
  },
  maxIterations: {
    type: Number,
    default: 10
  }
})

const progress = computed(() => {
  if (props.isComplete) return 100
  if (props.maxIterations === 0) return 0
  return Math.round((props.iterations / props.maxIterations) * 100)
})

const statusText = computed(() => {
  if (props.isError) return '分析错误'
  if (props.isComplete) return '分析完成'
  if (props.isAnalyzing) return 'ReAct分析中'
  return '等待中...'
})
</script>

<style lang="scss" scoped>
.react-progress-indicator {
  padding: 16px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  animation: slideDown 0.3s;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.status-text {
  font-size: 14px;
  font-weight: 600;
  color: #495057;
}

.progress-percent {
  font-size: 13px;
  color: #6c757d;
  font-weight: 500;
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: #e9ecef;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1976D2, #42A5F5);
  border-radius: 3px;
  transition: width 0.3s ease;

  &.is-complete {
    background: linear-gradient(90deg, #4CAF50, #66BB6A);
  }
}

.progress-details {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #6c757d;
}

.error-text {
  color: #F44336;
  font-weight: 500;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
