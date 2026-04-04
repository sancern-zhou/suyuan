<template>
  <div class="management-panel kb-panel">
    <div class="panel-header">
      <h3>知识库管理</h3>
      <div class="panel-actions">
        <button class="panel-btn" @click="$emit('show-create-dialog')">+ 新建知识库</button>
        <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
      </div>
    </div>

    <div v-if="!kbStore.currentKb" class="kb-content">
      <!-- 公共知识库 -->
      <div v-if="kbStore.publicKbs.length > 0" class="kb-section">
        <div class="kb-section-title">公共知识库</div>
        <div
          v-for="kb in kbStore.publicKbs"
          :key="kb.id"
          class="kb-item"
          @click="selectKb(kb)"
        >
          <div class="kb-item-header">
            <span class="kb-name">{{ kb.name }}</span>
            <span class="kb-badge public">公共</span>
          </div>
          <div class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块</div>
        </div>
      </div>

      <!-- 个人知识库 -->
      <div v-if="kbStore.privateKbs.length > 0" class="kb-section">
        <div class="kb-section-title">我的知识库</div>
        <div
          v-for="kb in kbStore.privateKbs"
          :key="kb.id"
          class="kb-item"
          @click="selectKb(kb)"
        >
          <div class="kb-item-header">
            <span class="kb-name">{{ kb.name }}</span>
            <span class="kb-badge private">个人</span>
          </div>
          <div class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块</div>
        </div>
      </div>

      <div v-if="kbStore.publicKbs.length === 0 && kbStore.privateKbs.length === 0" class="kb-empty">
        暂无知识库，点击上方按钮创建
      </div>
    </div>

    <!-- 知识库详情 -->
    <div v-else class="kb-detail-full">
      <div class="kb-detail-header">
        <div class="kb-detail-title">
          <h4>{{ kbStore.currentKb.name }}</h4>
          <span class="kb-badge" :class="kbStore.currentKb.kb_type">
            {{ kbStore.currentKb.kb_type === 'public' ? '公共' : '个人' }}
          </span>
        </div>
        <div class="kb-detail-actions">
          <button class="panel-btn small" @click="$emit('show-edit-dialog')">编辑</button>
          <button class="panel-btn small" @click="handleKbBack">返回</button>
        </div>
      </div>

      <div v-if="kbStore.currentKb.description" class="kb-detail-desc">{{ kbStore.currentKb.description }}</div>

      <div class="kb-detail-info">
        <span>分块策略: {{ getKbStrategyName(kbStore.currentKb.chunking_strategy) }}</span>
        <span>分块大小: {{ kbStore.currentKb.chunk_size }} 字符</span>
        <span>文档数: {{ kbStore.currentKb.document_count }}</span>
        <span>分块数: {{ kbStore.currentKb.chunk_count }}</span>
      </div>

      <!-- 文档上传 -->
      <div class="kb-upload-section">
        <div class="kb-section-title">上传文档</div>

        <!-- 分块策略选择 -->
        <div class="chunking-options">
          <div class="option-row">
            <div class="option-group">
              <label>分块策略</label>
              <select v-model="kbUploadOptions.chunking_strategy">
                <option value="llm">LLM智能分块（默认，质量最高）</option>
                <option value="sentence">句子分块（速度快）</option>
                <option value="semantic">语义分块（基于Embedding）</option>
                <option value="markdown">Markdown分块</option>
                <option value="hybrid">混合分块</option>
              </select>
            </div>
            <div class="option-group" v-if="kbUploadOptions.chunking_strategy === 'llm'">
              <label>LLM模式</label>
              <select v-model="kbUploadOptions.llm_mode">
                <option value="local">本地千问3（快速，25K字符阈值）</option>
                <option value="online">线上API（长文档，60K字符阈值）</option>
              </select>
            </div>
            <div class="option-group" v-if="kbUploadOptions.chunking_strategy !== 'llm'">
              <label>分块大小</label>
              <input type="number" v-model.number="kbUploadOptions.chunk_size" min="64" max="2048" />
            </div>
            <div class="option-group" v-if="kbUploadOptions.chunking_strategy !== 'llm' && kbUploadOptions.chunking_strategy !== 'markdown'">
              <label>分块重叠</label>
              <input type="number" v-model.number="kbUploadOptions.chunk_overlap" min="0" max="512" />
            </div>
          </div>
        </div>

        <div
          class="upload-area"
          :class="{ dragging: kbIsDragging, uploading: kbIsUploading }"
          @dragover.prevent="kbIsDragging = true"
          @dragleave="kbIsDragging = false"
          @drop.prevent="handleKbFileDrop"
          @click="triggerKbFileInput"
        >
          <input
            ref="kbFileInput"
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
            @change="handleKbFileSelect"
            style="display: none"
          />
          <div v-if="kbIsUploading" class="upload-progress">
            <div class="spinner"></div>
            <p>正在上传 {{ kbUploadProgress.current }}/{{ kbUploadProgress.total }}...</p>
            <p v-if="kbUploadOptions.chunking_strategy === 'llm'" class="upload-note">LLM分块处理中，请耐心等待...</p>
          </div>
          <div v-else>
            <p>点击或拖拽文件到此处上传</p>
            <p class="upload-hint">支持 PDF、Word、Excel、HTML、TXT、Markdown 等格式</p>
          </div>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="kb-documents-section">
        <div class="kb-section-title">文档列表 ({{ kbStore.documents.length }})</div>
        <div v-if="kbStore.documents.length === 0" class="kb-empty-docs">暂无文档</div>
        <div v-else class="kb-doc-list">
          <div
            v-for="doc in kbStore.documents"
            :key="doc.id"
            class="kb-doc-item"
            :class="{ clickable: doc.status === 'completed' }"
            @click="doc.status === 'completed' && $emit('view-chunks', doc)"
          >
            <div class="kb-doc-info">
              <span class="kb-doc-name">{{ doc.filename }}</span>
              <span class="kb-doc-meta">
                {{ formatFileSize(doc.file_size) }} |
                {{ doc.chunk_count }} 分块 |
                <span :class="'status-' + doc.status">{{ getKbStatusText(doc.status) }}</span>
                <span v-if="doc.status === 'completed'" class="view-hint">点击查看分段</span>
              </span>
            </div>
            <div class="kb-doc-actions" @click.stop>
              <button
                v-if="doc.status === 'failed'"
                class="kb-btn-text"
                @click="$emit('retry-doc', doc.id)"
              >
                重试
              </button>
              <button class="kb-btn-text danger" @click="$emit('delete-doc', doc.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'

