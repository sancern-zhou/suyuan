<template>
  <div class="message-list" ref="messagesContainer">
    <!-- 消息列表 -->
    <div v-for="message in messages" :key="message.id">
      <UserMessage
        v-if="message.type === 'user'"
        :message="message"
      />
      <AgentMessage
        v-else-if="message.type === 'agent'"
        :message="message"
        :debug-enabled="debugEnabled"
      />
    </div>

    <!-- 正在分析指示 -->
    <div v-if="isAnalyzing" class="typing-indicator">
      <div class="typing-content">
        <span class="typing-text">Agent正在分析中...</span>
        <span class="interrupt-hint">可随时输入新问题</span>
      </div>
      <div class="typing-dots">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import UserMessage from './UserMessage.vue'
import AgentMessage from './AgentMessage.vue'

defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  debugEnabled: {
    type: Boolean,
    default: false
  }
})

const messagesContainer = ref(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(
  () => [messages.length, isAnalyzing],
  () => {
    scrollToBottom()
  },
  { deep: true }
)
</script>

<style lang="scss" scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.typing-indicator {
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  gap: 16px;
  color: #999;
  font-size: 14px;
  animation: fadeIn 0.3s;
}

.typing-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.typing-text {
  font-weight: 500;
  color: #666;
}

.interrupt-hint {
  font-size: 12px;
  color: #FF9800;
}

.typing-dots {
  display: flex;
  gap: 4px;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  background: #ccc;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
</style>
