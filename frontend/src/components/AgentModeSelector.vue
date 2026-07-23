<template>
  <div class="agent-mode-selector">
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'assistant', running: isModeRunning('assistant') }"
      @click="selectMode('assistant')"
      title="助手"
    >
      <span v-if="isModeRunning('assistant')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
        <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
      </svg>
      <span>助手</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'ppt', running: isModeRunning('ppt') }"
      @click="selectMode('ppt')"
      title="幻灯片"
    >
      <span v-if="isModeRunning('ppt')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 5h16v12H4z" />
        <path d="M8 21h8" />
        <path d="M12 17v4" />
        <path d="m9 13 3-5 3 5" />
      </svg>
      <span>幻灯片</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'expert', running: isModeRunning('expert') }"
      @click="selectMode('expert')"
      title="专家"
    >
      <span v-if="isModeRunning('expert')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 4v5.5l-4.6 7.6A2 2 0 0 0 7.1 20h9.8a2 2 0 0 0 1.7-2.9L14 9.5V4" />
        <path d="M8 4h8" />
        <path d="M8 15h8" />
      </svg>
      <span>专家</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'query', running: isModeRunning('query') }"
      @click="selectMode('query')"
      title="问数"
    >
      <span v-if="isModeRunning('query')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="5.5" />
        <path d="m15 15 4.5 4.5" />
        <path d="M8 10h5" />
        <path d="M8 13h3" />
      </svg>
      <span>问数</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'report', running: isModeRunning('report') }"
      @click="selectMode('report')"
      title="报告"
    >
      <span v-if="isModeRunning('report')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 3.5h8l4 4v13H6v-17Z" />
        <path d="M14 3.5v4h4" />
        <path d="M9 12h6" />
        <path d="M9 15.5h6" />
      </svg>
      <span>报告</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'chart', running: isModeRunning('chart') }"
      @click="selectMode('chart')"
      title="图表"
    >
      <span v-if="isModeRunning('chart')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 19V5" />
        <path d="M5 19h14" />
        <path d="M9 16v-5" />
        <path d="M13 16V8" />
        <path d="M17 16v-3" />
      </svg>
      <span>图表</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'board', running: isModeRunning('board') }"
      @click="selectMode('board')"
      title="画板"
    >
      <span v-if="isModeRunning('board')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 5h16v14H4z" />
        <path d="M7 9h4v3H7z" />
        <path d="M13 12h4v3h-4z" />
        <path d="M11 10.5h2v3h-2" />
      </svg>
      <span>画板</span>
    </button>
    <button
      class="mode-button"
      :class="{ active: store.currentMode === 'ops', running: isModeRunning('ops') }"
      @click="selectMode('ops')"
      title="运维"
    >
      <span v-if="isModeRunning('ops')" class="running-indicator">●</span>
      <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h16" />
        <path d="M6 7v13h12V7" />
        <path d="M9 7V4h6v3" />
        <path d="M9 12h6" />
        <path d="M9 16h4" />
      </svg>
      <span>运维</span>
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
    validator: (value) => ['assistant', 'ppt', 'expert', 'query', 'report', 'chart', 'board', 'ops'].includes(value)
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
    'ppt': '幻灯片',
    'expert': '专家',
    'query': '问数',
    'report': '报告',
      'chart': '图表',
      'board': '画板',
    'ops': '运维'
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
  gap: 4px;
  flex-wrap: wrap;
  min-width: 0;
}

.mode-button {
  position: relative;
  min-height: 30px;
  padding: 4px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
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

.mode-icon {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: 0 0 auto;
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

@media (max-width: 768px) {
  .agent-mode-selector {
    width: 100%;
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 2px;
  }

  .mode-button {
    flex: 0 0 auto;
  }
}

/* 暗色主题支持 */
@media (prefers-color-scheme: dark) {
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
