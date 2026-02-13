<template>
  <div class="knowledge-qa-view">
    <div class="qa-header">
      <h1>知识问答</h1>
      <p>基于知识库的智能问答系统</p>
    </div>

    <div class="qa-main">
      <!-- 左侧：对话区域 -->
      <div class="conversation-panel">
        <div class="messages-container" ref="messagesContainer">
          <!-- 欢迎提示 -->
          <div v-if="messages.length === 0" class="welcome-message">
            <div class="welcome-icon">?</div>
            <h2>欢迎使用知识问答</h2>
            <p>我可以基于您上传的文档知识库回答问题。</p>
            <div class="quick-questions">
              <p>试试这样问：</p>
              <button
                v-for="(q, index) in quickQuestions"
                :key="index"
                type="button"
                @click="sendQuickQuestion(q)"
              >
                {{ q }}
              </button>
            </div>
          </div>

          <!-- 消息列表 -->
          <div
            v-for="(msg, index) in messages"
            :key="index"
            class="message-item"
            :class="msg.role"
          >
            <div class="message-avatar">
              <span v-if="msg.role === 'user'">U</span>
              <span v-else>AI</span>
            </div>
            <div class="message-content">
              <div class="message-role">{{ msg.role === 'user' ? '你' : '知识专家' }}</div>
              <div class="message-text" v-html="formatMessage(msg.content)"></div>
            </div>
          </div>

          <!-- 正在思考/检索中 -->
          <div v-if="isSearching" class="message-item assistant searching">
            <div class="message-avatar">AI</div>
            <div class="message-content">
              <div class="message-role">知识专家</div>
              <div class="message-text searching-text">
                <span class="searching-indicator"></span>
                正在检索知识库...
              </div>
            </div>
          </div>

          <!-- 正在生成回答 -->
          <div v-if="isGenerating" class="message-item assistant generating">
            <div class="message-avatar">AI</div>
            <div class="message-content">
              <div class="message-role">知识专家</div>
              <div class="message-text" id="generating-text">
                <span class="typing-cursor"></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="input-area">
          <div class="input-wrapper">
            <textarea
              v-model="userInput"
              ref="inputRef"
              placeholder="输入您的问题..."
              @keydown.enter.exact.prevent="sendMessage"
              @input="autoResize"
              rows="1"
            ></textarea>
            <button
              class="send-btn"
              type="button"
              :disabled="!canSend"
              @click="sendMessage"
            >
              发送
            </button>
          </div>
          <div class="input-hint">
            按 Enter 发送，Shift+Enter 换行
          </div>
        </div>
      </div>

      <!-- 右侧：来源详情面板 -->
      <div class="sources-panel" v-if="selectedSources.length > 0">
        <div class="sources-panel-header">
          <h3>参考来源详情</h3>
          <button class="close-btn" @click="selectedSources = []">&times;</button>
        </div>
        <div class="sources-panel-content">
          <div
            v-for="(source, sIdx) in selectedSources"
            :key="sIdx"
            class="source-detail-item"
          >
            <div class="source-header">
              <span class="source-rank">#{{ sIdx + 1 }}</span>
              <span class="source-score">{{ (source.score * 100).toFixed(0) }}% 相关</span>
              <span class="source-name">{{ source.source || source.knowledge_base_name || '未知来源' }}</span>
            </div>
            <div class="source-content">
              {{ source.content || source.text || '暂无内容' }}
            </div>
          </div>
        </div>
      </div>
      <div class="sources-panel empty" v-else>
        <div class="empty-tip">
          <span class="empty-icon">?</span>
          <p>点击AI回答查看检索到的参考来源详情</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { knowledgeQAStream, getConversationHistory } from '@/api/knowledgeQA'

const messages = ref([])
const userInput = ref('')
const isSearching = ref(false)
const isGenerating = ref(false)
const currentAnswer = ref('')
const messagesContainer = ref(null)
const inputRef = ref(null)
const sessionId = ref(null)
const selectedSources = ref([])

// 快捷问题
const quickQuestions = [
  '这个知识库包含哪些内容？',
  '如何上传和管理文档？',
  '支持哪些文件格式？',
  '知识检索是如何工作的？'
]

// Session storage key
const SESSION_ID_KEY = 'kqa_session_id'

// 加载对话历史
async function loadHistory(sid) {
  try {
    const history = await getConversationHistory(sid)
    if (history.turns && history.turns.length > 0) {
      // 恢复历史消息
      for (const turn of history.turns) {
        messages.value.push({
          role: turn.role,
          content: turn.content,
          sources: turn.sources || []
        })
      }
      // 滚动到底部
      scrollToBottom()
    }
  } catch (error) {
    console.warn('加载对话历史失败:', error)
    // 历史加载失败不影响正常使用
  }
}

// 计算属性
const canSend = computed(() => {
  return userInput.value.trim() && !isSearching.value && !isGenerating.value
})

