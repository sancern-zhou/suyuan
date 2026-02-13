<template>
  <div class="knowledge-base-view">
    <header class="page-header">
      <div class="header-left">
        <button class="btn-back" @click="goBack">
          <span class="back-icon">←</span>
          返回主页
        </button>
        <h1>知识库管理</h1>
        <span class="stats" v-if="stats">
          {{ stats.total_knowledge_bases }} 个知识库 / {{ stats.total_documents }} 个文档 / {{ stats.total_chunks }} 个分块
        </span>
      </div>
      <div class="header-actions">
        <button class="btn-secondary" @click="showSearchDialog = true">
          搜索测试
        </button>
        <button class="btn-primary" @click="showCreateDialog = true">
          + 新建知识库
        </button>
      </div>
    </header>

    <div class="main-content">
      <!-- 知识库列表 -->
      <div class="kb-list-panel">
        <div class="panel-header">
          <span>知识库列表</span>
          <button class="btn-text" @click="refreshList">刷新</button>
        </div>

        <div v-if="loading" class="loading-state">加载中...</div>

        <div v-else class="kb-sections">
          <!-- 公共知识库 -->
          <div class="kb-section" v-if="publicKbs.length > 0">
            <div class="section-title">公共知识库</div>
            <div
              v-for="kb in publicKbs"
              :key="kb.id"
              class="kb-card"
              :class="{ active: currentKb?.id === kb.id }"
              @click="selectKb(kb)"
            >
              <div class="kb-card-header">
                <span class="kb-name">{{ kb.name }}</span>
                <span class="kb-badge public">公共</span>
              </div>
              <div class="kb-card-meta">
                {{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块
              </div>
            </div>
          </div>

          <!-- 个人知识库 -->
          <div class="kb-section" v-if="privateKbs.length > 0">
            <div class="section-title">我的知识库</div>
            <div
              v-for="kb in privateKbs"
              :key="kb.id"
              class="kb-card"
              :class="{ active: currentKb?.id === kb.id }"
              @click="selectKb(kb)"
            >
              <div class="kb-card-header">
                <span class="kb-name">{{ kb.name }}</span>
                <span class="kb-badge private">个人</span>
              </div>
              <div class="kb-card-meta">
                {{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块
              </div>
            </div>
          </div>

          <div v-if="publicKbs.length === 0 && privateKbs.length === 0" class="empty-state">
            暂无知识库，点击上方按钮创建
          </div>
        </div>
      </div>

      <!-- 知识库详情 -->
      <div class="kb-detail-panel" v-if="currentKb">
        <div class="panel-header">
          <div class="detail-title">
            <h2>{{ currentKb.name }}</h2>
            <span class="kb-badge" :class="currentKb.kb_type">
              {{ currentKb.kb_type === 'public' ? '公共' : '个人' }}
            </span>
          </div>
          <div class="detail-actions">
            <button class="btn-secondary" @click="showEditDialog = true">编辑</button>
            <button class="btn-danger" @click="handleDelete">删除</button>
          </div>
        </div>

        <div class="kb-info">
          <p v-if="currentKb.description" class="kb-description">{{ currentKb.description }}</p>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">分块策略</span>
              <span class="info-value">{{ getStrategyName(currentKb.chunking_strategy) }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">分块大小</span>
              <span class="info-value">{{ currentKb.chunk_size }} 字符</span>
            </div>
            <div class="info-item">
              <span class="info-label">文档数</span>
              <span class="info-value">{{ currentKb.document_count }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">分块数</span>
              <span class="info-value">{{ currentKb.chunk_count }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">总大小</span>
              <span class="info-value">{{ formatFileSize(currentKb.total_size) }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">创建时间</span>
              <span class="info-value">{{ formatDate(currentKb.created_at) }}</span>
            </div>
          </div>
        </div>

        <!-- 文档上传 -->
        <div class="upload-section">
          <div class="section-title">上传文档</div>
          
          <!-- 分块策略选择 -->
          <div class="chunking-options">
            <div class="option-row">
              <div class="option-group">
                <label>分块策略</label>
                <select v-model="uploadOptions.chunking_strategy">
                  <option value="llm">LLM智能分块（默认，质量最高）</option>
                  <option value="sentence">句子分块（速度快）</option>
                  <option value="semantic">语义分块（基于Embedding）</option>
                  <option value="markdown">Markdown分块</option>
                  <option value="hybrid">混合分块</option>
                </select>
              </div>
              <div class="option-group" v-if="uploadOptions.chunking_strategy === 'llm'">
                <label>LLM模式</label>
                <select v-model="uploadOptions.llm_mode">
                  <option value="local">本地千问3（快速，25K字符阈值）</option>
                  <option value="online">线上API（长文档，60K字符阈值）</option>
                </select>
              </div>
              <div class="option-group" v-if="uploadOptions.chunking_strategy !== 'llm'">
                <label>分块大小</label>
                <input type="number" v-model.number="uploadOptions.chunk_size" min="64" max="2048" />
              </div>
              <div class="option-group" v-if="uploadOptions.chunking_strategy !== 'llm' && uploadOptions.chunking_strategy !== 'markdown'">
                <label>分块重叠</label>
                <input type="number" v-model.number="uploadOptions.chunk_overlap" min="0" max="512" />
              </div>
            </div>
            <p class="strategy-hint">{{ getChunkingStrategyHint(uploadOptions.chunking_strategy, uploadOptions.llm_mode) }}</p>
          </div>

          <div
            class="upload-area"
            :class="{ dragging: isDragging, uploading: isUploading }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
            @click="triggerFileInput"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
              @change="handleFileSelect"
              style="display: none"
            />
            <div v-if="isUploading" class="upload-progress">
              <div class="spinner"></div>
              <p>正在上传 {{ uploadProgress.current }}/{{ uploadProgress.total }}...</p>
              <p v-if="uploadOptions.chunking_strategy === 'llm'" class="upload-note">LLM分块处理中，请耐心等待...</p>
            </div>
            <div v-else>
              <p>点击或拖拽文件到此处上传</p>
              <p class="upload-hint">支持 PDF、Word、Excel、HTML、TXT、Markdown 等格式</p>
            </div>
          </div>
        </div>

        <!-- 文档列表 -->
        <div class="documents-section">
          <div class="section-title">文档列表 ({{ documents.length }})</div>
          <div v-if="documents.length === 0" class="empty-docs">暂无文档</div>
          <div v-else class="doc-list">
            <div
              v-for="doc in documents"
              :key="doc.id"
              class="doc-item"
              :class="{ clickable: doc.status === 'completed' }"
              @click="doc.status === 'completed' && viewChunks(doc)"
            >
              <div class="doc-info">
                <span class="doc-name">{{ doc.filename }}</span>
                <span class="doc-meta">
                  {{ formatFileSize(doc.file_size) }} |
                  {{ doc.chunk_count }} 分块 |
                  <span :class="'status-' + doc.status">{{ getStatusText(doc.status) }}</span>
                  <span v-if="doc.status === 'completed'" class="view-hint">点击查看分段</span>
                </span>
              </div>
              <div class="doc-actions" @click.stop>
                <button
                  v-if="doc.status === 'failed'"
                  class="btn-text"
                  @click="handleRetry(doc.id)"
                >
                  重试
                </button>
                <button class="btn-text danger" @click="handleDeleteDoc(doc.id)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="no-selection">
        <p>请从左侧选择一个知识库</p>
      </div>
    </div>

    <!-- 创建知识库对话框 -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>新建知识库</h3>
          <button class="btn-close" @click="showCreateDialog = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="createForm.name" type="text" placeholder="输入知识库名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="createForm.description" placeholder="输入知识库描述"></textarea>
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="createForm.kb_type">
              <option value="private">个人知识库</option>
              <option value="public">公共知识库</option>
            </select>
          </div>
          <div
            class="form-group warning"
            v-if="createForm.kb_type === 'public'"
          >
            <label>公共知识库权限</label>
            <label class="checkbox-inline">
              <input type="checkbox" v-model="adminConfirm" />
              以管理员身份创建（自动携带 X-Is-Admin: true）
            </label>
            <p class="form-hint danger">
              提醒：公共知识库必须以管理员身份创建，否则会返回 403。
            </p>
          </div>
          <div class="form-group">
            <label>分块策略</label>
            <select v-model="createForm.chunking_strategy">
              <option value="llm">LLM智能分块（推荐）</option>
              <option value="sentence">句子分块</option>
              <option value="semantic">语义分块</option>
              <option value="markdown">Markdown分块</option>
              <option value="hybrid">混合分块</option>
            </select>
            <p class="form-hint">{{ getStrategyDesc(createForm.chunking_strategy) }}</p>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>分块大小</label>
              <input v-model.number="createForm.chunk_size" type="number" min="64" max="2048" />
            </div>
            <div class="form-group">
              <label>分块重叠</label>
              <input v-model.number="createForm.chunk_overlap" type="number" min="0" max="512" />
            </div>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showCreateDialog = false">取消</button>
          <button class="btn-primary" @click="handleCreate" :disabled="!createForm.name">创建</button>
        </div>
      </div>
    </div>

    <!-- 编辑知识库对话框 -->
    <div v-if="showEditDialog" class="dialog-overlay" @click.self="showEditDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>编辑知识库</h3>
          <button class="btn-close" @click="showEditDialog = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="editForm.name" type="text" placeholder="输入知识库名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="editForm.description" placeholder="输入知识库描述"></textarea>
          </div>
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="editForm.is_default" />
              设为默认知识库
            </label>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showEditDialog = false">取消</button>
          <button class="btn-primary" @click="handleUpdate" :disabled="!editForm.name">保存</button>
        </div>
      </div>
    </div>

    <!-- 分段查看全屏页面 -->
    <div v-if="showChunksDialog" class="chunks-fullscreen">
      <div class="chunks-header">
        <div class="chunks-title">
          <button class="btn-back" @click="closeChunksDialog">← 返回</button>
          <h2>{{ currentDoc?.filename }}</h2>
          <span class="chunks-count">共 {{ documentChunks.length }} 个分块</span>
        </div>
        <div class="chunks-actions">
          <button class="btn-secondary" @click="closeChunksDialog">关闭</button>
        </div>
      </div>
      <div class="chunks-content">
        <div class="chunks-list-full">
          <div v-for="(chunk, index) in documentChunks" :key="index" class="chunk-card">
            <div class="chunk-card-header">
              <span class="chunk-number">分块 #{{ chunk.chunk_index + 1 }}</span>
              <span class="chunk-length">{{ chunk.content.length }} 字符</span>
              <span class="chunk-position" v-if="chunk.start_char !== null">
                位置: {{ chunk.start_char }} - {{ chunk.end_char }}
              </span>
            </div>
            <!-- 元数据展示 -->
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
                <span class="metadata-value type-tag" :class="'type-' + chunk.metadata.type">{{ getChunkTypeName(chunk.metadata.type) }}</span>
              </div>
              <div class="metadata-row" v-if="chunk.metadata.chunking_method">
                <span class="metadata-label">分块方法:</span>
                <span class="metadata-value">{{ chunk.metadata.chunking_method }}</span>
              </div>
              <div class="metadata-row" v-if="chunk.metadata.doc_context?.title">
                <span class="metadata-label">文档标题:</span>
                <span class="metadata-value">{{ chunk.metadata.doc_context.title }}</span>
              </div>
              <div class="metadata-row" v-if="chunk.metadata.doc_context?.doc_type">
                <span class="metadata-label">文档类型:</span>
                <span class="metadata-value">{{ chunk.metadata.doc_context.doc_type }}</span>
              </div>
            </div>
            <div class="chunk-card-body">{{ chunk.content }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 搜索测试对话框 -->
    <div v-if="showSearchDialog" class="dialog-overlay" @click.self="showSearchDialog = false">
      <div class="dialog dialog-wide">
        <div class="dialog-header">
          <h3>知识库搜索测试</h3>
          <button class="btn-close" @click="showSearchDialog = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="search-form">
            <div class="form-group">
              <label>搜索查询</label>
              <textarea
                v-model="searchForm.query"
                placeholder="输入搜索内容..."
                rows="2"
              ></textarea>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>返回数量</label>
                <input v-model.number="searchForm.top_k" type="number" min="1" max="20" />
              </div>
              <div class="form-group">
                <label>相似度阈值</label>
                <input v-model.number="searchForm.score_threshold" type="number" step="0.1" min="0" max="1" />
              </div>
              <div class="form-group">
                <label>
                  <input type="checkbox" v-model="searchForm.use_reranker" />
                  精准检索
                </label>
              </div>
            </div>
            <button class="btn-primary" @click="handleSearch" :disabled="!searchForm.query || searching">
              {{ searching ? '搜索中...' : '搜索' }}
            </button>
          </div>

          <div v-if="searchResults.length > 0" class="search-results">
            <div class="results-header">
              搜索结果 ({{ searchResults.length }}) - 耗时 {{ searchElapsed }}ms
            </div>
            <div v-for="(result, index) in searchResults" :key="index" class="result-item">
              <div class="result-header">
                <span class="result-rank">#{{ index + 1 }}</span>
                <span class="result-filename">{{ result.filename }}</span>
                <span class="result-score">相似度: {{ (result.score * 100).toFixed(1) }}%</span>
                <span class="result-kb">{{ result.knowledge_base?.name }}</span>
              </div>
              <div class="result-content">{{ result.content }}</div>
            </div>
          </div>

          <div v-else-if="searchPerformed && searchResults.length === 0" class="no-results">
            未找到匹配结果
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showSearchDialog = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { searchKnowledgeBase } from '@/api/knowledgeBase'

const store = useKnowledgeBaseStore()
const router = useRouter()

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showChunksDialog = ref(false)
const showSearchDialog = ref(false)
const isDragging = ref(false)
const isUploading = ref(false)
const uploadProgress = ref({ current: 0, total: 0 })
const fileInput = ref(null)

const createForm = ref({
  name: '',
  description: '',
  kb_type: 'private',
  chunking_strategy: 'llm',
  chunk_size: 800,
  chunk_overlap: 100
})
const adminConfirm = ref(localStorage.getItem('isAdmin') === 'true')

const editForm = ref({
  name: '',
  description: '',
  is_default: false
})

const searchForm = ref({
  query: '',
  top_k: 5,
  score_threshold: 0.5,
  use_reranker: true
})

const uploadOptions = ref({
  chunking_strategy: 'llm',
  chunk_size: 800,
  chunk_overlap: 100,
  llm_mode: 'local'  // 默认本地LLM
})

const searching = ref(false)
const searchResults = ref([])
const searchElapsed = ref(0)
const searchPerformed = ref(false)

const loading = computed(() => store.loading)
const publicKbs = computed(() => store.publicKbs)
const privateKbs = computed(() => store.privateKbs)
const currentKb = computed(() => store.currentKb)
const documents = computed(() => store.documents)
const stats = computed(() => store.stats)
const currentDoc = computed(() => store.currentDoc)
const documentChunks = computed(() => store.documentChunks)

onMounted(async () => {
  await store.fetchKnowledgeBases()
  await store.fetchStats()
})

watch(() => currentKb.value, (kb) => {
  if (kb) {
    editForm.value = {
      name: kb.name,
      description: kb.description || '',
      is_default: kb.is_default
    }
  }
})

const refreshList = async () => {
  await store.fetchKnowledgeBases()
  await store.fetchStats()
}

const selectKb = (kb) => {
  store.selectKnowledgeBase(kb)
}

const handleCreate = async () => {
  if (!createForm.value.name) return

  // 公共知识库需要管理员确认，否则后端会返回403
  if (createForm.value.kb_type === 'public' && !adminConfirm.value) {
    alert('创建公共知识库需要管理员权限，请勾选确认。')
    return
  }

  try {
    // 同步管理员标识到 localStorage，供 API 请求头使用
    if (createForm.value.kb_type === 'public' && adminConfirm.value) {
      localStorage.setItem('isAdmin', 'true')
    } else if (!adminConfirm.value) {
      localStorage.removeItem('isAdmin')
    }

    await store.createKnowledgeBase(createForm.value)
    showCreateDialog.value = false
    createForm.value = {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: 800,
      chunk_overlap: 100
    }
    adminConfirm.value = localStorage.getItem('isAdmin') === 'true'
    await store.fetchStats()
  } catch (e) {
    alert('创建失败: ' + e.message)
  }
}

const handleUpdate = async () => {
  if (!currentKb.value || !editForm.value.name) return

  try {
    await store.updateKnowledgeBase(currentKb.value.id, editForm.value)
    showEditDialog.value = false
  } catch (e) {
    alert('更新失败: ' + e.message)
  }
}

const handleDelete = async () => {
  if (!currentKb.value) return
  if (!confirm(`确定要删除知识库"${currentKb.value.name}"吗？此操作不可恢复。`)) return

  try {
    await store.deleteKnowledgeBase(currentKb.value.id)
    await store.fetchStats()
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

const triggerFileInput = () => {
  if (!isUploading.value) {
    fileInput.value?.click()
  }
}

const handleFileSelect = async (event) => {
  const files = event.target.files
  if (files && files.length > 0) {
    await uploadFiles(Array.from(files))
  }
  event.target.value = ''
}

const handleDrop = async (event) => {
  isDragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    await uploadFiles(Array.from(files))
  }
}

const uploadFiles = async (files) => {
  if (!currentKb.value || isUploading.value) return

  isUploading.value = true
  uploadProgress.value = { current: 0, total: files.length }

  for (const file of files) {
    try {
      uploadProgress.value.current++
      await store.uploadDocument(currentKb.value.id, file, {
        chunking_strategy: uploadOptions.value.chunking_strategy,
        chunk_size: uploadOptions.value.chunk_size,
        chunk_overlap: uploadOptions.value.chunk_overlap,
        llm_mode: uploadOptions.value.llm_mode
      })
    } catch (e) {
      alert(`上传"${file.name}"失败: ${e.message}`)
    }
  }

  isUploading.value = false
  await store.fetchStats()
}

const handleDeleteDoc = async (docId) => {
  if (!currentKb.value) return
  if (!confirm('确定要删除此文档吗？')) return

  try {
    await store.deleteDocument(currentKb.value.id, docId)
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

const handleRetry = async (docId) => {
  if (!currentKb.value) return
  try {
    await store.retryDocument(currentKb.value.id, docId)
  } catch (e) {
    alert('重试失败: ' + e.message)
  }
}

const viewChunks = async (doc) => {
  if (!currentKb.value) return
  try {
    await store.fetchDocumentChunks(currentKb.value.id, doc.id)
    showChunksDialog.value = true
  } catch (e) {
    alert('获取分段失败: ' + e.message)
  }
}

const closeChunksDialog = () => {
  showChunksDialog.value = false
  store.clearCurrentDoc()
}

const handleSearch = async () => {
  if (!searchForm.value.query) return

  searching.value = true
  searchPerformed.value = true

  try {
    const result = await searchKnowledgeBase({
      query: searchForm.value.query,
      top_k: searchForm.value.top_k,
      score_threshold: searchForm.value.score_threshold,
      use_reranker: searchForm.value.use_reranker
    })
    searchResults.value = result.results || []
    searchElapsed.value = result.elapsed_ms || 0
  } catch (e) {
    alert('搜索失败: ' + e.message)
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

const goBack = () => {
  router.push('/')
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getStatusText = (status) => {
  const map = {
    pending: '等待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '处理失败'
  }
  return map[status] || status
}

const getStrategyName = (strategy) => {
  const map = {
    sentence: '句子分块',
    semantic: '语义分块',
    markdown: 'Markdown分块',
    hybrid: '混合分块',
    llm: 'LLM智能分块'
  }
  return map[strategy] || strategy
}

const getStrategyDesc = (strategy) => {
  const map = {
    sentence: '按句子边界分割，适合大多数文档',
    semantic: '基于语义相似度分割，适合技术文档',
    markdown: '按Markdown标题层级分割，适合Markdown文档',
    hybrid: '多层级混合分割，适合长文档',
    llm: '使用大语言模型进行智能分割，质量最高但较慢'
  }
  return map[strategy] || ''
}

const getChunkTypeName = (type) => {
  const map = {
    paragraph: '正文',
    table: '表格',
    list: '列表',
    header: '标题',
    code: '代码'
  }
  return map[type] || type
}

const getChunkingStrategyHint = (strategy, llmMode = 'local') => {
  if (strategy === 'llm') {
    if (llmMode === 'online') {
      return '使用线上API(DeepSeek等)进行智能分块。60K字符分段阈值，适合超长文档。每段附带主题标签和上下文前缀，质量最高。'
    }
    return '使用本地千问3进行智能分块。25K字符分段阈值，速度快，无额外成本。每段附带主题标签和上下文前缀，推荐用于环保政策和技术规范。'
  }
  const hints = {
    sentence: '速度快，适合通用文档。按句子边界分割，简单可靠。',
    semantic: '基于Embedding模型判断语义边界，分块更连贯，适合技术文档和论文。',
    markdown: '按Markdown标题层级分割，保持文档结构，仅适合MD格式文件。',
    hybrid: '多层级混合分割（1024/256/64字符），适合长篇报告和规范文档。'
  }
  return hints[strategy] || ''
}
</script>

<style scoped>
.knowledge-base-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6fb;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #333;
  transition: all 0.2s;
}

.btn-back:hover {
  background: #e6f7ff;
  border-color: #1890ff;
  color: #1890ff;
}

.back-icon {
  font-size: 14px;
}

.header-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.stats {
  font-size: 13px;
  color: #666;
  margin-left: 16px;
}

.btn-primary {
  background: #1890ff;
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-primary:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #333;
  border: 1px solid #d9d9d9;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: #40a9ff;
  color: #40a9ff;
}

.btn-danger {
  background: #ff4d4f;
  color: #fff;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.btn-text {
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.btn-text:hover {
  background: #f0f7ff;
  border-radius: 4px;
}

.btn-text.danger {
  color: #ff4d4f;
}

.btn-text.danger:hover {
  background: #fff1f0;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.kb-list-panel {
  width: 300px;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kb-detail-panel {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  overflow-y: auto;
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 500;
}

.kb-sections {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.kb-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 13px;
  color: #666;
  padding: 8px;
  font-weight: 500;
}

.kb-card {
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.kb-card:hover {
  border-color: #1890ff;
}

.kb-card.active {
  border-color: #1890ff;
  background: #e6f7ff;
}

.kb-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.kb-name {
  font-weight: 500;
  font-size: 14px;
}

.kb-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.kb-badge.public {
  background: #e6f7ff;
  color: #1890ff;
}

.kb-badge.private {
  background: #f6ffed;
  color: #52c41a;
}

.kb-card-meta {
  font-size: 12px;
  color: #999;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title h2 {
  margin: 0;
  font-size: 18px;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.kb-info {
  margin-bottom: 24px;
}

.kb-description {
  color: #666;
  margin-bottom: 16px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  color: #999;
}

.info-value {
  font-size: 14px;
  font-weight: 500;
}

.upload-section {
  margin-bottom: 24px;
}

.chunking-options {
  margin-bottom: 16px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.option-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 180px;
}

.option-group label {
  font-size: 13px;
  font-weight: 500;
  color: #333;
}

.option-group select,
.option-group input[type="number"] {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
}

.option-group select:focus,
.option-group input[type="number"]:focus {
  border-color: #1890ff;
  outline: none;
}

.strategy-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}

.upload-note {
  font-size: 12px;
  color: #faad14;
  margin-top: 8px;
}

.upload-area {
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-area:hover,
.upload-area.dragging {
  border-color: #1890ff;
  background: #f0f7ff;
}

.upload-area.uploading {
  cursor: not-allowed;
  background: #fafafa;
}

.upload-hint {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.doc-list {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
}

.doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.doc-item.clickable {
  cursor: pointer;
}

.doc-item.clickable:hover {
  background: #f5f7fa;
}

.doc-item:last-child {
  border-bottom: none;
}

.view-hint {
  color: #1890ff;
  margin-left: 8px;
  font-size: 11px;
}

.doc-info {
  flex: 1;
}

.doc-name {
  font-weight: 500;
  font-size: 14px;
  display: block;
}

.doc-meta {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.doc-actions {
  display: flex;
  gap: 4px;
}

.status-completed {
  color: #52c41a;
}

.status-processing {
  color: #1890ff;
}

.status-failed {
  color: #ff4d4f;
}

.status-pending {
  color: #faad14;
}

.no-selection,
.empty-state,
.empty-docs,
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #999;
  font-size: 14px;
}

.no-selection {
  flex: 1;
  background: #fff;
  border-radius: 8px;
}

/* Dialog */
.dialog-overlay {
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
}

.dialog {
  background: #fff;
  border-radius: 8px;
  width: 480px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dialog-wide {
  width: 800px;
  max-width: 90vw;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  line-height: 1;
}

.btn-close:hover {
  color: #333;
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #f0f0f0;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
}

.form-group input[type="checkbox"] {
  margin-right: 8px;
}

.form-group textarea {
  min-height: 80px;
  resize: vertical;
}

.form-hint {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row .form-group {
  flex: 1;
}

/* Chunks Fullscreen Page */
.chunks-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #f5f6fb;
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

.chunks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
}

.chunks-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.chunks-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.chunks-count {
  font-size: 14px;
  color: #666;
  background: #f0f0f0;
  padding: 4px 12px;
  border-radius: 12px;
}

.btn-back {
  background: none;
  border: 1px solid #d9d9d9;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
}

.btn-back:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.chunks-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.chunks-list-full {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chunk-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.chunk-card-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

.chunk-number {
  font-weight: 600;
  color: #1890ff;
  font-size: 14px;
}

.chunk-length {
  font-size: 13px;
  color: #666;
}

.chunk-position {
  font-size: 12px;
  color: #999;
  margin-left: auto;
}

.chunk-metadata {
  padding: 12px 20px;
  background: #f0f7ff;
  border-bottom: 1px solid #e6f0fa;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.metadata-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.metadata-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.metadata-value {
  font-size: 13px;
  color: #1890ff;
}

.type-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.type-paragraph {
  background: #e6f7ff;
  color: #1890ff;
}

.type-table {
  background: #f6ffed;
  color: #52c41a;
}

.type-list {
  background: #fff7e6;
  color: #fa8c16;
}

.chunk-card-body {
  padding: 20px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
}

/* Search Dialog */
.search-form {
  margin-bottom: 24px;
}

.search-form .btn-primary {
  margin-top: 8px;
}

.search-results {
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
}

.results-header {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 12px;
  color: #333;
}

.result-item {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  font-size: 13px;
}

.result-rank {
  font-weight: 600;
  color: #1890ff;
}

.result-filename {
  font-weight: 500;
}

.result-score {
  color: #52c41a;
}

.result-kb {
  color: #999;
  margin-left: auto;
}

.result-content {
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}

.no-results {
  text-align: center;
  padding: 40px;
  color: #999;
}
</style>
