<template>
  <div class="skills-management-view">
    <!-- 列表视图 -->
    <div v-if="!showDetailFullscreen" class="list-view">
      <header class="page-header">
        <div class="header-left">
          <h2>技能管理</h2>
          <span class="stats" v-if="stats">
            共 {{ stats.total }} 个技能
          </span>
        </div>
        <div class="header-actions">
          <button class="btn-secondary" @click="refreshIndex">刷新索引</button>
          <button class="btn-secondary" @click="refreshList">刷新列表</button>
          <button class="btn-close" @click="$emit('close')">关闭</button>
          <div class="search-box">
            <input
              v-model="searchKeyword"
              type="text"
              placeholder="搜索技能..."
              @input="handleSearchDebounced"
            />
          </div>
        </div>
      </header>

      <div class="main-content">
        <div v-if="loading" class="loading-state">加载中...</div>

        <div v-else-if="filteredSkills.length === 0" class="empty-state">
          {{ searchKeyword ? '未找到匹配的技能' : '暂无技能文档' }}
        </div>

        <div v-else class="skills-list">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            class="skill-list-item"
            @click="viewSkillDetail(skill)"
          >
            <span class="skill-name">{{ skill.name }}</span>
            <span class="skill-arrow">→</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 全屏详情视图 -->
    <div v-else class="detail-fullscreen">
      <div class="detail-header">
        <div class="header-left">
          <button class="btn-back" @click="closeDetailFullscreen">
            ← 返回列表
          </button>
          <h2>{{ currentSkill?.name }}</h2>
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
import { getSkillsList, getSkillDetail, refreshSkillsIndex, saveSkillDetail } from '@/api/skillsManagement'
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
const skills = ref([])
const showDetailFullscreen = ref(false)
const currentSkill = ref(null)
const isEditing = ref(false)
const editedContent = ref('')
const saving = ref(false)
let searchDebounceTimer = null

const stats = computed(() => ({
  total: skills.value.length
}))

const filteredSkills = computed(() => {
  return skills.value
})

const loadSkills = async () => {
  loading.value = true
  try {
    const data = await getSkillsList(searchKeyword.value)
    if (data.success) {
      skills.value = data.data.skills
    }
  } catch (error) {
    console.error('加载技能列表失败:', error)
    alert('加载技能列表失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const handleSearchDebounced = () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    loadSkills()
  }, 300)
}

const getFileName = (filePath) => {
  return filePath.split('/').pop()
}

const viewSkillDetail = async (skill) => {
  try {
    const fileName = getFileName(skill.file).replace('.md', '')
    const data = await getSkillDetail(fileName)
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
    const fileName = getFileName(currentSkill.value.file).replace('.md', '')
    const data = await saveSkillDetail(fileName, editedContent.value)

    if (data.success) {
      alert('保存成功')
      currentSkill.value.content = editedContent.value
      isEditing.value = false
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

const refreshIndex = async () => {
  if (!confirm('确定要刷新技能索引吗？')) return

  try {
    const data = await refreshSkillsIndex()
    if (data.success) {
      alert('索引刷新成功')
      await loadSkills()
    }
  } catch (error) {
    console.error('刷新索引失败:', error)
    alert('刷新索引失败: ' + error.message)
  }
}

const refreshList = () => {
  loadSkills()
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.skills-management-view {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

/* 列表视图样式 */
.list-view {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 15px;
}

.header-left h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.stats {
  color: #666;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.btn-secondary {
  padding: 8px 16px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: #1976d2;
  color: white;
}

.btn-close {
  padding: 8px 16px;
  border: 1px solid #666;
  background: white;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: #666;
  color: white;
}

.btn-primary {
  padding: 8px 16px;
  border: 1px solid #1976d2;
  background: #1976d2;
  color: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #1565c0;
}

.btn-primary:disabled {
  background: #90caf9;
  cursor: not-allowed;
}

.btn-back {
  padding: 8px 16px;
  border: 1px solid #666;
  background: white;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-back:hover {
  background: #666;
  color: white;
}

.search-box input {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  width: 200px;
  font-size: 14px;
}

.main-content {
  min-height: 400px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
  font-size: 16px;
}

.skills-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.skill-list-item:hover {
  background: #f5f5f5;
  border-color: #1976d2;
}

.skill-list-item .skill-name {
  font-size: 15px;
  font-weight: 500;
  color: #333;
}

.skill-arrow {
  font-size: 18px;
  color: #999;
  transition: transform 0.2s;
}

.skill-list-item:hover .skill-arrow {
  transform: translateX(4px);
  color: #1976d2;
}

/* 全屏详情视图样式 */
.detail-fullscreen {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
  margin-bottom: 20px;
}

.detail-header .header-left {
  display: flex;
  align-items: center;
  gap: 15px;
}

.detail-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.detail-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-info {
  padding: 16px;
  background: #f9f9f9;
  border-radius: 6px;
}

.info-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row .info-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.info-row .info-value {
  font-size: 14px;
  color: #333;
}

.editor-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: white;
}

.markdown-preview {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  line-height: 1.6;
  color: #333;
}

.markdown-editor {
  flex: 1;
  width: 100%;
  padding: 20px;
  border: none;
  outline: none;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  background: #fafafa;
}

/* Markdown 预览样式 */
.markdown-preview :deep(h1) {
  font-size: 24px;
  margin: 20px 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.markdown-preview :deep(h2) {
  font-size: 20px;
  margin: 18px 0 14px 0;
}

.markdown-preview :deep(h3) {
  font-size: 18px;
  margin: 16px 0 12px 0;
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
</style>
