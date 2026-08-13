# ReactAnalysisView 重构版本使用指南

## 快速开始

### 1. 导入Composables

```javascript
// 从统一入口导入
import {
  // P0核心功能
  useKbFileUpload,
  useSessionRecovery,
  useVisualizationExtractor,

  // P1重要功能
  useScheduledTaskManager,
  useOfficeDocumentHandler,
  useFileDropZone,

  // P2辅助功能
  useErrorHandling,
  useLogger,
  useKeyboardShortcuts
} from '@/composables/reactAnalysis'
```

### 2. 使用Composables

```vue
<script setup>
import { useKbFileUpload } from '@/composables/reactAnalysis'
import { ref } from 'vue'

const kbStore = useKnowledgeBaseStore()

// 使用知识库上传
const {
  fileInputRef,
  isDragging,
  progress,
  triggerFileSelect,
  handleFileDrop
} = useKbFileUpload(kbStore, {
  onProgress: (progress) => {
    console.log('上传进度:', progress.percent)
  },
  onComplete: (result) => {
    console.log('上传完成:', result)
  }
})
</script>

<template>
  <div
    @drop="handleFileDrop"
    :class="{ 'drag-over': isDragging }"
  >
    <input
      ref="fileInputRef"
      type="file"
      @change="handleFileSelect"
    />
    <button @click="triggerFileSelect">选择文件</button>
  </div>
</template>
```

---

## 核心功能示例

### 知识库上传

```javascript
import { useKbFileUpload } from '@/composables/reactAnalysis'

const kbStore = useKnowledgeBaseStore()

const {
  fileInputRef,
  isDragging,
  progress,
  triggerFileSelect,
  handleFileSelect,
  handleFileDrop,
  uploadFiles,
  cancelUpload
} = useKbFileUpload(kbStore)

// 触发文件选择
triggerFileSelect()

// 上传文件
uploadFiles(fileList, {
  chunking_strategy: 'llm',
  chunk_size: 800,
  chunk_overlap: 100
})

// 取消上传
cancelUpload()
```

### 会话恢复

```javascript
import { useSessionRecovery } from '@/composables/reactAnalysis'

const store = useReactStore()

const {
  isRestoring,
  loadingMore,
  currentSessionId,
  messageCount,
  restoreSessionById,
  loadMoreMessages
} = useSessionRecovery(store)

// 恢复会话
const result = await restoreSessionById('session-id', {
  messageLimit: 5,
  restoreOfficeDocs: true
})

// 加载更多消息
await loadMoreMessages(5, 20)
```

### 可视化提取

```javascript
import { useVisualizationExtractor } from '@/composables/reactAnalysis'

const store = useReactStore()

const {
  allVisualizations,
  hasVisualizations,
  visualizationCount,
  visualizationsByType,
  filterByType,
  findById
} = useVisualizationExtractor(store)

// 获取所有可视化
console.log(allVisualizations.value)

// 按类型筛选
const charts = filterByType('chart')

// 查找特定可视化
const viz = findById('viz-id')
```

### 定时任务管理

```javascript
import { useScheduledTaskManager } from '@/composables/reactAnalysis'

const tasksStore = useScheduledTasksStore()

const {
  isRefreshing,
  tasks,
  stats,
  refreshTasks,
  toggleTask,
  executeTask,
  deleteTask
} = useScheduledTaskManager(tasksStore)

// 刷新任务列表
await refreshTasks()

// 切换任务状态
await toggleTask('task-id')

// 执行任务
await executeTask('task-id')
```

### Office文档处理

```javascript
import { useOfficeDocumentHandler } from '@/composables/reactAnalysis'

const store = useReactStore()

const {
  hasDocument,
  pdfPreview,
  markdownPreview,
  startEditing,
  cancelEdit,
  submitEdit
} = useOfficeDocumentHandler(store)

// 开始编辑
startEditing()

// 提交编辑
const result = await submitEdit({
  file_path: '/path/to/file.docx',
  content: '编辑后的内容',
  doc_type: 'word'
})
```

### 文件拖拽

```javascript
import { useFileDropZone } from '@/composables/reactAnalysis'

const {
  isDragging,
  dropZoneClass,
  handleDragEnter,
  handleDragLeave,
  handleDragOver,
  handleDrop,
  setupDropZone
} = useFileDropZone({
  onDrop: async (files) => {
    console.log('拖放文件:', files)
    // 处理文件
  },
  onError: (errors) => {
    console.error('文件错误:', errors)
  }
})
```

