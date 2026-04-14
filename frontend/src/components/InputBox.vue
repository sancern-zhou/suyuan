<template>
  <div class="input-area">
    <div class="input-container">
      <!-- 附件预览区域 -->
      <div v-if="attachments.length > 0" class="attachments-preview">
        <div v-for="(attachment, index) in attachments" :key="index" class="attachment-item">
          <img
            v-if="attachment.type === 'image' && attachment.preview"
            :src="attachment.preview"
            class="attachment-preview-image"
            @click="previewImage(attachment)"
          />
          <div v-else class="attachment-file-icon">
            <svg viewBox="0 0 24 24" class="file-icon-svg">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="none" stroke="currentColor" stroke-width="2"/>
              <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span class="attachment-file-name">{{ attachment.name }}</span>
          </div>
          <button class="attachment-remove" @click="removeAttachment(index)" :disabled="attachment.uploading">
            <svg viewBox="0 0 24 24" class="remove-icon">
              <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="2"/>
              <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2"/>
            </svg>
          </button>
          <div v-if="attachment.uploading" class="attachment-uploading">上传中...</div>
        </div>
      </div>

      <div
        class="input-wrapper"
        :class="{ 'drag-over': isDragOver }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <!-- 工作流工具提示 -->
        <div v-if="showWorkflowTools" class="workflow-tools-hint">
          <span
            v-for="tool in workflowTools"
            :key="tool.id"
            class="workflow-tool-item"
            :class="{ active: highlightedTool === tool.id }"
            @mousedown="selectWorkflowTool(tool, $event)"
            @mouseenter="highlightedTool = tool.id"
          >
            {{ tool.name }}
          </span>
        </div>

        <textarea
          ref="textareaRef"
          v-model="localValue"
          class="input-field"
          :placeholder="placeholder"
          :disabled="disabled"
          @keydown="handleKeydown"
          @input="handleInput"
          @focus="handleFocus"
          @blur="handleBlur"
          @paste="handlePaste"
          rows="1"
        />

        <div class="action-group">
          <button
            class="kb-toggle-button"
            :class="{ 'kb-active': showKnowledgeBaseSelector }"
            @click="toggleKnowledgeBase"
            title="选择知识库"
          >
            <svg viewBox="0 0 24 24" class="kb-icon">
              <path d="M4 4h16v4H4V4zm0 6h16v10H4V10zm4 2v6h8v-6H8z" fill="currentColor"/>
            </svg>
          </button>

          <label class="upload-label" title="上传文件或图片">
            <input
              ref="fileInputRef"
              type="file"
              @change="handleFileSelect"
              accept="image/*,.pdf,.txt,.md,.json,.csv,.docx,.xlsx,.pptx"
            />
            <span class="upload-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path
                  d="M8.5 13.5 17 5a3.5 3.5 0 0 1 5 5l-10 10a5.5 5.5 0 0 1-7.8-7.8L9 6"
                  fill="none"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
          </label>

          <button
            class="action-button"
            :class="{ 'pause-button': isAnalyzing, 'send-button': !isAnalyzing }"
            @click="isAnalyzing ? handlePause() : handleSend()"
            :disabled="(!localValue.trim() && attachments.length === 0 && !isAnalyzing) || disabled"
            :title="isAnalyzing ? '暂停分析 (Esc)' : '发送 (Enter)'"
          >
            <svg v-if="!isAnalyzing" viewBox="0 0 24 24" class="send-icon">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/>
            </svg>
            <span v-else>暂停</span>
          </button>
        </div>
      </div>

      <!-- 知识库选择器 -->
      <KnowledgeBaseSelector v-if="showKnowledgeBaseSelector" />

      <div class="feature-buttons">
        <!-- Agent模式选择器（仅在通用Agent模式显示） -->
        <AgentModeSelector
          v-if="assistantMode === 'general-agent'"
          v-model="agentMode"
          @update:modelValue="handleAgentModeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import KnowledgeBaseSelector from '@/components/knowledge/KnowledgeBaseSelector.vue'
import AgentModeSelector from '@/components/AgentModeSelector.vue'
import { uploadChatFile, validateFile, createImagePreview, getFileUrl } from '@/services/uploadApi'

const kbStore = useKnowledgeBaseStore()

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '输入您的问题... (支持Ctrl+V粘贴图片和文件)'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  useReranker: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'send', 'pause', 'update:useReranker', 'update:agentMode'])

