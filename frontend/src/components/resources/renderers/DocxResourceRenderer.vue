<template>
  <div class="docx-viewer">
    <div v-if="loading" class="docx-state">正在加载文档...</div>
    <div v-else-if="error" class="docx-state error">
      <p>{{ error }}</p>
      <p class="hint">可下载后使用 Word/WPS 打开查看完整排版。</p>
    </div>
    <div v-else class="docx-scroll">
      <!-- docx-editor viewing 模式：纯前端解析 OOXML 渲染，无服务端转换 -->
      <DocxEditor
        :document-buffer="buffer"
        mode="viewing"
        :show-toolbar="false"
        :color-mode="'light'"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, shallowRef } from 'vue'
import { DocxEditor } from '@eigenpal/docx-editor-vue'
import '@eigenpal/docx-editor-vue/styles.css'

const props = defineProps({
  resource: { type: Object, required: true },
  group: { type: Object, default: null },
  contentUrl: { type: String, required: true }
})

const loading = ref(true)
const error = ref('')
const buffer = shallowRef<ArrayBuffer | null>(null)

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
</script>

<style scoped>
.docx-viewer { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.docx-scroll { flex: 1; min-height: 0; overflow: auto; background: var(--bg-container, #f5f6f7); }
.docx-state { display: grid; place-content: center; height: 100%; color: var(--text-2, #667085); text-align: center; }
.docx-state.error { color: var(--color-danger, #d92d20); }
.docx-state .hint { color: var(--text-2, #667085); font-size: 12px; }
</style>