// 自动调整输入框高度
function autoResize() {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 150) + 'px'
    }
  })
}

// 发送快捷问题
function sendQuickQuestion(question) {
  userInput.value = question
  sendMessage()
}

// 发送消息
async function sendMessage() {
  if (!canSend.value) return

  const question = userInput.value.trim()
  if (!question) return

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: question
  })

  userInput.value = ''
  nextTick(() => {
    autoResize()
    scrollToBottom()
  })

  // 设置搜索状态
  isSearching.value = true
  isGenerating.value = false
  currentAnswer.value = ''

  // 添加空的AI消息容器
  messages.value.push({
    role: 'assistant',
    content: '',
    sources: []
  })

  try {
    // 调用流式问答API，传递session_id
    await knowledgeQAStream(
      question,
      {
        session_id: sessionId.value,
        knowledge_base_ids: null,
        top_k: 5,
        use_reranker: true
      },
      // onMessage
      (eventData) => {
        if (eventData.type === 'start') {
          // 收到会话ID，保存到本地
          const newSessionId = eventData.data.session_id
          if (newSessionId && newSessionId !== sessionId.value) {
            sessionId.value = newSessionId
            localStorage.setItem(SESSION_ID_KEY, newSessionId)
            console.log('QA started, session:', newSessionId)
          }
        }

        if (eventData.type === 'answer_delta') {
          // 更新回答
          isSearching.value = false
          isGenerating.value = true
          currentAnswer.value += eventData.data.delta

          // 更新最后一条消息
          const lastMsg = messages.value[messages.value.length - 1]
          lastMsg.content = currentAnswer.value

          // 实时滚动
          scrollToBottom()

          // 更新打字效果
          updateTypingEffect(currentAnswer.value)
        }

        if (eventData.type === 'complete') {
          // 问答完成
          isSearching.value = false
          isGenerating.value = false

          // 更新来源信息
          const lastMsg = messages.value[messages.value.length - 1]
          lastMsg.sources = eventData.data.sources || []
          selectedSources.value = lastMsg.sources  // 更新右侧面板显示

          // 移除打字光标
          const typingEl = document.querySelector('.typing-cursor')
          if (typingEl) {
            typingEl.remove()
          }

          console.log('QA completed, sources:', lastMsg.sources)
        }
      },
      // onError
      (error) => {
        console.error('QA error:', error)
        isSearching.value = false
        isGenerating.value = false

        // 添加错误消息
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg.role === 'assistant' && !lastMsg.content) {
          messages.value.pop()
        }
        messages.value.push({
          role: 'assistant',
          content: `抱歉，发生了错误：${error.message}`,
          sources: []
        })
      },
      // onComplete
      () => {
        isSearching.value = false
        isGenerating.value = false
      }
    )
  } catch (error) {
    console.error('QA failed:', error)
    isSearching.value = false
    isGenerating.value = false

    messages.value.push({
      role: 'assistant',
      content: `抱歉，发生了错误：${error.message}`,
      sources: []
    })
  }

  scrollToBottom()
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 更新打字效果
function updateTypingEffect(text) {
  nextTick(() => {
    const generatingText = document.getElementById('generating-text')
    if (generatingText) {
      // 移除光标元素（如果存在）
      let cursor = generatingText.querySelector('.typing-cursor')
      if (!cursor) {
        cursor = document.createElement('span')
        cursor.className = 'typing-cursor'
        generatingText.appendChild(cursor)
      }
    }
  })
}

// 格式化消息（支持简单的markdown）
function formatMessage(content) {
  if (!content) return ''

  // 转义HTML
  let formatted = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 处理代码块
  formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
  formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 处理粗体
  formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 处理列表
  formatted = formatted.replace(/^- (.+)$/gm, '<li>$1</li>')
  formatted = formatted.replace(/(<li>.*<\/li>)+/g, '<ul>$&</ul>')

  // 处理换行
  formatted = formatted.replace(/\n/g, '<br>')

  return formatted
}

onMounted(async () => {
  autoResize()

  // 恢复会话ID
  const savedSessionId = localStorage.getItem(SESSION_ID_KEY)
  if (savedSessionId) {
    sessionId.value = savedSessionId
    // 加载对话历史
    await loadHistory(savedSessionId)
  }
})
</script>

<style lang="scss" scoped>
.knowledge-qa-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6fb;
}

.qa-header {
  padding: 20px 24px;
  background: #fff;
  border-bottom: 1px solid #edf0f5;

  h1 {
    margin: 0;
    font-size: 20px;
    color: #1f2a44;
  }

  p {
    margin: 4px 0 0;
    font-size: 13px;
    color: #7a86a0;
  }
}