const textareaRef = ref(null)
const fileInputRef = ref(null)
const localValue = ref(props.modelValue)
const showKnowledgeBaseSelector = ref(false)
const showWorkflowTools = ref(false)
const atSymbolIndex = ref(-1)  // 记录@符号的位置
const highlightedTool = ref(null)  // 高亮的工具
const useReranker = ref(props.useReranker)  // 精准检索开关状态
// ✅ 使用统一的模式键名，与 store.currentMode 保持一致
const agentMode = ref(localStorage.getItem('current-mode') || 'assistant')
const attachments = ref([])  // 附件列表
const previewedImage = ref(null)  // 当前预览的图片
const isDragOver = ref(false)  // 拖拽状态

// 工作流工具列表
const workflowTools = [
  { id: 'quick_tracing_workflow', name: '快速溯源' },
  { id: 'standard_analysis_workflow', name: '标准分析' },
  { id: 'deep_trace_workflow', name: '深度溯源' },
  { id: 'knowledge_qa_workflow', name: '知识问答' }
]

const toggleKnowledgeBase = () => {
  showKnowledgeBaseSelector.value = !showKnowledgeBaseSelector.value
}

const handleAgentModeChange = (newMode) => {
  // ✅ 处理Agent模式变化
  agentMode.value = newMode
  emit('update:agentMode', newMode)
  console.log('[InputBox] Agent mode changed:', newMode)
}

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
  }
}

const handleInput = (e) => {
  autoResize()

  const textarea = textareaRef.value
  if (!textarea) return

  const value = localValue.value
  const cursorPosition = textarea.selectionStart

  console.log('[InputBox] handleInput:', {
    value,
    cursorPosition,
    charAtCursor: value[cursorPosition - 1],
    showWorkflowTools: showWorkflowTools.value
  })

  // 检查是否刚输入了@符号（且在行首或前面有空格）
  if (value[cursorPosition - 1] === '@' && (cursorPosition === 1 || value[cursorPosition - 2] === ' ' || value[cursorPosition - 2] === '\n')) {
    atSymbolIndex.value = cursorPosition - 1
    showWorkflowTools.value = true
    highlightedTool.value = null
    console.log('[InputBox] @ detected, atSymbolIndex:', atSymbolIndex.value)
  } else if (showWorkflowTools.value) {
    // 如果工具列表已显示，检查是否删除了@符号
    if (atSymbolIndex.value >= 0 && value[atSymbolIndex.value] !== '@') {
      showWorkflowTools.value = false
      atSymbolIndex.value = -1
      highlightedTool.value = null
      console.log('[InputBox] @ removed, hiding tools')
    }
  }
}

const selectWorkflowTool = (tool, event) => {
  const toolName = tool.name

  console.log('[InputBox] selectWorkflowTool called:', {
    toolName,
    currentLocalValue: localValue.value,
    event
  })

  // 阻止默认行为和冒泡，防止输入框失去焦点
  if (event) {
    event.preventDefault()
    event.stopPropagation()
  }

  // 直接替换@为工具名称
  let newValue = localValue.value.replace('@', '@' + toolName + ' ')

  console.log('[InputBox] New value:', newValue)

  // 更新 localValue
  localValue.value = newValue

  showWorkflowTools.value = false
  atSymbolIndex.value = -1
  highlightedTool.value = null

  // 设置光标位置到工具名称后面
  nextTick(() => {
    const newPosition = toolName.length + 2  // @ + 工具名 + 空格
    console.log('[InputBox] Setting cursor position:', newPosition, 'value:', localValue.value)
    if (textareaRef.value) {
      textareaRef.value.setSelectionRange(newPosition, newPosition)
      textareaRef.value.focus()
    }
  })
}

watch(() => props.modelValue, (newValue) => {
  localValue.value = newValue
})

watch(localValue, async (newValue) => {
  emit('update:modelValue', newValue)
  await nextTick()
  autoResize()
})

const handleKeydown = (e) => {
  // 如果工作流工具列表显示，处理键盘导航
  if (showWorkflowTools.value) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
      e.preventDefault()
      const currentIndex = workflowTools.findIndex(t => t.id === highlightedTool.value)
      const nextIndex = currentIndex < workflowTools.length - 1 ? currentIndex + 1 : 0
      highlightedTool.value = workflowTools[nextIndex].id
      return
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const currentIndex = workflowTools.findIndex(t => t.id === highlightedTool.value)
      const prevIndex = currentIndex > 0 ? currentIndex - 1 : workflowTools.length - 1
      highlightedTool.value = workflowTools[prevIndex].id
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedTool.value) {
        const tool = workflowTools.find(t => t.id === highlightedTool.value)
        if (tool) selectWorkflowTool(tool)
      }
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      showWorkflowTools.value = false
      atSymbolIndex.value = -1
      highlightedTool.value = null
      return
    }
  }

  if (e.key === 'Enter' && !e.shiftKey && !props.isAnalyzing) {
    e.preventDefault()
    handleSend()
  } else if (e.key === 'Escape' && props.isAnalyzing) {
    e.preventDefault()
    handlePause()
  }
}

