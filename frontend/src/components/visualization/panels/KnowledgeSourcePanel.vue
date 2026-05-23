<template>
  <div class="knowledge-source-full-panel">
    <div v-if="sources.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5.5C5 4.67 5.67 4 6.5 4h11c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-13Z" />
        <path d="M8 8h8" />
        <path d="M8 11.5h8" />
        <path d="M8 15h5" />
      </svg>
      <p class="empty-title">暂无知识溯源</p>
      <p class="empty-tip">使用知识库检索或问答后，参考文档会显示在这里</p>
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
  background: #f8fafc;
  overflow: hidden;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8a96a8;
  gap: 8px;
  padding: 32px 20px;
}

.empty-state svg {
  width: 46px;
  height: 46px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.empty-title {
  font-size: 15px;
  font-weight: 500;
  color: #526173;
  margin: 0;
}

.empty-tip {
  max-width: 240px;
  margin: 0;
  color: #8a96a8;
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.source-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
}

.source-item {
  padding: 12px;
  border: 1px solid #edf1f7;
  border-radius: 8px;
  background: #fff;
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.source-title {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.source-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-name {
  font-weight: 500;
  color: #35425f;
  font-size: 14px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-meta {
  flex-shrink: 0;
}

.relevance-badge {
  padding: 3px 8px;
  background: #f1f8f4;
  color: #2e7d32;
  border: 1px solid #c8e6c9;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
}

.source-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.info-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.info-row label {
  color: #7a879a;
  font-weight: 500;
  min-width: 50px;
}

.info-row span {
  color: #526173;
}

.source-content {
  margin-top: 8px;
}

.content-preview {
  padding: 10px;
  background: #f8fafc;
  border-radius: 6px;
  font-size: 13px;
  color: #526173;
  line-height: 1.65;
  max-height: 128px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>
