<template>
  <div class="progress-indicator" v-if="isAnalyzing && currentStep">
    <div class="progress-header">
      <span class="step-name">{{ stepLabel }}</span>
      <span class="progress-percent">{{ progress }}%</span>
    </div>
    <div class="progress-bar">
      <div
        class="progress-fill"
        :style="{ width: progress + '%' }"
        :class="{ 'is-complete': progress >= 100 }"
      ></div>
    </div>
    <div class="progress-message">{{ stepMessage }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  currentStep: {
    type: String,
    default: null
  },
  stepMessage: {
    type: String,
    default: ''
  },
  progress: {
    type: Number,
    default: 0
  }
})

const stepLabels = {
  'extract_params': '提取参数',
  'weather': '分析气象',
  'regional': '区域对比',
  'component': '成分分析',
  'comprehensive': '综合分析',
  'kpi': '生成报告'
}

const stepLabel = computed(() => {
  return stepLabels[props.currentStep] || props.currentStep || '分析中...'
})
</script>

<style lang="scss" scoped>
.progress-indicator {
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

.step-name {
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

.progress-message {
  font-size: 13px;
  color: #6c757d;
  line-height: 1.4;
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
