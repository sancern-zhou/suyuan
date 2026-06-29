<template>
  <div class="docx-online-editor">
    <div class="docx-editor-header">
      <div class="docx-editor-title">
        <span class="docx-editor-name">{{ documentName }}</span>
        <span v-if="dirty" class="docx-editor-state">未保存</span>
      </div>
      <div class="docx-editor-actions">
        <button type="button" class="secondary-btn" :disabled="saving" @click="handleCancel">
          取消
        </button>
        <button type="button" class="primary-btn" :disabled="!canSave" @click="handleSave">
          {{ saving ? '保存中...' : '保存并预览' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="docx-editor-status">
      <div class="spinner"></div>
      <span>正在打开DOCX文档...</span>
    </div>

    <div v-else-if="errorMessage" class="docx-editor-error">
      <p>{{ errorMessage }}</p>
      <button type="button" class="secondary-btn" @click="loadDocument">重试</button>
    </div>

    <DocxEditor
      v-else-if="documentBuffer"
      ref="editorRef"
      :document-buffer="documentBuffer"
      :document-name="documentName"
      mode="editing"
      color-mode="light"
      :show-file-open="false"
      :show-help-menu="false"
      :show-outline-button="false"
      class-name="embedded-docx-editor"
      @change="handleChange"
      @error="handleEditorError"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { DocxEditor } from '@eigenpal/docx-editor-vue'
import '@eigenpal/docx-editor-vue/styles.css'
import { openDocxForEditing, saveEditedDocx } from '@/services/docxOnlineEditorApi'

const props = defineProps({
  doc: {
    type: Object,
    required: true
  },
  sessionId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['cancel', 'saved'])

const editorRef = ref(null)
const documentBuffer = ref(null)
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const errorMessage = ref('')

const documentName = computed(() => props.doc?.file_name || 'document.docx')
const canSave = computed(() => !!documentBuffer.value && !loading.value && !saving.value)

onMounted(() => {
  loadDocument()
})

async function loadDocument() {
  if (!props.doc?.file_path) {
    errorMessage.value = '缺少DOCX文件路径'
    return
  }

  loading.value = true
  errorMessage.value = ''
  dirty.value = false
  try {
    documentBuffer.value = await openDocxForEditing(props.doc.file_path)
  } catch (error) {
    errorMessage.value = error.message || '打开DOCX文档失败'
  } finally {
    loading.value = false
  }
}

function handleChange() {
  dirty.value = true
}

function handleEditorError(error) {
  errorMessage.value = error?.message || 'DOCX编辑器加载失败'
}

function handleCancel() {
  emit('cancel')
}

async function handleSave() {
  if (!editorRef.value?.save) {
    errorMessage.value = 'DOCX编辑器尚未准备好'
    return
  }

  saving.value = true
  errorMessage.value = ''
  try {
    const buffer = await editorRef.value.save()
    if (!buffer) {
      throw new Error('没有可保存的DOCX内容')
    }
    const document = await saveEditedDocx({
      filePath: props.doc.file_path,
      sessionId: props.sessionId,
      fileName: documentName.value,
      buffer
    })
    dirty.value = false
    emit('saved', document)
  } catch (error) {
    errorMessage.value = error.message || '保存DOCX文档失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped lang="scss">
.docx-online-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #f5f6f8;
}

.docx-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #ffffff;
  border-bottom: 1px solid #d9dde5;
  flex-shrink: 0;
}

.docx-editor-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.docx-editor-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  color: #20242c;
}

.docx-editor-state {
  flex-shrink: 0;
  font-size: 12px;
  color: #8a5a00;
  background: #fff4d6;
  border: 1px solid #f0d58a;
  border-radius: 4px;
  padding: 2px 6px;
}

.docx-editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.primary-btn,
.secondary-btn {
  border: 1px solid transparent;
  border-radius: 4px;
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

.primary-btn {
  background: #1f6feb;
  color: #ffffff;
}

.secondary-btn {
  background: #ffffff;
  color: #24292f;
  border-color: #d0d7de;
}

.docx-editor-status,
.docx-editor-error {
  margin: 16px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid #d9dde5;
  border-radius: 6px;
  color: #394150;
  display: flex;
  align-items: center;
  gap: 10px;
}

.docx-editor-error {
  align-items: flex-start;
  flex-direction: column;
  color: #a40e26;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #e5e7eb;
  border-top-color: #1f6feb;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

:deep(.embedded-docx-editor) {
  flex: 1;
  min-height: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