const handleFocus = () => {
  // 输入框获得焦点时的处理
}

const handleBlur = () => {
  // 延迟关闭工作流工具列表，允许点击
  setTimeout(() => {
    showWorkflowTools.value = false
    atSymbolIndex.value = -1
    highlightedTool.value = null
  }, 200)
}

const handleSend = () => {
  if ((!localValue.value.trim() && attachments.value.length === 0) || props.disabled || props.isAnalyzing) return

  // 检查是否有附件还在上传中
  const uploadingAttachments = attachments.value.filter(a => a.uploading)
  if (uploadingAttachments.length > 0) {
    alert('文件正在上传中，请稍候...')
    return
  }

  // 关闭工作流工具列表
  showWorkflowTools.value = false
  atSymbolIndex.value = -1
  highlightedTool.value = null

  // 获取选中的知识库ID列表
  const knowledgeBaseIds = kbStore.selectedIds

  // 准备附件信息
  const attachmentsData = attachments.value.map(a => ({
    file_id: a.file_id,
    name: a.name,
    type: a.type,
    url: a.url
  }))

  // 将查询、知识库ID、Agent模式、附件一起发送
  emit('send', {
    query: localValue.value,
    knowledgeBaseIds: knowledgeBaseIds,
    agentMode: agentMode.value,
    attachments: attachmentsData
  })

  localValue.value = ''
  attachments.value = []

  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

const handlePause = () => {
  if (!props.isAnalyzing) return

  emit('pause')
}

const handleFileSelect = async (event) => {
  const files = event.target.files
  if (!files || files.length === 0) return

  await processFiles(Array.from(files))

  // 清空文件选择
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

// 处理粘贴板粘贴事件
const handlePaste = async (event) => {
  const clipboardData = event.clipboardData || window.clipboardData
  if (!clipboardData) return

  const items = clipboardData.items
  if (!items || items.length === 0) return

  // 收集粘贴的文件
  const pastedFiles = []

  for (let i = 0; i < items.length; i++) {
    const item = items[i]

    // 检查是否是文件类型
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        // 如果文件没有类型（粘贴的图片可能没有扩展名），尝试根据 MIME 类型推断
        if (!file.name && file.type) {
          const extension = getFileExtensionFromMimeType(file.type)
          file.name = `pasted-${Date.now()}${extension}`
        }
        pastedFiles.push(file)
      }
    }
  }

  // 如果有粘贴的文件，处理它们
  if (pastedFiles.length > 0) {
    // 阻止默认的粘贴行为（避免将图片URL粘贴到文本框）
    event.preventDefault()
    await processFiles(pastedFiles)
  }
}

// 根据 MIME 类型获取文件扩展名
const getFileExtensionFromMimeType = (mimeType) => {
  const mimeToExt = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/svg+xml': '.svg',
    'image/bmp': '.bmp',
    'application/pdf': '.pdf',
    'text/plain': '.txt',
    'text/markdown': '.md',
    'application/json': '.json',
    'text/csv': '.csv',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
  }
  return mimeToExt[mimeType] || ''
}

// 拖拽相关事件处理
const handleDragOver = (e) => {
  isDragOver.value = true
  e.dataTransfer.dropEffect = 'copy'
}

const handleDragLeave = (e) => {
  // 只有真正离开 input-wrapper 时才移除高亮
  const rect = e.currentTarget.getBoundingClientRect()
  const x = e.clientX
  const y = e.clientY

  // 检查鼠标是否还在元素范围内（避免子元素触发 dragleave）
  if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
    isDragOver.value = false
  }
}

const handleDrop = async (e) => {
  isDragOver.value = false

  const files = e.dataTransfer.files
  if (!files || files.length === 0) return

  await processFiles(Array.from(files))
}

const removeAttachment = (index) => {
  const attachment = attachments.value[index]
  if (attachment && attachment.uploading) {
    // 上传中不允许移除
    return
  }
  attachments.value.splice(index, 1)
}

const previewImage = (attachment) => {
  if (attachment.type === 'image') {
    previewedImage.value = attachment
  }
}