### 错误处理

```javascript
import { useErrorHandling } from '@/composables/reactAnalysis'

const {
  errors,
  lastError,
  hasErrors,
  handleError,
  clearAll,
  retry,
  withErrorHandling
} = useErrorHandling()

// 处理错误
handleError(error, {
  context: 'upload',
  fileId: 'file-123'
})

// 重试操作
await retry(async () => {
  return await someOperation()
}, 3)

// 包装异步函数
const safeFn = withErrorHandling(async () => {
  return await riskyOperation()
})
```

### 日志记录

```javascript
import { useLogger } from '@/composables/reactAnalysis'

const {
  logs,
  debug,
  info,
  warn,
  error,
  clear,
  exportLogs,
  search
} = useLogger({
  prefix: '[MyComponent]',
  level: 'debug'
})

// 记录日志
debug('调试信息', { data: 'value' })
info('普通信息')
warn('警告信息')
error('错误信息', { error: err })

// 导出日志
const jsonLogs = exportLogs()

// 搜索日志
const results = search('error')
```

---

## 最佳实践

### 1. 错误处理

```javascript
// ✅ 推荐：使用composable的错误处理
const { handleError } = useErrorHandling()

try {
  await riskyOperation()
} catch (error) {
  handleError(error, { context: 'upload' })
}

// ❌ 不推荐：直接console.error
console.error(error)
```

### 2. 日志记录

```javascript
// ✅ 推荐：使用composable的日志
const { info, error } = useLogger()

info('操作开始', { userId: '123' })
error('操作失败', { error: err })

// ❌ 不推荐：直接console.log
console.log('操作开始')
```

### 3. 资源清理

```javascript
// ✅ 推荐：在组件卸载时清理
import { onBeforeUnmount } from 'vue'

const { startAutoRefresh, stopAutoRefresh } = useScheduledTaskManager(tasksStore)

onMounted(() => {
  startAutoRefresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
```

### 4. 响应式数据

```javascript
// ✅ 推荐：使用computed访问响应式数据
const { allVisualizations } = useVisualizationExtractor(store)

watch(allVisualizations, (vizs) => {
  console.log('可视化变化:', vizs)
})

// ❌ 不推荐：直接访问内部状态
// store.currentState.visualizationHistory
```

---

## 迁移指南

### 从原始代码迁移到重构版本

**步骤1**: 替换大段逻辑为composable

```javascript
// ❌ 旧代码（300行）
const handleKbFileSelect = async (event) => {
  const files = event.target.files
  // ... 100行文件验证逻辑
  // ... 100行上传进度逻辑
  // ... 100行错误处理逻辑
}

// ✅ 新代码（3行）
const { handleFileSelect } = useKbFileUpload(kbStore)
```

**步骤2**: 更新模板绑定

```vue
<!-- ❌ 旧代码 -->
<div
  @dragover="handleChatAreaDragOver"
  @dragleave="handleChatAreaDragLeave"
  @drop="handleChatAreaDrop"
>

<!-- ✅ 新代码 -->
<div
  @dragover="handleDragOver"
  @dragleave="handleDragLeave"
  @drop="handleDrop"
>
```

**步骤3**: 测试验证

1. 功能测试
2. 性能测试
3. 错误处理测试

---

## 常见问题

### Q: 如何在多个组件间共享状态？

A: 使用store或创建共享的composable实例：

```javascript
// composables/sharedKbUpload.js
let sharedInstance = null

export function useSharedKbUpload() {
  if (!sharedInstance) {
    sharedInstance = useKbFileUpload(kbStore)
  }
  return sharedInstance
}
```

### Q: 如何处理异步错误？

A: 使用错误处理composable：

```javascript
const { handleError, retry } = useErrorHandling()

const result = await retry(async () => {
  return await apiCall()
}, 3)
```

### Q: 如何优化性能？

A: 使用computed和watch：

```javascript
const { allVisualizations } = useVisualizationExtractor(store)

// ✅ 使用computed缓存结果
const chartCount = computed(() =>
  allVisualizations.value.filter(v => v.type === 'chart').length
)
```

---

## 获取帮助

- 📖 查看测试报告：`tests/REFACTORING_TEST_REPORT.md`
- 📋 查看测试计划：`tests/REFACTORING_TEST_PLAN.md`
- 💻 查看代码示例：`src/composables/reactAnalysis/`

---

**版本**: 1.0.0
**更新日期**: 2026-04-11
**维护者**: Claude Code
