<template>
  <!-- 空状态 -->
  <div v-if="notebookDocuments.length === 0" class="empty-state">
    <p>暂无Notebook</p>
  </div>

  <!-- Notebook预览 -->
  <template v-else>
    <div v-for="doc in notebookDocuments" :key="doc.html_id || doc.file_path">
      <iframe
        v-if="doc.html_url"
        :src="doc.html_url"
        class="notebook-iframe"
        type="text/html"
      ></iframe>
    </div>
  </template>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useReactStore } from '@/stores/reactStore'

const reactStore = useReactStore()

// 本地存储Notebook文档列表
const notebookDocuments = ref([])

// 监听 store.lastOfficeDocument，检测Notebook文档
watch(() => reactStore.lastOfficeDocument, (doc, oldDoc) => {
  // 只处理Notebook文档（有html_preview）
  if (!doc?.html_preview) {
    return
  }

  // 确认是notebook类型
  const isNotebook = doc.file_type === 'notebook' ||
                     (doc.file_path && doc.file_path.endsWith('.ipynb'))

  if (!isNotebook) {
    return
  }

  const filePath = doc.file_path
  const fileName = filePath ? filePath.split(/[/\\]/).pop() : 'unknown.ipynb'

  // 检测是否切换到了不同的文档（会话切换）
  if (oldDoc?.file_path && oldDoc.file_path !== filePath) {
    notebookDocuments.value = []
  }

  // 查找现有文档
  const existingDoc = notebookDocuments.value.find(d =>
    d.file_path === filePath || d.file_name === fileName
  )

  if (existingDoc) {
    // 更新现有文档的HTML URL
    if (existingDoc.html_url !== doc.html_preview.html_url) {
      existingDoc.html_url = doc.html_preview.html_url
      existingDoc.html_id = doc.html_preview.html_id
      existingDoc.loading = false
    }
  } else {
    // 添加新文档
    const newDoc = {
      file_name: fileName,
      file_path: filePath,
      html_id: doc.html_preview.html_id,
      html_url: doc.html_preview.html_url,
      loading: false
    }
    notebookDocuments.value.push(newDoc)
  }
}, { immediate: true })
</script>

<style scoped>
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.notebook-iframe {
  width: 100%;
  height: calc(100vh - 200px);
  min-height: 600px;
  border: none;
  display: block;
}
</style>
