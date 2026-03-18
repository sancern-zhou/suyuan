<template>
  <div class="tools-management-view">
    <header class="page-header">
      <div class="header-left">
        <button class="btn-back" @click="goBack">
          <span class="back-icon">←</span>
          返回主页
        </button>
        <h1>工具/技能管理</h1>
        <span class="stats" v-if="stats">
          共 {{ stats.total }} 个工具 / {{ stats.enabled }} 已启用 / {{ stats.disabled }} 已禁用
        </span>
      </div>
      <div class="header-actions">
        <button class="btn-secondary" @click="refreshList">刷新</button>
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索工具..."
            @input="filterTools"
          />
        </div>
      </div>
    </header>

    <div class="main-content">
      <!-- 工具分类列表 -->
      <div class="category-list-panel">
        <div class="panel-header">
          <span>工具分类</span>
        </div>

        <div v-if="loading" class="loading-state">加载中...</div>

        <div v-else class="categories">
          <div
            v-for="category in filteredCategories"
            :key="category.id"
            class="category-card"
            :class="{ active: selectedCategory === category.id }"
            @click="selectCategory(category.id)"
          >
            <div class="category-card-header">
              <span class="category-name">{{ category.name }}</span>
              <span class="category-count">{{ category.count }}</span>
            </div>
            <div class="category-desc">{{ category.description }}</div>
          </div>
        </div>
      </div>

      <!-- 工具列表 -->
      <div class="tools-list-panel" v-if="selectedCategory">
        <div class="panel-header">
          <h2>{{ getCategoryName(selectedCategory) }}</h2>
        </div>

        <div v-if="filteredTools.length === 0" class="empty-state">
          未找到工具
        </div>

        <div v-else class="tools-list">
          <div
            v-for="tool in filteredTools"
            :key="tool.name"
            class="tool-card"
            :class="{ disabled: tool.status === 'disabled' }"
          >
            <div class="tool-card-header">
              <span class="tool-name">{{ tool.name }}</span>
              <span
                class="tool-badge"
                :class="tool.status"
              >
                {{ tool.status === 'enabled' ? '已启用' : '已禁用' }}
              </span>
            </div>
            <div class="tool-desc">{{ tool.description }}</div>
            <div class="tool-meta">
              <span class="tool-category">{{ getCategoryLabel(tool.category) }}</span>
              <span class="tool-version">v{{ tool.version }}</span>
              <span class="tool-calls">调用: {{ tool.statistics.total }}</span>
              <span class="tool-success-rate">
                成功率: {{ getSuccessRate(tool.statistics) }}%
              </span>
            </div>
            <div class="tool-actions">
              <button
                class="btn-toggle"
                :class="{ enabled: tool.status === 'enabled' }"
                @click="toggleToolStatus(tool)"
              >
                {{ tool.status === 'enabled' ? '禁用' : '启用' }}
              </button>
              <button
                class="btn-text"
                @click="viewToolDetail(tool)"
              >
                查看详情
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="no-selection">
        <p>请从左侧选择一个工具分类</p>
      </div>
    </div>

    <!-- 工具详情对话框 -->
    <div v-if="showDetailDialog" class="dialog-overlay" @click.self="showDetailDialog = false">
      <div class="dialog dialog-wide">
        <div class="dialog-header">
          <h3>工具详情</h3>
          <button class="btn-close" @click="showDetailDialog = false">×</button>
        </div>
        <div class="dialog-body" v-if="currentTool">
          <div class="tool-detail-section">
            <h4>基本信息</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">工具名称</span>
                <span class="info-value">{{ currentTool.name }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">描述</span>
                <span class="info-value">{{ currentTool.description }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">类别</span>
                <span class="info-value">{{ getCategoryLabel(currentTool.category) }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">版本</span>
                <span class="info-value">{{ currentTool.version }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">状态</span>
                <span class="info-value" :class="currentTool.status">
                  {{ currentTool.status === 'enabled' ? '已启用' : '已禁用' }}
                </span>
              </div>
              <div class="info-item">
                <span class="info-label">优先级</span>
                <span class="info-value">{{ currentTool.priority }}</span>
              </div>
            </div>
          </div>

          <div class="tool-detail-section">
            <h4>元数据</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">数据类型</span>
                <span class="info-value">{{ currentTool.metadata.data_type }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">支持批量</span>
                <span class="info-value">{{ currentTool.metadata.supports_batch ? '是' : '否' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">需要句柄</span>
                <span class="info-value">{{ currentTool.metadata.requires_handle ? '是' : '否' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">需要上下文</span>
                <span class="info-value">{{ currentTool.requires_context ? '是' : '否' }}</span>
              </div>
            </div>
          </div>

          <div class="tool-detail-section">
            <h4>统计信息</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">总调用次数</span>
                <span class="info-value">{{ currentTool.statistics.total }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">成功次数</span>
                <span class="info-value">{{ currentTool.statistics.success }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">失败次数</span>
                <span class="info-value">{{ currentTool.statistics.failed }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">成功率</span>
                <span class="info-value">{{ getSuccessRate(currentTool.statistics) }}%</span>
              </div>
              <div class="info-item">
                <span class="info-label">平均执行时间</span>
                <span class="info-value">{{ currentTool.statistics.avg_execution_time.toFixed(2) }}s</span>
              </div>
            </div>
          </div>

          <div class="tool-detail-section" v-if="currentTool.function_schema">
            <h4>函数定义</h4>
            <div class="code-block">
              <pre>{{ JSON.stringify(currentTool.function_schema, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showDetailDialog = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getToolsList, updateToolStatus } from '@/api/toolsManagement'

const router = useRouter()

const loading = ref(false)
const tools = ref([])
const categories = ref([])
const selectedCategory = ref(null)
const searchQuery = ref('')
const showDetailDialog = ref(false)
const currentTool = ref(null)

const categoryMap = {
  'query': {
    id: 'query',
    name: '数据查询',
    description: '从数据库查询各类环境数据'
  },
  'analysis': {
    id: 'analysis',
    name: '数据分析',
    description: '执行PMF、OBM等分析计算'
  },
  'visualization': {
    id: 'visualization',
    name: '数据可视化',
    description: '生成图表和可视化配置'
  },
  'task_management': {
    id: 'task_management',
    name: '任务管理',
    description: '管理任务清单和状态'
  }
}

const stats = computed(() => {
  const total = tools.value.length
  const enabled = tools.value.filter(t => t.status === 'enabled').length
  const disabled = total - enabled
  return { total, enabled, disabled }
})

const filteredCategories = computed(() => {
  const search = searchQuery.value.toLowerCase().trim()
  if (!search) return categories.value

  return categories.value.map(cat => {
    const catTools = tools.value.filter(t => t.category === cat.id)
    const filteredTools = catTools.filter(t =>
      t.name.toLowerCase().includes(search) ||
      t.description.toLowerCase().includes(search)
    )
    return {
      ...cat,
      count: filteredTools.length
    }
  }).filter(cat => cat.count > 0)
})

const filteredTools = computed(() => {
  if (!selectedCategory.value) return []

  const search = searchQuery.value.toLowerCase().trim()
  const catTools = tools.value.filter(t => t.category === selectedCategory.value)

  if (!search) return catTools

  return catTools.filter(t =>
    t.name.toLowerCase().includes(search) ||
    t.description.toLowerCase().includes(search)
  )
})

onMounted(async () => {
  await fetchTools()
})

const fetchTools = async () => {
  loading.value = true
  try {
    const response = await getToolsList()
    tools.value = response.tools || []

    // 计算分类统计
    const categoryCounts = {}
    tools.value.forEach(tool => {
      const cat = tool.category
      categoryCounts[cat] = (categoryCounts[cat] || 0) + 1
    })

    // 生成分类列表
    categories.value = Object.keys(categoryMap).map(catId => {
      return {
        ...categoryMap[catId],
        count: categoryCounts[catId] || 0
      }
    }).filter(cat => cat.count > 0)

    // 默认选择第一个分类
    if (categories.value.length > 0 && !selectedCategory.value) {
      selectedCategory.value = categories.value[0].id
    }
  } catch (e) {
    alert('获取工具列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const refreshList = async () => {
  await fetchTools()
}

const selectCategory = (categoryId) => {
  selectedCategory.value = categoryId
}

const filterTools = () => {
  // 触发计算属性重新计算
}

const getCategoryName = (categoryId) => {
  return categoryMap[categoryId]?.name || categoryId
}

const getCategoryLabel = (categoryId) => {
  const cat = categoryMap[categoryId]
  return cat ? cat.name : categoryId
}

const getSuccessRate = (statistics) => {
  const { total, success } = statistics
  if (total === 0) return 0
  return ((success / total) * 100).toFixed(1)
}

const toggleToolStatus = async (tool) => {
  const newStatus = tool.status === 'enabled' ? false : true
  const action = newStatus ? '启用' : '禁用'

  if (!confirm(`确定要${action}工具"${tool.name}"吗？`)) return

  try {
    await updateToolStatus(tool.name, newStatus)

    // 更新本地状态
    tool.status = newStatus ? 'enabled' : 'disabled'
  } catch (e) {
    alert(`${action}工具失败: ${e.message}`)
  }
}

const viewToolDetail = async (tool) => {
  currentTool.value = tool
  showDetailDialog.value = true
}

const goBack = () => {
  router.push('/')
}
</script>

<style scoped>
.tools-management-view {
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
  align-items: center;
}

.stats {
  font-size: 13px;
  color: #666;
  margin-left: 16px;
}

.search-box {
  display: flex;
  align-items: center;
}

.search-box input {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  width: 250px;
}

.search-box input:focus {
  border-color: #1890ff;
  outline: none;
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

.btn-toggle {
  padding: 6px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #666;
  background: #fff;
}

.btn-toggle:hover {
  border-color: #1890ff;
}

.btn-toggle.enabled {
  background: #e6f7ff;
  border-color: #1890ff;
  color: #1890ff;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.category-list-panel {
  width: 260px;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tools-list-panel {
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

.panel-header h2 {
  margin: 0;
  font-size: 16px;
}

.categories {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.category-card {
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.category-card:hover {
  border-color: #1890ff;
}

.category-card.active {
  border-color: #1890ff;
  background: #e6f7ff;
}

.category-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.category-name {
  font-weight: 500;
  font-size: 14px;
}

.category-count {
  font-size: 12px;
  color: #999;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 10px;
}

.category-desc {
  font-size: 12px;
  color: #999;
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.tool-card:hover {
  border-color: #1890ff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.tool-card.disabled {
  opacity: 0.6;
  background: #fafafa;
}

.tool-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.tool-name {
  font-weight: 600;
  font-size: 15px;
  color: #333;
}

.tool-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.tool-badge.enabled {
  background: #e6f7ff;
  color: #1890ff;
}

.tool-badge.disabled {
  background: #f0f0f0;
  color: #999;
}

.tool-desc {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
  line-height: 1.5;
}

.tool-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 12px;
  color: #999;
}

.tool-category,
.tool-version,
.tool-calls,
.tool-success-rate {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
}

.tool-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.no-selection,
.empty-state,
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
  width: 600px;
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

.tool-detail-section {
  margin-bottom: 24px;
}

.tool-detail-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #333;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8e8e8;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
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
  color: #333;
}

.info-value.enabled {
  color: #52c41a;
}

.info-value.disabled {
  color: #ff4d4f;
}

.code-block {
  background: #f5f5f5;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.code-block pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #333;
}
</style>
