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
        <div
          v-for="(chunk, index) in chunks"
          :key="chunk.id || index"
          :ref="element => setChunkElement(chunk.id, element)"
          class="chunk-card"
          :class="{ targeted: document?.targetChunkId === chunk.id }"
        >
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
const chunkElements = new Map()
const setChunkElement = (id, element) => { if (id && element) chunkElements.set(id, element) }
watch(
  () => [props.visible, props.document?.targetChunkId, props.chunks.length],
  ([visible, target]) => {
    if (visible && target) requestAnimationFrame(() => chunkElements.get(target)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  },
  { flush: 'post' }
)

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
  border-bottom: 1px solid var(--border-2);
  background: var(--bg-muted);
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
  border: 1px solid var(--border-3);
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-back:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.chunks-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.chunks-count {
  font-size: 14px;
  color: var(--text-2);
  background: var(--border-1);
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
  color: var(--text-3);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-1);
  border-top-color: var(--color-primary);
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
  border: 1px solid var(--border-2);
  border-radius: 8px;
  overflow: hidden;
}
.chunk-card.targeted { border-color: var(--color-primary); box-shadow: 0 0 0 2px var(--color-primary-ring); }

.chunk-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-muted);
  border-bottom: 1px solid var(--border-2);
}

.chunk-number {
  font-weight: 600;
  color: var(--color-primary);
  font-size: 14px;
}

.chunk-length,
.chunk-position {
  font-size: 12px;
  color: var(--text-3);
}

.chunk-metadata {
  padding: 12px 16px;
  background: #f9f9f9;
  border-bottom: 1px solid var(--border-1);
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
  color: var(--text-2);
}

.metadata-value {
  color: var(--text-1);
}

.type-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.type-tag.type-text {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.type-tag.type-code {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.type-tag.type-table {
  background: #fff7e6;
  color: #fa8c16;
}

.type-tag.type-image {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.type-tag.type-metadata {
  background: var(--bg-hover);
  color: var(--text-3);
}

.chunk-card-body {
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-1);
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
  border-color: var(--border-3);
  color: var(--text-1);
}

.btn-secondary:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}
</style>
