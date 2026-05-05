<template>
  <div class="agent-mode-selector">
    <span class="mode-label">Agent模式:</span>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'assistant', running: isModeRunning('assistant') }"
      @click="selectMode('assistant')"
      title="助手模式 - 通用办公任务：文件处理、Word/Excel/PPT、Shell命令"
    >
      <span v-if="isModeRunning('assistant')" class="running-indicator">●</span>
      🧑‍💼 助手
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'expert', running: isModeRunning('expert') }"
      @click="selectMode('expert')"
      title="专家模式 - 环境数据分析：空气质量、污染溯源、数据可视化"
    >
      <span v-if="isModeRunning('expert')" class="running-indicator">●</span>
      🔬 专家
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'query', running: isModeRunning('query') }"
      @click="selectMode('query')"
      title="问数模式 - 数据查询专家：本地数据库查询、SQL生成、数据聚合分析"
    >
      <span v-if="isModeRunning('query')" class="running-indicator">●</span>
      🔍 问数
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'code', running: isModeRunning('code') }"
      @click="selectMode('code')"
      title="编程模式 - 工具开发：创建、编辑、测试工具，查看代码"
    >
      <span v-if="isModeRunning('code')" class="running-indicator">●</span>
      💻 编程
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'report', running: isModeRunning('report') }"
      @click="selectMode('report')"
      title="报告模式 - 报告生成：基于模板和数据生成DOCX格式报告"
    >
      <span v-if="isModeRunning('report')" class="running-indicator">●</span>
      📄 报告
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'chart', running: isModeRunning('chart') }"
      @click="selectMode('chart')"
      title="图表模式 - 数据可视化：基于已保存数据生成Matplotlib图表"
    >
      <span v-if="isModeRunning('chart')" class="running-indicator">●</span>
      📊 图表
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'tracing', running: isModeRunning('tracing') }"
      @click="selectMode('tracing')"
      title="溯源模式 - 多专家并行快速溯源：气象+组分+可视化+报告（旧架构稳定版）"
    >
      <span v-if="isModeRunning('tracing')" class="running-indicator">●</span>
      🔍 溯源
    </button>

    <!-- 后台运行提示 -->
    <div v-if="backgroundRunningModes.length > 0" class="background-hint">
      后台运行: {{ backgroundRunningModes.map(m => getModeLabel(m)).join('、') }}
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits, computed } from 'vue'
import { useReactStore } from '@/stores/reactStore'

const props = defineProps({
  modelValue: {
    type: String,
    default: 'assistant',
    validator: (value) => ['assistant', 'expert', 'code', 'query', 'report', 'chart', 'tracing'].includes(value)
  }
})

const emit = defineEmits(['update:modelValue'])
const store = useReactStore()

// 检查模式是否正在运行
const isModeRunning = (mode) => {
  return !!store.modeStates[mode]?.isAnalyzing ||
    Object.values(store.sessionStates || {}).some(session => session.mode === mode && session.isAnalyzing)
}

// 获取后台运行的模式（排除当前模式）
const backgroundRunningModes = computed(() => {
  return store.runningModes.filter(mode => mode !== store.currentMode)
})

// 获取模式标签
const getModeLabel = (mode) => {
  const labelMap = {
    'assistant': '助手',
    'expert': '专家',
    'query': '问数',
    'code': '编程',
    'report': '报告',
    'chart': '图表',
    'tracing': '溯源'
  }
  return labelMap[mode] || mode
}

const selectMode = (mode) => {
  if (mode !== store.currentMode) {
    // 使用store的switchMode方法
    store.switchMode(mode)
    // 触发emit以保持向后兼容
    emit('update:modelValue', mode)
  }
}
</script>

<style scoped>
.agent-mode-selector {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mode-label {
  font-size: 12px;
  color: #718096;
  white-space: nowrap;
}

.mode-button {
  position: relative;
  padding: 4px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: white;
  color: #4a5568;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.mode-button:hover {
  border-color: #3182ce;
  background: #ebf8ff;
  color: #2c5282;
}

.mode-button.active {
  border-color: #3182ce;
  background: #3182ce;
  color: white;
}

.mode-button.running {
  border-color: #ed8936;
  background: #fffaf0;
  color: #c05621;
}

.mode-button.running:hover {
  border-color: #dd6b20;
  background: #feebc8;
  color: #9c4221;
}

.mode-button.active.running {
  border-color: #ed8936;
  background: #ed8936;
  color: white;
}

.running-indicator {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.2);
  }
}

.background-hint {
  font-size: 11px;
  color: #ed8936;
  padding: 2px 8px;
  background: #fffaf0;
  border-radius: 4px;
  margin-left: 8px;
  display: inline-flex;
  align-items: center;
}

/* 暗色主题支持 */
@media (prefers-color-scheme: dark) {
  .mode-label {
    color: #a0aec0;
  }

  .mode-button {
    background: #2d3748;
    color: #cbd5e0;
    border-color: #4a5568;
  }

  .mode-button:hover {
    background: #4a5568;
    border-color: #63b3ed;
    color: #ebf8ff;
  }

  .mode-button.active {
    background: #3182ce;
    color: white;
    border-color: #3182ce;
  }

  .mode-button.running {
    border-color: #ed8936;
    background: #7c2d12;
    color: #fed7aa;
  }

  .mode-button.running:hover {
    border-color: #f97316;
    background: #9a3412;
    color: #fef3c7;
  }

  .mode-button.active.running {
    background: #ed8936;
    color: white;
    border-color: #ed8936;
  }

  .background-hint {
    background: #7c2d12;
    color: #fed7aa;
  }
}
</style>