// 处理文件列表的通用方法（用于拖放和选择）
const processFiles = async (files) => {
  if (!files || files.length === 0) return

  for (const file of files) {
    // 验证文件
    const validation = validateFile(file)
    if (!validation.valid) {
      alert(`${file.name}: ${validation.message}`)
      continue
    }

    // 创建附件对象
    const attachment = {
      file,
      name: file.name,
      type: validation.category,
      size: file.size,
      preview: null,
      uploading: true,
      file_id: null,
      url: null
    }

    // 如果是图片，创建预览
    if (validation.category === 'image') {
      try {
        attachment.preview = await createImagePreview(file)
      } catch (err) {
        console.error('Failed to create image preview:', err)
      }
    }

    // 添加到附件列表
    attachments.value.push(attachment)

    // 上传文件
    try {
      const result = await uploadChatFile(file)
      attachment.file_id = result.file_id
      attachment.url = result.url
      attachment.uploading = false

      console.log('[InputBox] File uploaded:', result)
    } catch (error) {
      console.error('[InputBox] Upload failed:', error)
      alert(`文件上传失败: ${error.message}`)
      // 移除失败的附件
      const index = attachments.value.indexOf(attachment)
      if (index > -1) {
        attachments.value.splice(index, 1)
      }
    }
  }
}

// 外部调用接口：处理拖放的文件
const handleFilesDrop = async (files) => {
  await processFiles(files)
}

// 暴露方法给父组件
defineExpose({
  handleFilesDrop
})
</script>

<style lang="scss" scoped>
.input-area {
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.input-container {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-wrapper {
  display: flex;
  align-items: stretch;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
  position: relative;

  &:focus-within {
    border-color: #1976D2;
    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.1);
  }

  &.drag-over {
    border-color: #1976D2;
    background: #e3f2fd;
    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.15);
  }
}

.workflow-tools-hint {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 10;
  min-width: 120px;
}

.workflow-tool-item {
  padding: 8px 12px;
  font-size: 14px;
  color: #6b7a99;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;

  &:hover {
    background: #f5f5f5;
    color: #1976D2;
  }

  &.active {
    background: #e3f2fd;
    color: #1976D2;
    font-weight: 500;
  }
}

.input-field {
  flex: 1;
  min-height: 44px;
  max-height: 120px;
  padding: 10px 16px;
  border: none;
  border-radius: 8px 0 0 8px;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  overflow-y: hidden;

  &:focus {
    outline: none;
  }

  &:disabled {
    background: #f5f5f5;
    cursor: not-allowed;
    color: #999;
  }
}

.action-group {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #7c8db5;
  background: transparent;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;

  &:hover {
    background: #f5f5f5;
    color: #1976D2;
  }
}

.upload-label input {
  display: none;
}

.upload-icon svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
}

.kb-toggle-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  color: #7c8db5;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.kb-toggle-button:hover {
  background: #f5f5f5;
  color: #1976D2;
}

.kb-toggle-button.kb-active {
  background: #e3f2fd;
  color: #1976D2;
}

.kb-icon {
  width: 18px;
  height: 18px;
}

.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:disabled {
    cursor: not-allowed;
  }
}

.send-icon {
  width: 18px;
  height: 18px;
}

.send-button {
  background: #1976D2;
  color: white;

  &:hover:not(:disabled) {
    background: #1565C0;
  }

  &:disabled {
    background: #e0e0e0;
    color: #999;
  }
}

.pause-button {
  width: auto;
  padding: 0 12px;
  background: #FF5722;
  color: white;

  &:hover:not(:disabled) {
    background: #E64A19;
  }

  &:disabled {
    background: #e0e0e0;
    color: #999;
  }
}

.feature-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-left: 4px;
}

@media (max-width: 768px) {
  .action-group {
    padding: 4px;
  }
}

.attachments-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f5f5f5;
  border-radius: 8px;
  position: relative;
}

.attachment-preview-image {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.2s;

  &:hover {
    opacity: 0.8;
  }
}

.attachment-file-icon {
  display: flex;
  align-items: center;
  gap: 6px;
}

.file-icon-svg {
  width: 24px;
  height: 24px;
  color: #7c8db5;
}

.attachment-file-name {
  font-size: 13px;
  color: #6b7a99;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: #999;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: #e0e0e0;
    color: #333;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
}

.remove-icon {
  width: 14px;
  height: 14px;
}

.attachment-uploading {
  font-size: 11px;
  color: #1976D2;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
