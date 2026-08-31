<template>
  <div class="tools-management-view">
    <header class="page-header">
      <div class="header-copy">
        <div>
          <h2>工具管理</h2>
          <p>分类直接铺开，每个工具一个卡片</p>
        </div>
        <span class="stats" v-if="stats">
          共 {{ stats.total }} 个工具 / {{ stats.enabled }} 已启用 / {{ stats.disabled }} 已禁用
        </span>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" />
            <path d="M16 16l4.5 4.5" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索工具或描述"
          />
        </div>
      </div>
    </header>

    <section class="summary-row" aria-label="工具概览">
      <article v-for="item in summaryCards" :key="item.label" class="summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </section>

    <section v-if="loading" class="state-panel">
      <strong>加载中...</strong>
    </section>

    <section v-else-if="toolSections.length === 0" class="state-panel empty">
      <strong>未找到匹配工具</strong>
      <span>尝试调整搜索词，或稍后刷新再看。</span>
    </section>

    <section v-else class="tool-sections">
      <article
        v-for="section in toolSections"
        :key="section.id"
        class="tool-section"
      >
        <header class="section-header">
          <button
            type="button"
            class="section-toggle"
            :class="{ collapsed: isSectionCollapsed(section.id) }"
            :aria-expanded="!isSectionCollapsed(section.id)"
            @click="toggleSection(section.id)"
          >
            <div class="section-toggle-main">
              <div class="section-copy">
                <span class="section-badge">分类</span>
                <h3>{{ section.title }}</h3>
                <p>{{ section.description }}</p>
              </div>
              <div class="section-meta">
                <span>{{ section.count }} 个工具</span>
                <span>{{ section.enabledCount }} 已启用</span>
              </div>
            </div>
            <span class="section-toggle-icon" aria-hidden="true">
              <svg viewBox="0 0 20 20">
                <path d="m6 8 4 4 4-4" />
              </svg>
            </span>
          </button>
        </header>

        <div v-if="!isSectionCollapsed(section.id)" class="tool-grid">
          <article
            v-for="tool in section.tools"
            :key="tool.name"
            class="tool-card"
            :class="{ disabled: tool.status === 'disabled' }"
            role="button"
            tabindex="0"
            @click="viewToolDetail(tool)"
            @keydown.enter.prevent="viewToolDetail(tool)"
            @keydown.space.prevent="viewToolDetail(tool)"
            >
              <div class="tool-card-top">
                <div class="tool-card-title">
                  <span class="tool-name">{{ tool.name }}</span>
                  <span class="tool-badge" :class="tool.status">
                    {{ tool.status === 'enabled' ? '已启用' : '已禁用' }}
                  </span>
                </div>
              <p class="tool-desc" :title="tool.description">{{ getToolSummary(tool) }}</p>
              </div>

            <div class="tool-meta">
              <span class="tool-chip">{{ getCategoryLabel(tool.category) }}</span>
              <span class="tool-chip">v{{ tool.version }}</span>
              <span class="tool-chip">调用 {{ tool.statistics?.total ?? 0 }}</span>
              <span class="tool-chip">成功率 {{ getSuccessRate(tool.statistics) }}%</span>
            </div>

            <div class="tool-actions">
              <button
                type="button"
                class="btn-toggle"
                :class="{ enabled: tool.status === 'enabled' }"
                @click.stop="toggleToolStatus(tool)"
              >
                {{ tool.status === 'enabled' ? '禁用' : '启用' }}
              </button>
              <button
                type="button"
                class="btn-link"
                @click.stop="viewToolDetail(tool)"
              >
                查看详情
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="m7 4.5 5.5 5.5L7 15.5" />
                </svg>
              </button>
            </div>
          </article>
        </div>
      </article>
    </section>

    <div v-if="showDetailDialog" class="dialog-overlay" @click.self="showDetailDialog = false">
      <div class="dialog dialog-wide">
        <div class="dialog-header">
          <h3>工具详情</h3>
          <button class="btn-close" @click="showDetailDialog = false">×</button>
        </div>
        <div class="dialog-body" v-if="currentTool">
          <p v-if="detailLoading" class="detail-note">正在加载完整详情...</p>

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
                <span class="info-value">{{ currentTool.metadata?.data_type }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">支持批量</span>
                <span class="info-value">{{ currentTool.metadata?.supports_batch ? '是' : '否' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">需要句柄</span>
                <span class="info-value">{{ currentTool.metadata?.requires_handle ? '是' : '否' }}</span>
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
                <span class="info-value">{{ currentTool.statistics?.total ?? 0 }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">成功次数</span>
                <span class="info-value">{{ currentTool.statistics?.success ?? 0 }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">失败次数</span>
                <span class="info-value">{{ currentTool.statistics?.failed ?? 0 }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">成功率</span>
                <span class="info-value">{{ getSuccessRate(currentTool.statistics) }}%</span>
              </div>
              <div class="info-item">
                <span class="info-label">平均执行时间</span>
                <span class="info-value">{{ formatExecutionTime(currentTool.statistics?.avg_execution_time) }}s</span>
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
import { getToolsList, getToolDetail, updateToolStatus } from '@/api/toolsManagement'

const loading = ref(false)
const detailLoading = ref(false)
const tools = ref([])
const searchQuery = ref('')
const showDetailDialog = ref(false)
const currentTool = ref(null)
const collapsedSections = ref(new Set())

const categoryMap = {
  query: {
    id: 'query',
    name: '数据查询',
    description: '从数据库查询各类环境数据'
  },
  analysis: {
    id: 'analysis',
    name: '数据分析',
    description: '执行 PMF、OBM 等分析计算'
  },
  visualization: {
    id: 'visualization',
    name: '数据可视化',
    description: '生成图表和可视化配置'
  },
  task_management: {
    id: 'task_management',
    name: '任务管理',
    description: '管理任务清单和状态'
  }
}

const categoryOrder = ['query', 'analysis', 'visualization', 'task_management']

const stats = computed(() => {
  const total = tools.value.length
  const enabled = tools.value.filter((tool) => tool.status === 'enabled').length
  const disabled = total - enabled
  return { total, enabled, disabled }
})

const categoryCount = computed(() => {
  return new Set(tools.value.map((tool) => tool.category).filter(Boolean)).size
})

const normalizedSearch = computed(() => searchQuery.value.trim().toLowerCase())

const matchesSearch = (tool) => {
  const keyword = normalizedSearch.value
  if (!keyword) return true

  return [
    tool.name,
    tool.description,
    getCategoryLabel(tool.category),
    tool.version,
    tool.status
  ].some((value) => String(value ?? '').toLowerCase().includes(keyword))
}

const sortTools = (items) => {
  return [...items].sort((left, right) => {
    const leftPriority = Number(left.priority ?? 0)
    const rightPriority = Number(right.priority ?? 0)
    if (leftPriority !== rightPriority) return leftPriority - rightPriority
    return String(left.name ?? '').localeCompare(String(right.name ?? ''), 'zh-Hans-CN')
  })
}

const toolSections = computed(() => {
  const grouped = new Map()

  tools.value.filter(matchesSearch).forEach((tool) => {
    const key = tool.category || 'unknown'
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key).push(tool)
  })

  const keys = [
    ...categoryOrder.filter((key) => grouped.has(key)),
    ...[...grouped.keys()].filter((key) => !categoryOrder.includes(key)).sort((left, right) => {
      return getCategoryLabel(left).localeCompare(getCategoryLabel(right), 'zh-Hans-CN')
    })
  ]

  return keys.map((key) => {
    const items = sortTools(grouped.get(key) || [])
    const meta = categoryMap[key] || {}
    return {
      id: key,
      title: meta.name || getCategoryLabel(key),
      description: meta.description || '该分类暂无说明',
      count: items.length,
      enabledCount: items.filter((tool) => tool.status === 'enabled').length,
      tools: items
    }
  })
})

const summaryCards = computed(() => [
  {
    label: '工具总数',
    value: stats.value.total,
    hint: '全部注册工具'
  },
  {
    label: '分类数',
    value: categoryCount.value,
    hint: '页面直接按分类铺开'
  },
  {
    label: '启用率',
    value: stats.value.total ? `${((stats.value.enabled / stats.value.total) * 100).toFixed(1)}%` : '0%',
    hint: `${stats.value.enabled} 个已启用`
  }
])

const isSectionCollapsed = (sectionId) => collapsedSections.value.has(sectionId)

const toggleSection = (sectionId) => {
  const next = new Set(collapsedSections.value)
  if (next.has(sectionId)) {
    next.delete(sectionId)
  } else {
    next.add(sectionId)
  }
  collapsedSections.value = next
}

const fetchTools = async () => {
  loading.value = true
  try {
    const response = await getToolsList()
    tools.value = response.tools || []
  } catch (error) {
    console.error('获取工具列表失败:', error)
    alert('获取工具列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const getCategoryLabel = (categoryId) => {
  const category = categoryMap[categoryId]
  if (category) return category.name
  return String(categoryId || 'unknown').replace(/_/g, ' ')
}

const getSuccessRate = (statistics = {}) => {
  const total = Number(statistics.total || 0)
  const success = Number(statistics.success || 0)
  if (!total) return '0.0'
  return ((success / total) * 100).toFixed(1)
}

const getToolSummary = (tool) => {
  const raw = String(tool?.description || '').replace(/\s+/g, ' ').trim()
  if (!raw) return '暂无描述'
  if (raw.length <= 160) return raw
  return `${raw.slice(0, 159)}…`
}

const formatExecutionTime = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue.toFixed(2) : '0.00'
}

const toggleToolStatus = async (tool) => {
  const newStatus = tool.status === 'enabled' ? false : true
  const action = newStatus ? '启用' : '禁用'

  if (!confirm(`确定要${action}工具"${tool.name}"吗？`)) return

  try {
    await updateToolStatus(tool.name, newStatus)
    tool.status = newStatus ? 'enabled' : 'disabled'
    if (currentTool.value?.name === tool.name) {
      currentTool.value.status = tool.status
    }
  } catch (error) {
    alert(`${action}工具失败: ${error.message}`)
  }
}

const viewToolDetail = async (tool) => {
  showDetailDialog.value = true
  detailLoading.value = true
  currentTool.value = { ...tool }

  try {
    const data = await getToolDetail(tool.name)
    if (data.success && data.tool) {
      currentTool.value = data.tool
    }
  } catch (error) {
    console.error('加载工具详情失败:', error)
  } finally {
    detailLoading.value = false
  }
}

onMounted(fetchTools)
</script>

<style scoped>
.tools-management-view {
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 20px 24px 28px;
  background: #f5f7fb;
  color: #24333e;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.header-copy {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: baseline;
}

.header-copy h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 650;
  color: #15232d;
}

.header-copy p {
  margin: 4px 0 0;
  color: #607080;
  font-size: 12px;
}

.stats {
  color: #607080;
  font-size: 13px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 280px;
  padding: 0 12px;
  border: 1px solid #d7e0e8;
  border-radius: 10px;
  background: #fff;
}

.search-box svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: #6b7f90;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.7;
  flex: none;
}

.search-box input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #22313b;
  font: inherit;
  min-height: 38px;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.summary-card {
  display: grid;
  gap: 4px;
  min-height: 84px;
  padding: 14px 16px;
  border: 1px solid #dde5ec;
  border-radius: 12px;
  background: #fff;
}

.summary-card span,
.summary-card small {
  color: #6d7f8f;
  font-size: 11px;
}

.summary-card strong {
  font-size: 26px;
  font-weight: 700;
  color: #163041;
}

.state-panel {
  display: grid;
  place-items: center;
  min-height: 220px;
  border: 1px dashed #cfd9e2;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.6);
  color: #6f8090;
  text-align: center;
}

.state-panel.empty {
  gap: 6px;
}

.state-panel strong {
  color: #32495b;
  font-size: 14px;
}

.tool-sections {
  display: grid;
  gap: 18px;
}

.tool-section {
  display: grid;
  gap: 12px;
}

.section-header {
  display: block;
}

.section-toggle {
  display: flex;
  width: 100%;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  border: 1px solid #dde5ec;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.section-toggle:hover,
.section-toggle:focus-visible {
  border-color: #1590a0;
  box-shadow: 0 12px 28px rgba(16, 82, 94, 0.06);
  transform: translateY(-1px);
  outline: none;
}

.section-toggle-main {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}

.section-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.section-badge {
  color: #0f7b8a;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.section-copy h3 {
  margin: 0;
  font-size: 18px;
  color: #183241;
}

.section-copy p {
  margin: 0;
  color: #678090;
  font-size: 12px;
}

.section-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #6d7f8f;
  font-size: 11px;
  flex: none;
}

.section-meta span {
  padding: 5px 8px;
  border-radius: 999px;
  background: #edf4f8;
}

.section-toggle-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 999px;
  background: #f1f6f9;
  color: #5c7282;
}

.section-toggle-icon svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
  transition: transform 0.18s ease;
}

.section-toggle.collapsed .section-toggle-icon svg {
  transform: rotate(-90deg);
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.tool-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 236px;
  padding: 16px;
  border: 1px solid #dce5ec;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.tool-card:hover,
.tool-card:focus-visible {
  border-color: #1590a0;
  box-shadow: 0 12px 28px rgba(16, 82, 94, 0.08);
  transform: translateY(-1px);
  outline: none;
}

.tool-card.disabled {
  background: #fbfcfd;
  opacity: 0.72;
}

.tool-card-top {
  display: grid;
  gap: 8px;
  min-height: 0;
  flex: 1;
}

.tool-card-title {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  min-width: 0;
}

.tool-name {
  font-size: 15px;
  font-weight: 700;
  color: #183241;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-badge {
  flex: none;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.tool-badge.enabled {
  color: #0d7c49;
  background: #e7f8ef;
}

.tool-badge.disabled {
  color: #8b97a5;
  background: #edf1f5;
}

.tool-desc {
  margin: 0;
  color: #5e7384;
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  word-break: break-word;
}

.tool-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  min-height: 44px;
}

.tool-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f6f9;
  color: #5c7282;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-actions {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  min-height: 36px;
}

.btn-toggle,
.btn-secondary,
.btn-link {
  border: 0;
  border-radius: 9px;
  cursor: pointer;
  font: inherit;
  transition: background-color 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.btn-toggle {
  padding: 8px 12px;
  border: 1px solid #d8e1e8;
  background: #fff;
  color: #405868;
  white-space: nowrap;
}

.btn-secondary {
  padding: 8px 12px;
  border: 1px solid #d8e1e8;
  background: #fff;
  color: #405868;
  white-space: nowrap;
}

.btn-toggle.enabled {
  border-color: #1590a0;
  color: #0f7b8a;
  background: #eefcff;
}

.btn-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: transparent;
  color: #0f7b8a;
  white-space: nowrap;
}

.btn-link svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.btn-toggle:hover,
.btn-link:hover,
.btn-secondary:hover {
  border-color: #1590a0;
  color: #0f7b8a;
}

.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(8, 16, 24, 0.48);
}

.dialog {
  display: flex;
  flex-direction: column;
  width: min(860px, calc(100vw - 32px));
  max-height: calc(100vh - 40px);
  overflow: hidden;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 24px 60px rgba(8, 18, 28, 0.24);
}

.dialog-header,
.dialog-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 14px 18px;
}

