<template>
  <div class="skills-management-view">
    <div v-if="!showDetailFullscreen" class="list-view">
      <header class="page-header">
        <div class="header-copy">
          <div>
            <h2>技能管理</h2>
            <p>按目录直接展示每个技能卡片</p>
          </div>
          <span class="stats" v-if="stats">
            共 {{ stats.total }} 个技能 / {{ stats.official }} 个正式技能 / {{ stats.drafts }} 个待审核草稿
          </span>
        </div>
        <div class="header-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="refreshingIndex"
            @click="refreshSkillIndex"
          >
            {{ refreshingIndex ? '刷新中...' : '刷新技能' }}
          </button>
          <div class="search-box">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="6.5" />
              <path d="M16 16l4.5 4.5" />
            </svg>
            <input
              v-model="searchKeyword"
              type="text"
              placeholder="搜索技能或描述"
            />
          </div>
        </div>
      </header>

      <section v-if="loadError" class="load-note">
        {{ loadError }}
      </section>

      <section class="summary-row" aria-label="技能概览">
        <article v-for="item in summaryCards" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.hint }}</small>
        </article>
      </section>

      <section v-if="loading" class="state-panel">
        <strong>加载中...</strong>
      </section>

      <section v-else-if="skillSections.length === 0" class="state-panel empty">
        <strong>{{ emptyStateText }}</strong>
        <span>尝试调整搜索词，或点击刷新重新生成索引。</span>
      </section>

      <section v-else class="skill-sections">
        <article
          v-for="section in skillSections"
          :key="section.id"
          class="skill-section"
        >
          <button
            type="button"
            class="section-toggle"
            :class="{ collapsed: isSectionCollapsed(section.id) }"
            :aria-expanded="!isSectionCollapsed(section.id)"
            @click="toggleSection(section.id)"
          >
            <div class="section-toggle-main">
              <div class="section-copy">
                <span class="section-badge">{{ section.badge }}</span>
                <h3>{{ section.title }}</h3>
                <p>{{ section.description }}</p>
              </div>
              <div class="section-meta">
                <span>{{ section.count }} 个技能</span>
                <span v-if="section.draftCount">{{ section.draftCount }} 个待审核</span>
              </div>
            </div>
            <span class="section-toggle-icon" aria-hidden="true">
              <svg viewBox="0 0 20 20">
                <path d="m6 8 4 4 4-4" />
              </svg>
            </span>
          </button>

          <div v-if="!isSectionCollapsed(section.id)" class="skill-grid">
            <article
              v-for="skill in section.items"
              :key="skill.file || skill.name"
              class="skill-card"
              :class="{ draft: skill.is_draft }"
              role="button"
              tabindex="0"
              @click="viewSkillDetail(skill)"
              @keydown.enter.prevent="viewSkillDetail(skill)"
              @keydown.space.prevent="viewSkillDetail(skill)"
            >
              <div class="skill-card-top">
                <div class="skill-card-title">
                  <span class="skill-name">{{ skill.name }}</span>
                  <span class="skill-badge" :class="{ draft: skill.is_draft }">
                    {{ skill.is_draft ? '待审核' : '正式' }}
                  </span>
                </div>
                <p class="skill-desc" :title="skill.description">{{ getSkillSummary(skill) }}</p>
              </div>

              <div class="skill-meta">
                <span class="skill-chip">{{ getSkillGroupLabel(skill) }}</span>
                <span class="skill-chip">{{ getSkillRelativePath(skill.file) }}</span>
              </div>

              <div class="skill-actions">
                <button type="button" class="btn-link" @click.stop="viewSkillDetail(skill)">
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
    </div>

    <div v-else class="detail-fullscreen">
      <div class="detail-header">
        <div class="header-copy detail-copy">
          <button class="btn-back" @click="closeDetailFullscreen">
            ← 返回列表
          </button>
          <div>
            <h2>{{ currentSkill?.name }}</h2>
            <div class="detail-badges">
              <span v-if="currentSkill?.is_draft" class="draft-badge">待审核草稿</span>
              <span v-if="currentSkill?.file" class="path-badge">{{ getSkillRelativePath(currentSkill.file) }}</span>
            </div>
          </div>
        </div>
        <div class="header-actions">
          <button v-if="!isEditing" class="btn-primary" @click="startEdit">
            编辑
          </button>
          <button v-else class="btn-primary" @click="saveSkill" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
          <button v-if="isEditing" class="btn-secondary" @click="cancelEdit">
            取消
          </button>
        </div>
      </div>

      <div class="detail-content">
        <div v-if="currentSkill" class="detail-info">
          <div class="info-row">
            <span class="info-label">技能名称</span>
            <span class="info-value">{{ currentSkill.name }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">{{ currentSkill?.is_draft ? '待审核草稿' : '正式技能' }}</span>
          </div>
          <div class="info-row" v-if="currentSkill.file">
            <span class="info-label">文件</span>
            <span class="info-value">{{ getSkillRelativePath(currentSkill.file) }}</span>
          </div>
        </div>

        <div class="editor-container">
          <div v-if="!isEditing" class="markdown-preview" v-html="renderMarkdown(currentSkill?.content)"></div>
          <textarea v-else v-model="editedContent" class="markdown-editor"></textarea>
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

const md = markdownIt({
  html: true,
  linkify: true,
  typographer: true
})
  .use(markdownItKatex)
  .use(markdownItMultimdTable)

const loading = ref(false)
const loadError = ref('')
const searchKeyword = ref('')
const officialSkills = ref([])
const draftSkills = ref([])
const showDetailFullscreen = ref(false)
const currentSkill = ref(null)
const isEditing = ref(false)
const editedContent = ref('')
const saving = ref(false)
const refreshingIndex = ref(false)
const collapsedSections = ref(new Set())

const skillGroupLabels = {
  root: '根目录技能',
  drafts: '待审核草稿',
  tender_market: '生态环境招投标市场分析'
}

const skillGroupDescriptions = {
  root: '直接位于技能根目录的单文件技能',
  drafts: '等待人工审核的技能草稿',
  tender_market: '按目录拆分的招投标市场分析技能包'
}

const normalizePath = (value) => String(value || '').replace(/\\/g, '/')

const getSkillRelativePath = (filePath) => {
  const normalized = normalizePath(filePath)
  const marker = '/docs/skills/'
  const index = normalized.lastIndexOf(marker)
  if (index >= 0) {
    return normalized.slice(index + marker.length)
  }
  return normalized.split('/').slice(-2).join('/')
}

const isDraftSkill = (skill) => {
  if (skill?.is_draft) return true
  return getSkillRelativePath(skill?.file).startsWith('.drafts/')
}

const getSkillGroupKey = (skill) => {
  if (isDraftSkill(skill)) return 'drafts'

  const relativePath = getSkillRelativePath(skill?.file)
  const segments = relativePath.split('/').filter(Boolean)
  if (segments.length <= 1) return 'root'

  const topLevel = segments[0]
  if (topLevel.toLowerCase() === 'skill_template.md' || topLevel.toLowerCase() === 'skills_index.md') {
    return 'root'
  }
  return topLevel
}

const getSkillGroupLabel = (skillOrKey) => {
  const key = typeof skillOrKey === 'string' ? skillOrKey : getSkillGroupKey(skillOrKey)
  return skillGroupLabels[key] || key.replace(/[_-]+/g, ' ')
}

const getSkillGroupDescription = (groupKey) => {
  return skillGroupDescriptions[groupKey] || '按目录展开的技能文档'
}

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

const getSkillIdentifier = (skill) => {
  if (skill?.id) return skill.id

  const filePath = normalizePath(skill?.file)
  const fileName = filePath.split('/').pop() || ''

  if (fileName.toLowerCase() === 'skill.md') {
    const pathParts = filePath.split('/').filter(Boolean)
    return pathParts[pathParts.length - 2] || fileName.replace(/\.md$/i, '')
  }
  return fileName.replace(/\.md$/i, '')
}

const getSkillSummary = (skill) => {
  const description = String(skill?.description || '').replace(/\s+/g, ' ').trim()
  if (!description) return '暂无技能描述'
  return description.length > 160 ? `${description.slice(0, 157)}...` : description
}

const matchesKeyword = (skill) => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return true

  return [
    skill.name,
    skill.description,
    getSkillGroupLabel(skill),
    getSkillRelativePath(skill.file)
  ].some((value) => String(value ?? '').toLowerCase().includes(keyword))
}

