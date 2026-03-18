<template>
  <div class="agent-mode-selector">
    <span class="mode-label">Agent模式:</span>
    <button
      class="mode-button"
      :class="{ active: modelValue === 'assistant' }"
      @click="selectMode('assistant')"
      title="助手模式 - 通用办公任务：文件处理、Word/Excel/PPT、Shell命令"
    >
      🧑‍💼 助手
    </button>
    <button
      class="mode-button"
      :class="{ active: modelValue === 'expert' }"
      @click="selectMode('expert')"
      title="专家模式 - 环境数据分析：空气质量、污染溯源、数据可视化"
    >
      🔬 专家
    </button>
    <button
      class="mode-button"
      :class="{ active: modelValue === 'query' }"
      @click="selectMode('query')"
      title="问数模式 - 数据查询专家：本地数据库查询、SQL生成、数据聚合分析"
    >
      🔍 问数
    </button>
    <button
      class="mode-button"
      :class="{ active: modelValue === 'code' }"
      @click="selectMode('code')"
      title="编程模式 - 工具开发：创建、编辑、测试工具，查看代码"
    >
      💻 编程
    </button>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: 'assistant',
    validator: (value) => ['assistant', 'expert', 'code', 'query'].includes(value)
  }
})

const emit = defineEmits(['update:modelValue'])

const selectMode = (mode) => {
  if (mode !== props.modelValue) {
    emit('update:modelValue', mode)
    // 保存到localStorage
    localStorage.setItem('agent-mode', mode)
  }
}
</script>

<style scoped>
.agent-mode-selector {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.mode-label {
  font-size: 12px;
  color: #718096;
  white-space: nowrap;
}

.mode-button {
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
}
</style>
