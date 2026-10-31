<template>
  <div class="tools-management-view">
    <header class="page-header">
      <div class="header-title">
        <h2>工具</h2>
        <span class="count-chip">{{ stats.total }} 个工具</span>
        <span v-if="stats.disabled" class="count-chip count-chip-warn">{{ stats.disabled }} 个已禁用</span>
      </div>
      <div class="header-tools">
        <label class="search-box">
          <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input v-model="searchQuery" type="search" placeholder="搜索工具…" />
        </label>
        <button
          type="button"
          class="icon-btn"
          :disabled="loading"
          :title="loading ? '正在加载工具列表' : '刷新工具列表'"
          @click="fetchTools"
        >
          <svg class="refresh-icon" :class="{ spinning: loading }" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 11a8 8 0 1 0-2.6 6" />
            <path d="M20 5v6h-6" />
          </svg>
        </button>
      </div>
    </header>

    <div class="main-content">
      <div v-if="loading && !tools.length" class="skeleton-list" aria-busy="true">
        <div v-for="index in 4" :key="index" class="skeleton-row">
          <span class="skeleton-icon"></span>
          <span class="skeleton-lines">
            <span class="skeleton-line short"></span>
            <span class="skeleton-line"></span>
          </span>
        </div>
      </div>

      <div v-else-if="groups.length === 0" class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M14.7 6.3a4 4 0 0 0 5 5l-8.4 8.4a2.1 2.1 0 0 1-3-3z" />
          <path d="M4 20l3-3" />
        </svg>
        <p>{{ searchQuery.trim() ? '未找到匹配的工具' : '暂无工具' }}</p>
      </div>

      <div v-else class="tool-groups">
        <section v-for="group in groups" :key="group.id" class="tool-group">
          <div class="group-header">
            <h3>{{ group.label }}</h3>
            <span class="group-count">{{ group.items.length }}</span>
          </div>

          <div class="tool-rows">
            <div
              v-for="tool in group.items"
              :key="tool.name"
              class="tool-row"
              :class="{ off: tool.status === 'disabled' }"
              role="button"
              tabindex="0"
              @click="viewToolDetail(tool)"
              @keydown.enter="viewToolDetail(tool)"
              @keydown.space.prevent="viewToolDetail(tool)"
            >
              <span class="tool-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M14.7 6.3a4 4 0 0 0 5 5l-8.4 8.4a2.1 2.1 0 0 1-3-3z" />
                  <path d="M4 20l3-3" />
                </svg>
              </span>

              <span class="tool-body">
                <span class="tool-name-row">
                  <span class="tool-name">{{ tool.name }}</span>
                  <span v-if="tool.status === 'disabled'" class="chip chip-off">已禁用</span>
                </span>
                <span class="tool-desc" :title="tool.description">
                  {{ tool.description || '暂无描述' }}
                </span>
              </span>

              <button
                type="button"
                class="switch"
                :class="{ on: tool.status === 'enabled' }"
                role="switch"
                :aria-checked="tool.status === 'enabled'"
                :title="tool.status === 'enabled' ? '点击禁用该工具' : '点击启用该工具'"
                @click.stop="toggleToolStatus(tool)"
                @keydown.enter.stop
                @keydown.space.stop.prevent
              >
                <span class="switch-dot"></span>
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 工具详情 -->
    <div v-if="showDetailDialog" class="dialog-overlay" @click.self="showDetailDialog = false">
      <div class="dialog" role="dialog" aria-modal="true" aria-label="工具详情">
        <header class="dialog-header">
          <div class="dialog-title">
            <h3>{{ currentTool?.name }}</h3>
            <span class="chip" :class="currentTool?.status === 'enabled' ? 'chip-on' : 'chip-off'">
              {{ currentTool?.status === 'enabled' ? '已启用' : '已禁用' }}
            </span>
          </div>
          <button type="button" class="icon-btn" title="关闭" @click="showDetailDialog = false">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </header>

        <div class="dialog-body" v-if="currentTool">
          <p class="dialog-desc">{{ currentTool.description }}</p>

          <section class="detail-section">
            <h4>基本信息</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">类别</span>
                <span class="info-value">{{ getCategoryLabel(currentTool.category) }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">版本</span>
                <span class="info-value">v{{ currentTool.version }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">优先级</span>
                <span class="info-value">{{ currentTool.priority }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">需要上下文</span>
                <span class="info-value">{{ currentTool.requires_context ? '是' : '否' }}</span>
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
                <span class="info-label">数据类型</span>
                <span class="info-value">{{ currentTool.metadata.data_type }}</span>
              </div>
            </div>
          </section>

          <section class="detail-section">
            <h4>调用统计</h4>
            <div class="stat-grid">
              <div class="stat-item">
                <span class="stat-value">{{ currentTool.statistics.total }}</span>
                <span class="stat-label">总调用</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ currentTool.statistics.success }}</span>
                <span class="stat-label">成功</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ currentTool.statistics.failed }}</span>
                <span class="stat-label">失败</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ getSuccessRate(currentTool.statistics) }}%</span>
                <span class="stat-label">成功率</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ currentTool.statistics.avg_execution_time.toFixed(2) }}s</span>
                <span class="stat-label">平均耗时</span>
              </div>
            </div>

            <div v-if="recentErrors(currentTool).length" class="recent-errors">
              <h5>最近错误（最多 10 条）</h5>
              <ul class="error-list">
                <li v-for="(item, idx) in recentErrors(currentTool)" :key="idx" class="error-item">
                  <span class="error-time">{{ formatErrorTime(item.at) }}</span>
                  <span class="error-text">{{ item.error }}</span>
                </li>
              </ul>
            </div>
          </section>

          <section class="detail-section" v-if="currentTool.function_schema">
            <h4>函数定义</h4>
            <div class="code-block">
              <pre>{{ JSON.stringify(currentTool.function_schema, null, 2) }}</pre>
            </div>
          </section>
        </div>

        <footer class="dialog-footer">
          <button type="button" class="btn-primary" @click="toggleToolStatus(currentTool)">
            {{ currentTool?.status === 'enabled' ? '禁用该工具' : '启用该工具' }}
          </button>
          <button type="button" class="btn-ghost" @click="showDetailDialog = false">关闭</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getToolsList, updateToolStatus } from '@/api/toolsManagement'

