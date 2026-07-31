<template>
  <div class="input-area">
    <div class="input-container">
      <div v-if="selectedSkill || selectedFileRefs.length" class="composer-selection-bar">
        <button
          v-if="selectedSkill"
          type="button"
          class="composer-chip skill-chip"
          :class="{ invalid: !selectedSkill.compatible }"
          :title="selectedSkill.compatible ? selectedSkill.description : `当前模式缺少：${selectedSkill.missingTools.join('、')}`"
          @click="clearSelectedSkill"
        >
          /{{ selectedSkill.name }} <span aria-hidden="true">×</span>
        </button>
        <div
          v-for="file in selectedFileRefs"
          :key="file.resourceRefId"
          class="composer-chip file-chip"
          :class="{ 'active-policy-chip': file.pinnedPolicy }"
        >
          <button
            type="button"
            class="chip-policy-toggle"
            :disabled="!canPinAsPolicy(file)"
            :title="canPinAsPolicy(file) ? (file.pinnedPolicy ? '取消固定规范' : '固定为会话规范') : '仅文本类文档可固定为规范'"
            @click="togglePolicyPin(file.resourceRefId)"
          >
            {{ file.pinnedPolicy ? '已固定' : '固定' }}
          </button>
          <span :title="file.title || file.name">@{{ file.name }}</span>
          <button
            type="button"
            class="chip-remove"
            :title="`移除 ${file.name}`"
            @click="removeSelectedFile(file.resourceRefId)"
          >×</button>
        </div>
      </div>

      <!-- 附件预览区域 -->
      <div v-if="visibleAttachments.length > 0" class="attachments-preview">
        <div
          v-for="(attachment, index) in visibleAttachments"
          :key="attachment.id || attachment.file_id || index"
          class="attachment-item"
          :class="{ 'context-attachment': attachment.readonlySource === 'drawio_board_selection' }"
          :title="attachment.title || attachment.name"
        >
          <AuthenticatedImage
            v-if="attachment.type === 'image' && attachment.preview"
            :source="attachment.preview"
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
          <button
            v-if="attachment.readonlySource !== 'drawio_board_selection'"
            class="attachment-remove"
            @click="removeVisibleAttachment(index)"
            :disabled="attachment.uploading"
          >
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
        <div v-if="showCommandPalette" class="workflow-tools-hint" role="listbox">
          <div class="palette-header">
            {{ activeTrigger?.type === 'skill' ? '选择技能' : '引用对话文件' }}
          </div>
          <div v-if="paletteLoading" class="palette-empty">加载中…</div>
          <div v-else-if="paletteError" class="palette-empty error">{{ paletteError }}</div>
          <div v-else-if="paletteItems.length === 0" class="palette-empty">没有匹配项</div>
          <template v-else>
            <button
              v-for="(item, index) in paletteItems"
              :key="item.id"
              type="button"
              class="workflow-tool-item"
              :class="{ active: highlightedPaletteIndex === index, disabled: item.compatible === false }"
              :disabled="item.compatible === false"
              @mousedown="selectPaletteItem(item, $event)"
              @mouseenter="highlightedPaletteIndex = index"
            >
              <span class="palette-item-name">{{ item.name }}</span>
              <small>{{ item.description || item.group }}</small>
              <small v-if="item.compatible === false">当前模式缺少：{{ item.missingTools.join('、') }}</small>
            </button>
          </template>
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
          @compositionstart="isComposing = true"
          @compositionend="handleCompositionEnd"
          rows="1"
        />

        <div v-if="boardSyncMessage" class="board-sync-message" :class="{ error: boardSyncError }" role="status">
          {{ boardSyncMessage }}
        </div>

        <div class="input-footer">
          <div class="action-group">
            <div v-if="showModelTierSelector" class="model-tier-wrapper">
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

            <button
              v-if="showVoiceControls"
              class="voice-button"
              :class="{ recording: isRecording, processing: isTranscribing }"
              @click="toggleRecording"
              :disabled="props.disabled || isTranscribing"
              :title="voiceButtonTitle"
            >
              <svg viewBox="0 0 24 24" class="voice-icon">
                <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z"/>
                <path d="M19 11a7 7 0 0 1-14 0"/>
                <path d="M12 18v3"/>
                <path d="M8 21h8"/>
              </svg>
            </button>

            <button
              v-if="showVoiceControls"
              class="voice-button"
              :class="{ active: voiceOutputEnabled }"
              @click="toggleVoiceOutput"
              title="切换AI回复语音播报"
            >
              <svg viewBox="0 0 24 24" class="voice-icon">
                <path d="M4 9v6h4l5 4V5L8 9H4Z"/>
                <path d="M16 9.5a4 4 0 0 1 0 5"/>
                <path d="M18.5 7a7 7 0 0 1 0 10"/>
              </svg>
            </button>

            <label class="upload-label" title="上传文件或图片">
              <input
                ref="fileInputRef"
                type="file"
                @change="handleFileSelect"
                accept="image/*,.pdf,.txt,.md,.html,.htm,.json,.csv,.docx,.xlsx,.pptx"
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
import AuthenticatedImage from '@/components/AuthenticatedImage.vue'
import { uploadChatFile, validateFile, createImagePreview, getFileUrl } from '@/services/uploadApi'
import { transcribeVoice } from '@/services/voiceApi.js'
import { getPendingSteeringDisplay } from '@/components/inputBoxPendingSteering.js'
import { getSkillsList } from '@/api/skillsManagement.js'
import { getSession, getSessionResources } from '@/api/session.js'
import { withComposerShortcutGuide } from '@/components/inputBoxPlaceholder.js'
import {
  buildComposerPayload,
  filterPaletteItems,
  findComposerTrigger,
  normalizeConversationResources,
  normalizeSkills,
  removeComposerTrigger,
  resolveAcceptedActiveContextState,
  shouldApplyActiveContextRestore,
  shouldClearAcceptedComposer
} from '@/components/inputBoxCommandPalette.js'
import {
  createSelectionRestoreGuard,
  readSelectionDraft,
  reconcileSelectionDraft,
  writeSelectionDraft
} from '@/components/inputBoxSelectionDraft.js'
import { completeUploadedAttachment } from '@/components/inputBoxAttachments.js'
import {
  createVoiceFilename,
  getPreferredRecordingMimeType,
  getVoiceRecordingAvailability,
  shouldShowVoiceControls
} from '@/components/voiceMode.js'
import {
  getEffectiveModelTier,
  shouldShowModelTierSelector
} from '@/components/inputBoxModelTier.js'

