<template>
  <div v-if="visible" class="chunks-fullscreen">
    <div class="chunks-header">
      <div class="chunks-title">
        <button class="btn-back" @click="handleClose">← 返回</button>
        <h2>{{ document?.filename || '未知文档' }}</h2>
        <span class="chunks-count">共 {{ chunks.length }} 个分块</span>
      </div>
      <div class="chunks-actions">
        <button class="btn-secondary" @click="handleClose">关闭</button>
      </div>
    </div>

    <div class="chunks-content">
      <div v-if="loading" class="chunks-loading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="error" class="chunks-error">
        <p>{{ error }}</p>
        <button class="btn-primary" @click="handleRetry">重试</button>
      </div>

      <div v-else-if="chunks.length === 0" class="chunks-empty">
        <p>暂无分块数据</p>
      </div>

      <div v-else class="chunks-list-full">
        <div v-for="(chunk, index) in chunks" :key="index" class="chunk-card">
          <div class="chunk-card-header">
            <span class="chunk-number">分块 #{{ chunk.chunk_index + 1 }}</span>
            <span class="chunk-length">{{ chunk.content?.length || 0 }} 字符</span>
            <span class="chunk-position" v-if="chunk.start_char !== null && chunk.end_char !== null">
              位置: {{ chunk.start_char }} - {{ chunk.end_char }}
            </span>
          </div>

          <div class="chunk-metadata" v-if="chunk.metadata && Object.keys(chunk.metadata).length > 0">
            <div class="metadata-row" v-if="chunk.metadata.topic">
              <span class="metadata-label">主题:</span>
              <span class="metadata-value">{{ chunk.metadata.topic }}</span>
            </div>
            <div class="metadata-row" v-if="chunk.metadata.section">
              <span class="metadata-label">章节:</span>
              <span class="metadata-value">{{ chunk.metadata.section }}</span>
            </div>
            <div class="metadata-row" v-if="chunk.metadata.type">
              <span class="metadata-label">类型:</span>
              <span class="metadata-value type-tag" :class="'type-' + chunk.metadata.type">
                {{ getChunkTypeName(chunk.metadata.type) }}
              </span>
            </div>
          </div>

          <div class="chunk-card-body">{{ chunk.content }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { CHUNK_TYPE_NAMES } from '@/utils/constants'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  document: {
    type: Object,
    default: null
  },
  chunks: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  }
})

const emit = defineEmits([
  'close',
  'retry',
  'update:visible'
])

// 获取分块类型名称
const getChunkTypeName = (type) => {
  return CHUNK_TYPE_NAMES[type] || type
}

// 处理关闭
const handleClose = () => {
  emit('close')
  emit('update:visible', false)
}

// 处理重试
const handleRetry = () => {
  emit('retry')
}

// 暴露方法
defineExpose({
  scrollToChunk: (index) => {
    const element = document.querySelector(`[data-chunk-index="${index}"]`)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
})
</script>

<style scoped>
.chunks-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: white;
  z-index: 2000;
  display: flex;
  flex-direction: column;
}

.chunks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
}

.chunks-title {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}

.btn-back {
  padding: 6px 12px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-back:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.chunks-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.chunks-count {
  font-size: 14px;
  color: #666;
  background: #f0f0f0;
  padding: 4px 12px;
  border-radius: 12px;
}

.chunks-actions {
  display: flex;
  gap: 12px;
}

.chunks-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.chunks-loading,
.chunks-error,
.chunks-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.chunks-loading p,
.chunks-error p,
.chunks-empty p {
  margin: 16px 0 0 0;
  font-size: 14px;
}

.chunks-list-full {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chunk-card {
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.chunk-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.chunk-number {
  font-weight: 600;
  color: #1890ff;
  font-size: 14px;
}

.chunk-length,
.chunk-position {
  font-size: 12px;
  color: #999;
}

.chunk-metadata {
  padding: 12px 16px;
  background: #f9f9f9;
  border-bottom: 1px solid #f0f0f0;
}

.metadata-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}

.metadata-row:last-child {
  margin-bottom: 0;
}

.metadata-label {
  font-weight: 500;
  color: #666;
}

.metadata-value {
  color: #333;
}

.type-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.type-tag.type-text {
  background: #e6f7ff;
  color: #1890ff;
}

.type-tag.type-code {
  background: #f6ffed;
  color: #52c41a;
}

.type-tag.type-table {
  background: #fff7e6;
  color: #fa8c16;
}

.type-tag.type-image {
  background: #fff1f0;
  color: #ff4d4f;
}

.type-tag.type-metadata {
  background: #f5f5f5;
  color: #999;
}

.chunk-card-body {
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.btn-secondary,
.btn-primary {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.btn-secondary {
  background: white;
  border-color: #d9d9d9;
  color: #333;
}

.btn-secondary:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}
</style>
