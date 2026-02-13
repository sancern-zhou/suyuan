<template>
  <div class="report-generation-panel">
    <div class="panel-header">
      <h3>报告生成</h3>
      <p class="subtitle">基于模板智能生成专业报告</p>
    </div>

    <div class="panel-content">
      <!-- 模板选择区域 -->
      <div class="template-section">
        <h4>选择模板</h4>
        <div class="template-options">
          <div class="option-card" :class="{ active: selectedMode === 'upload' }" @click="selectedMode = 'upload'">
            <div class="option-icon">📄</div>
            <div class="option-info">
              <h5>上传模板文件</h5>
              <p>上传历史报告作为模板</p>
            </div>
          </div>
          <div class="option-card" :class="{ active: selectedMode === 'saved' }" @click="selectedMode = 'saved'">
            <div class="option-icon">📚</div>
            <div class="option-info">
              <h5>使用保存的模板</h5>
              <p>从模板库中选择</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 上传模式 -->
      <div v-if="selectedMode === 'upload'" class="upload-section">
        <h4>上传模板文件</h4>
        <div class="upload-area" @drop.prevent="handleDrop" @dragover.prevent @click="triggerFileSelect">
          <input ref="fileInput" type="file" accept=".md,.txt,.docx" style="display: none" @change="handleFileSelect" />
          <div class="upload-content">
            <div class="upload-icon">⬆️</div>
            <p>拖拽文件到此处，或点击选择文件</p>
            <p class="upload-hint">支持 .md, .txt, .docx 格式</p>
          </div>
        </div>
        <div v-if="uploadedFile" class="file-info">
          <span>📎 {{ uploadedFile.name }}</span>
          <button @click="clearFile">×</button>
        </div>
      </div>

      <!-- 保存的模板列表 -->
      <div v-if="selectedMode === 'saved'" class="saved-templates-section">
        <h4>已保存的模板</h4>
        <div class="templates-list">
          <div v-if="loadingTemplates" class="loading">加载中...</div>
          <div v-else-if="savedTemplates.length === 0" class="empty-state">
            <p>暂无可用模板</p>
          </div>
          <div v-else>
            <div
              v-for="template in savedTemplates"
              :key="template.id"
              class="template-item"
              :class="{ selected: selectedTemplate?.id === template.id }"
              @click="selectedTemplate = template"
            >
              <div class="template-info">
                <h5>{{ template.name }}</h5>
                <p>{{ template.description }}</p>
              </div>
              <div class="template-meta">
                <span class="usage-count">使用 {{ template.usage_count }} 次</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 时间范围设置 -->
      <div class="time-range-section">
        <h4>设置时间范围</h4>
        <div class="time-inputs">
          <div class="time-input">
            <label>开始日期</label>
            <input v-model="timeRange.start" type="date" />
          </div>
          <div class="time-input">
            <label>结束日期</label>
            <input v-model="timeRange.end" type="date" />
          </div>
        </div>
      </div>

      <!-- 生成选项 -->
      <div class="options-section">
        <h4>生成选项</h4>
        <div class="checkbox-group">
          <label class="checkbox-item">
            <input v-model="options.includeAnalysis" type="checkbox" />
            <span>包含LLM分析</span>
          </label>
          <label class="checkbox-item">
            <input v-model="options.includeCharts" type="checkbox" />
            <span>包含图表</span>
          </label>
        </div>
      </div>

      <!-- 生成按钮 -->
      <div class="action-section">
        <button
          class="generate-btn"
          :disabled="!canGenerate || isGenerating"
          @click="startGeneration"
        >
          <span v-if="!isGenerating">🚀 开始生成报告</span>
          <span v-else>生成中...</span>
        </button>
      </div>

      <!-- 生成进度 -->
      <GenerationProgress
        v-if="isGenerating"
        :progress="generationProgress"
        :current-phase="currentPhase"
        :events="generationEvents"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { generateFromTemplateFile, generateFromTemplateAgent, generateFromSavedTemplate, listTemplates } from '@/services/reportApi'
import GenerationProgress from '@/components/report/GenerationProgress.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { useReactStore } from '@/stores/reactStore'