const kbStore = useKnowledgeBaseStore()
const reactStore = useReactStore()

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: withComposerShortcutGuide('输入您的问题')
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

const emit = defineEmits(['update:modelValue', 'send', 'pause', 'update:useReranker'])

const textareaRef = ref(null)
const fileInputRef = ref(null)
const localValue = ref(props.modelValue)
const showKnowledgeBaseSelector = ref(false)
const activeTrigger = ref(null)
const highlightedPaletteIndex = ref(0)
const paletteLoading = ref(false)
const paletteError = ref('')
const availableSkills = ref([])
const conversationResources = ref([])
const selectedSkill = ref(null)
const selectionRestoreGuard = createSelectionRestoreGuard()
let restoringSelection = false
const isComposing = ref(false)
const useReranker = ref(props.useReranker)  // 精准检索开关状态
const validAgentModes = ['assistant', 'ppt', 'expert', 'query', 'report', 'chart', 'board', 'ops', 'graph']
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
const isRecording = ref(false)
const isTranscribing = ref(false)
const mediaRecorder = ref(null)
const recordedChunks = ref([])
const voiceOutputEnabled = ref(
  typeof localStorage !== 'undefined' &&
  localStorage.getItem('query-voice-output-enabled') === 'true'
)
const pendingBoardSnapshotAttachment = computed(() => {
  if (reactStore.currentMode !== 'board') return null
  const attachment = reactStore.currentState?.board?.pendingSnapshotAttachment
  if (!attachment) return null
  return {
    ...attachment,
    id: attachment.id || attachment.file_id || 'drawio-board-snapshot',
    name: attachment.name || attachment.filename || '画板截图.png',
    type: attachment.type || attachment.file_type || 'image',
    preview: attachment.preview || attachment.url || null,
    uploading: false,
    resourceRefId: attachment.resourceRefId || attachment.resource_ref?.ref_id || null,
    readonlySource: 'drawio_board_snapshot'
  }
})

