<template>
  <div class="knowledge-source-panel">
    <div class="panel-header">
      <div class="header-title">
        <span class="panel-icon">📚</span>
        <span class="panel-text">知识溯源</span>
        <span class="source-count">{{ sources.length }} 篇参考文档</span>
      </div>
      <button
        v-if="sources.length > 0"
        @click="toggleExpand"
        class="toggle-btn"
      >
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>

    <div v-if="expanded && sources.length > 0" class="source-list">
      <div
        v-for="(source, index) in sources"
        :key="index"
        class="source-item"
        :class="getRelevanceClass(source.relevance)"
      >
        <div class="source-header">
          <div class="source-title">
            <span class="source-index">{{ index + 1 }}</span>
            <span class="source-name">{{ source.title || '未知标题' }}</span>
          </div>
          <div class="source-meta">
            <span class="relevance-badge" :title="`相关度: ${(source.relevance * 100).toFixed(1)}%`">
              相关度: {{ (source.relevance * 100).toFixed(1) }}%
            </span>
          </div>
        </div>

        <div class="source-info">
          <div class="info-row">
            <label>来源:</label>
            <span>{{ source.source || '未知来源' }}</span>
          </div>
          <div v-if="source.chunk_index !== undefined" class="info-row">
            <label>段落:</label>
            <span>第 {{ source.chunk_index + 1 }} 段</span>
          </div>
        </div>

        <div v-if="source.content" class="source-content">
          <div class="content-preview">{{ source.content }}</div>
          <button
            v-if="isContentTruncated(source.content)"
            @click="showFullContent(source)"
            class="view-more-btn"
          >
            查看完整内容
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="!sources.length" class="empty-state">
      <span class="empty-icon">📭</span>
      <p class="empty-text">暂无检索到的参考文档</p>
    </div>

    <!-- 完整内容弹窗 -->
    <div v-if="showContentModal" class="content-modal" @click.self="closeContentModal">
      <div class="modal-content">
        <div class="modal-header">
          <h4>{{ currentSource.title }}</h4>
          <button @click="closeContentModal" class="close-btn">×</button>
        </div>
        <div class="modal-body">
          <div class="modal-info">
            <span class="modal-source">{{ currentSource.source }}</span>
            <span class="modal-chunk">第 {{ currentSource.chunk_index + 1 }} 段</span>
          </div>
          <div class="modal-content-text">{{ currentSource.fullContent }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  sources: {
    type: Array,
    default: () => []
  }
})

const expanded = ref(true)
const showContentModal = ref(false)
const currentSource = ref({
  title: '',
  source: '',
  chunk_index: 0,
  fullContent: ''
})

const toggleExpand = () => {
  expanded.value = !expanded.value
}

const getRelevanceClass = (relevance) => {
  const score = relevance || 0
  if (score >= 0.8) return 'high'
  if (score >= 0.5) return 'medium'
  return 'low'
}

const isContentTruncated = (content) => {
  return content && content.endsWith('...')
}

const showFullContent = (source) => {
  // 获取完整内容（需要从后端获取，这里暂时使用截取的内容）
  currentSource.value = {
    title: source.title || '未知标题',
    source: source.source || '未知来源',
    chunk_index: source.chunk_index || 0,
    fullContent: source.content || '暂无内容'
  }
  showContentModal.value = true
}

const closeContentModal = () => {
  showContentModal.value = false
}
</script>

<style lang="scss" scoped>
.knowledge-source-panel {
  width: 100%;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-bottom: 1px solid #f0f0f0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-icon {
  font-size: 18px;
}

.panel-text {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.source-count {
  font-size: 12px;
  color: #666;
  background: #fff;
  padding: 2px 8px;
  border-radius: 999px;
}

.toggle-btn {
  padding: 4px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
    background: #e3f2fd;
  }
}

.source-list {
  max-height: 500px;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
  transition: all 0.2s;

  &:hover {
    background: #f0f8ff;
    border-color: #d0e7ff;
  }

  &.high {
    border-left: 3px solid #4caf50;
  }

  &.medium {
    border-left: 3px solid #ff9800;
  }

  &.low {
    border-left: 3px solid #ff5722;
  }
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.source-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.source-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: #1976d2;
  color: white;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  word-break: break-word;
}

.source-meta {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.relevance-badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.source-item.high .relevance-badge {
  background: #e8f5e9;
  color: #2e7d32;
}

.source-item.medium .relevance-badge {
  background: #fff3e0;
  color: #f57c00;
}

.source-item.low .relevance-badge {
  background: #ffebee;
  color: #c62828;
}

.source-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.info-row label {
  color: #666;
  font-weight: 500;
}

.info-row span {
  color: #333;
}

.source-content {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 8px 12px;
}

.content-preview {
  font-size: 12px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 8px;
}

.view-more-btn {
  padding: 4px 8px;
  border: none;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #bbdefb;
  }
}

.empty-state {
  padding: 24px 16px;
  text-align: center;
  color: #999;
}

.empty-icon {
  font-size: 32px;
  display: block;
  margin-bottom: 8px;
}

.empty-text {
  font-size: 13px;
  margin: 0;
}

/* 完整内容弹窗 */
.content-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 800px;
  width: 100%;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.modal-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;

  &:hover {
    background: #e0e0e0;
  }
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.modal-info {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 12px;
}

.modal-source, .modal-chunk {
  padding: 4px 8px;
  border-radius: 4px;
  background: #f0f0f0;
  color: #666;
}

.modal-content-text {
  font-size: 13px;
  line-height: 1.8;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
