<template>
  <div class="skills-management-view">
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

      <div v-else class="skills-grid">
        <div
          v-for="skill in filteredSkills"
          :key="skill.name"
          class="skill-card"
          @click="viewSkillDetail(skill)"
        >
          <div class="skill-card-header">
            <span class="skill-name">{{ skill.name }}</span>
          </div>
          <div class="skill-desc">{{ skill.description }}</div>
          <div class="skill-meta">
            <span class="skill-file">{{ getFileName(skill.file) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 技能详情对话框 -->
    <div v-if="showDetailDialog" class="dialog-overlay" @click.self="showDetailDialog = false">
      <div class="dialog dialog-wide">
        <div class="dialog-header">
          <h3>{{ currentSkill?.name }}</h3>
          <button class="btn-close" @click="showDetailDialog = false">×</button>
        </div>
        <div class="dialog-body" v-if="currentSkill">
          <div class="skill-detail-section">
            <h4>基本信息</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">技能名称</span>
                <span class="info-value">{{ currentSkill.name }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">描述</span>
                <span class="info-value">{{ currentSkill.description }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">文件</span>
                <span class="info-value">{{ getFileName(currentSkill.file) }}</span>
              </div>
            </div>
          </div>

          <div class="skill-detail-section">
            <h4>技能文档内容</h4>
            <div class="markdown-content" v-html="renderMarkdown(currentSkill.content)"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getSkillsList, getSkillDetail, refreshSkillsIndex } from '@/api/skillsManagement'
import markdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import markdownItMultimdTable from 'markdown-it-multimd-table'

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
const showDetailDialog = ref(false)
const currentSkill = ref(null)
let searchDebounceTimer = null

const stats = computed(() => ({
  total: skills.value.length
}))

const filteredSkills = computed(() => {
  // 已经通过API过滤了，这里直接返回
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
  // 防抖处理搜索
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
      showDetailDialog.value = true
    }
  } catch (error) {
    console.error('加载技能详情失败:', error)
    alert('加载技能详情失败: ' + error.message)
  }
}

const renderMarkdown = (content) => {
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

.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.skill-card {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.skill-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.skill-card-header {
  margin-bottom: 12px;
}

.skill-name {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.skill-desc {
  color: #666;
  font-size: 14px;
  line-height: 1.5;
  margin-bottom: 12px;
  min-height: 40px;
}

.skill-meta {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #999;
}

.skill-file {
  font-family: monospace;
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
}

/* 对话框样式 */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 8px;
  max-width: 900px;
  width: 90%;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.dialog-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #333;
}

.btn-close {
  background: none;
  border: none;
  font-size: 28px;
  color: #999;
  cursor: pointer;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-close:hover {
  color: #333;
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.skill-detail-section {
  margin-bottom: 24px;
}

.skill-detail-section h4 {
  margin: 0 0 12px 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  color: #666;
}

.info-value {
  font-size: 14px;
  color: #333;
}

.markdown-content {
  line-height: 1.6;
  color: #333;
}

.markdown-content :deep(h1) {
  font-size: 24px;
  margin: 20px 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.markdown-content :deep(h2) {
  font-size: 20px;
  margin: 18px 0 14px 0;
}

.markdown-content :deep(h3) {
  font-size: 18px;
  margin: 16px 0 12px 0;
}

.markdown-content :deep(p) {
  margin: 12px 0;
}

.markdown-content :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 14px;
}

.markdown-content :deep(pre) {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 12px 0;
}

.markdown-content :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
}

.markdown-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.markdown-content :deep(table th),
.markdown-content :deep(table td) {
  border: 1px solid #ddd;
  padding: 8px 12px;
  text-align: left;
}

.markdown-content :deep(table th) {
  background: #f5f5f5;
  font-weight: 600;
}
</style>