const getSelectedCellLabel = (cell = {}) => {
  return String(cell.value || cell.label || cell.id || cell.cell_id || '选中项').trim() || '选中项'
}

const boardSelectionContextAttachment = computed(() => {
  if (reactStore.currentMode !== 'board') return null
  const selectedCells = reactStore.currentState?.board?.selectedCells || []
  if (!Array.isArray(selectedCells) || selectedCells.length === 0) return null

  const firstLabel = getSelectedCellLabel(selectedCells[0])
  const name = selectedCells.length === 1
    ? `当前选中：${firstLabel}`
    : `当前选中：${selectedCells.length} 项`
  const detail = selectedCells
    .map(cell => getSelectedCellLabel(cell))
    .filter(Boolean)
    .slice(0, 6)
    .join('、')

  return {
    id: 'drawio-board-selection-context',
    name,
    type: 'context',
    uploading: false,
    readonlySource: 'drawio_board_selection',
    title: detail ? `当前选中：${detail}` : name
  }
})

const visibleAttachments = computed(() => [
  ...attachments.value,
  ...(boardSelectionContextAttachment.value ? [boardSelectionContextAttachment.value] : []),
  ...(pendingBoardSnapshotAttachment.value ? [pendingBoardSnapshotAttachment.value] : [])
])
const selectedFileRefs = computed(() => [
  ...attachments.value.filter(item => item.resourceRefId),
  ...(pendingBoardSnapshotAttachment.value?.resourceRefId ? [pendingBoardSnapshotAttachment.value] : [])
])
const activeContextsLoaded = ref(!props.sessionId)
const activeContextsDirty = ref(false)
const activeContextsEditVersion = ref(0)
const activeContextsSessionId = ref(props.sessionId || null)
const activeContextSignature = computed(() => JSON.stringify({
  skillId: selectedSkill.value?.id || null,
  policyFileIds: selectedFileRefs.value
    .filter(file => file.pinnedPolicy)
    .map(file => file.resourceRefId)
    .sort()
}))
const hasActiveContextUpdate = computed(() => activeContextsDirty.value)

const markActiveContextsDirty = () => {
  activeContextsDirty.value = true
  activeContextsEditVersion.value += 1
}

const resourceToAttachment = (item) => ({
  id: item.id,
  resourceRefId: item.id,
  file_id: item.metadata?.file_id || null,
  name: item.name,
  type: item.metadata?.mime_type?.startsWith('image/') ? 'image' : 'file',
  mime_type: item.metadata?.mime_type || null,
  url: item.metadata?.file_id ? getFileUrl(item.metadata.file_id) : null,
  preview: item.metadata?.file_id && item.metadata?.mime_type?.startsWith('image/')
    ? getFileUrl(item.metadata.file_id)
    : null,
  uploading: false,
  source: item.source,
  pinnedPolicy: item.pinnedPolicy === true,
  title: `${item.group}${item.turnSequence !== null ? ` · 第 ${item.turnSequence} 轮` : ''}`
})

const POLICY_FILE_PATTERN = /\.(md|markdown|qmd|txt|json|ya?ml)$/i
const canPinAsPolicy = (file) => POLICY_FILE_PATTERN.test(String(file?.name || ''))
const togglePolicyPin = (resourceRefId) => {
  const file = attachments.value.find(item => item.resourceRefId === resourceRefId)
  if (!file || !canPinAsPolicy(file)) return
  file.pinnedPolicy = !file.pinnedPolicy
  markActiveContextsDirty()
}

const persistSelectionDraft = (sessionId = props.sessionId) => {
  if (restoringSelection) return
  writeSelectionDraft(sessionId, {
    skillId: selectedSkill.value?.id || null,
    fileIds: selectedFileRefs.value.map(file => file.resourceRefId),
    policyFileIds: selectedFileRefs.value
      .filter(file => file.pinnedPolicy)
      .map(file => file.resourceRefId)
  })
}

