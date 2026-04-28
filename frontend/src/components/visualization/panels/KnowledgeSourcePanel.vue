<template>
  <div class="knowledge-source-full-panel">
    <div class="panel-header">
      <div class="header-title">
        <span class="panel-icon">📚</span>
        <span class="panel-text">知识溯源</span>
        <span v-if="sources.length > 0" class="source-count">{{ sources.length }} 篇参考文档</span>
      </div>
    </div>

    <div v-if="sources.length === 0" class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
        <path d="M2 17l10 5 10-5"/>
        <path d="M2 12l10 5 10-5"/>
      </svg>
      <p>暂无知识溯源信息</p>
    </div>

    <div v-else class="source-list">
      <div
        v-for="(source, index) in sources"
        :key="index"
        class="source-item"
      >
        <div class="source-header">
          <div class="source-title">
            <span class="source-index">{{ index + 1 }}</span>
            <span class="source-name">{{ source.title || source.document_name || source.knowledge_base_name || '未知标题' }}</span>
          </div>
          <div class="source-meta">
            <span class="relevance-badge">
              相关度: {{ ((source.relevance || source.score || 0) * 100).toFixed(0) }}%
            </span>
          </div>
        </div>

        <div class="source-info">
          <div class="info-row">
            <label>来源:</label>
            <span>{{ source.source || source.knowledge_base_name || '未知来源' }}</span>
          </div>
          <div v-if="source.chunk_index !== undefined" class="info-row">
            <label>段落:</label>
            <span>第 {{ source.chunk_index + 1 }} 段</span>
          </div>
          <div v-if="source.document_name" class="info-row">
            <label>文档:</label>
            <span>{{ source.document_name }}</span>
          </div>
        </div>

        <div v-if="source.content" class="source-content">
          <div class="content-preview">{{ source.content }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Props
const props = defineProps({
  sources: {
    type: Array,
    default: () => []
  },
  history: {
    type: Array,
    default: () => []
  },
  selectedMessageId: {
    type: String,
    default: null
  }
})
</script>

<style scoped>
.knowledge-source-full-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6fb;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: white;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-icon {
  font-size: 20px;
}

.panel-text {
  font-weight: 600;
  font-size: 16px;
  color: #333;
}

.source-count {
  padding: 4px 12px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
  gap: 16px;
}

.empty-state p {
  font-size: 14px;
  margin: 0;
}

.source-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-item {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: white;
  transition: all 0.2s;
}

.source-item:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.source-title {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
}

.source-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: #1976d2;
  color: white;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-name {
  font-weight: 500;
  color: #333;
  font-size: 15px;
  line-height: 1.5;
}

.source-meta {
  flex-shrink: 0;
}

.relevance-badge {
  padding: 4px 10px;
  background: #4caf50;
  color: white;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.source-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  padding-left: 40px;
}

.info-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
}

.info-row label {
  color: #666;
  font-weight: 500;
  min-width: 50px;
}

.info-row span {
  color: #333;
}

.source-content {
  padding-left: 40px;
}

.content-preview {
  padding: 12px;
  background: #f5f5f5;
  border-radius: 6px;
  font-size: 13px;
  color: #666;
  line-height: 1.7;
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>