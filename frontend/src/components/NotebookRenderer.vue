<template>
  <div class="notebook-renderer">
    <!-- 空状态 -->
    <div v-if="!notebookData || !notebookData.cells" class="empty-state">
      <p>暂无Notebook内容</p>
    </div>

    <!-- Notebook内容 -->
    <template v-else>
      <!-- 分享按钮 -->
      <div class="notebook-actions">
        <button
          @click="handleShare"
          class="share-button"
          :disabled="isGenerating"
        >
          <span v-if="isGenerating">生成中...</span>
          <span v-else>📤 分享报告</span>
        </button>
      </div>

      <!-- Notebook单元格 -->
      <div v-for="(cell, index) in notebookData.cells" :key="index" class="cell">
        <!-- Markdown单元格 -->
        <div v-if="cell.cell_type === 'markdown'" class="markdown-cell">
          <div class="markdown-content" v-html="renderMarkdown(cell.source)"></div>
        </div>

        <!-- 代码单元格 -->
        <div v-else-if="cell.cell_type === 'code'" class="code-cell">
          <div class="input-area">
            <span class="input-prompt">In:</span>
            <pre><code>{{ cell.source }}</code></pre>
          </div>

          <!-- 输出区域 -->
          <div v-if="cell.outputs && cell.outputs.length" class="output-area">
            <div v-for="(output, i) in cell.outputs" :key="i">
              <!-- 文本输出 -->
              <pre v-if="output.text" class="output-text">{{ output.text }}</pre>

              <!-- 数据输出 -->
              <template v-if="output.data">
                <!-- PNG图片 -->
                <img
                  v-if="output.data['image/png']"
                  :src="getImageUrl(output, 'image/png')"
                  alt="Output"
                />

                <!-- JPEG图片 -->
                <img
                  v-else-if="output.data['image/jpeg']"
                  :src="getImageUrl(output, 'image/jpeg')"
                  alt="Output"
                />

                <!-- 纯文本 -->
                <pre v-else-if="output.data['text/plain']" class="output-text">
                  {{ output.data['text/plain'] }}
                </pre>
              </template>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 分享结果对话框 -->
    <div v-if="shareResult" class="share-dialog-overlay" @click="closeShareDialog">
      <div class="share-dialog" @click.stop>
        <h3>分享链接已生成</h3>
        <p>复制以下链接分享给他人：</p>
        <div class="share-link-box">
          <input
            ref="shareLinkInput"
            type="text"
            :value="shareResult.share_link"
            readonly
            @click="copyLink"
          />
          <button @click="copyLink" class="copy-button">复制</button>
        </div>
        <div class="share-dialog-actions">
          <button @click="closeShareDialog" class="close-button">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

const props = defineProps({
  notebookData: {
    type: Object,
    required: true
  },
  notebookPath: {
    type: String,
    default: ''
  },
  imageBaseUrl: {
    type: String,
    default: '/reports/'
  }
})

const emit = defineEmits(['share'])

const isGenerating = ref(false)
const shareResult = ref(null)
const shareLinkInput = ref(null)

// 渲染Markdown
const renderMarkdown = (source) => {
  if (!source) return ''
  try {
    return md.render(source)
  } catch (e) {
    console.error('Markdown渲染失败:', e)
    return source
  }
}

// 获取图片URL
const getImageUrl = (output, mimeType) => {
  // 尝试从metadata获取文件名
  const metadata = output.metadata || {}
  const filename = metadata.filename || (metadata.filenames && metadata.filenames[0])

  if (filename) {
    return `${props.imageBaseUrl}${filename}`
  }

  // 如果没有文件名，尝试使用base64数据
  if (output.data && output.data[mimeType]) {
    return `data:${mimeType};base64,${output.data[mimeType]}`
  }

  return ''
}