const sortSkills = (items) => {
  return [...items].sort((left, right) => {
    const leftName = String(left.name ?? '')
    const rightName = String(right.name ?? '')
    return leftName.localeCompare(rightName, 'zh-Hans-CN')
  })
}

const filteredOfficialSkills = computed(() => officialSkills.value.filter(matchesKeyword))
const filteredDraftSkills = computed(() => draftSkills.value.filter(matchesKeyword))

const buildOfficialSections = computed(() => {
  const grouped = new Map()

  filteredOfficialSkills.value.forEach((skill) => {
    const key = getSkillGroupKey(skill)
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key).push(skill)
  })

  const orderedKeys = [
    ...(grouped.has('root') ? ['root'] : []),
    ...[...grouped.keys()]
      .filter((key) => key !== 'root')
      .sort((left, right) => {
        return getSkillGroupLabel(left).localeCompare(getSkillGroupLabel(right), 'zh-Hans-CN')
      })
  ]

  return orderedKeys
    .filter((key) => grouped.has(key))
    .map((key) => {
      const items = sortSkills(grouped.get(key) || [])
      return {
        id: `official-${key}`,
        badge: '正式',
        title: getSkillGroupLabel(key),
        description: getSkillGroupDescription(key),
        count: items.length,
        draftCount: 0,
        items
      }
    })
})

