<template>
  <div
    class="chat-area"
    :class="{ 'drag-over': dragOver }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <!-- 顶部功能区：左侧为侧边栏收起/展开按钮，右侧为右侧面板开关和更多功能菜单 -->
    <div class="conversation-actions">
      <button
        type="button"
        class="sidebar-toggle-btn"
        @click="handleToggleSidebar"
        :title="leftSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        :aria-label="leftSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
      >
        <svg class="sidebar-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">
          <rect width="18" height="18" x="3" y="3" rx="2" />
          <path d="M9 3v18" />
          <path v-if="leftSidebarCollapsed" d="m14 9 3 3-3 3" />
          <path v-else d="m16 15-3-3 3-3" />
        </svg>
      </button>

      <div class="actions-right-group">
        <button
          v-if="hasVizContent"
          type="button"
          class="panel-toggle-btn"
          @click="handleToggleVizPanel"
          :title="rightPanelExpanded ? '隐藏右侧面板' : '显示右侧面板'"
          :aria-label="rightPanelExpanded ? '隐藏右侧面板' : '显示右侧面板'"
        >
          <svg class="panel-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M15 3v18" />
            <path v-if="rightPanelExpanded" d="m8 9 3 3-3 3" />
            <path v-else d="m10 15-3-3 3-3" />
          </svg>
        </button>

        <div ref="moreMenuRootRef" class="more-menu-root">
          <button
            type="button"
            class="more-menu-trigger"
            :class="{ active: moreMenuOpen }"
            @click="toggleMoreMenu"
            title="更多功能"
            aria-label="更多功能"
            :aria-expanded="moreMenuOpen"
            aria-haspopup="menu"
          >
            <svg class="more-menu-icon" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="1" />
              <circle cx="19" cy="12" r="1" />
              <circle cx="5" cy="12" r="1" />
            </svg>
          </button>
  
          <transition name="more-menu-fade">
            <div v-if="moreMenuOpen" class="more-menu" role="menu">
              <button
                type="button"
                class="more-menu-item"
                role="menuitem"
                :disabled="!sessionId"
                :title="sessionId ? '' : '当前没有进行中的会话'"
                @click="handleMenuAction('trajectory')"
              >
                <svg class="menu-item-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m10.586 5.414-5.172 5.172" />
                  <path d="m18.586 13.414-5.172 5.172" />
                  <path d="M6 12h12" />
                  <circle cx="12" cy="20" r="2" />
                  <circle cx="12" cy="4" r="2" />
                  <circle cx="20" cy="12" r="2" />
                  <circle cx="4" cy="12" r="2" />
                </svg>
                <span>查看调用轨迹</span>
              </button>
              <button
                type="button"
                class="more-menu-item"
                role="menuitem"
                :disabled="!sessionId"
                :title="sessionId ? '' : '当前没有进行中的会话'"
                @click="handleMenuAction('copy-session-id')"
              >
                <svg class="menu-item-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                </svg>
                <span>{{ copySessionIdLabel }}</span>
              </button>
              <button
                type="button"
                class="more-menu-item"
                role="menuitem"
                :disabled="!exportableMessages.length"
                :title="exportableMessages.length ? '' : '当前没有可导出的对话内容'"
                @click="handleMenuAction('export-conversation')"
              >
                <svg class="menu-item-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 15V3" />
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <path d="m7 10 5 5 5-5" />
                </svg>
                <span>导出对话记录</span>
              </button>
  
              <div class="more-menu-separator" role="separator"></div>
  
              <button
                type="button"
                class="more-menu-item"
                role="menuitem"
                @click="handleMenuAction('new-conversation')"
              >
                <svg class="menu-item-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z" />
                  <path d="M12 8v6" />
                  <path d="M9 11h6" />
                </svg>
                <span>新建对话</span>
              </button>
            </div>
          </transition>
        </div>
      </div>
    </div>

    <!-- 管理面板插槽 -->
    <div v-show="showManagementPanel" class="management-panel-container">
      <slot name="management-panels"></slot>
    </div>

    <!-- 消息列表 -->
    <ReActMessageList
      v-show="!showManagementPanel"
      :messages="messages"
      :is-analyzing="isAnalyzing"
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

    <AgentInteractionDialog
      v-show="!showManagementPanel"
      :interaction="pendingInteraction"
      :resolving="interactionResolving"
      @resolve="$emit('resolve-interaction', $event)"
      @close="$emit('close-interaction')"
    />

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
      :agent-mode="agentMode"
      :use-reranker="useReranker"
      @send="$emit('send', $event)"
      @pause="$emit('pause')"
      @update:useReranker="$emit('update:useReranker', $event)"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import AgentInteractionDialog from './dialogs/AgentInteractionDialog.vue'
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
  pendingInteraction: {
    type: Object,
    default: null
  },
  interactionResolving: {
    type: Boolean,
    default: false
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
  leftSidebarCollapsed: {
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
  'preview-message-attachment',
  'resolve-interaction',
  'close-interaction',
  'open-trajectory',
  'toggle-left-sidebar',
  'new-conversation'
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

const handleToggleSidebar = () => {
  emit('toggle-left-sidebar')
}

// ===== 更多功能菜单（参考 ZCode 的 Ellipsis 下拉菜单） =====
const moreMenuRootRef = ref(null)
const moreMenuOpen = ref(false)
const sessionCopied = ref(false)
let sessionCopiedTimer = null
let moreMenuOutsideHandler = null
let moreMenuKeydownHandler = null

const copySessionIdLabel = computed(() => (sessionCopied.value ? '已复制会话 ID' : '复制会话 ID'))

// 可导出的对话消息（用户提问与助手回答）
const exportableMessages = computed(() => (props.messages || []).filter(message => {
  if (message.type === 'user') return Boolean(String(message.content || '').trim())
  if (message.type === 'assistant' || message.type === 'final') return Boolean(String(message.content || '').trim())
  return false
}))

const toggleMoreMenu = () => {
  if (moreMenuOpen.value) {
    closeMoreMenu()
    return
  }
  moreMenuOpen.value = true
  moreMenuOutsideHandler = (event) => {
    if (moreMenuRootRef.value && !moreMenuRootRef.value.contains(event.target)) closeMoreMenu()
  }
  moreMenuKeydownHandler = (event) => {
    if (event.key === 'Escape') closeMoreMenu()
  }
  document.addEventListener('mousedown', moreMenuOutsideHandler)
  document.addEventListener('keydown', moreMenuKeydownHandler)
}

const closeMoreMenu = () => {
  moreMenuOpen.value = false
  if (moreMenuOutsideHandler) {
    document.removeEventListener('mousedown', moreMenuOutsideHandler)
    moreMenuOutsideHandler = null
  }
  if (moreMenuKeydownHandler) {
    document.removeEventListener('keydown', moreMenuKeydownHandler)
    moreMenuKeydownHandler = null
  }
}

onBeforeUnmount(() => {
  closeMoreMenu()
  clearTimeout(sessionCopiedTimer)
})

const handleMenuAction = async (action) => {
  closeMoreMenu()
  if (action === 'trajectory') {
    emit('open-trajectory')
    return
  }
  if (action === 'copy-session-id') {
    if (!props.sessionId) return
    try {
      await navigator.clipboard.writeText(props.sessionId)
      sessionCopied.value = true
      clearTimeout(sessionCopiedTimer)
      sessionCopiedTimer = setTimeout(() => { sessionCopied.value = false }, 2000)
    } catch (error) {
      console.error('Failed to copy session id:', error)
    }
    return
  }
  if (action === 'export-conversation') {
    exportConversation()
    return
  }
  if (action === 'new-conversation') {
    emit('new-conversation')
  }
}

const exportConversation = () => {
  const lines = []
  lines.push(`# 对话记录${props.sessionId ? `（${props.sessionId}）` : ''}`)
  lines.push('')
  lines.push(`> 导出时间：${new Date().toLocaleString()}`)
  lines.push('')
  for (const message of exportableMessages.value) {
    const isUser = message.type === 'user'
    lines.push(`## ${isUser ? '用户' : '助手'}`)
    lines.push('')
    lines.push(String(message.content || '').trim())
    lines.push('')
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `conversation-${props.sessionId || new Date().toISOString().slice(0, 10)}.md`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
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
.conversation-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 20px;
}

.sidebar-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s, color 0.2s;
}

.sidebar-toggle-btn:hover {
  background: var(--bg-muted);
  color: var(--text-1);
}

.sidebar-toggle-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.more-menu-root {
  position: relative;
  display: inline-flex;
}

.more-menu-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s, color 0.2s;
}

.more-menu-trigger:hover,
.more-menu-trigger.active {
  background: var(--bg-muted);
  color: var(--text-1);
}

.more-menu-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.more-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 1200;
  min-width: 180px;
  padding: 6px;
  background: var(--bg-container, #fff);
  border: 1px solid var(--border-3, #e5e7eb);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.more-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: var(--text-1, #1f2937);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.15s;
}

.more-menu-item:hover:not(:disabled) {
  background: var(--bg-muted, #f1f5f9);
}

.more-menu-item:disabled {
  color: #b0b9cc;
  cursor: not-allowed;
}

.menu-item-icon {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.more-menu-separator {
  height: 1px;
  margin: 4px 2px;
  background: var(--border-3, #e5e7eb);
}

.more-menu-fade-enter-active,
.more-menu-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.more-menu-fade-enter-from,
.more-menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.chat-area {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background: var(--bg-hover);
  transition: background-color 0.3s;
}

.chat-area.drag-over {
  background: var(--color-primary-bg);
  border: 2px dashed var(--color-primary);
}

.actions-right-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.panel-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s, color 0.2s;
}

.panel-toggle-btn:hover {
  background: var(--bg-muted);
  color: var(--text-1);
}

.panel-toggle-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
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
  border: 1px solid var(--color-primary);
  border-radius: 4px;
  color: var(--color-primary);
  background: var(--bg-container);
  cursor: pointer;
}
</style>