const restoreSelectionDraft = async (sessionId) => {
  const mode = reactStore.currentMode
  const token = selectionRestoreGuard.begin(sessionId, mode)
  restoringSelection = true
  const targetSessionId = sessionId || null
  if (activeContextsSessionId.value !== targetSessionId) {
    activeContextsSessionId.value = targetSessionId
    activeContextsDirty.value = false
    activeContextsEditVersion.value += 1
  }
  activeContextsLoaded.value = !sessionId
  const restoreEditVersion = activeContextsEditVersion.value
  let restoreSucceeded = true
  const recoverRestoreDependency = async (promise, fallback) => {
    try {
      return await promise
    } catch {
      restoreSucceeded = false
      return fallback
    }
  }
  try {
    const [skillsResponse, resourcesResponse, sessionResponse] = await Promise.all([
      recoverRestoreDependency(
        getSkillsList(null, reactStore.currentMode),
        { data: { skills: [] } }
      ),
      sessionId
        ? recoverRestoreDependency(getSessionResources(sessionId), { resources: [] })
        : Promise.resolve({ resources: [] }),
      sessionId
        ? recoverRestoreDependency(getSession(sessionId), null)
        : Promise.resolve(null)
    ])
    if (!selectionRestoreGuard.isCurrent(token, props.sessionId, reactStore.currentMode)) return
    availableSkills.value = normalizeSkills(skillsResponse)
    conversationResources.value = normalizeConversationResources(resourcesResponse)
    const localDraft = readSelectionDraft(sessionId)
    const serverPayload = sessionResponse?.metadata?.active_contexts
    const serverItems = serverPayload?.version === 1 && Array.isArray(serverPayload.items)
      ? serverPayload.items
      : null
    const activeSkill = serverItems?.find(item => item.type === 'skill')
    const activePolicyIds = serverItems
      ?.filter(item => item.type === 'fixed_policy')
      .map(item => item.id) || []
    const restored = reconcileSelectionDraft(
      serverItems === null
        ? localDraft
        : {
            skillId: activeSkill?.id || null,
            fileIds: Array.from(new Set([...localDraft.fileIds, ...activePolicyIds])),
            policyFileIds: activePolicyIds
          },
      availableSkills.value,
      conversationResources.value
    )
    const shouldApplyRestore = shouldApplyActiveContextRestore({
      restoreEditVersion,
      currentEditVersion: activeContextsEditVersion.value,
      dirty: activeContextsDirty.value
    })
    if (shouldApplyRestore) {
      selectedSkill.value = restored.skill
      attachments.value = restored.files.map(resourceToAttachment)
      writeSelectionDraft(sessionId, {
        skillId: restored.skill?.id || null,
        fileIds: restored.files.map(file => file.id),
        policyFileIds: restored.files.filter(file => file.pinnedPolicy).map(file => file.id)
      })
    }
    if (restoreEditVersion === activeContextsEditVersion.value) {
      activeContextsLoaded.value = !sessionId || restoreSucceeded
    }
  } finally {
    if (selectionRestoreGuard.isCurrent(token, props.sessionId, reactStore.currentMode)) {
      restoringSelection = false
    }
  }
}
const paletteItems = computed(() => {
  if (!activeTrigger.value) return []
  const source = activeTrigger.value.type === 'skill'
    ? availableSkills.value
    : conversationResources.value.filter(item => (
      !selectedFileRefs.value.some(selected => selected.resourceRefId === item.id)
    ))
  return filterPaletteItems(source, activeTrigger.value.search)
})
const showCommandPalette = computed(() => activeTrigger.value !== null)
const activeModelTierMode = computed(() => (
  validAgentModes.includes(reactStore.currentMode) ? reactStore.currentMode : 'assistant'
))
const showModelTierSelector = computed(() => shouldShowModelTierSelector(activeModelTierMode.value))
const showVoiceControls = computed(() => shouldShowVoiceControls(reactStore.currentMode))
const canSteerWhileRunning = computed(() => props.isAnalyzing && reactStore.currentMode === 'assistant')
const boardSyncStatus = computed(() => (
  reactStore.currentMode === 'board'
    ? reactStore.currentState?.board?.syncStatus || 'idle'
    : 'idle'
))
const boardSyncError = computed(() => reactStore.currentMode === 'board' ? reactStore.currentState?.board?.syncError : null)
const boardSyncMessage = computed(() => {
  if (reactStore.currentMode !== 'board') return ''
  const status = boardSyncStatus.value
  if (status === 'syncing') return '正在同步画板…'
  if (status === 'error') {
    const labels = {
      board_editor_not_ready: '画板编辑器尚未就绪，请稍后重试',
      board_sync_timeout: '同步画板超时，消息未发送',
      board_sync_invalid_xml: '画板 XML 无效，消息未发送',
      board_version_conflict: '画板版本已更新，请重新加载后再发送',
      board_manual_commit_failed: '保存手工画板版本失败，消息未发送'
    }
    return labels[boardSyncError.value] || '同步画板失败，消息未发送'
  }
  return ''
})
const runningActionLabel = computed(() => canSteerWhileRunning.value ? '追加' : '排队')
const runningActionTitle = computed(() => canSteerWhileRunning.value ? '追加指令 (Enter)' : '排队发送 (Enter)')
const pendingSteeringDisplay = computed(() => getPendingSteeringDisplay(props.pendingSteeringInputs))
const voiceButtonTitle = computed(() => {
  if (isTranscribing.value) return '语音转文字中'
  return isRecording.value ? '停止录音并转文字' : '语音输入'
})