const buildDraftSection = computed(() => {
  const items = sortSkills(filteredDraftSkills.value)
  return {
    id: 'drafts',
    badge: '草稿',
    title: getSkillGroupLabel('drafts'),
    description: getSkillGroupDescription('drafts'),
    count: items.length,
    draftCount: items.length,
    items
  }
})

const skillSections = computed(() => {
  const sections = [...buildOfficialSections.value]
  if (buildDraftSection.value.items.length > 0) {
    sections.push(buildDraftSection.value)
  }
  return sections
})

const stats = computed(() => {
  const official = officialSkills.value.length
  const drafts = draftSkills.value.length
  return {
    total: official + drafts,
    official,
    drafts
  }
})

const summaryCards = computed(() => [
  {
    label: '技能总数',
    value: stats.value.total,
    hint: '正式技能 + 草稿'
  },
  {
    label: '正式技能',
    value: stats.value.official,
    hint: '已发布文档'
  },
  {
    label: '草稿数量',
    value: stats.value.drafts,
    hint: '待审核内容'
  },
  {
    label: '分类数',
    value: skillSections.value.length,
    hint: '页面直接按分类展开'
  }
])

const emptyStateText = computed(() => {
  return searchKeyword.value.trim()
    ? '未找到匹配的技能'
    : '当前没有可展示的技能'
})

