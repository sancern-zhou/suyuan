<template>
  <div
    v-if="show"
    class="workflow-tool-selector"
    :style="{ left: position.x + 'px', top: position.y + 'px' }"
  >
    <div class="selector-header">
      <h3>选择工作流工具</h3>
      <p class="selector-desc">使用工作流工具快速完成复杂分析任务</p>
    </div>

    <div class="tool-list">
      <div
        v-for="tool in workflowTools"
        :key="tool.id"
        class="tool-item"
        :class="{ active: selectedTool === tool.id, highlighted: highlightedTool === tool.id }"
        @click="selectTool(tool)"
        @mouseenter="highlightedTool = tool.id"
        @mouseleave="highlightedTool = null"
      >
        <div class="tool-icon">
          <span :class="tool.icon"></span>
        </div>
        <div class="tool-info">
          <p class="tool-name">{{ tool.name }}</p>
          <p class="tool-desc">{{ tool.description }}</p>
          <p class="tool-params" v-if="tool.params">
            <span v-for="param in tool.params" :key="param" class="param-tag">{{ param }}</span>
          </p>
        </div>
      </div>
    </div>

    <div class="selector-footer">
      <span class="hint">点击选择工作流工具</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  position: {
    type: Object,
    default: () => ({ x: 0, y: 0 })
  }
})

const emit = defineEmits(['select', 'close'])

const workflowTools = [
  {
    id: 'quick_tracing_workflow',
    name: '快速溯源',
    description: '多专家快速溯源分析（支持自然语言）',
    icon: 'icon-zippy',
    params: ['查询文本']
  },
  {
    id: 'standard_analysis_workflow',
    name: '标准分析',
    description: '完整的污染溯源分析（多专家协作）',
    icon: 'icon-analysis',
    params: ['查询文本', '精度模式']
  },
  {
    id: 'deep_trace_workflow',
    name: '深度溯源',
    description: 'PMF源解析+OBM/OBP深度分析',
    icon: 'icon-search',
    params: ['城市', '污染物', '时间范围']
  },
  {
    id: 'knowledge_qa_workflow',
    name: '知识问答',
    description: '基于知识库的专业问答',
    icon: 'icon-book',
    params: ['问题']
  }
]

const selectedTool = ref(null)
const highlightedTool = ref(null)

const selectTool = (tool) => {
  selectedTool.value = tool.id
  emit('select', tool)
  emit('close')
}

// 键盘导航
const handleKeydown = (e) => {
  if (!props.show) return

  const currentIndex = workflowTools.findIndex(t => t.id === highlightedTool.value)

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      const nextIndex = currentIndex < workflowTools.length - 1 ? currentIndex + 1 : 0
      highlightedTool.value = workflowTools[nextIndex].id
      break
    case 'ArrowUp':
      e.preventDefault()
      const prevIndex = currentIndex > 0 ? currentIndex - 1 : workflowTools.length - 1
      highlightedTool.value = workflowTools[prevIndex].id
      break
    case 'Enter':
      e.preventDefault()
      if (highlightedTool.value) {
        const tool = workflowTools.find(t => t.id === highlightedTool.value)
        if (tool) selectTool(tool)
      }
      break
    case 'Escape':
      e.preventDefault()
      emit('close')
      break
  }
}

// 监听显示状态，重置选中
watch(() => props.show, (newVal) => {
  if (newVal) {
    selectedTool.value = null
    highlightedTool.value = null
    // 添加全局键盘监听
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
  }
})

defineExpose({
  selectTool,
  highlightedTool
})
</script>

<style lang="scss" scoped>
.workflow-tool-selector {
  position: fixed;
  background: #fff;
  border: 1px solid #e4e7f0;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(31, 42, 68, 0.15);
  z-index: 1000;
  max-width: 400px;
  min-width: 320px;
  animation: slideIn 0.15s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.selector-header {
  padding: 16px 16px 12px;
  border-bottom: 1px solid #f0f0f0;

  h3 {
    margin: 0 0 4px;
    font-size: 16px;
    color: #1f2a44;
    font-weight: 600;
  }

  .selector-desc {
    margin: 0;
    font-size: 13px;
    color: #7a86a0;
  }
}

.tool-list {
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;

  &:hover {
    background: #f8f9fa;
  }

  &.active {
    background: #e9f3ff;
    border-color: #1976d2;
  }

  &.highlighted {
    background: #f0f4ff;
    border-color: #b3d5ff;
  }
}

.tool-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f4ff;
  border-radius: 8px;
  color: #1976d2;
  font-size: 18px;

  .icon-zippy::before {
    content: '⚡';
  }

  .icon-analysis::before {
    content: '📊';
  }

  .icon-search::before {
    content: '🔍';
  }

  .icon-book::before {
    content: '📚';
  }
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-name {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2a44;
}

.tool-desc {
  margin: 0 0 4px;
  font-size: 12px;
  color: #7a86a0;
  line-height: 1.4;
}

.tool-params {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.param-tag {
  font-size: 11px;
  padding: 2px 6px;
  background: #f0f4ff;
  color: #1976d2;
  border-radius: 4px;
}

.selector-footer {
  padding: 8px 16px;
  border-top: 1px solid #f0f0f0;
  background: #fafbff;
  border-radius: 0 0 12px 12px;

  .hint {
    font-size: 12px;
    color: #9aa6c1;
  }
}
</style>