const actionButtonDisabled = computed(() => {
  if (boardSyncStatus.value === 'syncing') return true
  const hasContent = Boolean(
    localValue.value.trim() || hasActiveContextUpdate.value || selectedFileRefs.value.some(file => !file.pinnedPolicy)
  )
  if (attachments.value.some(item => item.uploading)) return true
  if (selectedSkill.value?.compatible === false) return true
  if (props.isAnalyzing) {
    if (!canSteerWhileRunning.value) return false
    return !hasContent || props.disabled
  }
  return !hasContent || props.disabled
})

const toggleKnowledgeBase = () => {
  showKnowledgeBaseSelector.value = !showKnowledgeBaseSelector.value
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

const loadPaletteSource = async (type) => {
  paletteLoading.value = true
  paletteError.value = ''
  try {
    if (type === 'skill') {
      availableSkills.value = normalizeSkills(await getSkillsList(null, reactStore.currentMode))
    } else if (props.sessionId) {
      conversationResources.value = normalizeConversationResources(await getSessionResources(props.sessionId))
    } else {
      conversationResources.value = []
    }
  } catch (error) {
    if (type === 'skill' || conversationResources.value.length === 0) {
      paletteError.value = type === 'skill' ? '技能加载失败' : '对话文件加载失败'
    }
    console.error('[InputBox] palette load failed:', error)
  } finally {
    paletteLoading.value = false
  }
}

const updateActiveTrigger = () => {
  if (isComposing.value || !textareaRef.value) return
  const nextTrigger = findComposerTrigger(localValue.value, textareaRef.value.selectionStart)
  const typeChanged = nextTrigger?.type && nextTrigger.type !== activeTrigger.value?.type
  activeTrigger.value = nextTrigger
  highlightedPaletteIndex.value = 0
  if (typeChanged || (
    nextTrigger?.type === 'skill' && availableSkills.value.length === 0
  ) || (
    nextTrigger?.type === 'file' && conversationResources.value.length === 0
  )) {
    void loadPaletteSource(nextTrigger.type)
  }
}

const handleInput = () => {
  autoResize()
  updateActiveTrigger()
}

const selectPaletteItem = (item, event) => {
  if (item.compatible === false) return
  if (event) {
    event.preventDefault()
    event.stopPropagation()
  }
  const cursorPosition = textareaRef.value?.selectionStart ?? localValue.value.length
  const removed = removeComposerTrigger(localValue.value, activeTrigger.value, cursorPosition)
  localValue.value = removed.value
  if (activeTrigger.value?.type === 'skill') {
    selectedSkill.value = item
    markActiveContextsDirty()
  } else if (!attachments.value.some(file => file.resourceRefId === item.id)) {
    attachments.value.push(resourceToAttachment(item))
  }
  activeTrigger.value = null
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.setSelectionRange(removed.cursor, removed.cursor)
      textareaRef.value.focus()
    }
  })
}