const loadSkills = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [officialResult, draftResult] = await Promise.allSettled([
      getSkillsList(),
      getSkillDraftsList()
    ])

    const errors = []

    if (officialResult.status === 'fulfilled' && officialResult.value.success) {
      officialSkills.value = officialResult.value.data?.skills || []
    } else {
      officialSkills.value = []
      errors.push('正式技能列表加载失败')
    }

    if (draftResult.status === 'fulfilled' && draftResult.value.success) {
      draftSkills.value = draftResult.value.data?.drafts || []
    } else {
      draftSkills.value = []
      errors.push('草稿列表加载失败')
    }

    loadError.value = errors.join('；')
  } catch (error) {
    console.error('加载技能列表失败:', error)
    loadError.value = error.message || '加载技能列表失败'
    alert('加载技能列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
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

const viewSkillDetail = async (skill) => {
  try {
    const skillIdentifier = getSkillIdentifier(skill)
    const loader = isDraftSkill(skill) ? getSkillDraftDetail : getSkillDetail
    const data = await loader(skillIdentifier)
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
    const data = isDraftSkill(currentSkill.value)
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
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 20px 24px 28px;
  background: #f5f7fb;
  color: #24333e;
}

.list-view {
  display: grid;
  gap: 16px;
}

.page-header,
.detail-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
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

.load-note {
  padding: 10px 12px;
  border: 1px solid #f0d7a3;
  border-radius: 10px;
  background: #fff8e5;
  color: #8a5f12;
  font-size: 12px;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
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

.skill-sections {
  display: grid;
  gap: 18px;
}

.skill-section {
  display: grid;
  gap: 12px;
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

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.skill-card {
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

.skill-card:hover,
.skill-card:focus-visible {
  border-color: #1590a0;
  box-shadow: 0 12px 28px rgba(16, 82, 94, 0.08);
  transform: translateY(-1px);
  outline: none;
}

.skill-card.draft {
  background: #fbfcfd;
}

.skill-card-top {
  display: grid;
  gap: 8px;
  min-height: 0;
  flex: 1;
}

.skill-card-title {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  min-width: 0;
}

.skill-name {
  font-size: 15px;
  font-weight: 700;
  color: #183241;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-badge,
.draft-badge,
.path-badge {
  flex: none;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.skill-badge {
  color: #0d7c49;
  background: #e7f8ef;
}

.skill-badge.draft,
.draft-badge {
  color: #8a5f12;
  background: #fff3d8;
}

.path-badge {
  color: #5f7181;
  background: #edf4f8;
}

.skill-desc {
  margin: 0;
  color: #5e7384;
  font-size: 13px;
  line-height: 1.6;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.skill-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.skill-chip {
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

.skill-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: auto;
}

.btn-primary,
.btn-secondary,
.btn-back,
.btn-link {
  border: 0;
  border-radius: 9px;
  cursor: pointer;
  font: inherit;
  transition: background-color 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.btn-primary {
  padding: 8px 14px;
  border: 1px solid #1590a0;
  background: #1590a0;
  color: #fff;
}

.btn-primary:hover {
  background: #0f7b8a;
}

.btn-primary:disabled {
  opacity: 0.58;
  cursor: default;
}

.btn-secondary,
.btn-back {
  padding: 8px 12px;
  border: 1px solid #d8e1e8;
  background: #fff;
  color: #405868;
}

.btn-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: transparent;
  color: #0f7b8a;
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

.btn-secondary:hover,
.btn-back:hover,
.btn-link:hover {
  border-color: #1590a0;
  color: #0f7b8a;
}

.detail-fullscreen {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.detail-copy {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.detail-copy h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 650;
  color: #15232d;
}

.detail-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.detail-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.detail-info {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 16px;
  border: 1px solid #dce5ec;
  border-radius: 12px;
  background: #fff;
}

.info-row {
  display: grid;
  gap: 6px;
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

.editor-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border: 1px solid #dce5ec;
  border-radius: 12px;
  background: #fff;
}

.markdown-preview {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 20px;
  line-height: 1.7;
  color: #24333e;
}

.markdown-editor {
  flex: 1;
  width: 100%;
  min-height: 0;
  padding: 20px;
  border: 0;
  outline: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  background: #fafbfd;
}

.markdown-preview :deep(h1) {
  font-size: 24px;
  margin: 20px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.markdown-preview :deep(h2) {
  font-size: 20px;
  margin: 18px 0 14px;
}

.markdown-preview :deep(h3) {
  font-size: 18px;
  margin: 16px 0 12px;
}

.markdown-preview :deep(p) {
  margin: 12px 0;
}

.markdown-preview :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 14px;
}

.markdown-preview :deep(pre) {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-preview :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
}

.markdown-preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.markdown-preview :deep(table th),
.markdown-preview :deep(table td) {
  border: 1px solid #ddd;
  padding: 8px 12px;
  text-align: left;
}

.markdown-preview :deep(table th) {
  background: #f5f5f5;
  font-weight: 600;
}

@media (max-width: 820px) {
  .page-header,
  .detail-header {
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

  .detail-info {
    gap: 14px;
  }
}
</style>
