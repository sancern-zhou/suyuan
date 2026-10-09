<template>
  <div v-if="visible" class="dialog-overlay" @click.self="handleClose">
    <div class="dialog">
      <div class="dialog-header">
        <div class="dialog-title">
          <h3>模式记忆</h3>
          <span class="mode-badge">{{ modeLabel }}</span>
        </div>
        <button class="btn-close" title="关闭" @click="handleClose">×</button>
      </div>

      <div class="dialog-body">
        <div v-if="loading" class="dialog-state">加载中...</div>

        <template v-else-if="loadError">
          <div class="dialog-state error">{{ loadError }}</div>
          <div class="dialog-state-actions">
            <button class="btn-secondary" @click="loadMemory">重新加载</button>
          </div>
        </template>

        <template v-else>
          <div class="memory-meta-bar">
            <span>版本 v{{ memoryData.meta?.version ?? 0 }}</span>
            <span v-if="memoryData.meta?.updated_at">更新于 {{ formatTime(memoryData.meta.updated_at) }}</span>
            <span class="memory-hint">记忆由 Agent 在对话中自动积累，可在此人工纠正</span>
          </div>

          <template v-if="editing">
            <textarea
              v-model="memoryDraft"
              class="memory-editor"
              rows="16"
              placeholder="编辑模式长期记忆（Markdown）"
              spellcheck="false"
            ></textarea>
            <div v-if="editError" class="form-error" role="alert">{{ editError }}</div>
            <div v-if="conflictDetected" class="dialog-footer inline">
              <button class="btn-secondary" :disabled="saving" @click="reloadAfterConflict">
                {{ saving ? '加载中...' : '重新加载最新记忆' }}
              </button>
            </div>
            <div class="dialog-footer inline">
              <button class="btn-secondary" :disabled="saving" @click="cancelEdit">取消</button>
              <button class="btn-primary" :disabled="saving || !memoryDraft.trim()" @click="saveMemory">
                {{ saving ? '保存中...' : '保存记忆' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div v-if="memoryData.memory" class="memory-content markdown-body" v-html="renderedMemory"></div>
            <div v-else class="dialog-state">当前模式暂无记忆内容</div>
            <div class="dialog-footer inline">
              <button class="btn-secondary" @click="handleClose">关闭</button>
              <button class="btn-primary" @click="startEdit">编辑记忆</button>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { getModeMemory, updateModeMemory } from '@/api/agentMemory.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  agentMode: {
    type: String,
    default: 'assistant'
  }
})

const emit = defineEmits(['close'])

const md = new MarkdownIt({ html: false, linkify: true, breaks: false })

const loading = ref(false)
const loadError = ref('')
const memoryData = ref({ mode: '', memory: '', meta: {} })
const editing = ref(false)
const memoryDraft = ref('')
const saving = ref(false)
const editError = ref('')
const conflictDetected = ref(false)

const MODE_LABELS = {
  assistant: '通用助手',
  query: '智能问数',
  knowledge: '知识问答',
  expert: '专家分析',
  report: '报告生成',
  chart: '图表生成',
  ppt: 'PPT 生成',
  board: '看板'
}

const modeLabel = computed(() => MODE_LABELS[props.agentMode] || props.agentMode)

const renderedMemory = computed(() => {
  const content = memoryData.value?.memory
  return content ? md.render(content) : ''
})

const loadMemory = async () => {
  if (!props.agentMode) return
  loading.value = true
  loadError.value = ''
  editing.value = false
  editError.value = ''
  conflictDetected.value = false
  try {
    memoryData.value = await getModeMemory(props.agentMode)
  } catch (error) {
    console.error('Failed to load mode memory:', error)
    loadError.value = '记忆读取失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

const startEdit = () => {
  memoryDraft.value = memoryData.value?.memory || ''
  editError.value = ''
  conflictDetected.value = false
  editing.value = true
}

const cancelEdit = () => {
  editing.value = false
  editError.value = ''
  conflictDetected.value = false
}

const saveMemory = async () => {
  const content = memoryDraft.value.trim()
  if (!content) {
    editError.value = '记忆内容不能为空'
    return
  }
  saving.value = true
  editError.value = ''
  conflictDetected.value = false
  try {
    memoryData.value = await updateModeMemory(
      props.agentMode,
      content,
      memoryData.value?.meta?.version ?? 0,
      memoryData.value?.meta?.file_mtime_ns ?? null
    )
    editing.value = false
  } catch (error) {
    console.error('Failed to save mode memory:', error)
    if (error.status === 409) {
      conflictDetected.value = true
      editError.value = '记忆已被其他操作更新（后台整合或他人编辑），请重新加载后再编辑'
    } else {
      editError.value = error.message || '记忆保存失败'
    }
  } finally {
    saving.value = false
  }
}

const reloadAfterConflict = async () => {
  await loadMemory()
}

const formatTime = (value) => {
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

const handleClose = () => {
  if (saving.value) return
  editing.value = false
  editError.value = ''
  emit('close')
}

watch(() => props.visible, (visible) => {
  if (visible) loadMemory()
})

watch(() => props.agentMode, () => {
  if (props.visible) loadMemory()
})

defineExpose({ loadMemory, reloadAfterConflict })
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 720px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-2);
}

.dialog-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dialog-title h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.mode-badge {
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-muted, #f1f5f9);
  color: var(--text-2, #475569);
  font-size: 12px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-3);
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: var(--bg-hover);
  color: var(--text-1);
}

.dialog-body {
  padding: 16px 20px 20px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dialog-state {
  padding: 24px 0;
  text-align: center;
  color: var(--text-3, #94a3b8);
  font-size: 14px;
}

.dialog-state.error {
  color: var(--color-danger, #dc2626);
}

.dialog-state-actions {
  display: flex;
  justify-content: center;
}

.memory-meta-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 12px;
  color: var(--text-3, #64748b);
}

.memory-hint {
  margin-left: auto;
}

.memory-editor {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-3);
  border-radius: 6px;
  font-size: 13px;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  line-height: 1.6;
  resize: vertical;
  min-height: 280px;
}

.memory-editor:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-ring);
}

.memory-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-1, #1f2937);
  border: 1px solid var(--border-3);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--bg-muted, #f8fafc);
  overflow-wrap: anywhere;
}

.memory-content :deep(h1),
.memory-content :deep(h2),
.memory-content :deep(h3) {
  margin: 12px 0 6px;
  font-size: 14px;
}

.memory-content :deep(h1:first-child),
.memory-content :deep(h2:first-child) {
  margin-top: 0;
}

.memory-content :deep(ul),
.memory-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}

.form-error {
  color: var(--color-danger, #dc2626);
  font-size: 13px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.dialog-footer.inline {
  padding-top: 4px;
}

.btn-primary {
  padding: 8px 16px;
  background: var(--color-primary, #2563eb);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 8px 16px;
  background: var(--bg-muted, #f1f5f9);
  color: var(--text-1, #1f2937);
  border: 1px solid var(--border-3);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover, #e2e8f0);
}
</style>