const removeSelectedFile = (resourceRefId) => {
  const index = attachments.value.findIndex(file => file.resourceRefId === resourceRefId)
  if (index >= 0) {
    const [removed] = attachments.value.splice(index, 1)
    if (removed?.pinnedPolicy) markActiveContextsDirty()
  }
  if (pendingBoardSnapshotAttachment.value?.resourceRefId === resourceRefId) {
    reactStore.setDrawioBoardSnapshotAttachment(null)
  }
}

const clearSelectedSkill = () => {
  if (!selectedSkill.value) return
  selectedSkill.value = null
  markActiveContextsDirty()
}

const handleCompositionEnd = () => {
  isComposing.value = false
  nextTick(updateActiveTrigger)
}

watch(() => props.modelValue, (newValue) => {
  localValue.value = newValue
})

watch(localValue, async (newValue) => {
  emit('update:modelValue', newValue)
  await nextTick()
  autoResize()
})

watch(
  () => props.sessionId,
  (newSessionId, oldSessionId) => {
    if (oldSessionId && oldSessionId !== newSessionId) persistSelectionDraft(oldSessionId)
    modelTier.value = readStoredModelTier(newSessionId)
    activeTrigger.value = null
    if (
      !oldSessionId &&
      newSessionId &&
      (attachments.value.length > 0 || selectedSkill.value)
    ) {
      selectionRestoreGuard.invalidate()
      restoringSelection = false
      persistSelectionDraft(newSessionId)
      return
    }
    void restoreSelectionDraft(newSessionId)
  },
  { immediate: true }
)

watch(
  () => reactStore.currentMode,
  () => {
    persistSelectionDraft()
    void restoreSelectionDraft(props.sessionId)
  }
)

watch(
  [
    () => selectedSkill.value?.id || null,
    () => selectedFileRefs.value
      .map(file => `${file.resourceRefId}:${file.pinnedPolicy ? 'pinned' : 'turn'}`)
      .join('\n')
  ],
  () => persistSelectionDraft()
)

watch([modelTier, () => props.sessionId], ([newTier, newSessionId]) => {
  if (!validModelTiers.includes(newTier)) return
  if (!showModelTierSelector.value) return
  if (newSessionId) {
    localStorage.setItem(getSessionModelTierKey(newSessionId), newTier)
    return
  }
  localStorage.setItem(draftModelTierKey, newTier)
})

const handleKeydown = (e) => {
  if (isComposing.value || e.isComposing) return
  if (showCommandPalette.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      highlightedPaletteIndex.value = paletteItems.value.length
        ? (highlightedPaletteIndex.value + 1) % paletteItems.value.length
        : 0
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      highlightedPaletteIndex.value = paletteItems.value.length
        ? (highlightedPaletteIndex.value - 1 + paletteItems.value.length) % paletteItems.value.length
        : 0
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const item = paletteItems.value[highlightedPaletteIndex.value]
      if (item) selectPaletteItem(item)
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      activeTrigger.value = null
      return
    }
  }

  if (
    (e.key === 'Backspace' || e.key === 'Delete') &&
    localValue.value.length === 0 &&
    (selectedFileRefs.value.length > 0 || selectedSkill.value)
  ) {
    e.preventDefault()
    const lastFile = selectedFileRefs.value.at(-1)
    if (lastFile) removeSelectedFile(lastFile.resourceRefId)
    else clearSelectedSkill()
    return
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
  setTimeout(() => {
    activeTrigger.value = null
  }, 200)
}

