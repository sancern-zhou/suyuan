<template>
  <div
    class="chat-area"
    :class="{ 'drag-over': dragOver }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <!-- 可视化面板折叠/展开按钮 -->
    <button
      v-if="hasVizContent"
      class="viz-toggle-btn"
      :class="{ expanded: rightPanelExpanded }"
      @click="handleToggleVizPanel"
      :title="rightPanelExpanded ? '隐藏右侧面板' : '显示右侧面板'"
    >
      <span class="toggle-icon">{{ rightPanelExpanded ? '»' : '«' }}</span>
    </button>

    <!-- 管理面板插槽 -->
    <div v-if="showManagementPanel" class="management-panel-container">
      <slot name="management-panels"></slot>
    </div>

    <!-- 消息列表 -->
    <ReActMessageList
      v-else
      :messages="messages"
      :show-reflexion="showReflexion"
      :reflexion-count="reflexionCount"
      :use-markdown="true"
      :assistant-mode="assistantMode"
      :selected-message-id="selectedMessageId"
      :visualization-panel-ref="null"
      :on-message-click="handleMessageClick"
      :has-more-messages="hasMoreMessages"
      :total-message-count="totalMessageCount"
      :loading-more="loadingMore"
      @load-more="$emit('load-more')"
    />

    <!-- 输入框 -->
    <InputBox
      v-if="!showManagementPanel"
      ref="inputBoxRef"
      v-model="inputValue"
      :disabled="inputDisabled"
      :is-analyzing="isAnalyzing"
      :placeholder="inputPlaceholder"
      :assistant-mode="assistantMode"
      :use-reranker="useReranker"
      @send="$emit('send', $event)"
      @pause="$emit('pause')"
      @update:useReranker="$emit('update:useReranker', $event)"
      @update:agentMode="$emit('update:agentMode', $event)"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  inputDisabled: {
    type: Boolean,
    default: false
  },
  currentMessage: {
    type: String,
    default: ''
  },
  showReflexion: {
    type: Boolean,
    default: false
  },
  reflexionCount: {
    type: Number,
    default: 0
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  useReranker: {
    type: Boolean,
    default: false
  },
  hasMoreMessages: {
    type: Boolean,
    default: false
  },
  totalMessageCount: {
    type: Number,
    default: 0
  },
  loadingMore: {
    type: Boolean,
    default: false
  },
  selectedMessageId: {
    type: String,
    default: null
  },
  dragOver: {
    type: Boolean,
    default: false
  },
  rightPanelExpanded: {
    type: Boolean,
    default: false
  },
  hasVizContent: {
    type: Boolean,
    default: false
  },
  showManagementPanel: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'send',
  'pause',
  'update:useReranker',
  'update:agentMode',
  'select-message',
  'load-more',
  'toggle-viz-panel',
  'drag-over',
  'drag-leave',
  'drop'
])

const inputBoxRef = ref(null)

const inputValue = computed({
  get: () => props.currentMessage,
  set: () => {
    // 值由store管理，这里是单向绑定
  }
})

const inputPlaceholder = computed(() => {
  const placeholders = {
    'general-agent': '输入您的问题...',
    'weather-expert': '描述您想分析的气象问题...',
    'component-expert': '描述您想分析的污染物组分问题...',
    'viz-expert': '描述您想生成的可视化需求...',
    'report-generation-expert': '输入报告生成需求...',
    'office-assistant': '输入您需要处理的办公任务...'
  }
  return placeholders[props.assistantMode] || '输入您的问题...'
})

// 事件处理
const handleMessageClick = (messageId) => {
  emit('select-message', messageId)
}

const handleToggleVizPanel = () => {
  emit('toggle-viz-panel')
}

const handleDragOver = (e) => {
  emit('drag-over', e)
}

const handleDragLeave = (e) => {
  emit('drag-leave', e)
}

const handleDrop = (e) => {
  emit('drop', e)
}

// 公开方法
const focusInput = () => {
  nextTick(() => {
    inputBoxRef.value?.focus()
  })
}

const handleFilesDrop = async (files) => {
  if (inputBoxRef.value && typeof inputBoxRef.value.handleFilesDrop === 'function') {
    await inputBoxRef.value.handleFilesDrop(files)
  }
}

defineExpose({
  focusInput,
  handleFilesDrop
})
</script>

<style scoped>
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background: #f5f5f5;
  transition: background-color 0.3s;
}

.chat-area.drag-over {
  background: #e6f7ff;
  border: 2px dashed #1890ff;
}

.viz-toggle-btn {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  z-index: 10;
  width: 24px;
  height: 60px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px 0 0 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
}

.viz-toggle-btn:hover {
  background: #40a9ff;
  width: 28px;
}

.viz-toggle-btn.expanded {
  right: auto;
  left: 0;
  border-radius: 0 4px 4px 0;
}

.toggle-icon {
  font-size: 16px;
  font-weight: bold;
}

.management-panel-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
</style>