.qa-main {
  flex: 1;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.welcome-message {
  text-align: center;
  padding: 60px 20px;
  max-width: 600px;
  margin: 0 auto;

  .welcome-icon {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    font-size: 36px;
    font-weight: bold;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 20px;
  }

  h2 {
    margin: 0 0 12px;
    font-size: 24px;
    color: #1f2a44;
  }

  p {
    margin: 0 0 24px;
    font-size: 15px;
    color: #7a86a0;
  }

  .quick-questions {
    p {
      margin-bottom: 12px;
      font-size: 13px;
      color: #7a86a0;
    }

    button {
      display: block;
      width: 100%;
      padding: 12px 16px;
      margin: 8px 0;
      border: 1px solid #e4e7f0;
      border-radius: 8px;
      background: #fff;
      color: #1f2a44;
      font-size: 14px;
      cursor: pointer;
      text-align: left;
      transition: all 0.2s;

      &:hover {
        border-color: #1976d2;
        color: #1976d2;
        background: #f8fbff;
      }
    }
  }
}

.message-item {
  display: flex;
  margin-bottom: 20px;
  cursor: default;
  transition: all 0.2s;

  &.user {
    flex-direction: row-reverse;

    .message-avatar {
      background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
      color: #fff;
    }

    .message-content {
      align-items: flex-end;

      .message-role {
        text-align: right;
      }

      .message-text {
        background: #1976d2;
        color: #fff;
        border-radius: 16px 16px 4px 16px;
      }
    }
  }

  &.assistant {
    .message-avatar {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
    }

    .message-content {
      align-items: flex-start;

      .message-text {
        background: #fff;
        border-radius: 16px 16px 16px 4px;
        border: 1px solid #e4e7f0;
      }
    }

    &.searching .message-text {
      background: #f8fbff;
    }

    &.generating .message-text {
      min-height: 40px;
    }
  }
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  margin: 0 12px;
}

.message-content {
  flex: 1;
  max-width: 70%;
  display: flex;
  flex-direction: column;
}

.message-role {
  font-size: 12px;
  color: #7a86a0;
  margin-bottom: 4px;
}

.message-text {
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;

  :deep(pre) {
    background: #f5f6fb;
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 8px 0;
  }

  :deep(code) {
    background: #f5f6fb;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Consolas', monospace;
    font-size: 13px;
  }

  :deep(ul) {
    margin: 8px 0;
    padding-left: 20px;
  }

  :deep(li) {
    margin: 4px 0;
  }

  :deep(strong) {
    font-weight: 600;
  }

  :deep(br) {
    content: '';
    display: block;
    margin: 4px 0;
  }
}

.searching-text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.searching-indicator {
  width: 16px;
  height: 16px;
  border: 2px solid #e4e7f0;
  border-top-color: #1976d2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  background: #1976d2;
  margin-left: 2px;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.input-area {
  padding: 16px 24px;
  background: #fff;
  border-top: 1px solid #edf0f5;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: #f5f6fb;
  border-radius: 12px;
  padding: 8px;
  border: 1px solid #e4e7f0;

  &:focus-within {
    border-color: #1976d2;
    box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.1);
  }

  textarea {
    flex: 1;
    border: none;
    background: transparent;
    resize: none;
    font-size: 14px;
    line-height: 1.5;
    max-height: 150px;
    padding: 8px 12px;
    outline: none;

    &::placeholder {
      color: #a0aec0;
    }
  }
}

.send-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: #1976d2;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(:disabled) {
    background: #1565c0;
  }

  &:disabled {
    background: #c5d4e8;
    cursor: not-allowed;
  }
}

.input-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #a0aec0;
  text-align: center;
}

// 来源详情面板
.sources-panel {
  width: 400px;
  background: #fff;
  border-left: 1px solid #edf0f5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;

  &.empty {
    align-items: center;
    justify-content: center;
    background: #fafbfc;
  }
}

.sources-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #edf0f5;

  h3 {
    margin: 0;
    font-size: 15px;
    color: #1f2a44;
    font-weight: 600;
  }

  .close-btn {
    width: 28px;
    height: 28px;
    border: none;
    background: #f5f6fb;
    border-radius: 6px;
    font-size: 18px;
    color: #7a86a0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;

    &:hover {
      background: #e4e7f0;
      color: #1f2a44;
    }
  }
}

.sources-panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.source-detail-item {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8fbff;
  border: 1px solid #e4e7f0;
  border-radius: 8px;

  &:last-child {
    margin-bottom: 0;
  }
}

.source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7f0;
}

.source-rank {
  width: 20px;
  height: 20px;
  background: #1976d2;
  color: #fff;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-score {
  padding: 2px 8px;
  background: #e9f3ff;
  color: #1976d2;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.source-name {
  font-size: 12px;
  color: #7a86a0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-content {
  font-size: 13px;
  color: #1f2a44;
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-tip {
  text-align: center;
  padding: 20px;

  .empty-icon {
    width: 48px;
    height: 48px;
    background: #f0f4f8;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 12px;
    font-size: 20px;
    color: #7a86a0;
  }

  p {
    margin: 0;
    font-size: 13px;
    color: #7a86a0;
  }
}
</style>