const props = defineProps({
  assistantMode: {
    type: String,
    default: 'report-generation-expert'
  }
})

// 状态管理
const reactStore = useReactStore()
const selectedMode = ref('upload') // 'upload' | 'saved'
const fileInput = ref(null)
const uploadedFile = ref(null)
const selectedTemplate = ref(null)
const savedTemplates = ref([])
const loadingTemplates = ref(false)
const isGenerating = ref(false)
const generationProgress = ref(0)
const currentPhase = ref('')
const generationEvents = ref([])

// 时间范围和选项
const timeRange = ref({
  start: new Date(new Date().setDate(new Date().getDate() - 30)).toISOString().split('T')[0],
  end: new Date().toISOString().split('T')[0]
})

const options = ref({
  includeAnalysis: true,
  includeCharts: false
})

// 计算属性
const canGenerate = computed(() => {
  if (selectedMode.value === 'upload') {
    return uploadedFile.value !== null
  } else {
    return selectedTemplate.value !== null
  }
})

// 方法
const triggerFileSelect = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    uploadedFile.value = file
  }
}

const handleDrop = (event) => {
  const file = event.dataTransfer.files[0]
  if (
    file &&
    (file.type === 'text/plain' ||
      file.name.endsWith('.md') ||
      file.name.endsWith('.txt') ||
      file.name.endsWith('.docx'))
  ) {
    uploadedFile.value = file
  }
}

const clearFile = () => {
  uploadedFile.value = null
}

const loadTemplates = async () => {
  loadingTemplates.value = true
  try {
    savedTemplates.value = await listTemplates()
  } catch (error) {
    console.error('Failed to load templates:', error)
    savedTemplates.value = []
  } finally {
    loadingTemplates.value = false
  }
}

const startGeneration = async () => {
  if (!canGenerate.value) return

  // ===== 主对话区：记录本次生成请求与进度 =====
  const rangeText = `${timeRange.value.start} 至 ${timeRange.value.end}`
  const templateText =
    selectedMode.value === 'upload'
      ? (uploadedFile.value?.name || '上传模板文件')
      : `模板：${selectedTemplate.value?.name || selectedTemplate.value?.id}`

  // 用户意图消息
  reactStore.addMessage(
    'user',
    `生成空气质量报告：${templateText}，时间范围 ${rangeText}`
  )

  // 进度提示消息
  reactStore.addMessage(
    'thought',
    '已收到模板，正在调用模板报告专家生成临时报告，请稍候…',
    { source: 'template_report_agent' }
  )

  // ===== 右侧面板：保持原有进度与按钮状态 =====
  isGenerating.value = true
  generationProgress.value = 0
  currentPhase.value = '准备生成'
  generationEvents.value = []

  try {
    let result
    if (selectedMode.value === 'upload') {
      // 直接将文件传给后端，由后端负责 docx/md/txt -> Markdown 转换
      const displayRange = `${timeRange.value.start}至${timeRange.value.end}`
      const { reportContent, sessionId } = await generateFromTemplateFile(uploadedFile.value, {
        start: timeRange.value.start,
        end: timeRange.value.end,
        display: displayRange
      })
      result = reportContent

      // 如果后端返回了 ReAct 会话ID，则将其接入当前reactStore，
      // 这样后续在“报告生成场景”中的对话可以基于同一session进行ReAct连续对话。
      if (sessionId) {
        reactStore.sessionId = sessionId
      }
    } else {
      // 固定模板走原有保存模板流程
      result = await generateFromSavedTemplate(selectedTemplate.value.id, {
        time_range: timeRange.value,
        options: options.value
      })
    }

    currentPhase.value = '生成完成'
    generationProgress.value = 100

    // 主对话区：以最终答案形式展示完整报告内容（Markdown）
    reactStore.addMessage(
      'final',
      result,
      {
        source: 'template_report_agent',
        time_range: { ...timeRange.value },
        template:
          selectedMode.value === 'upload'
            ? { type: 'file', name: uploadedFile.value?.name }
            : {
                type: 'saved',
                id: selectedTemplate.value.id,
                name: selectedTemplate.value.name
              }
      }
    )
  } catch (error) {
    console.error('Report generation failed:', error)
    currentPhase.value = '生成失败'

    // 主对话区：展示错误信息
    reactStore.addMessage(
      'error',
      `报告生成失败：${error?.message || String(error)}`,
      { source: 'template_report_agent' }
    )
  } finally {
    isGenerating.value = false
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style lang="scss" scoped>
.report-generation-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;

  h3 {
    margin: 0 0 4px;
    font-size: 18px;
    color: #1f2a44;
  }

  .subtitle {
    margin: 0;
    font-size: 13px;
    color: #7a86a0;
  }
}

.panel-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.template-section,
.upload-section,
.saved-templates-section,
.time-range-section,
.options-section {
  h4 {
    margin: 0 0 12px;
    font-size: 14px;
    color: #1f2a44;
    font-weight: 600;
  }
}

.template-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.option-card {
  border: 1px solid #e4e7f0;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  gap: 12px;
  align-items: center;

  &:hover {
    border-color: #c5d4e8;
  }

  &.active {
    border-color: #1976d2;
    background: #e9f3ff;
  }

  .option-icon {
    font-size: 24px;
  }

  .option-info {
    flex: 1;

    h5 {
      margin: 0 0 4px;
      font-size: 14px;
      color: #1f2a44;
    }

    p {
      margin: 0;
      font-size: 12px;
      color: #7a86a0;
    }
  }
}

.upload-area {
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #1976d2;
    background: #f5f5f5;
  }

  .upload-content {
    .upload-icon {
      font-size: 32px;
      margin-bottom: 8px;
    }

    p {
      margin: 0;
      color: #666;
      font-size: 14px;

      &.upload-hint {
        font-size: 12px;
        color: #999;
        margin-top: 4px;
      }
    }
  }
}