const loading = ref(false)
const tools = ref([])
const searchQuery = ref('')
const showDetailDialog = ref(false)
const currentTool = ref(null)

const CATEGORY_META = {
  query: { name: '数据查询', order: 1 },
  analysis: { name: '数据分析', order: 2 },
  visualization: { name: '数据可视化', order: 3 },
  task_management: { name: '任务管理', order: 4 },
  planning: { name: '规划', order: 5 },
  reporting: { name: '报告', order: 6 },
  knowledge_qa: { name: '知识问答', order: 7 },
  quick_trace: { name: '快速溯源', order: 8 },
  deep_trace: { name: '深度溯源', order: 9 }
}

const getCategoryLabel = (categoryId) => CATEGORY_META[categoryId]?.name || categoryId || '其他'

const stats = computed(() => {
  const total = tools.value.length
  const enabled = tools.value.filter((tool) => tool.status === 'enabled').length
  return { total, enabled, disabled: total - enabled }
})

const filteredTools = computed(() => {
  const terms = searchQuery.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return tools.value
  return tools.value.filter((tool) => {
    const haystack = `${tool.name || ''} ${tool.description || ''}`.toLowerCase()
    return terms.some((term) => haystack.includes(term))
  })
})

// 分类分组：已知分类按固定顺序，未知分类排在后面按 id 排序
const groups = computed(() => {
  const buckets = new Map()
  for (const tool of filteredTools.value) {
    const id = tool.category || 'unknown'
    if (!buckets.has(id)) buckets.set(id, [])
    buckets.get(id).push(tool)
  }
  const ids = [...buckets.keys()].sort((a, b) => {
    const aOrder = CATEGORY_META[a]?.order ?? 99
    const bOrder = CATEGORY_META[b]?.order ?? 99
    return aOrder === bOrder ? a.localeCompare(b) : aOrder - bOrder
  })
  return ids.map((id) => ({ id, label: getCategoryLabel(id), items: buckets.get(id) }))
})

