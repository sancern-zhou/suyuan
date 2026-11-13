<template>
  <div class="docx-viewer">
    <div class="docx-toolbar">
      <div class="toolbar-actions">
        <span v-if="dirty" class="dirty-state">未保存</span>
        <template v-if="editable">
          <button v-if="!editing" type="button" :disabled="loading" @click="enterEditing">编辑</button>
          <template v-else>
            <button type="button" class="primary" :disabled="saving || !dirty" @click="saveDocument">
              {{ saving ? '保存中...' : '保存为新版本' }}
            </button>
            <button type="button" :disabled="saving" @click="leaveEditing">退出编辑</button>
          </template>
        </template>
        <span v-if="status" class="status">{{ status }}</span>
      </div>
    </div>
    <div v-if="loading" class="docx-state">正在加载文档...</div>
    <div v-else-if="error" class="docx-state error">
      <p>{{ error }}</p>
      <p class="hint">可下载后使用 Word/WPS 打开查看完整排版。</p>
    </div>
    <div v-else class="docx-scroll">
      <!-- docx-editor：viewing 预览 / editing 交互编辑，纯前端解析 OOXML -->
      <DocxEditor
        :key="editing ? 'editing' : 'viewing'"
        ref="editorRef"
        :document-buffer="buffer"
        :mode="editing ? 'editing' : 'viewing'"
        :show-toolbar="editing"
        :show-menu-bar="editing"
        :show-file-open="false"
        :color-mode="'light'"
        :on-change="handleChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { DocxEditor } from '@eigenpal/docx-editor-vue'
import '@eigenpal/docx-editor-vue/styles.css'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { saveDocxResource } from '@/services/spreadsheetResourceApi.js'

const props = defineProps({
  resource: { type: Object, required: true },
  group: { type: Object, default: null },
  contentUrl: { type: String, required: true }
})

const resourceStore = useSessionResourceStore()
const loading = ref(true)
const error = ref('')
const status = ref('')
const buffer = shallowRef<ArrayBuffer | null>(null)
const editing = ref(false)
const dirty = ref(false)
const saving = ref(false)
const editorRef = ref<any>(null)

const editable = computed(() => Boolean(props.resource?.actions?.save))

onMounted(async () => {
  try {
    const response = await fetch(props.contentUrl)
    if (!response.ok) throw new Error(`文档内容加载失败 (${response.status})`)
    buffer.value = await response.arrayBuffer()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '文档加载失败'
  } finally {
    loading.value = false
  }
})

const handleChange = () => {
  dirty.value = true
  status.value = ''
}

const enterEditing = () => {
  editing.value = true
  dirty.value = false
  status.value = ''
}

const leaveEditing = async () => {
  if (dirty.value && !window.confirm('文档有未保存的修改，确定要放弃这些修改吗？')) return
  editing.value = false
  dirty.value = false
  status.value = ''
}

const saveDocument = async () => {
  if (!editorRef.value?.save) return
  const originSessionId = resourceStore.activeSessionId
  const originResourceId = props.resource.resource_id
  saving.value = true
  error.value = ''
  status.value = ''
  try {
    const bytes = await editorRef.value.save()
    if (!bytes || bytes.byteLength === 0) throw new Error('导出内容为空')
    const receipt = await saveDocxResource(props.resource, bytes)
    dirty.value = false
    status.value = `已保存为 v${receipt.resource_version ?? ''} 新版本`
    await resourceStore.refreshIfNewer(originSessionId, receipt.resource_version)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    if (
      resourceStore.activeSessionId === originSessionId
      && props.resource.resource_id === originResourceId
    ) saving.value = false
  }
}
</script>

<style scoped>
.docx-viewer { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.docx-toolbar { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 6px 12px; border-bottom: 1px solid var(--border-1, #e2e8f0); min-height: 34px; }
.toolbar-actions { display: flex; align-items: center; gap: 8px; }
.dirty-state { color: var(--color-danger, #d92d20); font-size: 12px; }
.status { color: var(--text-2, #667085); font-size: 12px; }
.docx-viewer button { border: 0; background: transparent; color: var(--color-primary); cursor: pointer; font: inherit; }
.docx-viewer button.primary { font-weight: 600; }
.docx-viewer button:disabled { opacity: 0.5; cursor: default; }
.docx-scroll { flex: 1; min-height: 0; overflow: auto; background: var(--bg-container, #f5f6f7); }
.docx-state { display: grid; place-content: center; height: 100%; color: var(--text-2, #667085); text-align: center; }
.docx-state.error { color: var(--color-danger, #d92d20); }
.docx-state .hint { color: var(--text-2, #667085); font-size: 12px; }
</style>