const kbStore = useKnowledgeBaseStore()

// State
const kbUploadOptions = ref({
  chunking_strategy: 'llm',
  llm_mode: 'local',
  chunk_size: 512,
  chunk_overlap: 50
})

const kbIsDragging = ref(false)
const kbIsUploading = ref(false)
const kbUploadProgress = ref({ current: 0, total: 0 })
const kbFileInput = ref(null)

// Methods
const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const selectKb = (kb) => {
  kbStore.selectKb(kb.id)
}

const handleKbBack = () => {
  kbStore.clearCurrentKb()
}

const triggerKbFileInput = () => {
  kbFileInput.value?.click()
}

const handleKbFileSelect = async (event) => {
  const files = Array.from(event.target.files)
  if (files.length > 0) {
    await uploadDocuments(files)
  }
}

const handleKbFileDrop = async (event) => {
  kbIsDragging.value = false
  const files = Array.from(event.dataTransfer.files).filter(file => {
    const validTypes = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.html', '.htm', '.txt', '.md', '.csv', '.json']
    return validTypes.some(type => file.name.toLowerCase().endsWith(type))
  })

  if (files.length > 0) {
    await uploadDocuments(files)
  }
}

const uploadDocuments = async (files) => {
  kbIsUploading.value = true
  kbUploadProgress.value = { current: 0, total: files.length }

  try {
    for (let i = 0; i < files.length; i++) {
      kbUploadProgress.value.current = i + 1
      await kbStore.uploadDocument(files[i], kbUploadOptions.value)
    }
  } finally {
    kbIsUploading.value = false
    kbUploadProgress.value = { current: 0, total: 0 }
    if (kbFileInput.value) {
      kbFileInput.value.value = ''
    }
  }
}

