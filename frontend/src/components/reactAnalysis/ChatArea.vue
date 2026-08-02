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
    <div v-show="showManagementPanel" class="management-panel-container">
      <slot name="management-panels"></slot>
    </div>

    <!-- 消息列表 -->
    <ReActMessageList
      v-show="!showManagementPanel"
      :messages="messages"
      :show-reflexion="showReflexion"
      :reflexion-count="reflexionCount"
      :use-markdown="true"
      :assistant-mode="assistantMode"
      :agent-mode="agentMode"
      :selected-message-id="selectedMessageId"
      :on-message-click="handleMessageClick"
      :has-more-messages="hasMoreMessages"
      :total-message-count="totalMessageCount"
      :loading-more="loadingMore"
      :session-id="sessionId"
      @load-more="$emit('load-more')"
      @preview-message-attachment="$emit('preview-message-attachment', $event)"
    />

    <div v-if="readOnly && !showManagementPanel" class="read-only-notice">
      <span>{{ readOnlyNotice }}</span>
      <button type="button" @click="$emit('new-web-conversation')">新建 Web 对话</button>
    </div>

    <!-- 输入框 -->
    <InputBox
      v-show="!showManagementPanel"
      ref="inputBoxRef"
      v-model="inputValue"
      :pending-steering-inputs="pendingSteeringInputs"
      :session-id="sessionId"
      :disabled="inputDisabled || readOnly"
      :is-analyzing="isAnalyzing"
      :placeholder="inputPlaceholder"
      :assistant-mode="assistantMode"
      :use-reranker="useReranker"
      @send="$emit('send', $event)"
      @pause="$emit('pause')"
      @update:useReranker="$emit('update:useReranker', $event)"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import { withComposerShortcutGuide } from '@/components/inputBoxPlaceholder.js'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  pendingSteeringInputs: {
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
  agentMode: {
    type: String,
    default: 'assistant'
  },
  useReranker: {
    type: Boolean,
    default: false
  },
  sessionId: {
    type: String,
    default: ''
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
  },
  readOnly: {
    type: Boolean,
    default: false
  },
  readOnlyNotice: {
    type: String,
    default: ''
  }
})

const emit = defineEmits([
  'send',
  'pause',
  'update:useReranker',
  'select-message',
  'load-more',
  'toggle-viz-panel',
  'drag-over',
  'drag-leave',
  'drop',
  'new-web-conversation',
  'preview-message-attachment'
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
  return withComposerShortcutGuide(placeholders[props.assistantMode])
})

// 事件处理
const handleMessageClick = (messageId) => {
  emit('select-message', messageId)
}

const handleToggleVizPanel = () => {
  emit('toggle-viz-panel')
}

const handleDragOver = (e) => {
  if (props.readOnly) return
  emit('drag-over', e)
}

const handleDragLeave = (e) => {
  emit('drag-leave', e)
}

const handleDrop = (e) => {
  if (props.readOnly) return
  emit('drop', e)
}

// 公开方法
const focusInput = () => {
  nextTick(() => {
    inputBoxRef.value?.focus()
  })
}

const handleFilesDrop = async (files) => {
  if (props.readOnly) return
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
  z-index: 1000;
  width: 20px;
  height: 80px;
  background: #f5f5f5;
  color: #666;
  border: 1px solid #d9d9d9;
  border-radius: 4px 0 0 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  font-weight: bold;
}

.viz-toggle-btn:hover {
  background: #e6e6e6;
  transform: translateY(-50%) scale(1.05);
  box-shadow: -2px 0 12px rgba(0, 0, 0, 0.15);
  border-color: #bbb;
}

.viz-toggle-btn.expanded {
  right: 0;
  border-radius: 4px 0 0 4px;
}

.viz-toggle-btn:not(.expanded) {
  right: 0;
  border-radius: 0 4px 4px 0;
}

.toggle-icon {
  font-size: 14px;
  font-weight: bold;
}

.management-panel-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.read-only-notice {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 9px 14px;
  color: #8a5a00;
  background: #fff6df;
  border-top: 1px solid #f1d48a;
}

.read-only-notice button {
  padding: 5px 10px;
  border: 1px solid #1976d2;
  border-radius: 4px;
  color: #1976d2;
  background: #fff;
  cursor: pointer;
}
</style>
