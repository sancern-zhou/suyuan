<template>
  <div class="input-area">
    <div class="input-container">
      <!-- 附件预览区域 -->
      <div v-if="visibleAttachments.length > 0" class="attachments-preview">
        <div v-for="(attachment, index) in visibleAttachments" :key="attachment.id || attachment.file_id || index" class="attachment-item">
          <img
            v-if="attachment.type === 'image' && attachment.preview"
            :src="attachment.preview"
            :title="attachment.name"
            class="attachment-preview-image"
            @click="previewImage(attachment)"
          />
          <div v-else class="attachment-file-icon">
            <svg viewBox="0 0 24 24" class="file-icon-svg">
              <path d="M6 3.5h8l4 4v13H6v-17Z"/>
              <path d="M14 3.5v4h4"/>
              <path d="M9 12h6"/>
              <path d="M9 15.5h5"/>
            </svg>
            <span class="attachment-file-name">{{ attachment.name }}</span>
          </div>
          <button class="attachment-remove" @click="removeVisibleAttachment(index)" :disabled="attachment.uploading">
            <svg viewBox="0 0 24 24" class="remove-icon">
              <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="2"/>
              <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2"/>
            </svg>
          </button>
          <div v-if="attachment.uploading" class="attachment-uploading" title="上传中"></div>
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

        <div
          v-if="pendingSteeringInputs.length > 0"
          class="pending-steering-indicator"
          role="status"
          aria-label="等待 Agent 接收"
        >
          <div class="pending-steering-icon" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div
            v-if="pendingSteeringDisplay.text"
            class="pending-steering-text"
            :title="pendingSteeringDisplay.text"
          >
            <span class="pending-steering-content">{{ pendingSteeringDisplay.text }}</span>
            <span v-if="pendingSteeringDisplay.extraCount > 0" class="pending-steering-count">
              +{{ pendingSteeringDisplay.extraCount }}
            </span>
          </div>
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

        <div class="input-footer">
          <AgentModeSelector
            v-if="assistantMode === 'general-agent'"
            v-model="agentMode"
            @update:modelValue="handleAgentModeChange"
          />

          <div class="action-group">
            <div class="model-tier-wrapper">
              <select
                v-model="modelTier"
                class="model-tier-select"
                :disabled="disabled || isAnalyzing"
                title="选择本次对话使用的模型"
              >
                <option value="auto">自动</option>
                <option value="flash">Flash</option>
                <option value="pro">Pro</option>
              </select>
              <div class="model-tier-tooltip">
                <span v-if="modelTier === 'flash'" class="tooltip-text">快速模式，适合日常问数、对话</span>
                <span v-if="modelTier === 'pro'" class="tooltip-text">专家模式，适合报告生成、深度分析等复杂任务</span>
                <span v-if="modelTier === 'auto'" class="tooltip-text">自动根据任务复杂度选择模型</span>
              </div>
            </div>

            <button
              class="kb-toggle-button"
              :class="{ 'kb-active': showKnowledgeBaseSelector }"
              @click="toggleKnowledgeBase"
              title="选择知识库"
            >
              <svg viewBox="0 0 24 24" class="kb-icon">
                <path d="M5 5.5C5 4.67 5.67 4 6.5 4h11c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-13Z"/>
                <path d="M8 8h8"/>
                <path d="M8 11.5h8"/>
                <path d="M8 15h5"/>
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
                    d="M12 16V4"
                  />
                  <path
                    d="m7 9 5-5 5 5"
                  />
                  <path
                    d="M5 16v2.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V16"
                  />
                </svg>
              </span>
            </label>

            <button
              class="action-button"
              :class="{ 'send-button': !isAnalyzing, 'steer-button': isAnalyzing }"
              @click="handleSend()"
              :disabled="actionButtonDisabled"
              :title="isAnalyzing ? runningActionTitle : '发送 (Enter)'"
            >
              <svg v-if="!isAnalyzing" viewBox="0 0 24 24" class="send-icon">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/>
              </svg>
              <span v-else>{{ runningActionLabel }}</span>
            </button>
            <button
              v-if="isAnalyzing"
              class="action-button pause-button"
              @click="handlePause"
              title="暂停分析 (Esc)"
            >
              <span>暂停</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 知识库选择器 -->
      <KnowledgeBaseSelector v-if="showKnowledgeBaseSelector" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { useReactStore } from '@/stores/reactStore'
import KnowledgeBaseSelector from '@/components/knowledge/KnowledgeBaseSelector.vue'
import AgentModeSelector from '@/components/AgentModeSelector.vue'
import { uploadChatFile, validateFile, createImagePreview, getFileUrl } from '@/services/uploadApi'
import { getPendingSteeringDisplay } from '@/components/inputBoxPendingSteering.js'

