<template>
  <div
    class="message agent-message"
    :id="`msg-${message.id}`"
    :class="{ 'has-debug': debugEnabled && message.debugInfo }"
  >
    <div class="message-meta">
      <span class="sender">Agent</span>
      <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
      <a :href="`#msg-${message.id}`" class="link" title="复制消息链接">#</a>
    </div>

    <div class="message-content">
      <div class="text">{{ contentToString(message.content) }}</div>

      <!-- 调试信息（可选显示） -->
      <div v-if="debugEnabled && message.debugInfo" class="debug-info">
        <details>
          <summary>调试信息</summary>
          <pre>{{ message.debugInfo }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup>
// 辅助函数：将 content 转换为字符串（支持字符串和 content blocks 格式）
const contentToString = (content) => {
  if (typeof content === 'string') {
    return content
  }
  if (Array.isArray(content)) {
    // Anthropic content blocks 格式：提取所有文本块并拼接
    const textBlocks = content
      .filter(block => block.type === 'text')
      .map(block => block.text || '')
    return textBlocks.length > 0 ? textBlocks.join('') : '[结构化内容]'
  }
  return '[未知格式]'
}

const props = defineProps({
  message: {
    type: Object,
    required: true
  },
  debugEnabled: {
    type: Boolean,
    default: false
  }
})

const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style lang="scss" scoped>
.agent-message {
  padding: 16px 0;
  border-bottom: 1px solid var(--border-1);
  animation: fadeIn 0.3s;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
}

.sender {
  font-weight: 600;
  color: var(--text-2);
}

.timestamp {
  color: var(--text-3);
  font-size: 12px;
}

.link {
  color: var(--border-3);
  text-decoration: none;
  font-size: 11px;
  margin-left: auto;
  transition: color 0.2s;

  &:hover {
    color: var(--color-primary);
  }
}

.message-content {
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-1);
}

.text {
  white-space: pre-wrap;
}

.debug-info {
  margin-top: 12px;
  padding: 12px;
  background: transparent;
  border-radius: 6px;
  border-left: 3px solid var(--color-warning);
  font-size: 13px;

  summary {
    cursor: pointer;
    color: var(--text-2);
    font-weight: 500;
    outline: none;
    user-select: none;

    &:hover {
      color: var(--color-primary);
    }
  }

  pre {
    margin-top: 8px;
    white-space: pre-wrap;
    font-family: 'Courier New', monospace;
    color: var(--text-2);
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>
