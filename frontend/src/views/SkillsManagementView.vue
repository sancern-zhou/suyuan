<template>
  <div class="skills-management-view">
    <!-- 列表视图 -->
    <div v-if="!showDetailFullscreen" class="list-view">
      <header class="page-header">
        <div class="header-title">
          <h2>技能</h2>
          <span class="count-chip">{{ activeCountLabel }}</span>
        </div>
        <div class="header-tools">
          <label class="search-box">
            <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              v-model="searchKeyword"
              type="search"
              :placeholder="activeSkillType === 'draft' ? '搜索待审核草稿…' : '搜索技能…'"
            />
          </label>
          <button
            type="button"
            class="icon-btn"
            :disabled="refreshingIndex"
            :title="refreshingIndex ? '正在刷新技能索引' : '刷新技能索引'"
            @click="refreshSkillIndex"
          >
            <svg class="refresh-icon" :class="{ spinning: refreshingIndex }" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 11a8 8 0 1 0-2.6 6" />
              <path d="M20 5v6h-6" />
            </svg>
          </button>
        </div>
      </header>

      <div class="type-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          class="type-tab"
          :class="{ active: activeSkillType === 'official' }"
          :aria-selected="activeSkillType === 'official'"
          @click="switchSkillType('official')"
        >
          正式技能
          <span class="tab-count">{{ officialSkills.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          class="type-tab"
          :class="{ active: activeSkillType === 'draft' }"
          :aria-selected="activeSkillType === 'draft'"
          @click="switchSkillType('draft')"
        >
          待审核草稿
          <span class="tab-count">{{ drafts.length }}</span>
        </button>
      </div>

      <div class="main-content">
        <div v-if="loading" class="skeleton-list" aria-busy="true">
          <div v-for="index in 4" :key="index" class="skeleton-row">
            <span class="skeleton-icon"></span>
            <span class="skeleton-lines">
              <span class="skeleton-line short"></span>
              <span class="skeleton-line"></span>
            </span>
          </div>
        </div>

        <div v-else-if="filteredSkills.length === 0" class="empty-state">
          <svg class="empty-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 4 5 7.5l7 3.5 7-3.5L12 4Z" />
            <path d="M5 12l7 3.5L19 12" />
            <path d="M5 16.5 12 20l7-3.5" />
          </svg>
          <p>{{ emptyStateText }}</p>
        </div>

        <div v-else class="skill-groups">
          <section v-for="group in skillGroups" :key="group.id" class="skill-group">
            <div class="group-header">
              <h3>{{ group.label }}</h3>
              <span class="group-count">{{ group.items.length }}</span>
            </div>

            <div class="skill-cards">
              <div
                v-for="skill in group.items"
                :key="skill.file || skill.name"
                class="skill-card"
                role="button"
                tabindex="0"
                @click="viewSkillDetail(skill)"
                @keydown.enter="viewSkillDetail(skill)"
                @keydown.space.prevent="viewSkillDetail(skill)"
              >
                <span class="skill-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M12 4 5 7.5l7 3.5 7-3.5L12 4Z" />
                    <path d="M5 12l7 3.5L19 12" />
                    <path d="M5 16.5 12 20l7-3.5" />
                  </svg>
                </span>

                <span class="skill-body">
                  <span class="skill-name-row">
                    <span class="skill-name">{{ skill.name }}</span>
                    <span v-if="skill.is_draft" class="chip chip-draft">待审核</span>
                  </span>
                  <span class="skill-desc" :title="skill.description">
                    {{ skill.description || '暂无描述' }}
                  </span>
                </span>

                <svg class="skill-chevron" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m9 6 6 6-6 6" />
                </svg>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>

    <!-- 全屏详情视图 -->
    <div v-else class="detail-view">
      <header class="detail-header">
        <button type="button" class="back-btn" @click="closeDetailFullscreen">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6" /></svg>
          返回
        </button>
        <div class="detail-title">
          <h2>{{ currentSkill?.name }}</h2>
          <span v-if="currentSkill?.is_draft" class="chip chip-draft">待审核草稿</span>
        </div>
        <div class="detail-actions">
          <template v-if="!isEditing">
            <button type="button" class="btn-primary" @click="startEdit">编辑</button>
          </template>
          <template v-else>
            <button type="button" class="btn-ghost" @click="cancelEdit">取消</button>
            <button type="button" class="btn-primary" :disabled="saving" @click="saveSkill">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </template>
        </div>
      </header>

      <div class="detail-content">
        <div v-if="currentSkill" class="detail-meta">
          <div class="meta-item">
            <span class="meta-label">来源</span>
            <span class="meta-value">{{ sourceLabel(currentSkill) }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">文件</span>
            <span class="meta-value mono">{{ displayPath(currentSkill.file) }}</span>
          </div>
        </div>

        <div class="editor-container">
          <div v-if="!isEditing" class="markdown-preview" v-html="renderMarkdown(currentSkill?.content)"></div>
          <textarea v-else v-model="editedContent" class="markdown-editor" spellcheck="false"></textarea>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getSkillsList,
  getSkillDetail,
  getSkillDraftsList,
  getSkillDraftDetail,
  refreshSkillsIndex,
  saveSkillDetail,
  saveSkillDraftDetail
} from '@/api/skillsManagement'
import markdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import markdownItMultimdTable from 'markdown-it-multimd-table'

defineEmits(['close'])

// 配置 markdown-it
const md = markdownIt({
  html: true,
  linkify: true,
  typographer: true
})
  .use(markdownItKatex)
  .use(markdownItMultimdTable)

const loading = ref(false)
const searchKeyword = ref('')
const officialSkills = ref([])
const drafts = ref([])
const activeSkillType = ref('official')
const showDetailFullscreen = ref(false)
const currentSkill = ref(null)
const isEditing = ref(false)
const editedContent = ref('')
const saving = ref(false)
const refreshingIndex = ref(false)

const activeSkills = computed(() =>
  activeSkillType.value === 'draft' ? drafts.value : officialSkills.value
)

const activeCountLabel = computed(() =>
  activeSkillType.value === 'draft'
    ? `${drafts.value.length} 个待审核草稿`
    : `${officialSkills.value.length} 个技能`
)

// 搜索在前端完成，name / description / aliases 任一命中即保留
const filteredSkills = computed(() => {
  const terms = searchKeyword.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return activeSkills.value
  return activeSkills.value.filter((skill) => {
    const haystack = [skill.name, skill.description, ...(skill.aliases || [])]
      .join(' ')
      .toLowerCase()
    return terms.some((term) => haystack.includes(term))
  })
})

// 按技能来源分组：项目技能优先，其次共享技能库
const skillGroups = computed(() => {
  if (activeSkillType.value === 'draft') {
    return [{ id: 'draft', label: '待审核草稿', items: filteredSkills.value }]
  }
  const groups = [
    { id: 'project', label: '项目技能', items: [] },
    { id: 'shared', label: '共享技能库', items: [] },
    { id: 'other', label: '其他', items: [] }
  ]
  const byId = Object.fromEntries(groups.map((group) => [group.id, group]))
  for (const skill of filteredSkills.value) {
    byId[sourceId(skill)].items.push(skill)
  }
  return groups.filter((group) => group.items.length)
})

const emptyStateText = computed(() => {
  if (searchKeyword.value.trim()) {
    return activeSkillType.value === 'draft' ? '未找到匹配的待审核草稿' : '未找到匹配的技能'
  }
  return activeSkillType.value === 'draft' ? '暂无待审核技能草稿' : '暂无技能文档'
})

const normalizedPath = (filePath) => String(filePath || '').replace(/\\/g, '/')

const sourceId = (skill) => {
  const path = normalizedPath(skill?.file)
  // 索引里的链接可能是仓库相对路径（projects/...），也可能已被解析成绝对路径
  if (/(^|\/)projects\//.test(path)) return 'project'
  if (/(^|\/)backend\/docs\/skills\//.test(path)) return 'shared'
  return 'other'
}

const sourceLabel = (skill) => {
  if (skill?.is_draft) return '待审核草稿'
  return { project: '项目技能', shared: '共享技能库', other: '其他' }[sourceId(skill)]
}

const displayPath = (filePath) => {
  const path = normalizedPath(filePath)
  const projectIndex = path.indexOf('/projects/')
  if (projectIndex >= 0) return path.slice(projectIndex + 1)
  const docsIndex = path.indexOf('backend/docs/skills')
  if (docsIndex >= 0) return path.slice(docsIndex)
  return path
}

const loadSkills = async () => {
  loading.value = true
  try {
    const [officialResult, draftResult] = await Promise.all([
      getSkillsList(),
      getSkillDraftsList().catch(() => ({ success: false }))
    ])
    if (officialResult.success) {
      officialSkills.value = officialResult.data.skills || []
    }
    drafts.value = draftResult?.success ? draftResult.data.drafts || [] : []
  } catch (error) {
    console.error('加载技能列表失败:', error)
    alert('加载技能列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const switchSkillType = (type) => {
  if (activeSkillType.value === type) return
  activeSkillType.value = type
  searchKeyword.value = ''
}

const refreshSkillIndex = async () => {
  refreshingIndex.value = true
  try {
    const data = await refreshSkillsIndex()
    if (data.success) {
      await loadSkills()
    } else {
      throw new Error(data.message || '刷新技能索引失败')
    }
  } catch (error) {
    console.error('刷新技能索引失败:', error)
    alert('刷新技能索引失败: ' + error.message)
  } finally {
    refreshingIndex.value = false
  }
}

const getFileName = (filePath) => {
  return filePath.split('/').pop()
}

const getSkillIdentifier = (skill) => {
  if (skill?.id) return skill.id

  const filePath = String(skill?.file || '')
  const fileName = getFileName(filePath)
  // Project skills are package directories whose entry point is SKILL.md.
  if (fileName.toLowerCase() === 'skill.md') {
    const pathParts = filePath.split('/').filter(Boolean)
    return pathParts[pathParts.length - 2] || fileName.replace(/\.md$/i, '')
  }
  return fileName.replace(/\.md$/i, '')
}

const viewSkillDetail = async (skill) => {
  try {
    const skillIdentifier = getSkillIdentifier(skill)
    const data = skill.is_draft || activeSkillType.value === 'draft'
      ? await getSkillDraftDetail(skillIdentifier)
      : await getSkillDetail(skillIdentifier)
    if (data.success) {
      currentSkill.value = data.data
      editedContent.value = data.data.content
      showDetailFullscreen.value = true
    }
  } catch (error) {
    console.error('加载技能详情失败:', error)
    alert('加载技能详情失败: ' + error.message)
  }
}

const closeDetailFullscreen = () => {
  if (isEditing.value) {
    if (!confirm('正在编辑中，确定要返回吗？未保存的修改将丢失。')) {
      return
    }
  }
  showDetailFullscreen.value = false
  currentSkill.value = null
  isEditing.value = false
  editedContent.value = ''
}

const startEdit = () => {
  isEditing.value = true
  editedContent.value = currentSkill.value.content
}

const cancelEdit = () => {
  if (!confirm('确定要取消编辑吗？未保存的修改将丢失。')) {
    return
  }
  isEditing.value = false
  editedContent.value = currentSkill.value.content
}

const saveSkill = async () => {
  if (!currentSkill.value) return

  saving.value = true
  try {
    const skillIdentifier = getSkillIdentifier(currentSkill.value)
    const data = currentSkill.value.is_draft
      ? await saveSkillDraftDetail(skillIdentifier, editedContent.value)
      : await saveSkillDetail(skillIdentifier, editedContent.value)

    if (data.success) {
      alert('保存成功')
      currentSkill.value = {
        ...currentSkill.value,
        ...(data.data || {}),
        content: editedContent.value
      }
      isEditing.value = false
      await loadSkills()
    }
  } catch (error) {
    console.error('保存技能文档失败:', error)
    alert('保存技能文档失败: ' + error.message)
  } finally {
    saving.value = false
  }
}

const renderMarkdown = (content) => {
  if (!content) return ''
  try {
    return md.render(content)
  } catch (error) {
    console.error('Markdown渲染失败:', error)
    return '<pre>' + content + '</pre>'
  }
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.skills-management-view {
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

.search-box input::-webkit-search-cancel-button {
  cursor: pointer;
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

.refresh-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.refresh-icon.spinning {
  animation: skill-spin 0.9s linear infinite;
}

@keyframes skill-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 分类 tab */
.type-tabs {
  display: inline-flex;
  gap: 2px;
  margin: 14px 0 4px;
  padding: 3px;
  background: var(--bg-muted, #f8fafc);
  border: 1px solid var(--border-1, #f0f0f0);
  border-radius: var(--radius-lg, 8px);
}

.type-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: none;
  border-radius: var(--radius-md, 6px);
  background: transparent;
  color: var(--text-2, #666);
  font-size: var(--text-size-sm, 13px);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease), color var(--transition-fast, 0.15s ease);
}

.type-tab:hover {
  color: var(--text-1, #333);
}

.type-tab.active {
  background: var(--bg-container, #fff);
  color: var(--color-primary, #1890ff);
  font-weight: var(--font-weight-medium, 500);
  box-shadow: var(--shadow-1, 0 1px 2px rgba(31, 42, 68, 0.06));
}

.tab-count {
  color: var(--text-3, #999);
  font-size: var(--text-size-xs, 12px);
  font-weight: 400;
}

.type-tab.active .tab-count {
  color: var(--color-primary, #1890ff);
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

.skill-cards {
  background: var(--bg-container, #fff);
  border: 1px solid var(--border-2, #e8e8e8);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.skill-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  outline: none;
  transition: background var(--transition-fast, 0.15s ease);
}

.skill-card + .skill-card {
  border-top: 1px solid var(--border-1, #f0f0f0);
}

.skill-card:hover,
.skill-card:focus-visible {
  background: var(--bg-muted, #f8fafc);
}

.skill-icon {
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

.skill-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.skill-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.skill-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.skill-name {
  font-size: var(--text-size-base, 14px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--text-1, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-desc {
  font-size: var(--text-size-sm, 13px);
  color: var(--text-3, #999);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.5;
}

.skill-chevron {
  flex: none;
  width: 16px;
  height: 16px;
  fill: none;
  stroke: var(--text-disabled, #bfbfbf);
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke var(--transition-fast, 0.15s ease), transform var(--transition-fast, 0.15s ease);
}

.skill-card:hover .skill-chevron,
.skill-card:focus-visible .skill-chevron {
  stroke: var(--color-primary, #1890ff);
  transform: translateX(2px);
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

.chip-draft {
  color: var(--color-warning-text, #d48806);
  background: var(--color-warning-bg, #fffbe6);
  border: 1px solid #f5d78e;
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

/* 详情视图 */
.detail-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-1, #f0f0f0);
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: none;
  padding: 5px 10px 5px 6px;
  border: 1px solid var(--border-3, #d9d9d9);
  border-radius: var(--radius-md, 6px);
  background: var(--bg-container, #fff);
  color: var(--text-2, #666);
  font-size: var(--text-size-sm, 13px);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease), color var(--transition-fast, 0.15s ease);
}

.back-btn:hover {
  background: var(--bg-hover, #f5f5f5);
  color: var(--text-1, #333);
}

.back-btn svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.detail-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
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

.btn-primary:disabled {
  background: var(--color-primary-disabled, #e3effc);
  border-color: var(--color-primary-disabled, #e3effc);
  cursor: not-allowed;
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

.detail-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 12px;
  overflow-y: auto;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 10px 14px;
  background: var(--bg-muted, #f8fafc);
  border: 1px solid var(--border-1, #f0f0f0);
  border-radius: var(--radius-lg, 8px);
}

.meta-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.meta-label {
  flex: none;
  font-size: var(--text-size-xs, 12px);
  color: var(--text-3, #999);
}

.meta-value {
  font-size: var(--text-size-sm, 13px);
  color: var(--text-2, #666);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-value.mono {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-size-xs, 12px);
}

.editor-container {
  flex: 1;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-2, #e8e8e8);
  border-radius: var(--radius-lg, 8px);
  background: var(--bg-container, #fff);
  overflow: hidden;
}

.markdown-preview {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  line-height: var(--line-height-body, 1.6);
  color: var(--text-1, #333);
}

.markdown-editor {
  flex: 1;
  width: 100%;
  padding: 20px;
  border: none;
  outline: none;
  font-family: var(--font-mono, monospace);
  font-size: var(--text-size-sm, 13px);
  line-height: var(--line-height-body, 1.6);
  resize: none;
  background: var(--bg-muted, #f8fafc);
}

/* Markdown 预览样式 */
.markdown-preview :deep(h1) {
  font-size: 22px;
  margin: 8px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-1, #f0f0f0);
}

.markdown-preview :deep(h2) {
  font-size: 18px;
  margin: 20px 0 12px;
}

.markdown-preview :deep(h3) {
  font-size: 16px;
  margin: 16px 0 10px;
}

.markdown-preview :deep(p) {
  margin: 10px 0;
}

.markdown-preview :deep(code) {
  background: var(--bg-hover, #f5f5f5);
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
  font-family: var(--font-mono, monospace);
  font-size: 13px;
}

.markdown-preview :deep(pre) {
  background: var(--code-block-bg, #282c34);
  color: #e6e6e6;
  padding: 14px;
  border-radius: var(--radius-md, 6px);
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-preview :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  margin: 10px 0;
  padding-left: 24px;
}

.markdown-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 13px;
}

.markdown-preview :deep(table th),
.markdown-preview :deep(table td) {
  border: 1px solid var(--border-3, #d9d9d9);
  padding: 8px 12px;
  text-align: left;
}

.markdown-preview :deep(table th) {
  background: var(--bg-muted, #f8fafc);
  font-weight: 600;
}

@media (max-width: 720px) {
  .search-box {
    width: 170px;
  }

  .detail-title h2 {
    font-size: 16px;
  }
}
</style>
