<template>
  <div class="debug-panel">
    <div class="debug-header">
      <h4>调试信息</h4>
      <button @click="$emit('close')">收起</button>
    </div>

    <div class="debug-content">
      <div class="debug-section">
        <h5>LLM上下文</h5>
        <pre class="context">{{ context || '暂无上下文信息' }}</pre>
        <button @click="copyContext" class="copy-btn">复制上下文</button>
      </div>

      <div class="debug-section">
        <h5>工具调用历史</h5>
        <div class="tool-calls">
          <div
            v-for="call in toolCalls"
            :key="call.id"
            class="tool-call"
          >
            <div class="call-header">
              <strong>{{ call.tool }}</strong>
              <span :class="['status-badge', call.status]">{{ getStatusText(call.status) }}</span>
            </div>
            <pre class="params">{{ JSON.stringify(call.params, null, 2) }}</pre>
            <small class="timestamp">{{ formatTime(call.timestamp) }}</small>
          </div>
          <div v-if="toolCalls.length === 0" class="empty-calls">
            暂无工具调用记录
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  context: {
    type: String,
    default: ''
  },
  toolCalls: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close'])

const copyContext = () => {
  navigator.clipboard.writeText(props.context).then(() => {
    alert('上下文已复制到剪贴板')
  }).catch(err => {
    console.error('复制失败:', err)
  })
}

const getStatusText = (status) => {
  const statusMap = {
    'pending': '待执行',
    'running': '进行中',
    'success': '成功',
    'failed': '失败'
  }
  return statusMap[status] || status
}

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
.debug-panel {
  position: fixed;
  right: 20px;
  top: 80px;
  width: 400px;
  max-height: 600px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  animation: fadeIn 0.3s;
}

.debug-header {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafafa;
  border-radius: 8px 8px 0 0;
}

.debug-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.debug-header button {
  padding: 4px 12px;
  border: none;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #e0e0e0;
  }
}

.debug-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.debug-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.debug-section h5 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #666;
}

.debug-section pre {
  margin: 0;
  padding: 12px;
  background: #f8f8f8;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
}

.copy-btn {
  align-self: flex-start;
  padding: 4px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #1976D2;
    color: #1976D2;
  }
}

.tool-calls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-call {
  padding: 12px;
  background: #f8f8f8;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #e0e0e0;
}

.call-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.call-header strong {
  font-size: 13px;
  color: #333;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.status-badge.success {
  background: #E8F5E9;
  color: #2E7D32;
}

.status-badge.running {
  background: #E3F2FD;
  color: #1565C0;
}

.status-badge.pending {
  background: #FFF3E0;
  color: #F57C00;
}

.status-badge.failed {
  background: #FFEBEE;
  color: #C62828;
}

.tool-call pre {
  margin: 0;
  font-size: 11px;
  color: #666;
  max-height: 100px;
}

.timestamp {
  font-size: 11px;
  color: #999;
}

.empty-calls {
  text-align: center;
  padding: 20px;
  color: #999;
  font-size: 13px;
}
</style>