const handleSend = async () => {
  if (
    (!localValue.value.trim() && !hasActiveContextUpdate.value && !selectedFileRefs.value.some(file => !file.pinnedPolicy)) ||
    props.disabled ||
    boardSyncStatus.value === 'syncing'
  ) return

  // 检查是否有附件还在上传中
  const uploadingAttachments = attachments.value.filter(a => a.uploading)
  if (uploadingAttachments.length > 0) {
    alert('文件正在上传中，请稍候...')
    return
  }

  activeTrigger.value = null

  // 获取选中的知识库ID列表
  const knowledgeBaseIds = kbStore.selectedIds

  const activeAgentMode = validAgentModes.includes(reactStore.currentMode)
    ? reactStore.currentMode
    : 'assistant'

  if (activeAgentMode === 'board' && reactStore.currentState?.board?.currentXml) {
    try {
      await reactStore.prepareDrawioBoardForSend(activeAgentMode)
    } catch (error) {
      console.error('[drawio-board] pre-send synchronization blocked send', error)
      return
    }
  }

  const sentSnapshot = {
    query: localValue.value,
    skillId: selectedSkill.value?.id || null,
    fileIds: selectedFileRefs.value.map(file => `${file.resourceRefId}:${file.pinnedPolicy ? 'pinned' : 'turn'}`),
    activeContextsExplicit: activeContextsLoaded.value || activeContextsDirty.value,
    activeContextSignature: activeContextSignature.value
  }
  const clearAcceptedDraft = () => {
    const currentSnapshot = {
      query: localValue.value,
      skillId: selectedSkill.value?.id || null,
      fileIds: selectedFileRefs.value.map(file => `${file.resourceRefId}:${file.pinnedPolicy ? 'pinned' : 'turn'}`)
    }
    const acceptedActiveContextState = resolveAcceptedActiveContextState({
      explicit: sentSnapshot.activeContextsExplicit,
      sentSignature: sentSnapshot.activeContextSignature,
      currentSignature: activeContextSignature.value,
      dirty: activeContextsDirty.value,
      currentEditVersion: activeContextsEditVersion.value
    })
    if (acceptedActiveContextState) {
      activeContextsLoaded.value = acceptedActiveContextState.loaded
      activeContextsDirty.value = acceptedActiveContextState.dirty
      activeContextsEditVersion.value = acceptedActiveContextState.editVersion
    }
    if (!shouldClearAcceptedComposer(sentSnapshot, currentSnapshot)) return
    localValue.value = ''
    attachments.value = attachments.value.filter(file => file.pinnedPolicy)
    if (pendingBoardSnapshotAttachment.value) reactStore.setDrawioBoardSnapshotAttachment(null)
    nextTick(() => {
      if (textareaRef.value) {
        textareaRef.value.style.height = 'auto'
        textareaRef.value.style.overflowY = 'hidden'
      }
    })
  }

  emit('send', {
    ...buildComposerPayload({
      query: localValue.value,
      skill: selectedSkill.value,
      files: selectedFileRefs.value.map(file => ({
        id: file.resourceRefId,
        fileId: file.file_id || null,
        name: file.name,
        type: file.type,
        mimeType: file.mime_type || null,
        url: file.url || (file.file_id ? getFileUrl(file.file_id) : null),
        pinnedPolicy: file.pinnedPolicy === true
      })),
      knowledgeBaseIds,
      agentMode: activeAgentMode,
      modelTier: getEffectiveModelTier(modelTier.value, activeAgentMode),
      activeContextsLoaded: activeContextsLoaded.value,
      activeContextsDirty: activeContextsDirty.value
    }),
    onAccepted: clearAcceptedDraft
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

const toggleVoiceOutput = () => {
  voiceOutputEnabled.value = !voiceOutputEnabled.value
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('query-voice-output-enabled', voiceOutputEnabled.value ? 'true' : 'false')
  }
}

const toggleRecording = async () => {
  if (isRecording.value) {
    stopRecording()
    return
  }
  await startRecording()
}

const startRecording = async () => {
  const availability = getVoiceRecordingAvailability()
  if (!availability.available) {
    alert(availability.message)
    return
  }

  try {
    reactStore.stopQueryVoiceOutput()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = getPreferredRecordingMimeType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recordedChunks.value = []
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordedChunks.value.push(event.data)
      }
    }
    recorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop())
      await submitRecordedAudio(mimeType || recorder.mimeType || 'audio/webm')
    }
    mediaRecorder.value = recorder
    recorder.start()
    isRecording.value = true
  } catch (error) {
    console.error('[InputBox] Failed to start recording:', error)
    alert(`无法开始录音: ${error.message}`)
  }
}

const stopRecording = () => {
  if (!mediaRecorder.value || mediaRecorder.value.state === 'inactive') return
  mediaRecorder.value.stop()
  isRecording.value = false
}