const kbStore = useKnowledgeBaseStore()
const reactStore = useReactStore()

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
  pendingSteeringInputs: {
    type: Array,
    default: () => []
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  useReranker: {
    type: Boolean,
    default: false
  },
  sessionId: {
    type: String,
    default: ''
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
const validAgentModes = ['assistant', 'expert', 'query', 'report', 'chart', 'ops']
// ✅ 使用统一的模式键名，与 store.currentMode 保持一致
const cachedMode = localStorage.getItem('current-mode') || 'assistant'
const initialAgentMode = validAgentModes.includes(reactStore.currentMode)
  ? reactStore.currentMode
  : (validAgentModes.includes(cachedMode) ? cachedMode : 'assistant')
const agentMode = ref(initialAgentMode)
const validModelTiers = ['auto', 'flash', 'pro']
const legacyModelTier = localStorage.getItem('llm-model-tier') || 'auto'
const draftModelTierKey = 'llm-model-tier:draft'

const getSessionModelTierKey = (sessionId) => `llm-model-tier:${sessionId}`

const readStoredModelTier = (sessionId) => {
  const sessionKey = sessionId ? getSessionModelTierKey(sessionId) : null
  const sessionValue = sessionKey ? localStorage.getItem(sessionKey) : null
  if (sessionValue && validModelTiers.includes(sessionValue)) {
    return sessionValue
  }

  const draftValue = localStorage.getItem(draftModelTierKey)
  if (draftValue && validModelTiers.includes(draftValue)) {
    return draftValue
  }

  if (legacyModelTier && validModelTiers.includes(legacyModelTier)) {
    return legacyModelTier
  }

  return 'auto'
}

const modelTier = ref(readStoredModelTier(props.sessionId))
const attachments = ref([])  // 附件列表
const previewedImage = ref(null)  // 当前预览的图片
const isDragOver = ref(false)  // 拖拽状态
const pendingBoardSnapshotAttachment = computed(() => {
  if (reactStore.currentMode !== 'chart') return null
  const attachment = reactStore.currentState?.board?.pendingSnapshotAttachment
  if (!attachment) return null
  return {
    ...attachment,
    id: attachment.id || attachment.file_id || 'drawio-board-snapshot',
    name: attachment.name || attachment.filename || '画板截图.png',
    type: attachment.type || attachment.file_type || 'image',
    preview: attachment.preview || attachment.url || null,
    uploading: false,
    readonlySource: 'drawio_board_snapshot'
  }
})
const visibleAttachments = computed(() => [
  ...attachments.value,
  ...(pendingBoardSnapshotAttachment.value ? [pendingBoardSnapshotAttachment.value] : [])
])
const canSteerWhileRunning = computed(() => props.isAnalyzing && reactStore.currentMode === 'assistant')
const runningActionLabel = computed(() => canSteerWhileRunning.value ? '追加' : '排队')
const runningActionTitle = computed(() => canSteerWhileRunning.value ? '追加指令 (Enter)' : '排队发送 (Enter)')
const pendingSteeringDisplay = computed(() => getPendingSteeringDisplay(props.pendingSteeringInputs))

const actionButtonDisabled = computed(() => {
  if (props.isAnalyzing) {
    if (!canSteerWhileRunning.value) return false
    return (!localValue.value.trim() && visibleAttachments.value.length === 0) || props.disabled
  }
  return (!localValue.value.trim() && visibleAttachments.value.length === 0) || props.disabled
})

// 工作流工具列表
const workflowTools = [
  { id: 'standard_analysis_workflow', name: '标准分析' },
  { id: 'knowledge_qa_workflow', name: '知识问答' }
]

const toggleKnowledgeBase = () => {
  showKnowledgeBaseSelector.value = !showKnowledgeBaseSelector.value
}

const handleAgentModeChange = (newMode) => {
  if (!validAgentModes.includes(newMode)) {
    console.warn('[InputBox] Invalid agent mode:', newMode)
    return
  }

  // ✅ 处理Agent模式变化
  agentMode.value = newMode
  if (reactStore.currentMode !== newMode) {
    reactStore.switchMode(newMode)
  }
  emit('update:agentMode', newMode)
  console.log('[InputBox] Agent mode changed:', newMode)
}

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    const maxHeight = 120
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
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

  const replaceStart = atSymbolIndex.value >= 0 ? atSymbolIndex.value : localValue.value.indexOf('@')
  const before = replaceStart >= 0 ? localValue.value.slice(0, replaceStart) : localValue.value
  const after = replaceStart >= 0 ? localValue.value.slice(replaceStart + 1) : ''
  const insertedText = '@' + toolName + ' '
  const newValue = before + insertedText + after

  console.log('[InputBox] New value:', newValue)

  // 更新 localValue
  localValue.value = newValue

  showWorkflowTools.value = false
  atSymbolIndex.value = -1
  highlightedTool.value = null

  // 设置光标位置到工具名称后面
  nextTick(() => {
    const newPosition = before.length + insertedText.length
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

watch(
  () => reactStore.currentMode,
  (newMode) => {
    if (validAgentModes.includes(newMode) && agentMode.value !== newMode) {
      agentMode.value = newMode
    }
  },
  { immediate: true }
)

watch(localValue, async (newValue) => {
  emit('update:modelValue', newValue)
  await nextTick()
  autoResize()
})

watch(
  () => props.sessionId,
  (newSessionId) => {
    modelTier.value = readStoredModelTier(newSessionId)
  },
  { immediate: true }
)

watch([modelTier, () => props.sessionId], ([newTier, newSessionId]) => {
  if (!validModelTiers.includes(newTier)) return
  if (newSessionId) {
    localStorage.setItem(getSessionModelTierKey(newSessionId), newTier)
    return
  }
  localStorage.setItem(draftModelTierKey, newTier)
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

  if (e.key === 'Enter' && !e.shiftKey) {
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
  if ((!localValue.value.trim() && visibleAttachments.value.length === 0) || props.disabled) return

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
  const activeAgentMode = validAgentModes.includes(reactStore.currentMode)
    ? reactStore.currentMode
    : agentMode.value
  agentMode.value = activeAgentMode

  emit('send', {
    query: localValue.value,
    knowledgeBaseIds: knowledgeBaseIds,
    agentMode: activeAgentMode,
    modelTier: modelTier.value,
    attachments: attachmentsData
  })

  localValue.value = ''
  attachments.value = []

  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.overflowY = 'hidden'
    }
  })
}

const focus = () => {
  nextTick(() => {
    textareaRef.value?.focus()
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

const removeVisibleAttachment = (index) => {
  const attachment = visibleAttachments.value[index]
  if (!attachment) return
  if (attachment.readonlySource === 'drawio_board_snapshot') {
    reactStore.setDrawioBoardSnapshotAttachment(null)
    return
  }
  removeAttachment(index)
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
  focus,
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
  flex-direction: column;
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
  width: 100%;
  min-width: 0;
  min-height: 44px;
  max-height: 120px;
  padding: 12px 16px 8px;
  border: none;
  border-radius: 8px 8px 0 0;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  overflow-y: auto;

  &:focus {
    outline: none;
  }

  &:disabled {
    background: #f5f5f5;
    cursor: not-allowed;
    color: #999;
  }
}

.pending-steering-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px 0;
  min-height: 18px;
  min-width: 0;
}

.pending-steering-icon {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 14px;

  span {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #64748b;
    opacity: 0.42;
    animation: pending-steering-pulse 1.2s ease-in-out infinite;

    &:nth-child(2) {
      animation-delay: 0.16s;
    }

    &:nth-child(3) {
      animation-delay: 0.32s;
    }
  }
}

.pending-steering-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  color: #475569;
  font-size: 13px;
  line-height: 18px;
}

.pending-steering-content {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-steering-count {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 12px;
}

@keyframes pending-steering-pulse {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }

  40% {
    transform: translateY(-3px);
    opacity: 0.9;
  }
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 4px 8px 8px 12px;
  border-top: 1px solid #f2f4f8;
}

.action-group {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
}

.model-tier-select {
  height: 30px;
  padding: 0 24px 0 10px;
  border: 1px solid #d8deea;
  border-radius: 999px;
  color: #526173;
  background: #fff;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, currentColor 50%),
    linear-gradient(135deg, currentColor 50%, transparent 50%);
  background-position:
    calc(100% - 13px) 12px,
    calc(100% - 8px) 12px;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  transition: color 0.16s ease, border-color 0.16s ease, background-color 0.16s ease;

  &:hover:not(:disabled),
  &:focus:not(:disabled) {
    color: #1976D2;
    border-color: #90CAF9;
    background-color: #f8fbff;
  }

  &:disabled {
    color: #9aa5b8;
    background: #f5f7fb;
    cursor: not-allowed;
  }
}

.model-tier-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.model-tier-tooltip {
  position: absolute;
  bottom: -28px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  z-index: 1000;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.model-tier-wrapper:hover .model-tier-tooltip {
  opacity: 1;
}

.model-tier-tooltip .tooltip-text {
  font-size: 11px;
  color: #526173;
  background: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #d8deea;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
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
  fill: none;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
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
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
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

.steer-button {
  width: auto;
  padding: 0 12px;
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

@media (max-width: 768px) {
  .input-area {
    padding: 12px;
  }

  .input-field {
    padding: 10px 12px 8px;
  }

  .input-footer {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
    padding: 6px 8px 8px;
  }

  .action-group {
    width: 100%;
    justify-content: flex-end;
    padding: 4px;
  }
}

.attachments-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 2px 0 8px;
}

.attachment-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 32px;
  padding: 3px 6px;
  background: #fff;
  border: 1px solid #d8deea;
  border-radius: 999px;
  position: relative;
  color: #5f6f89;
}

.attachment-preview-image {
  width: 42px;
  height: 30px;
  object-fit: cover;
  border-radius: 999px;
  cursor: pointer;
  transition: opacity 0.16s ease;

  &:hover {
    opacity: 0.8;
  }
}

.attachment-file-icon {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.file-icon-svg {
  width: 15px;
  height: 15px;
  color: currentColor;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: 0 0 auto;
}

.attachment-file-name {
  min-width: 0;
  max-width: 136px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1;
  color: #526173;
}

.attachment-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: #8a96a8;
  cursor: pointer;
  border-radius: 50%;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: #eef2f7;
    color: #35425f;
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
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #1976D2;
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