const fetchTools = async () => {
  loading.value = true
  try {
    const response = await getToolsList()
    tools.value = response.tools || []
  } catch (e) {
    alert('获取工具列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const getSuccessRate = (statistics) => {
  const { total, success } = statistics
  if (total === 0) return 0
  return ((success / total) * 100).toFixed(1)
}

const recentErrors = (tool) => {
  const errors = tool?.statistics?.recent_errors
  return Array.isArray(errors) ? errors : []
}

const formatErrorTime = (value) => {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const toggleToolStatus = async (tool) => {
  if (!tool) return
  const newStatus = tool.status !== 'enabled'
  const action = newStatus ? '启用' : '禁用'

  if (!confirm(`确定要${action}工具"${tool.name}"吗？`)) return

  try {
    await updateToolStatus(tool.name, newStatus)
    tool.status = newStatus ? 'enabled' : 'disabled'
  } catch (e) {
    alert(`${action}工具失败: ${e.message}`)
  }
}

const viewToolDetail = (tool) => {
  currentTool.value = tool
  showDetailDialog.value = true
}

onMounted(() => {
  fetchTools()
})
</script>

<style scoped>
.tools-management-view {
  padding: 4px 2px 24px;
  height: 100%;
  overflow-y: auto;
  color: var(--text-1, #333);
  font-size: var(--text-size-base, 14px);
}

/* 顶部 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.header-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.header-title h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--text-1, #333);
}

.count-chip {
  padding: 2px 8px;
  border-radius: var(--radius-pill, 999px);
  background: var(--bg-muted, #f8fafc);
  border: 1px solid var(--border-1, #f0f0f0);
  color: var(--text-3, #999);
  font-size: var(--text-size-xs, 12px);
  line-height: 18px;
  white-space: nowrap;
}

.count-chip-warn {
  color: var(--color-warning-text, #d48806);
  background: var(--color-warning-bg, #fffbe6);
  border-color: #f5d78e;
}

.header-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--control-h-md, 32px);
  padding: 0 10px;
  width: 240px;
  background: var(--bg-container, #fff);
  border: 1px solid var(--border-3, #d9d9d9);
  border-radius: var(--radius-lg, 8px);
  transition: border-color var(--transition-fast, 0.15s ease), box-shadow var(--transition-fast, 0.15s ease);
}

.search-box:focus-within {
  border-color: var(--color-primary, #1890ff);
  box-shadow: 0 0 0 3px var(--color-primary-ring, rgba(24, 144, 255, 0.12));
}

.search-icon {
  width: 15px;
  height: 15px;
  flex: none;
  fill: none;
  stroke: var(--text-3, #999);
  stroke-width: 1.8;
  stroke-linecap: round;
}

.search-box input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: var(--text-size-sm, 13px);
  color: var(--text-1, #333);
}

.search-box input::placeholder {
  color: var(--text-disabled, #bfbfbf);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--control-h-md, 32px);
  height: var(--control-h-md, 32px);
  padding: 0;
  border: 1px solid var(--border-3, #d9d9d9);
  border-radius: var(--radius-lg, 8px);
  background: var(--bg-container, #fff);
  color: var(--icon-1, #595959);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease), color var(--transition-fast, 0.15s ease);
}

.icon-btn:hover:not(:disabled) {
  background: var(--bg-hover, #f5f5f5);
  color: var(--color-primary, #1890ff);
}

.icon-btn:disabled {
  cursor: default;
  opacity: 0.8;
}

.icon-btn svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.refresh-icon.spinning {
  animation: tool-spin 0.9s linear infinite;
}

@keyframes tool-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 列表 */
.main-content {
  min-height: 300px;
  margin-top: 12px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 8px;
}

.group-header:first-child {
  margin-top: 4px;
}

.group-header h3 {
  margin: 0;
  font-size: var(--text-size-sm, 13px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--text-2, #666);
}

.group-count {
  color: var(--text-3, #999);
  font-size: var(--text-size-xs, 12px);
}

.tool-rows {
  background: var(--bg-container, #fff);
  border: 1px solid var(--border-2, #e8e8e8);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.tool-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  outline: none;
  transition: background var(--transition-fast, 0.15s ease);
}

.tool-row + .tool-row {
  border-top: 1px solid var(--border-1, #f0f0f0);
}

.tool-row:hover,
.tool-row:focus-visible {
  background: var(--bg-muted, #f8fafc);
}

.tool-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-md, 6px);
  background: var(--color-primary-bg, #e6f7ff);
  color: var(--color-primary, #1890ff);
}

.tool-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.tool-row.off .tool-icon {
  background: var(--bg-hover, #f5f5f5);
  color: var(--text-3, #999);
}

.tool-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.tool-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tool-name {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  font-weight: var(--font-weight-medium, 500);
  color: var(--text-1, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-row.off .tool-name {
  color: var(--text-3, #999);
}

.tool-desc {
  font-size: var(--text-size-sm, 13px);
  color: var(--text-3, #999);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.5;
}

.tool-row.off .tool-desc {
  color: var(--text-disabled, #bfbfbf);
}

/* 启用开关 */
.switch {
  position: relative;
  flex: none;
  width: 38px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: var(--radius-pill, 999px);
  background: var(--border-3, #d9d9d9);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease);
}

.switch.on {
  background: var(--color-primary, #1890ff);
}

.switch:focus-visible {
  outline: 2px solid var(--color-primary-ring, rgba(24, 144, 255, 0.4));
  outline-offset: 2px;
}

.switch-dot {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--shadow-1, 0 1px 2px rgba(31, 42, 68, 0.06));
  transition: transform var(--transition-fast, 0.15s ease);
}

.switch.on .switch-dot {
  transform: translateX(16px);
}

.chip {
  display: inline-flex;
  align-items: center;
  flex: none;
  padding: 1px 7px;
  border-radius: var(--radius-sm, 4px);
  font-size: var(--text-size-xs, 12px);
  font-weight: 400;
  line-height: 18px;
  white-space: nowrap;
}

.chip-off {
  color: var(--text-2, #666);
  background: var(--bg-hover, #f5f5f5);
  border: 1px solid var(--border-3, #d9d9d9);
}

.chip-on {
  color: var(--color-success, #52c41a);
  background: var(--color-success-bg, #f6ffed);
  border: 1px solid #b7eb8f;
}

/* 空态 / 骨架屏 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 56px 20px;
  color: var(--text-3, #999);
}

.empty-icon {
  width: 32px;
  height: 32px;
  fill: none;
  stroke: var(--text-disabled, #bfbfbf);
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.empty-state p {
  margin: 0;
  font-size: var(--text-size-sm, 13px);
}

.skeleton-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-container, #fff);
  border: 1px solid var(--border-2, #e8e8e8);
  border-radius: var(--radius-lg, 8px);
  margin-bottom: 8px;
}

.skeleton-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-md, 6px);
  background: var(--bg-hover, #f5f5f5);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}

.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 7px;
  flex: 1;
}

.skeleton-line {
  height: 10px;
  border-radius: var(--radius-sm, 4px);
  background: var(--bg-hover, #f5f5f5);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}

.skeleton-line.short {
  width: 24%;
}

@keyframes skeleton-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

/* 详情对话框 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal, 1000);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
}

.dialog {
  display: flex;
  flex-direction: column;
  width: 720px;
  max-width: 100%;
  max-height: 84vh;
  background: var(--bg-container, #fff);
  border-radius: var(--radius-lg, 8px);
  box-shadow: var(--shadow-3, 0 8px 24px rgba(31, 42, 68, 0.16));
  overflow: hidden;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-1, #f0f0f0);
}

.dialog-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.dialog-title h3 {
  margin: 0;
  font-family: var(--font-mono, monospace);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dialog-body {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
}

.dialog-desc {
  margin: 0 0 18px;
  font-size: var(--text-size-sm, 13px);
  line-height: var(--line-height-body, 1.6);
  color: var(--text-2, #666);
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-1, #f0f0f0);
  font-size: var(--text-size-sm, 13px);
  font-weight: 500;
  color: var(--text-2, #666);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.info-label {
  font-size: var(--text-size-xs, 12px);
  color: var(--text-3, #999);
}

.info-value {
  font-size: var(--text-size-sm, 13px);
  color: var(--text-1, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  background: var(--bg-muted, #f8fafc);
  border: 1px solid var(--border-1, #f0f0f0);
  border-radius: var(--radius-md, 6px);
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1, #333);
}

.stat-label {
  font-size: var(--text-size-xs, 12px);
  color: var(--text-3, #999);
}

.recent-errors {
  margin-top: 14px;
}

.recent-errors h5 {
  margin: 0 0 8px;
  font-size: var(--text-size-xs, 12px);
  font-weight: 500;
  color: var(--color-danger, #f5222d);
}

.error-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 200px;
  overflow-y: auto;
}

.error-item {
  display: flex;
  gap: 12px;
  align-items: baseline;
  padding: 6px 8px;
  border-bottom: 1px dashed var(--border-1, #f0f0f0);
  font-size: var(--text-size-xs, 12px);
}

.error-time {
  flex-shrink: 0;
  color: var(--text-3, #999);
  font-family: var(--font-mono, monospace);
}

.error-text {
  color: var(--color-danger, #f5222d);
  word-break: break-all;
}

.code-block {
  max-height: 260px;
  padding: 12px;
  overflow: auto;
  border-radius: var(--radius-md, 6px);
  background: var(--bg-muted, #f8fafc);
  border: 1px solid var(--border-1, #f0f0f0);
}

.code-block pre {
  margin: 0;
  font-family: var(--font-mono, monospace);
  font-size: var(--text-size-xs, 12px);
  line-height: 1.6;
  color: var(--text-2, #666);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-1, #f0f0f0);
}

.btn-primary {
  padding: 6px 16px;
  border: 1px solid var(--color-primary, #1890ff);
  border-radius: var(--radius-md, 6px);
  background: var(--color-primary, #1890ff);
  color: #fff;
  font-size: var(--text-size-sm, 13px);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease);
}

.btn-primary:hover {
  background: var(--color-primary-hover, #40a9ff);
  border-color: var(--color-primary-hover, #40a9ff);
}

.btn-ghost {
  padding: 6px 16px;
  border: 1px solid var(--border-3, #d9d9d9);
  border-radius: var(--radius-md, 6px);
  background: var(--bg-container, #fff);
  color: var(--text-2, #666);
  font-size: var(--text-size-sm, 13px);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease);
}

.btn-ghost:hover {
  background: var(--bg-hover, #f5f5f5);
}

@media (max-width: 720px) {
  .search-box {
    width: 170px;
  }

  .info-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