// 处理分享
const handleShare = async () => {
  if (!props.notebookPath) {
    alert('无法分享：缺少Notebook文件路径')
    return
  }

  isGenerating.value = true

  try {
    // 调用后端API生成分享HTML
    const response = await fetch('/api/tools/execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        tool: 'generate_shareable_notebook',
        parameters: {
          notebook_path: props.notebookPath
        }
      })
    })

    const result = await response.json()

    if (result.success) {
      shareResult.value = result.data
      emit('share', result.data)
    } else {
      alert('生成分享链接失败：' + (result.summary || '未知错误'))
    }
  } catch (error) {
    console.error('生成分享链接失败:', error)
    alert('生成分享链接失败：' + error.message)
  } finally {
    isGenerating.value = false
  }
}

// 复制链接
const copyLink = () => {
  if (shareLinkInput.value) {
    shareLinkInput.value.select()
    navigator.clipboard.writeText(shareResult.value.share_link).then(() => {
      alert('链接已复制到剪贴板')
    }).catch(() => {
      // 降级方案
      document.execCommand('copy')
      alert('链接已复制到剪贴板')
    })
  }
}

// 关闭分享对话框
const closeShareDialog = () => {
  shareResult.value = null
}
</script>

<style scoped>
.notebook-renderer {
  padding: 20px;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.notebook-actions {
  margin-bottom: 20px;
  display: flex;
  justify-content: flex-end;
}

.share-button {
  padding: 8px 16px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.3s;
}

.share-button:hover:not(:disabled) {
  background: #40a9ff;
}

.share-button:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

.cell {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: white;
}

.markdown-cell {
  border-left: 3px solid #4CAF50;
  background: #f9f9f9;
}

.code-cell {
  border-left: 3px solid #2196F3;
}

.input-area {
  margin-bottom: 12px;
}

.input-prompt {
  color: #303F9F;
  font-weight: bold;
  font-family: "Courier New", monospace;
  font-size: 14px;
}

.output-area {
  margin-top: 12px;
  padding: 12px;
  background: #f8f8f8;
  border-radius: 4px;
  border-left: 3px solid #D32F2F;
}

.output-prompt {
  color: #D32F2F;
  font-weight: bold;
  font-family: "Courier New", monospace;
}

pre {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  overflow-x: auto;
  font-family: "Courier New", monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 8px 0;
}

code {
  font-family: "Courier New", monospace;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}

.output-text {
  background: white;
  margin: 0;
}

.markdown-content {
  line-height: 1.6;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4),
.markdown-content :deep(h5),
.markdown-content :deep(h6) {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  color: #333;
  font-weight: 600;
}

.markdown-content :deep(h1) {
  font-size: 2em;
  border-bottom: 2px solid #eee;
  padding-bottom: 0.3em;
}

.markdown-content :deep(h2) {
  font-size: 1.5em;
  border-bottom: 1px solid #eee;
  padding-bottom: 0.3em;
}

.markdown-content :deep(h3) {
  font-size: 1.25em;
}

.markdown-content :deep(p) {
  margin: 1em 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 2em;
  margin: 1em 0;
}

.markdown-content :deep(li) {
  margin: 0.5em 0;
}

.markdown-content :deep(img) {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 16px 0;
}

/* 分享对话框 */
.share-dialog-overlay {
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

.share-dialog {
  background: white;
  padding: 24px;
  border-radius: 8px;
  min-width: 400px;
  max-width: 600px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.share-dialog h3 {
  margin-top: 0;
  margin-bottom: 16px;
  color: #333;
}

.share-dialog p {
  color: #666;
  margin-bottom: 12px;
}

.share-link-box {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.share-link-box input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}

.share-link-box input:focus {
  outline: none;
  border-color: #1890ff;
}

.copy-button {
  padding: 8px 16px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

.copy-button:hover {
  background: #40a9ff;
}

.share-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.close-button {
  padding: 8px 16px;
  background: #f5f5f5;
  color: #666;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.close-button:hover {
  background: #e8e8e8;
}

/* 响应式 */
@media (max-width: 768px) {
  .notebook-renderer {
    padding: 16px;
  }

  .cell {
    padding: 12px;
    margin-bottom: 16px;
  }

  .share-dialog {
    min-width: auto;
    max-width: 90%;
    margin: 16px;
  }

  .share-link-box {
    flex-direction: column;
  }

  pre {
    font-size: 12px;
    padding: 8px;
  }

  code {
    font-size: 12px;
  }
}
</style>