.dialog-header {
  border-bottom: 1px solid #e8eef3;
}

.dialog-footer {
  justify-content: flex-end;
  border-top: 1px solid #e8eef3;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  color: #163041;
}

.btn-close {
  border: 0;
  background: transparent;
  color: #6d7f8f;
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.detail-note {
  margin: 0 0 14px;
  color: #0f7b8a;
  font-size: 12px;
}

.tool-detail-section {
  margin-bottom: 22px;
}

.tool-detail-section h4 {
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8eef3;
  color: #183241;
  font-size: 14px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.info-item {
  display: grid;
  gap: 4px;
}

.info-label {
  color: #708391;
  font-size: 12px;
}

.info-value {
  color: #183241;
  font-size: 14px;
  font-weight: 600;
  word-break: break-word;
}

.info-value.enabled {
  color: #0d7c49;
}

.info-value.disabled {
  color: #c03d3d;
}

.code-block {
  overflow-x: auto;
  padding: 12px;
  border-radius: 10px;
  background: #f6f9fb;
}

.code-block pre {
  margin: 0;
  color: #2c3b46;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 820px) {
  .page-header {
    flex-direction: column;
  }

  .header-actions,
  .search-box {
    width: 100%;
  }

  .summary-row {
    grid-template-columns: 1fr;
  }

  .section-header {
    flex-direction: column;
  }

  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