const submitRecordedAudio = async (mimeType) => {
  if (recordedChunks.value.length === 0) return
  isTranscribing.value = true
  try {
    const audioBlob = new Blob(recordedChunks.value, { type: mimeType || 'audio/webm' })
    const result = await transcribeVoice(audioBlob, {
      filename: createVoiceFilename(mimeType),
      language: 'zh'
    })
    const transcript = (result?.text || '').trim()
    if (transcript) {
      localValue.value = localValue.value.trim()
        ? `${localValue.value.trim()}\n${transcript}`
        : transcript
      await nextTick()
      textareaRef.value?.focus()
    }
  } catch (error) {
    console.error('[InputBox] Voice transcription failed:', error)
    alert(`语音转文字失败: ${error.message}`)
  } finally {
    isTranscribing.value = false
    recordedChunks.value = []
    mediaRecorder.value = null
  }
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
    'text/html': '.html',
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
  if (attachment.readonlySource === 'drawio_board_selection') return
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
      if (!reactStore.currentState?.sessionId) {
        selectionRestoreGuard.invalidate()
        restoringSelection = false
        reactStore.createSessionId()
      }
      const result = await uploadChatFile(
        file,
        reactStore.currentState?.sessionId,
        reactStore.currentMode
      )
      completeUploadedAttachment(attachments.value, attachment, result)
      const [resource] = normalizeConversationResources({ resources: [result.resource_ref] })
      if (resource && !conversationResources.value.some(item => item.id === resource.id)) {
        conversationResources.value.push(resource)
      }

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

.composer-selection-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.composer-chip {
  border: 1px solid #c9d8ee;
  border-radius: 999px;
  padding: 4px 9px;
  background: #f4f8ff;
  color: #28517a;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.composer-chip.skill-chip {
  border-color: #d4c3ee;
  background: #f8f3ff;
  color: #68429a;
}

.composer-chip.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: default;
}

.composer-chip.active-policy-chip {
  border-color: #75a789;
  background: #f1faf4;
  color: #245c38;
}

.chip-policy-toggle,
.chip-remove {
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.chip-policy-toggle {
  border-right: 1px solid currentColor;
  padding-right: 5px;
  opacity: 0.8;
}

.chip-policy-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.chip-remove {
  font-size: 14px;
  line-height: 1;
}

.composer-chip.invalid {
  border-color: #ef9a9a;
  background: #fff4f4;
  color: #b42318;
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
  width: min(420px, 100%);
  max-height: 320px;
  overflow-y: auto;
}

.palette-header {
  padding: 4px 8px;
  color: #344054;
  font-size: 12px;
  font-weight: 600;
}

.palette-empty {
  padding: 10px 12px;
  color: #667085;
  font-size: 13px;
}

.palette-empty.error {
  color: #b42318;
}

.workflow-tool-item {
  padding: 8px 12px;
  font-size: 14px;
  color: #6b7a99;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;

  small {
    color: #7b879b;
    font-weight: 400;
  }

  &:hover {
    background: #f5f5f5;
    color: #1976D2;
  }

  &.active {
    background: #e3f2fd;
    color: #1976D2;
    font-weight: 500;
  }

  &.disabled {
    cursor: not-allowed;
    opacity: 0.55;
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

.voice-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #d8deea;
  border-radius: 6px;
  background: #fff;
  color: #526173;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    border-color: #1976D2;
    color: #1976D2;
    background: #f4f9ff;
  }

  &:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  &.recording {
    border-color: #d32f2f;
    color: #d32f2f;
    background: #fff5f5;
  }

  &.processing {
    color: #1976D2;
    background: #eef6ff;
  }

  &.active {
    border-color: #1976D2;
    color: #1976D2;
    background: #e3f2fd;
  }
}

.voice-icon {
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
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

.attachment-item.context-attachment {
  border-color: #b7d6ff;
  background: #f4f9ff;
  color: #23527c;
}

.board-sync-message {
  padding: 2px 14px 0;
  color: #526173;
  font-size: 12px;
}

.board-sync-message.error {
  color: #c62828;
}

.attachment-item.context-attachment .attachment-file-name {
  color: #23527c;
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