.file-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f0f0f0;
  border-radius: 4px;
  margin-top: 8px;

  button {
    border: none;
    background: #ff4d4f;
    color: #fff;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

.templates-list {
  max-height: 240px;
  overflow-y: auto;
}

.template-item {
  border: 1px solid #e4e7f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #c5d4e8;
  }

  &.selected {
    border-color: #1976d2;
    background: #e9f3ff;
  }

  .template-info {
    h5 {
      margin: 0 0 4px;
      font-size: 14px;
      color: #1f2a44;
    }

    p {
      margin: 0;
      font-size: 12px;
      color: #7a86a0;
    }
  }

  .template-meta {
    margin-top: 8px;
    display: flex;
    justify-content: flex-end;

    .usage-count {
      font-size: 11px;
      color: #999;
    }
  }
}

.time-inputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.time-input {
  display: flex;
  flex-direction: column;
  gap: 4px;

  label {
    font-size: 12px;
    color: #666;
  }

  input {
    padding: 8px;
    border: 1px solid #d9d9d9;
    border-radius: 4px;
    font-size: 14px;
  }
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;

  input[type="checkbox"] {
    width: 16px;
    height: 16px;
  }

  span {
    font-size: 14px;
    color: #1f2a44;
  }
}

.action-section {
  margin-top: auto;
}

.generate-btn {
  width: 100%;
  padding: 12px 24px;
  background: #1976d2;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: #1565c0;
  }

  &:disabled {
    background: #ccc;
    cursor: not-allowed;
  }
}

.preview-section {
  margin-top: 24px;

  h4 {
    margin: 0 0 12px;
    font-size: 14px;
    color: #1f2a44;
    font-weight: 600;
  }

  .report-preview {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    padding: 16px;
    background: #fafafa;
  }

  .preview-actions {
    display: flex;
    gap: 12px;
    margin-top: 12px;

    button {
      padding: 8px 16px;
      border: 1px solid #d9d9d9;
      border-radius: 6px;
      background: #fff;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        border-color: #1976d2;
        color: #1976d2;
      }
    }
  }
}

.loading,
.empty-state {
  text-align: center;
  padding: 24px;
  color: #999;
  font-size: 14px;
}
</style>