const getKbStrategyName = (strategy) => {
  const names = {
    llm: 'LLM智能分块',
    sentence: '句子分块',
    semantic: '语义分块',
    markdown: 'Markdown分块',
    hybrid: '混合分块'
  }
  return names[strategy] || strategy
}

const getKbStatusText = (status) => {
  const statusMap = {
    pending: '等待中',
    processing: '处理中',
    completed: '已完成',
    failed: '失败'
  }
  return statusMap[status] || status
}

// Emit events
defineEmits(['show-create-dialog', 'show-edit-dialog', 'close', 'view-chunks', 'retry-doc', 'delete-doc'])
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.panel-actions {
  display: flex;
  gap: 10px;
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover {
  background: #1976d2;
  color: white;
}

.panel-btn.small {
  padding: 4px 8px;
  font-size: 12px;
}

.kb-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.kb-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.kb-section-title {
  font-weight: 600;
  color: #495057;
  margin-bottom: 12px;
  font-size: 14px;
}

.kb-item {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.kb-item:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.kb-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.kb-name {
  font-weight: 500;
  color: #212529;
}

.kb-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.kb-badge.public {
  background: #e3f2fd;
  color: #1976d2;
}

.kb-badge.private {
  background: #f3e5f5;
  color: #7b1fa2;
}

.kb-meta {
  font-size: 12px;
  color: #6c757d;
}

.kb-empty {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
  font-style: italic;
}

.kb-detail-full {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.kb-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.kb-detail-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kb-detail-title h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.kb-detail-actions {
  display: flex;
  gap: 8px;
}

.kb-detail-desc {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  color: #495057;
  font-size: 14px;
  line-height: 1.6;
}

.kb-detail-info {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  padding: 12px;
  background: #e3f2fd;
  border-radius: 6px;
  font-size: 13px;
  color: #1565c0;
}

.kb-upload-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.chunking-options {
  margin-bottom: 15px;
}

.option-row {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.option-group {
  flex: 1;
  min-width: 200px;
}

.option-group label {
  display: block;
  margin-bottom: 5px;
  font-size: 12px;
  font-weight: 500;
  color: #495057;
}

.option-group select,
.option-group input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 13px;
}

.upload-area {
  border: 2px dashed #ced4da;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.upload-area:hover,
.upload-area.dragging {
  border-color: #1976d2;
  background: #e3f2fd;
}

.upload-area.uploading {
  pointer-events: none;
  opacity: 0.7;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.spinner {
  width: 30px;
  height: 30px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #1976d2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.upload-area p {
  margin: 5px 0;
  color: #495057;
  font-size: 14px;
}

.upload-hint {
  font-size: 12px;
  color: #6c757d;
}

.upload-note {
  font-size: 12px;
  color: #ff9800;
  font-style: italic;
}

.kb-documents-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.kb-empty-docs {
  text-align: center;
  padding: 20px;
  color: #6c757d;
  font-style: italic;
}

.kb-doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kb-doc-item {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kb-doc-item.clickable {
  cursor: pointer;
}

.kb-doc-item.clickable:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.kb-doc-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kb-doc-name {
  font-weight: 500;
  color: #212529;
  font-size: 14px;
}

.kb-doc-meta {
  font-size: 12px;
  color: #6c757d;
}

.status-completed {
  color: #28a745;
  font-weight: 500;
}

.status-processing {
  color: #ffc107;
  font-weight: 500;
}

.status-failed {
  color: #dc3545;
  font-weight: 500;
}

.view-hint {
  color: #1976d2;
  font-size: 11px;
}

.kb-doc-actions {
  display: flex;
  gap: 8px;
}

.kb-btn-text {
  background: none;
  border: none;
  color: #1976d2;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.kb-btn-text:hover {
  background: #e3f2fd;
}

.kb-btn-text.danger {
  color: #dc3545;
}

.kb-btn-text.danger:hover {
  background: #f8d7da;
}
</style>