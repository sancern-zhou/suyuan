<template>
  <div class="knowledge-source-section">
    <div class="panel-header">
      <div class="header-title">
        <span class="panel-icon">📚</span>
        <span class="panel-text">知识溯源</span>
        <span class="source-count">{{ sources.length }} 篇参考文档</span>
      </div>
      <button
        @click="$emit('toggle-expand')"
        class="toggle-btn"
      >
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>

    <div v-if="expanded" class="source-list">
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
  expanded: {
    type: Boolean,
    default: true
  }
})

// Emit events
defineEmits(['toggle-expand'])
</script>

<style scoped>
.knowledge-source-section {
  background: white;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
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
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.source-count {
  padding: 2px 8px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.toggle-btn {
  padding: 4px 12px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: #1976d2;
  color: white;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-item {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
  transition: all 0.2s;
}

.source-item:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 6px rgba(25, 118, 210, 0.15);
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.source-title {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
}

.source-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: #1976d2;
  color: white;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-name {
  font-weight: 500;
  color: #333;
  font-size: 14px;
  line-height: 1.4;
}

.source-meta {
  flex-shrink: 0;
}

.relevance-badge {
  padding: 2px 8px;
  background: #4caf50;
  color: white;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.source-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
  padding-left: 32px;
}

.info-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.info-row label {
  color: #666;
  font-weight: 500;
  min-width: 40px;
}

.info-row span {
  color: #333;
}

.source-content {
  padding-left: 32px;
}

.content-preview {
  padding: 8px;
  background: white;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  max-height: 100px;
  overflow-y: auto;
}
</style>