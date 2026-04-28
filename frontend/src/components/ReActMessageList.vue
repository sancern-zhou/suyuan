<template>
  <div class="react-message-list" ref="messagesContainer">
    <!-- 欢迎消息 -->
    <div v-if="messages.length === 0" class="welcome-message">
      <h2>{{ welcomeContent.title }}</h2>
      <p>{{ welcomeContent.description }}</p>
      <ul>
        <li v-for="(feature, index) in welcomeContent.features" :key="index">{{ feature }}</li>
      </ul>
      <p class="hint">{{ welcomeContent.example }}</p>
    </div>

    <!-- 加载更多按钮 -->
    <div v-if="hasMoreMessages" class="load-more-container">
      <button
        v-if="!loadingMore"
        @click="emit('load-more')"
        class="load-more-btn"
      >
        加载更早的消息 ({{ totalMessageCount - messages.length }} 条)
      </button>
      <div v-else class="loading-indicator">
        <span class="spinner"></span> 加载中...
      </div>
    </div>

    <!-- 消息列表 -->
    <div v-for="(message, index) in filteredMessages" :key="message.id" class="message-wrapper"
      :class="{
        'has-sources': getMessageType(message) === 'final' && (message.data?.sources?.length > 0 || message.sources?.length > 0),
        'clickable': getMessageType(message) === 'final' && (message.data?.sources?.length > 0 || message.sources?.length > 0),
        'selected': selectedMessageId === message.id
      }"
      @click="handleMessageClick(message, index)"
    >
      <!-- 用户消息 -->
      <div v-if="getMessageType(message) === 'user'" class="message user-message">
        <!-- 附件显示 -->
        <div v-if="message.attachments && message.attachments.length > 0" class="message-attachments">
          <div v-for="(attachment, idx) in message.attachments" :key="idx" class="message-attachment">
            <!-- 图片附件 -->
            <img
              v-if="attachment.type === 'image'"
              :src="attachment.url"
              :alt="attachment.name"
              class="attachment-image"
              @click="previewAttachment(attachment)"
            />
            <!-- 文档附件 -->
            <div v-else class="attachment-file">
              <svg viewBox="0 0 24 24" class="attachment-file-icon">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="none" stroke="currentColor" stroke-width="2"/>
                <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
              </svg>
              <span class="attachment-file-name">{{ attachment.name }}</span>
            </div>
          </div>
        </div>

        <div class="message-content" v-if="useMarkdown && message.content">
          <!-- 【Vue 3 最佳实践】使用 key 强制重新渲染 -->
          <!-- 当 streaming 从 true 变为 false 时，key 变化，组件会重新创建 -->
          <MarkdownRenderer
            :key="`${message.id}-${message.streaming === true ? 'streaming' : 'complete'}`"
            :content="message.content"
            :streaming="message.streaming === true"
          />
        </div>
        <div class="message-content" v-else-if="message.content">{{ message.content }}</div>

        <!-- Reflexion状态提示 -->
        <div v-if="showReflexion && reflexionCount > 0" class="reflexion-badge">
          <span class="badge-icon">🧠</span>
          <span class="badge-text">智能恢复中 ({{ reflexionCount }})</span>
        </div>
      </div>

      <!-- Agent消息（最终答案） -->
      <!-- 移除 v-once 以支持流式更新 -->
      <div v-else-if="getMessageType(message) === 'final'" class="message agent-message final">
        <!-- 统一折叠区域：显示该final之前的所有过程消息 -->
        <details
          v-if="getUnifiedProcessMessages(message, messages).length > 0"
          class="process-collapse"
          :open="isProcessExpanded(message.id)"
          @toggle="handleProcessToggle(message.id, $event)"
        >
          <summary>查看分析过程 ({{ getUnifiedProcessMessages(message, messages).length }} 个步骤)</summary>
          <div class="process-content">
            <div v-for="(procMsg, idx) in getUnifiedProcessMessages(message, messages)" :key="idx" class="process-item">
              <!-- 思考事件 -->
              <div v-if="getMessageType(procMsg) === 'thought'" class="process-thought">
                <span class="process-icon">💭</span>
                <span class="process-label">思考</span>
                <div class="process-text">{{ procMsg.content }}</div>
                <details v-if="procMsg.data?.reasoning" class="process-reasoning">
                  <summary>详细推理</summary>
                  <div class="reasoning-text">{{ procMsg.data.reasoning }}</div>
                </details>
              </div>

              <!-- V3: tool_use 事件 -->
              <div v-else-if="getMessageType(procMsg) === 'tool_use'" class="process-action">
                <span class="process-icon">🔧</span>
                <span class="process-label">工具调用</span>
                <div class="process-text">{{ procMsg.content }}</div>
              </div>

              <!-- V3: tool_result 事件 -->
              <div v-else-if="getMessageType(procMsg) === 'tool_result'" class="process-observation">
                <span class="process-icon">{{ procMsg.data?.is_error ? '❌' : '✅' }}</span>
                <span class="process-label">工具结果</span>
                <div class="process-text">{{ procMsg.data?.result?.summary || procMsg.content }}</div>
              </div>

            </div>
          </div>
        </details>

        <div class="message-content" v-if="useMarkdown">
          <!-- 【Vue 3 最佳实践】使用 key 强制重新渲染 -->
          <MarkdownRenderer
            :key="`${message.id}-${message.streaming === true ? 'streaming' : 'complete'}`"
            :content="message.content"
            :streaming="message.streaming === true"
          />
        </div>
        <div class="message-content" v-else>{{ message.content }}</div>

        <!-- 多专家系统：直接显示报告内容，无额外装饰 -->
        <div v-if="message.data?.expert_results?.report && reportContentCacheMap.get(message.data.expert_results.report)" class="expert-report-content">
          <div v-if="reportContentCacheMap.get(message.data.expert_results.report).markdown_content">
            <MarkdownRenderer
              :key="`report-${message.id}`"
              :content="reportContentCacheMap.get(message.data.expert_results.report).markdown_content"
            />
          </div>
          <div v-else class="report-section" v-for="(section, sectionKey) in reportContentCacheMap.get(message.data.expert_results.report)" :key="sectionKey">
            <h5 class="section-title">{{ formatSectionTitle(sectionKey) }}</h5>
            <div class="section-content">
              <template v-if="typeof section === 'string'">
                {{ section }}
              </template>
              <template v-else-if="Array.isArray(section)">
                <ul>
                  <li v-for="(item, idx) in section" :key="idx">{{ typeof item === 'object' ? JSON.stringify(item) : item }}</li>
                </ul>
              </template>
              <template v-else-if="typeof section === 'object'">
                <div v-for="(val, key) in section" :key="key" class="subsection">
                  <span class="subsection-key">{{ key }}:</span>
                  <span class="subsection-value">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- 错误事件 -->
      <div v-else-if="getMessageType(message) === 'error'" class="event-content error">
        <div class="event-icon">⚠️</div>
        <div class="event-text">{{ message.content }}</div>
      </div>

      <!-- 思考事件（未被折叠时实时显示） -->
      <div v-else-if="getMessageType(message) === 'thought' && !isMessageHidden(message)" class="react-event event-thought">
        <div class="event-content">
          <div class="event-icon">💭</div>
          <div class="event-text">
            <div>{{ message.content }}</div>
            <details v-if="message.data?.reasoning" class="event-reasoning">
              <summary>详细推理</summary>
              <div class="reasoning-text">{{ message.data.reasoning }}</div>
            </details>
          </div>
        </div>
      </div>

      <!-- ✅ V3: Tool Use 事件 -->
      <div v-else-if="getMessageType(message) === 'tool_use' && !isMessageHidden(message)" class="react-event event-tool-use">
        <div class="event-content">
          <div class="event-icon">🔧</div>
          <div class="event-text">
            <div class="tool-use-main">{{ message.content }}</div>
            <div v-if="message.data?.input && Object.keys(message.data.input).length > 0" class="tool-use-details">
              <details>
                <summary>查看参数</summary>
                <pre>{{ JSON.stringify(message.data.input, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>

      <!-- ✅ V3: Tool Result 事件 -->
      <div v-else-if="getMessageType(message) === 'tool_result' && !isMessageHidden(message)" class="react-event event-tool-result">
        <div class="event-content">
          <div class="event-icon">{{ message.data?.is_error ? '❌' : '✅' }}</div>
          <div class="event-text">
            <div class="tool-result-main">{{ message.content }}</div>
            <div v-if="message.data?.result?.summary" class="tool-result-summary">
              {{ message.data.result.summary }}
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- 图片预览模态框 -->
    <div v-if="previewedImage" class="image-preview-modal" @click="closeImagePreview">
      <div class="image-preview-content" @click.stop>
        <img :src="previewedImage.url" :alt="previewedImage.name" class="preview-image" />
        <div class="preview-info">
          <span class="preview-filename">{{ previewedImage.name }}</span>
          <a :href="previewedImage.url" :download="previewedImage.name" class="preview-download" @click.stop>
            下载
          </a>
        </div>
        <button class="preview-close" @click="closeImagePreview" title="关闭 (ESC)">
          <svg viewBox="0 0 24 24">
            <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="2"/>
            <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import MarkdownRenderer from './MarkdownRenderer.vue'

const reactStore = useReactStore()

// 【修复】辅助函数：获取消息类型（兼容 type 和 role 字段）
const getMessageType = (message) => {
  // 优先使用 type 字段（后端返回的格式），如果没有则使用 role 字段（旧格式）
  const type = message.type || message.role
  // 将后端的 assistant 映射为 final
  if (type === 'assistant') return 'final'
  return type
}

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  showReflexion: {
    type: Boolean,
    default: false
  },
  reflexionCount: {
    type: Number,
    default: 0
  },
  useMarkdown: {
    type: Boolean,
    default: true  // 默认启用Markdown渲染
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  // 【新增】当前选中的消息ID（用于高亮显示）
  selectedMessageId: {
    type: String,
    default: null
  },
  // 【新增】接收VisualizationPanel的引用，用于获取图表截图
  visualizationPanelRef: {
    type: Object,
    default: null
  },
  // 【新增】消息点击回调（用于知识问答模式选择消息查看来源）
  onMessageClick: {
    type: Function,
    default: null
  },
  // 【新增】分页加载状态
  hasMoreMessages: {
    type: Boolean,
    default: false
  },
  totalMessageCount: {
    type: Number,
    default: 0
  },
  loadingMore: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['load-more'])

const messagesContainer = ref(null)

// 【新增】处理消息点击（支持所有模式的final消息）
const handleMessageClick = (message, index) => {
  // 检查是否是final消息且有sources字段（兼容新旧两种位置）
  const hasSources = getMessageType(message) === 'final' &&
    ((message.data?.sources && Array.isArray(message.data.sources) && message.data.sources.length > 0) ||
     (message.sources && Array.isArray(message.sources) && message.sources.length > 0))

  if (hasSources && props.onMessageClick) {
    props.onMessageClick(message.id, message)
  }
}

// 【新增】缓存报告内容，避免重复处理
const reportContentCache = ref(new Map())
// 【关键修复】添加响应式触发器，确保缓存更新后能触发视图更新
const cacheUpdateTrigger = ref(0)

// 【新增】事件完成状态管理（防抖机制：等待所有事件结束后再截图）
const pendingEventsCount = ref(0) // 待处理事件计数
const isProcessingComplete = ref(true) // 是否处理完成
let debounceTimer = null // 防抖定时器
const DEBOUNCE_DELAY = 2000 // 等待2秒确认没有新事件后开始处理

// 更新待处理事件计数
const updatePendingEvents = (messages) => {
  const toolUseCount = messages.filter(m => m.type === 'tool_use').length
  const toolResultCount = messages.filter(m => m.type === 'tool_result').length
  const thoughtCount = messages.filter(m => m.type === 'thought').length
  const totalPending = toolUseCount + toolResultCount + thoughtCount

  if (totalPending !== pendingEventsCount.value) {
    console.log(`[ReActMessageList] 待处理事件变化: ${pendingEventsCount.value} -> ${totalPending}`, {
      actions: toolUseCount,
      observations: toolResultCount,
      thoughts: thoughtCount
    })
    pendingEventsCount.value = totalPending

    // 如果没有待处理事件，设置防抖定时器
    if (totalPending === 0 && isProcessingComplete.value === false) {
      console.log(`[ReActMessageList] 所有事件已完成，等待 ${DEBOUNCE_DELAY}ms 后开始截图...`)
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(async () => {
        console.log('[ReActMessageList] 防抖时间到，开始截图和处理报告')
        isProcessingComplete.value = true
        await fillReportCache(messages)
      }, DEBOUNCE_DELAY)
    } else if (totalPending > 0) {
      // 有待处理事件，取消之前的防抖定时器
      clearTimeout(debounceTimer)
      debounceTimer = null
      isProcessingComplete.value = false
      console.log(`[ReActMessageList] 有 ${totalPending} 个待处理事件，暂停截图`)
    }
  }
}

// 【新增】备用触发函数：直接处理report expert数据
// 【新方案】后端直接生成图片URL，无需截图和占位符处理
const triggerReportCacheImmediately = async (messages) => {
  console.log('[ReActMessageList] triggerReportCacheImmediately 被调用')

  // 查找包含 report expert 的消息
  for (const msg of messages) {
    if (msg.data?.expert_results?.report) {
      const reportExpertData = msg.data.expert_results.report
      const cacheKey = JSON.stringify(reportExpertData?.tool_results || [])

      console.log('[ReActMessageList] 找到report expert:', {
        hasToolResults: !!reportExpertData?.tool_results,
        toolResultsLength: reportExpertData?.tool_results?.length || 0,
        cacheKey: cacheKey.substring(0, 50)
      })

      if (!reportContentCache.value.has(cacheKey)) {
        console.log('[ReActMessageList] 立即处理报告内容...')
        const res = await getReportContent(reportExpertData)
        reportContentCache.value.set(cacheKey, res)
        cacheUpdateTrigger.value++
        console.log('[ReActMessageList] 立即处理完成:', {
          hasContent: !!res?.markdown_content,
          contentLength: res?.markdown_content?.length || 0
        })
      }
    }
  }
}

// 【修复】异步预先处理报告内容（URL直接输出方案，无需截图）
const fillReportCache = async (messages) => {
  // 【新增】详细调试日志
  console.log('[ReActMessageList] fillReportCache 被调用', {
    messagesCount: messages?.length || 0,
    isProcessingComplete: isProcessingComplete.value
  })

  // 如果正在处理中，跳过
  if (!isProcessingComplete.value) {
    console.log('[ReActMessageList] 正在处理中，跳过')
    return
  }

  // 【新方案】后端直接生成图片URL，无需前端截图和占位符替换
  const tasks = []
  messages.forEach(msg => {
    if (msg.data?.expert_results?.report) {
      const reportExpertData = msg.data.expert_results.report
      const cacheKey = JSON.stringify(reportExpertData?.tool_results || [])
      if (!reportContentCache.value.has(cacheKey)) {
        tasks.push(
          getReportContent(reportExpertData).then(res => {
            // 【关键修复】更新缓存并触发响应式更新
            reportContentCache.value.set(cacheKey, res)
            cacheUpdateTrigger.value++ // 触发响应式更新
            console.log('[ReActMessageList] 缓存已更新，触发视图刷新', {
              cacheKey: cacheKey.substring(0, 50),
              hasContent: !!res?.markdown_content,
              contentLength: res?.markdown_content?.length || 0
            })
          })
        )
      }
    }
  })
  if (tasks.length) {
    console.log('[ReActMessageList] 开始处理', tasks.length, '个报告任务')
    await Promise.allSettled(tasks)
    console.log('[ReActMessageList] 所有报告任务完成')
  } else {
    console.log('[ReActMessageList] 没有需要处理的报告任务')
  }
}

// 监听消息变化，填充缓存（在展示前获取截图并替换占位符）
// 【关键修复】使用防抖机制，等待所有事件完成后再截图
watch(
  () => props.messages,
  async (newMessages, oldMessages) => {
    console.log('[ReActMessageList] watch触发 - 消息变化:', {
      新消息数量: newMessages?.length || 0,
      旧消息数量: oldMessages?.length || 0,
      消息类型分布: {
        user: newMessages?.filter(m => m.type === 'user').length || 0,
        thought: newMessages?.filter(m => m.type === 'thought').length || 0,
        tool_use: newMessages?.filter(m => m.type === 'tool_use').length || 0,
        tool_result: newMessages?.filter(m => m.type === 'tool_result').length || 0,
        final: newMessages?.filter(m => m.type === 'final').length || 0
      }
    })

    // 【新增】检查是否有report expert数据，如果有立即处理（不等待防抖）
    const hasReportData = newMessages.some(msg => msg.data?.expert_results?.report)
    if (hasReportData) {
      console.log('[ReActMessageList] 检测到report数据，触发备用处理')
      triggerReportCacheImmediately(newMessages)
    }

    // 检查消息数量变化
    const newLength = newMessages?.length || 0
    const oldLength = oldMessages?.length || 0

    if (newLength === 0) {
      console.log('[ReActMessageList] 消息数量为0，跳过处理')
      return
    }

    // 如果是首次加载，直接处理
    if (oldLength === 0) {
      console.log('[ReActMessageList] 首次加载消息，消息数量:', newLength)
      isProcessingComplete.value = false
      updatePendingEvents(newMessages)
      return
    }

    // 检查是否有新消息添加
    const hasNewMessages = newLength > oldLength

    if (hasNewMessages) {
      // 有新消息，标记为处理中并更新待处理事件计数
      console.log('[ReActMessageList] 检测到新消息，延迟处理')
      isProcessingComplete.value = false
      clearTimeout(debounceTimer)
      updatePendingEvents(newMessages)
    } else {
      console.log('[ReActMessageList] 消息数量未变化，可能是内容更新')
    }
  },
  { deep: true, immediate: true }
)

// 只读取已缓存的结果，避免在计算属性里做异步
// 【关键修复】依赖 cacheUpdateTrigger 确保缓存更新后重新计算
const reportContentCacheMap = computed(() => {
  // 依赖 cacheUpdateTrigger 触发重新计算
  const _ = cacheUpdateTrigger.value
  
  const cacheMap = new Map()
  props.messages.forEach(msg => {
    if (msg.data?.expert_results?.report) {
      const reportExpertData = msg.data.expert_results.report
      const cacheKey = JSON.stringify(reportExpertData?.tool_results || [])
      if (reportContentCache.value.has(cacheKey)) {
        const cached = reportContentCache.value.get(cacheKey)
        cacheMap.set(reportExpertData, cached)
        console.log('[ReActMessageList] reportContentCacheMap 读取缓存', {
          cacheKey: cacheKey.substring(0, 50),
          hasContent: !!cached?.markdown_content,
          contentLength: cached?.markdown_content?.length || 0,
          hasPlaceholder: cached?.markdown_content?.includes?.('[ECHARTS_PLACEHOLDER:')
        })
      }
    }
  })
  return cacheMap
})

// 根据助手模式返回欢迎消息内容
const welcomeContent = computed(() => {
  const contentMap = {
    'meteorology-expert': {
      title: '气象分析场景',
      description: '专注气象数据分析，自动生成专业图表和传输路径分析：',
      features: [
        '分析ERA5历史气象数据',
        '查询气象轨迹传输路径',
        '获取气象条件关联分析',
        '生成专业气象图表和可视化'
      ],
      example: '请输入您的问题，例如："分析北京今天的气象条件"'
    },
    'quick-tracing-expert': {
      title: '快速溯源场景',
      description: '整合气象、组分、可视化多维度数据，快速识别污染来源和传输路径：',
      features: [
        '多专家协同分析污染来源',
        '快速响应污染事件溯源',
        '识别主要污染传输路径',
        '综合评估污染影响范围'
      ],
      example: '请输入您的问题，例如："分析广州天河区昨天O3超标的污染来源"'
    },
    'data-visualization-expert': {
      title: '数据可视化场景',
      description: '根据数据特征智能推荐图表类型，支持灵活调整图表样式和布局：',
      features: [
        '智能推荐最佳图表类型',
        '支持多种专业图表绑制',
        '自定义图表样式和配色',
        '一键导出高清图表'
      ],
      example: '请输入您的问题，例如："绑制广州11月PM2.5浓度变化趋势图"'
    },
    'report-generation-expert': {
      title: '报告生成场景',
      description: '整合文字、图表与结论，生成周报、专项报告模板：',
      features: [
        '模版化段落输出',
        '自动整合分析图表',
        '生成专业分析结论',
        '支持多格式报告导出'
      ],
      example: '功能正在开发中，敬请期待...'
    },
    'general-agent': {
      title: '风清气智Agent',
      description: '专业的污染溯源分析助手，可以通过以下方式为您服务：',
      features: [
        '分析特定时间段的空气质量',
        '查询污染源和扩散路径',
        '获取气象数据关联分析',
        '生成可视化图表和报告'
      ],
      example: '请输入您的问题，例如："分析广州天河站2025-11-01的O3污染情况"'
    }
  }
  return contentMap[props.assistantMode] || contentMap['general-agent']
})

// 调试：监听消息变化
watch(() => props.messages, (newMessages) => {
  console.log('[ReActMessageList] 消息数量变化:', newMessages.length)
  // newMessages.forEach((msg, idx) => {
  //   if (msg.type === 'observation') {
  //     console.log(`[ReActMessageList] 观察事件 #${idx}:`, {
  //       id: msg.id,
  //       hasData: !!msg.data,
  //       dataKeys: msg.data ? Object.keys(msg.data) : [],
  //       data: msg.data
  //     })
  //   }
  // })
}, { deep: true, immediate: true })

// 过滤掉系统消息，保留所有其他消息（实时显示过程消息）
const filteredMessages = computed(() => {
  const filtered = props.messages.filter(msg => {
    // 【修复】兼容 role 和 type 字段
    const msgType = msg.role || msg.type
    // 过滤掉系统消息
    if (msgType === 'start' || msgType === 'agent') return false
    return true
  })

  // 【修复】检查是否有重复的消息ID（同一消息被多次显示）
  const messageIds = new Set()
  const duplicates = []
  filtered.forEach((msg, idx) => {
    if (messageIds.has(msg.id)) {
      duplicates.push({ id: msg.id, index: idx, content: msg.content?.substring(0, 50) })
    } else {
      messageIds.add(msg.id)
    }
  })

  if (duplicates.length > 0) {
    console.error(`[ReActMessageList] ⚠️ 发现 ${duplicates.length} 个重复的消息ID:`, duplicates)
  }

  // 【修复】兼容 role 和 type 字段统计
  const getType = (m) => m.role || m.type

  console.log('[ReActMessageList] filteredMessages计算:', {
    原始消息数: props.messages.length,
    过滤后消息数: filtered.length,
    唯一消息ID数: messageIds.size,
    重复数: duplicates.length,
    过滤后类型分布: {
      user: filtered.filter(m => getType(m) === 'user').length,
      thought: filtered.filter(m => getType(m) === 'thought').length,
      tool_use: filtered.filter(m => getType(m) === 'tool_use').length,
      tool_result: filtered.filter(m => getType(m) === 'tool_result').length,
      final: filtered.filter(m => getType(m) === 'final' || getType(m) === 'assistant').length
    }
  })

  return filtered
})

// 【新增】折叠的过程消息ID集合
const collapsedProcessIds = ref(new Set())

// 【新增】details展开状态管理（用于控制<details>的open属性）
const expandedProcessIds = ref(new Set())

// 【新增】全局初始加载标志，用于强制所有 details 在初次加载时折叠
const isInitialLoad = ref(true)

// 【新增】判断final消息的过程区域是否应该展开
const isProcessExpanded = (messageId) => {
  // 【关键修复】初次加载时，强制所有 details 折叠
  if (isInitialLoad.value) {
    // console.log('[ReActMessageList] isProcessExpanded: initial load, forcing collapse')
    return undefined
  }

  // 处理 messageId 为 undefined 或 null 的情况
  if (!messageId) {
    // console.log('[ReActMessageList] isProcessExpanded: messageId is empty, returning undefined (collapsed)')
    return undefined
  }

  const isExpanded = expandedProcessIds.value.has(messageId)
  // console.log('[ReActMessageList] isProcessExpanded:', {
  //   messageId,
  //   isExpanded,
  //   expandedIds: Array.from(expandedProcessIds.value)
  // })

  if (isExpanded) {
    return true
  } else {
    return undefined  // 返回 undefined 确保 details 折叠
  }
}

// 【新增】处理details的toggle事件
const handleProcessToggle = (messageId, event) => {
  // event.target 是 <details> 元素
  // event.target.open 表示当前状态（toggle之后的状态）
  if (event.target.open) {
    expandedProcessIds.value.add(messageId)
  } else {
    expandedProcessIds.value.delete(messageId)
  }
}

// 【新增】检测并折叠当前final消息之前的所有过程消息
const collapsePreviousProcessMessages = (finalMessage, allMessages) => {
  const finalIndex = allMessages.findIndex(m => m.id === finalMessage.id)
  if (finalIndex === -1) return

  // 标记所有过程消息为折叠
  // 包括final消息之前和之后的过程消息（因为流式事件顺序可能导致thought在final之后到达）
  const newCollapsedIds = new Set(collapsedProcessIds.value)
  let processCount = 0
  for (const msg of allMessages) {
    if (msg.id === finalMessage.id) continue
    const msgType = getMessageType(msg)
    if (msgType === 'thought' || msgType === 'tool_use' || msgType === 'tool_result') {
      newCollapsedIds.add(msg.id)
      processCount++
    }
  }
  collapsedProcessIds.value = newCollapsedIds
}

// 【新增】判断消息是否应该被隐藏（已被final折叠）
const isMessageHidden = (message) => {
  return collapsedProcessIds.value.has(message.id)
}

// 【新增】判断是否是带PDF预览的Office工具消息（这些消息在OfficeDocumentPanel中显示，不需要在聊天列表重复显示）
const isOfficeToolWithPdf = (message) => {
  if (getMessageType(message) !== 'tool_result') return false

  const result = message.data?.result
  if (!result) return false

  const metadata = result.metadata || {}
  const generator = metadata.generator

  // 检查是否是Office工具
  const officeTools = ['unpack_office', 'pack_office', 'word_processor', 'excel_processor', 'ppt_processor', 'find_replace_word', 'accept_word_changes', 'recalc_excel', 'add_ppt_slide']
  if (!officeTools.includes(generator)) return false

  // 检查是否有PDF预览
  const data = result.data || result
  return !!(data?.pdf_preview)
}

// 【新增】获取当前final消息之前的过程消息（用于统一折叠区域）
// 【修复】只返回该轮对话的过程消息，不包括之前轮次的
// 【性能优化】使用缓存避免重复计算
const processMessagesCache = ref(new Map())

const getUnifiedProcessMessages = (finalMessage, allMessages) => {
  // 【性能优化】使用缓存键：final消息的引用或ID
  const cacheKey = finalMessage.id || JSON.stringify(finalMessage)

  // 检查缓存
  if (processMessagesCache.value.has(cacheKey)) {
    return processMessagesCache.value.get(cacheKey)
  }

  // 【关键调试】检查 finalMessage.id 是否存在
  console.log('[getUnifiedProcessMessages] 接收到final消息:', {
    hasId: !!finalMessage.id,
    id: finalMessage.id,
    type: finalMessage.type,
    role: finalMessage.role,
    effectiveType: getMessageType(finalMessage),
    allMessagesCount: allMessages.length
  })

  let processMessages = []

  // 如果 finalMessage.id 不存在，尝试使用其他方式查找
  if (!finalMessage.id) {
    console.warn('[getUnifiedProcessMessages] finalMessage.id 为空，尝试使用索引查找')

    // 尝试在 allMessages 中直接查找这个 finalMessage
    const finalIndex = allMessages.findIndex(m => m === finalMessage || (m.type === 'final' && !m.id))
    if (finalIndex === -1) {
      console.error('[getUnifiedProcessMessages] 无法找到final消息索引')
      processMessages = []
    } else {
      console.log('[getUnifiedProcessMessages] 通过引用找到final消息，索引:', finalIndex)

      // 获取该final之前的消息
      const beforeMessages = allMessages.slice(0, finalIndex)

      // 找到上一个final的位置
      let lastFinalIndex = -1
      for (let i = finalIndex - 1; i >= 0; i--) {
        if (getMessageType(allMessages[i]) === 'final') {
          lastFinalIndex = i
          break
        }
      }

      const currentRoundMessages = beforeMessages.slice(lastFinalIndex + 1)
      processMessages = currentRoundMessages.filter(msg => {
        const msgType = getMessageType(msg)
        return msgType === 'thought' || msgType === 'tool_use' || msgType === 'tool_result'
      })

      console.log('[getUnifiedProcessMessages] 通过引用找到过程消息:', {
        processMessageCount: processMessages.length,
        types: processMessages.map(m => getMessageType(m))
      })
    }
  } else {
    // 正常情况：使用 id 查找
    const finalIndex = allMessages.findIndex(m => m.id === finalMessage.id)
    console.log('[getUnifiedProcessMessages] 开始查找过程消息:', {
      finalMessageId: finalMessage.id,
      finalIndex,
      totalMessages: allMessages.length
    })

    if (finalIndex === -1) {
      console.log('[getUnifiedProcessMessages] 未找到final消息，返回空数组')
      processMessages = []
    } else {
      // 获取该final之前的消息
      const beforeMessages = allMessages.slice(0, finalIndex)

      // 找到上一个final的位置，只获取两轮final之间的过程消息
      let lastFinalIndex = -1
      for (let i = finalIndex - 1; i >= 0; i--) {
        if (getMessageType(allMessages[i]) === 'final') {
          lastFinalIndex = i
          break
        }
      }

      // 只获取上一轮final之后、当前final之前的过程消息
      const currentRoundMessages = beforeMessages.slice(lastFinalIndex + 1)

      processMessages = currentRoundMessages.filter(msg => {
        const msgType = getMessageType(msg)
        return msgType === 'thought' || msgType === 'tool_use' || msgType === 'tool_result'
      })

      console.log('[getUnifiedProcessMessages] 找到过程消息:', {
        processMessageCount: processMessages.length,
        types: processMessages.map(m => m.type)
      })
    }
  }

  // 【性能优化】缓存结果
  processMessagesCache.value.set(cacheKey, processMessages)

  return processMessages
}

// 【新增】监听消息变化，清空缓存
watch(() => props.messages, () => {
  processMessagesCache.value.clear()
  console.log('[getUnifiedProcessMessages] 消息变化，清空缓存')
}, { deep: true })

// 【修复】智能滚动控制
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 判断用户是否在底部（接近底部30px内）
const isAtBottom = () => {
  if (!messagesContainer.value) return true
  const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value
  return scrollHeight - scrollTop - clientHeight < 30
}

// 【新增】用户滚动状态追踪
const userHasScrolled = ref(false)
const scrollTimeout = ref(null)

// 检测用户是否手动滚动
const handleUserScroll = () => {
  // 只有当用户向上滚动（查看历史消息）时才标记
  if (messagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value
    const distanceToBottom = scrollHeight - scrollTop - clientHeight

    // 只有距离底部超过50px时才认为用户在查看历史消息
    if (distanceToBottom > 50) {
      userHasScrolled.value = true
    }
  }

  // 清除之前的超时
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
    scrollTimeout.value = null
  }
  // 2秒后重置，让用户在停止滚动后可以恢复自动滚动
  scrollTimeout.value = setTimeout(() => {
    userHasScrolled.value = false
  }, 2000)

  // 滚动到顶部时自动加载更多历史消息
  if (messagesContainer.value) {
    const { scrollTop } = messagesContainer.value
    if (scrollTop <= 30 && props.hasMoreMessages && !props.loadingMore) {
      emit('load-more')
    }
  }
}

// 只在"首次加载"或"用户发送消息"时强制滚动到底部
// 展开details查看详情时不强制滚动，避免界面跳动
watch(
  () => props.messages.length,
  (newLength, oldLength) => {
    // 如果是首次加载（oldLength为0），滚动到底部
    if (oldLength === 0 && newLength > 0) {
      scrollToBottom()
      return
    }

    // 如果有新的消息，滚动到底部
    if (newLength > oldLength) {
      const lastMessage = props.messages[newLength - 1]

      // 用户发送消息时，总是滚动到底部
      if (lastMessage.type === 'user') {
        userHasScrolled.value = false // 重置滚动状态
        scrollToBottom()
        return
      }

      // AI回复时，只有在用户未手动滚动查看历史消息时才自动滚动
      if (!userHasScrolled.value && isAtBottom()) {
        scrollToBottom()
      }
    }
  }
)

// 监听滚动事件，判断用户是否在查看历史消息
// mounted时绑定滚动事件
onMounted(() => {
  if (messagesContainer.value) {
    messagesContainer.value.addEventListener('scroll', handleUserScroll)
  }
  // 监听ESC键关闭图片预览
  document.addEventListener('keydown', handleEscKey)
})

// 【修复】监听新final消息的添加，自动折叠之前的过程消息
watch(
  () => props.messages,
  (newMessages, oldMessages) => {
    if (!newMessages || newMessages.length === 0) return

    // 【增强】检测是否需要批量折叠（初次加载或消息数量大幅变化）
    const isFirstLoad = !oldMessages || oldMessages.length === 0
    const isBulkLoad = oldMessages && Math.abs(newMessages.length - oldMessages.length) > 5 // 超过5条消息变化视为批量加载

    console.log('[ReActMessageList] watch触发，消息变化:', {
      newCount: newMessages?.length,
      oldCount: oldMessages?.length,
      isFirstLoad,
      isBulkLoad
    })

    if (isFirstLoad || isBulkLoad) {
      // 批量加载时，清空展开状态，确保所有 details 默认折叠
      expandedProcessIds.value.clear()
      collapsedProcessIds.value.clear() // 【修复】清空折叠集合，重新计算
      isInitialLoad.value = true // 【修复】重置初始加载标志
      // console.log('[ReActMessageList] 批量加载历史对话，默认折叠所有过程消息', {
      //   isFirstLoad,
      //   isBulkLoad,
      //   messageCount: newMessages.length
      // })

      // 【修复】遍历所有final消息，折叠它们之前的过程消息
      nextTick(() => {
        let lastFinalIndex = -1
        let totalCollapsedCount = 0

        // 找到所有的final消息
        for (let i = 0; i < newMessages.length; i++) {
          const msg = newMessages[i]
          const msgType = getMessageType(msg)
          if (msgType === 'final') {
            // 获取上一个final之后、当前final之前的所有消息
            const messagesBetween = newMessages.slice(lastFinalIndex + 1, i)

            // 折叠这些消息中的过程消息
            for (const procMsg of messagesBetween) {
              const procMsgType = getMessageType(procMsg)
              if (procMsgType === 'thought' || procMsgType === 'tool_use' || procMsgType === 'tool_result') {
                if (procMsg.id) { // 【修复】确保有id才折叠
                  collapsedProcessIds.value.add(procMsg.id)
                  totalCollapsedCount++
                  // console.log('[ReActMessageList] 折叠过程消息:', {
                  //   type: procMsgType,
                  //   id: procMsg.id,
                  //   hasContent: !!procMsg.content
                  // })
                }
              }
            }

            lastFinalIndex = i
          }
        }

        // console.log(`[ReActMessageList] 批量加载：已折叠 ${totalCollapsedCount} 个过程消息`)
        // console.log('[ReActMessageList] collapsedProcessIds数量:', collapsedProcessIds.value.size)
      })

      // 【新增】延迟一段时间后允许用户手动展开 details
      setTimeout(() => {
        isInitialLoad.value = false
        // console.log('[ReActMessageList] 初始加载完成，允许用户手动展开 details')
      }, 3000) // 3秒后允许用户手动展开
    } else {
      // 非初次加载：检查是否有新的final消息需要折叠过程消息
      // 注意：thought消息可能在final消息之后到达（流式事件顺序问题），
      // 所以每次消息变化都检查是否有未被折叠的过程消息
      const hasFinalMessage = newMessages.some(m => getMessageType(m) === 'final')
      if (hasFinalMessage) {
        // 找到最后一个final消息
        const lastFinalMessage = [...newMessages].reverse().find(m => getMessageType(m) === 'final')
        nextTick(() => {
          collapsePreviousProcessMessages(lastFinalMessage, newMessages)
        })
      }
    }
  },
  { deep: true }
)

// 清理滚动事件监听
onBeforeUnmount(() => {
  if (messagesContainer.value) {
    messagesContainer.value.removeEventListener('scroll', handleUserScroll)
  }
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
  document.removeEventListener('keydown', handleEscKey)
})

// 处理ESC键关闭图片预览
const handleEscKey = (e) => {
  if (e.key === 'Escape' && previewedImage.value) {
    closeImagePreview()
  }
}

// 获取数据大小（用于显示在折叠标签中）
const getDataSize = (data) => {
  if (!data) return '0B'
  const jsonStr = JSON.stringify(data)
  const bytes = new Blob([jsonStr]).size

  if (bytes < 1024) {
    return bytes + 'B'
  } else if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + 'KB'
  } else {
    return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
  }
}

const getActionPayload = (data) => {
  if (!data) return null
  if (data.input !== undefined) return data.input
  if (data.params !== undefined) return data.params
  if (data.arguments !== undefined) return data.arguments
  if (data.payload !== undefined) return data.payload
  const { toolInfo, ...rest } = data
  if (Object.keys(rest).length === 0) {
    return toolInfo || null
  }
  return rest
}

const toAbsoluteUrl = (url) => {
  if (!url) return '#'
  // 已经是完整URL
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  // 相对路径：补上当前站点 origin，确保前端可点击跳转
  try {
    return window.location.origin + url
  } catch {
    return url
  }
}

const formatActionParams = (data) => {
  const payload = getActionPayload(data)
  if (payload === null || payload === undefined || payload === '') {
    return '无输入参数'
  }
  if (typeof payload === 'string') {
    return payload
  }
  try {
    return JSON.stringify(payload, null, 2)
  } catch (error) {
    return String(payload)
  }
}

// 获取专家标签
const getExpertLabel = (expertType) => {
  const labelMap = {
    'weather': '气象分析专家',
    'component': '组分分析专家',
    'viz': '可视化专家',
    'report': '报告生成专家'
  }
  return labelMap[expertType] || expertType
}

// 获取专家图标
const getExpertIcon = (expertType) => {
  const iconMap = {
    'weather': '🌤️',
    'component': '🧪',
    'viz': '📊',
    'report': '📋'
  }
  return iconMap[expertType] || '🔬'
}

// 已移除脱敏限制

// 【新增】带缓存的获取报告内容函数（用于模板中避免重复调用）
const getCachedReportContent = async (expertData) => {
  const cacheKey = JSON.stringify(expertData?.tool_results || [])
  if (reportContentCache.value.has(cacheKey)) {
    return reportContentCache.value.get(cacheKey)
  }
  // 如果缓存中没有，调用原始函数
  return await getReportContent(expertData)
}

// 【新增】从API获取图片（支持 [IMAGE:xxx] 格式）
const fetchImageFromApi = async (imageId) => {
  try {
    const apiUrl = `/api/image/${imageId}`
    console.log(`[ReActMessageList] 从API获取图片: ${apiUrl}`)
    const response = await fetch(apiUrl)
    if (response.ok) {
      const data = await response.json()
      if (data.data) {
        // 返回完整格式的 data URL
        return data.data.startsWith('data:') ? data.data : `data:image/png;base64,${data.data}`
      }
    }
    console.warn(`[ReActMessageList] API图片获取失败: ${imageId}`)
    return null
  } catch (error) {
    console.error(`[ReActMessageList] API图片获取异常: ${imageId}`, error)
    return null
  }
}

// 【新增】从可视化面板获取图表信息（ID和标题的映射）
const getChartInfoMap = () => {
  console.log('[ReActMessageList] getChartInfoMap 被调用')
  console.log('[ReActMessageList] visualizationPanelRef 存在:', !!props.visualizationPanelRef)

  if (!props.visualizationPanelRef) {
    console.log('[ReActMessageList] visualizationPanelRef 为空，返回空对象')
    return {}
  }

  // 获取图表引用
  const chartRefs = props.visualizationPanelRef.getChartRefs?.() || {}
  console.log('[ReActMessageList] chartRefs 数量:', Object.keys(chartRefs).length)

  // 获取可视化数据（包含标题等信息）
  const visualizations = props.visualizationPanelRef.visualizations || []
  console.log('[ReActMessageList] visualizations 数量:', visualizations.length)

  // 【修复】当visualizations为空时，从chartRefs的props中获取图表信息
  if (visualizations.length === 0 && Object.keys(chartRefs).length > 0) {
    console.log('[ReActMessageList] visualizations为空，从chartRefs构建图表信息...')
    // 从每个chartRef的props中获取图表信息
    Object.keys(chartRefs).forEach(chartId => {
      const chartRef = chartRefs[chartId]
      if (chartRef && chartRef.props) {
        const { data } = chartRef.props
        if (data) {
          visualizations.push({
            id: chartId,
            type: data.type || '',
            title: data.title || '',
            meta: data.meta || {}
          })
        }
      }
    })
    console.log('[ReActMessageList] 从chartRefs构建后visualizations数量:', visualizations.length)
  }

  // 构建 chartId -> { id, title, type, meta } 的映射
  const chartInfoMap = {}

  // 从visualizations获取标题信息
  visualizations.forEach((viz, idx) => {
    const vizId = viz.id || `viz_${idx}`
    chartInfoMap[vizId] = {
      id: vizId,
      title: viz.title || '',
      type: viz.type || '',
      meta: viz.meta || {}
    }
  })

  // 【调试】打印每个图表的chartType信息
  console.log('[ReActMessageList] getChartInfoMap - 可用图表类型信息:')
  Object.keys(chartInfoMap).forEach(id => {
    console.log(`  [${id}]: type=${chartInfoMap[id].type}, meta.chartType=${chartInfoMap[id].meta?.chartType || 'undefined'}, title="${chartInfoMap[id].title}"`)
  })

  // 从chartRefs中获取更多信息并补充到chartInfoMap
  Object.keys(chartRefs).forEach(chartId => {
    const chartRef = chartRefs[chartId]
    if (!chartRef) return

    // 尝试从ID中解析图表类型（如 ec_oc_scatter_xxx -> ec_oc_scatter）
    let parsedType = ''
    if (chartId.includes('_')) {
      const parts = chartId.split('_')
      const possibleType = parts.slice(0, -1).join('_') // 去掉最后的时间戳部分
      // 检查是否是已知的图表类型
      const knownTypes = ['ternary_SNA', 'sor_nor_scatter', 'charge_balance', 'ec_oc_scatter', 'crustal_boxplot', 'ion_timeseries', 'noaa_trajectory', 'air_quality', 'particulate_stacked', 'weather_ts', 'pressure_pbl']
      // 精确匹配已知类型
      const exactMatch = knownTypes.find(t => t.toLowerCase() === possibleType.toLowerCase())
      if (exactMatch) {
        parsedType = exactMatch
      } else if (knownTypes.some(t => possibleType.toLowerCase().includes(t.toLowerCase()))) {
        parsedType = possibleType
      } else if (parts.length >= 2) {
        // 使用最后两个部分作为类型（如 ec_oc_scatter）
        parsedType = parts.slice(-2).join('_')
      }
    }

    console.log(`[ReActMessageList] 解析图表ID: ${chartId} -> type=${parsedType || '(空)'}`)

    // 如果chartInfoMap中已有此ID，更新type和meta
    if (chartInfoMap[chartId]) {
      // 从ChartPanel中获取chartType
      const chartType = chartRef.chartType || chartRef.props?.chartType || ''
      const title = chartRef.title || chartRef.props?.title || chartInfoMap[chartId].title

      // 优先使用已解析的类型，其次使用chartType
      const finalType = parsedType || chartType || chartInfoMap[chartId].type
      chartInfoMap[chartId].type = finalType
      if (title) {
        chartInfoMap[chartId].title = title
      }
      console.log(`[ReActMessageList] 更新 chartRefs 图表信息: ${chartId}, type=${finalType}, title="${title}"`)
    } else {
      // 新图表，从chartRef获取信息
      const chartType = chartRef.chartType || chartRef.props?.chartType || ''
      const title = chartRef.title || chartRef.props?.title || ''

      chartInfoMap[chartId] = {
        id: chartId,
        title: title,
        type: parsedType || chartType || '',
        meta: {}
      }
      console.log(`[ReActMessageList] 新增 chartRefs 图表信息: ${chartId}, type=${parsedType || chartType}, title="${title}"`)
    }
  })

  // 最终调试输出
  console.log('[ReActMessageList] 最终 chartInfoMap:')
  Object.keys(chartInfoMap).forEach(id => {
    console.log(`  [${id}]: type=${chartInfoMap[id].type}, title="${chartInfoMap[id].title}"`)
  })

  return chartInfoMap
}

// 【新增】标题匹配函数
const matchChartByTitle = (placeholderTitle, chartInfoMap) => {
  if (!placeholderTitle) return null

  // 清理标题（去除序号如"图1："前缀）
  const cleanTitle = placeholderTitle.replace(/^图\d+：/, '').trim()

  // 如果清理后为空，返回null
  if (!cleanTitle) return null

  const charts = Object.values(chartInfoMap)

  // 优先级1：ID直接匹配（placeholderId就是chartId）
  // 优先级2：标题完全匹配
  const exactMatch = charts.find(chart => chart.title === cleanTitle)
  if (exactMatch) {
    console.log(`[ReActMessageList] 标题完全匹配: "${cleanTitle}" -> ${exactMatch.id}`)
    return exactMatch
  }

  // 优先级3：标题模糊匹配（包含关系）
  // 去除常见词汇后比较
  const cleanTitleNoCommon = cleanTitle
    .replace(/时序图$/, '')
    .replace(/分布图$/, '')
    .replace(/分析图$/, '')
    .replace(/趋势图$/, '')
    .replace(/对比图$/, '')
    .replace(/图$/, '')
    .trim()

  const fuzzyMatch = charts.find(chart => {
    if (!chart.title) return false
    const chartClean = chart.title
      .replace(/时序图$/, '')
      .replace(/分布图$/, '')
      .replace(/分析图$/, '')
      .replace(/趋势图$/, '')
      .replace(/对比图$/, '')
      .replace(/图$/, '')
      .trim()

    // 包含关系检查
    return chartClean.includes(cleanTitleNoCommon) ||
           cleanTitleNoCommon.includes(chartClean)
  })

  if (fuzzyMatch) {
    console.log(`[ReActMessageList] 标题模糊匹配: "${cleanTitle}" -> ${fuzzyMatch.id}`)
    return fuzzyMatch
  }

  console.log(`[ReActMessageList] 标题匹配失败: "${cleanTitle}"`)
  return null
}

// 【新增】按图表类型匹配函数（支持大小写不敏感 + ID前缀匹配）
const matchChartByType = (chartType, chartInfoMap, idToScreenshot) => {
  if (!chartType) return null

  const charts = Object.values(chartInfoMap)
  const lowerChartType = chartType.toLowerCase()

  console.log(`[ReActMessageList] matchChartByType: "${chartType}", 可用图表数量: ${charts.length}`)
  console.log(`[ReActMessageList] 可用图表详情:`, charts.map(c => ({ id: c.id, type: c.type, title: c.title })))
  console.log(`[ReActMessageList] idToScreenshot IDs:`, Object.keys(idToScreenshot))

  // 策略1：按图表类型匹配（大小写不敏感）
  // 【关键修复】优先检查 meta.chartType（当type被替换为image时保留原始类型）
  const match = charts.find(chart => {
    // 检查viz.type
    if (chart.type && chart.type.toLowerCase() === lowerChartType) {
      return true
    }
    // 【新增】检查meta.chartType（当type为image时，原始类型保存在meta.chartType）
    if (chart.meta?.chartType && chart.meta.chartType.toLowerCase() === lowerChartType) {
      return true
    }
    return false
  })
  if (match) {
    console.log(`[ReActMessageList] 图表类型匹配: "${chartType}" -> ${match.id} (原始type: ${match.type}, chartType: ${match.meta?.chartType})`)
    return match
  }

  // 策略2：ID前缀匹配（占位符作为前缀/主体匹配图表ID）
  // 例如: ternary_SNA -> ternary_sna_20251231001003
  // 例如: sor_nor_scatter -> sor_nor_20251231002542 (占位符是sor_nor_scatter，ID主体是sor_nor)
  const matchedId = Object.keys(idToScreenshot).find(id => {
    const lowerId = id.toLowerCase()

    // 策略2a: 占位符作为完整前缀
    if (lowerId.startsWith(lowerChartType + '_')) return true

    // 策略2b: 占位符在ID中间
    if (lowerId.includes('_' + lowerChartType + '_')) return true

    // 策略2c: 完全相等
    if (lowerId === lowerChartType) return true

    // 策略2d: ID以占位符开头（忽略常见后缀）
    // 例如: sor_nor_scatter -> sor_nor_xxx (去除 _scatter 后匹配)
    const suffixes = ['_scatter', '_timeseries', '_boxplot', '_bar', '_line', '_pie', '_map', '_image']
    for (const suffix of suffixes) {
      if (lowerChartType.endsWith(suffix)) {
        const baseType = lowerChartType.slice(0, -suffix.length)
        if (baseType && lowerId.startsWith(baseType + '_')) return true
        if (baseType && lowerId.includes('_' + baseType + '_')) return true
      }
    }

    return false
  })

  if (matchedId) {
    console.log(`[ReActMessageList] ID前缀匹配: "${chartType}" -> ${matchedId}`)
    return { id: matchedId, title: '', type: chartType }
  }

  // 策略3：关键词匹配（用于LLM生成名称与实际ID差异较大的情况）
  // 例如: ion_timeseries -> 包含 ion 关键词的ID
  // 例如: no_charts -> 这不是一个有效的图表类型，应该忽略
  const lowerChartTypeLower = lowerChartType.toLowerCase()
  // 如果占位符太短或包含 "no_" "empty" "none" 等，视为无效，跳过匹配
  if (lowerChartTypeLower.startsWith('no_') ||
      lowerChartTypeLower === 'n_charts' ||
      lowerChartTypeLower === 'none' ||
      lowerChartTypeLower === 'empty') {
    console.log(`[ReActMessageList] 跳过无效图表类型: "${chartType}"`)
    return null
  }

  // 提取占位符中的核心关键词进行匹配
  const chartTypeParts = lowerChartType.split(/[_\s]+/)
  const keyKeywords = chartTypeParts.filter(part =>
    part.length > 2 &&
    !['chart', 'plot', 'type', 'figure', 'img'].includes(part)
  )

  if (keyKeywords.length > 0) {
    // 查找包含任一关键词的ID
    const keywordMatch = Object.keys(idToScreenshot).find(id => {
      const lowerId = id.toLowerCase()
      return keyKeywords.some(keyword => {
        // 关键词作为独立词匹配
        const regex = new RegExp(`(^|_)${keyword}(_|$)`, 'i')
        return regex.test(lowerId)
      })
    })

    if (keywordMatch) {
      console.log(`[ReActMessageList] 关键词匹配: "${chartType}" -> ${keywordMatch} (关键词: ${keyKeywords.join(', ')})`)
      return { id: keywordMatch, title: '', type: chartType }
    }
  }

  console.log(`[ReActMessageList] 图表类型匹配失败: "${chartType}"`)
  return null
}

// 【新增】全局截图缓存（避免重复获取）
const chartScreenshotsCache = ref({})
const chartScreenshotsCacheTime = ref(0)
const CHART_CACHE_DURATION = 60000 // 缓存60秒

// 【新增】截图获取锁（防止并发获取同一截图）
let screenshotFetchPromise = null

// 【新增】统一的截图获取函数（使用单例模式 + 锁）
const getOrFetchScreenshots = async () => {
  const now = Date.now()

  // 1. 检查全局缓存是否有效
  if (chartScreenshotsCache.value && Object.keys(chartScreenshotsCache.value).length > 0) {
    const cacheAge = now - chartScreenshotsCacheTime.value
    if (cacheAge < CHART_CACHE_DURATION) {
      console.log(`[ReActMessageList] 使用全局截图缓存（${cacheAge}ms前获取，${Object.keys(chartScreenshotsCache.value).length}张）`)
      return chartScreenshotsCache.value
    }
    console.log(`[ReActMessageList] 全局缓存已过期（${cacheAge}ms），需要重新获取`)
  }

  // 2. 如果已有获取请求在执行，等待它完成
  if (screenshotFetchPromise) {
    console.log('[ReActMessageList] 等待已有截图获取请求完成...')
    return await screenshotFetchPromise
  }

  // 3. 开始新的获取请求
  screenshotFetchPromise = (async () => {
    if (!props.visualizationPanelRef) {
      screenshotFetchPromise = null
      return {}
    }

    console.log('[ReActMessageList] 开始获取截图...')
    const MAX_ATTEMPTS = 8
    const DELAY_MS = 500

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      console.log(`[ReActMessageList] 第${attempt}次尝试获取截图...`)

      try {
        const allChartImages = await props.visualizationPanelRef.getAllChartImages({ excludeMaps: true })
        console.log(`[ReActMessageList] 第${attempt}次获取到图表数量:`, Object.keys(allChartImages || {}).length)

        // 过滤有效截图
        const validScreenshots = {}
        for (const [id, img] of Object.entries(allChartImages || {})) {
          if (img && typeof img === 'string') {
            const isDataUrl = img.startsWith('data:image/')
            const isBase64 = !isDataUrl && /^[A-Za-z0-9+/=]+$/.test(img.substring(0, 100))
            const minLength = isDataUrl ? 100 : 1000
            if (img.length > minLength && (isDataUrl || isBase64)) {
              validScreenshots[id] = img
            }
          }
        }
        console.log(`[ReActMessageList] 第${attempt}次有效截图数量:`, Object.keys(validScreenshots).length)

        if (Object.keys(validScreenshots).length > 0) {
          // 保存到全局缓存
          chartScreenshotsCache.value = { ...validScreenshots }
          chartScreenshotsCacheTime.value = now
          console.log(`[ReActMessageList] 截图获取成功，共${Object.keys(validScreenshots).length}张`)
          return validScreenshots
        }

        if (attempt < MAX_ATTEMPTS) {
          await new Promise(resolve => setTimeout(resolve, DELAY_MS))
        }
      } catch (error) {
        console.warn(`[ReActMessageList] 第${attempt}次获取截图失败:`, error)
        if (attempt < MAX_ATTEMPTS) {
          await new Promise(resolve => setTimeout(resolve, DELAY_MS))
        }
      }
    }

    console.warn('[ReActMessageList] 截图获取失败，返回空缓存')
    return {}
  })()

  try {
    const result = await screenshotFetchPromise
    screenshotFetchPromise = null
    return result
  } catch (error) {
    screenshotFetchPromise = null
    console.error('[ReActMessageList] 截图获取异常:', error)
    return {}
  }
}

// 【已废弃】insertChartsIntoPlaceholders 函数已删除
// 新方案：后端直接生成图片URL格式 ![](/api/image/xxx)，前端无需处理占位符

// 【修复】使用缓存的截图替换占位符（不再调用getAllChartImages，确保只截图一次）
// 尝试多次收集图表截图并替换占位符（用于主对话区报告显示）
const replaceEchartsPlaceholders = async (markdown, cacheKey, cachedScreenshots = null) => {
  if (!markdown || !markdown.includes('[ECHARTS_PLACEHOLDER:')) {
    console.log('[ReActMessageList] 跳过占位符替换：无占位符', {
      hasPlaceholder: markdown?.includes?.('[ECHARTS_PLACEHOLDER:')
    })
    return markdown
  }

  // 使用传入的缓存截图或全局缓存
  let validImages = {}

  if (cachedScreenshots && Object.keys(cachedScreenshots).length > 0) {
    console.log('[ReActMessageList] 使用传入的截图缓存替换ECHARTS占位符，共', Object.keys(cachedScreenshots).length, '张')
    validImages = { ...cachedScreenshots }
  } else if (chartScreenshotsCache.value && Object.keys(chartScreenshotsCache.value).length > 0) {
    console.log('[ReActMessageList] 使用全局截图缓存替换ECHARTS占位符，共', Object.keys(chartScreenshotsCache.value).length, '张')
    validImages = { ...chartScreenshotsCache.value }
  } else {
    console.warn('[ReActMessageList] 无可用截图缓存，无法替换ECHARTS占位符')
    return markdown
  }

  console.log('[ReActMessageList] 有效截图数量:', Object.keys(validImages).length)
  console.log('[ReActMessageList] 有效截图ID:', Object.keys(validImages))

  let replacedCount = 0
  const missingIds = new Set()

  let content = markdown.replace(/\[ECHARTS_PLACEHOLDER:([^\]]+)\]/g, (match, chartId) => {
    if (validImages && validImages[chartId]) {
      replacedCount++
      let imageData = validImages[chartId]

      // 检查是否是ScreenshotCache对象
      const imgData = (imageData.dataURL || imageData)

      // 检查返回的数据格式
      if (typeof imgData === 'string') {
        if (imgData.startsWith('data:image/')) {
          console.log(`[ReActMessageList] ✓ 替换占位符 ${chartId} 为截图（完整格式，长度: ${imgData.length}）`)
          return `![图表 ${chartId}](${imgData})`
        } else {
          console.log(`[ReActMessageList] ✓ 替换占位符 ${chartId} 为截图（纯base64，长度: ${imgData.length}）`)
          return `![图表 ${chartId}](data:image/png;base64,${imgData})`
        }
      } else {
        console.warn(`[ReActMessageList] ⚠️ 图表 ${chartId} 的截图格式异常:`, typeof imgData)
        missingIds.add(chartId)
        return match
      }
    } else {
      missingIds.add(chartId)
      console.warn(`[ReActMessageList] ⚠️ 占位符 ${chartId} 没有找到有效截图`)
      return match
    }
  })

  console.log('[ReActMessageList] ECHARTS占位符替换完成，成功数量:', replacedCount, '缺失ID:', Array.from(missingIds))
  console.log('[ReActMessageList] 替换后剩余占位符:', (content.match(/\[ECHARTS_PLACEHOLDER:/g) || []).length)

  return content
}

// 获取报告完整内容（新方案：后端直接生成图片URL）
const getReportContent = async (expertData) => {
  console.log('getReportContent expertData:', expertData)

  // 【新增】使用缓存，避免重复处理
  const cacheKey = JSON.stringify(expertData?.tool_results || [])
  if (reportContentCache.value.has(cacheKey)) {
    console.log('[ReActMessageList] 使用缓存的报告内容')
    const cached = reportContentCache.value.get(cacheKey)
    console.log('[ReActMessageList] 缓存内容是否仍含占位符:', cached?.markdown_content?.includes?.('[ECHARTS_PLACEHOLDER:'))
    console.log('[ReActMessageList] 缓存内容长度:', cached?.markdown_content?.length || 0)
    return reportContentCache.value.get(cacheKey)
  }

  if (!expertData?.tool_results?.length) {
    console.log('No tool_results')
    return null
  }
  const reportResult = expertData.tool_results.find(t => t.tool === 'report_generation')
  console.log('reportResult:', reportResult)
  if (!reportResult?.result) {
    console.log('No result in reportResult')
    return null
  }

  const result = reportResult.result

  // 【修复】处理Markdown格式的报告内容 - 合并所有sections
  if (result.sections && result.sections.length > 0) {
    // 检查是否为Markdown格式（通过检查第一个section）
    const firstSection = result.sections[0]
    if (firstSection.markdown_content) {
      // 【关键修复】合并所有sections的markdown_content，而不是只取第一个
      let allMarkdownContent = result.sections
        .filter(section => section.markdown_content)
        .map(section => section.markdown_content)
        .join('\n\n')

      console.log('Markdown格式报告（合并所有sections）:', allMarkdownContent.substring(0, 500) + '...')
      console.log('总sections数量:', result.sections.length)
      console.log('合并后内容长度:', allMarkdownContent.length)

      // 【新方案】后端直接生成图片URL格式，前端无需处理占位符
      console.log('[ReActMessageList] 检查图片格式...')
      console.log('[ReActMessageList] 包含/api/image/:', allMarkdownContent.includes('/api/image/'))
      console.log('[ReActMessageList] 包含base64:', allMarkdownContent.includes('data:image/png;base64,'))

      // 【新增】清理后端章节标识标记（这些标识用于提取章节，但不应显示给用户）
      allMarkdownContent = allMarkdownContent
        .replace(/\[WEATHER_SECTION_START\]/g, '')
        .replace(/\[WEATHER_SECTION_END\]/g, '')
        .replace(/\[COMPONENT_SECTION_START\]/g, '')
        .replace(/\[COMPONENT_SECTION_END\]/g, '')
        .replace(/\[CONCLUSION_SECTION_START\]/g, '')
        .replace(/\[CONCLUSION_SECTION_END\]/g, '')
        .replace(/\[CHART_\d+_START\]/g, '')
        .replace(/\[CHART_\d+_END\]/g, '')

      const result1 = { markdown_content: allMarkdownContent }
      reportContentCache.value.set(cacheKey, result1)
      // 【关键修复】触发响应式更新，确保视图刷新
      cacheUpdateTrigger.value++
      console.log('[ReActMessageList] getReportContent 更新缓存并触发刷新', {
        cacheKey: cacheKey.substring(0, 50),
        contentLength: allMarkdownContent.length,
        hasPlaceholder: allMarkdownContent.includes('[ECHARTS_PLACEHOLDER:')
      })
      return result1
    } else if (typeof firstSection === 'object' && !firstSection.markdown_content) {
      // JSON格式的sections（兼容旧格式）- 也需要合并所有sections
      console.log('JSON格式sections数量:', result.sections.length)
      // 返回所有sections的合并对象
      const mergedSections = {}
      result.sections.forEach((section, index) => {
        Object.keys(section).forEach(key => {
          mergedSections[`${index}_${key}`] = section[key]
        })
      })
      reportContentCache.value.set(cacheKey, mergedSections)
      cacheUpdateTrigger.value++ // 触发响应式更新
      return mergedSections
    }
  } else if (result.summary || result.title) {
    // 如果只有summary或title，构建简单的markdown内容
    const markdownContent = `# ${result.title || '污染溯源分析报告'}\n\n${result.summary || ''}`
    console.log('构建的Markdown内容:', markdownContent)
    const result2 = { markdown_content: markdownContent }
    reportContentCache.value.set(cacheKey, result2)
    cacheUpdateTrigger.value++ // 触发响应式更新
    return result2
  }

  console.log('无法解析报告内容，result:', result)
  const result3 = null
  reportContentCache.value.set(cacheKey, result3)
  cacheUpdateTrigger.value++ // 触发响应式更新
  return result3
}

// 格式化section标题
const formatSectionTitle = (key) => {
  const titleMap = {
    '1_overall_assessment': '总体评估',
    '2_meteorological_analysis': '气象分析',
    '3_chemical_diagnostics': '化学诊断',
    '4_upwind_enterprises': '上风向企业',
    '5_control_recommendations': '控制建议',
    '6_risk_assessment': '风险评估',
    'executive_summary': '执行摘要',
    'report_metadata': '报告元数据'
  }
  return titleMap[key] || key
}

// 附件预览
const previewedImage = ref(null)

const previewAttachment = (attachment) => {
  if (attachment.type === 'image') {
    previewedImage.value = attachment
  }
}

const closeImagePreview = () => {
  previewedImage.value = null
}
</script>

<style lang="scss" scoped>
.react-message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 0;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background: #d0d0d0;
    border-radius: 3px;
  }
}

// 加载更多按钮
.load-more-container {
  display: flex;
  justify-content: center;
  padding: 12px 0 8px;
}

.load-more-btn {
  padding: 8px 20px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  background: #f8f9fa;
  color: #666;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #e9ecef;
    border-color: #d0d0d0;
    color: #333;
  }
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #999;
  font-size: 13px;

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid #e0e0e0;
    border-top-color: #999;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.welcome-message {
  text-align: center;
  padding: 40px 20px;
  color: #666;

  h2 {
    color: #1976D2;
    margin-bottom: 20px;
  }

  ul {
    text-align: left;
    max-width: 500px;
    margin: 20px auto;
    line-height: 1.8;
  }

  .hint {
    margin-top: 30px;
    font-style: italic;
    color: #999;
  }
}

.message {
  animation: fadeIn 0.3s;
}

.message-wrapper {
  margin: 0;
  display: flex;
  flex-direction: column;

  // 有来源的消息可点击（所有模式）
  &.clickable {
    cursor: pointer;
    border-radius: 8px;
    transition: background 0.2s;
    position: relative;

    &:hover {
      background: #f8fbff;
    }

    // 选中状态
    &.selected {
      background: #e3f2fd;
      border-left: 3px solid #1976d2;

      &:hover {
        background: #e3f2fd;
      }
    }

    // 来源提示样式
    .qa-sources {
      opacity: 0.7;
      transition: opacity 0.2s;
    }

    &:hover .qa-sources {
      opacity: 1;
    }
  }

  &.has-sources {
    .qa-sources {
      cursor: pointer;
    }
  }
}

.message-wrapper + .message-wrapper {
  margin-top: 0;
}

.user-message {
  padding: 10px 16px;
  background: #f5f5f5;
  border-radius: 18px;
  border: 1px solid #e0e0e0;
  margin-left: auto;
  margin-right: 0;
  align-self: flex-end;
  text-align: left;
  font-size: 14px;
  line-height: 1.6;
  display: inline-flex;
  justify-content: flex-start;
  width: auto;
  max-width: 70%;
  box-sizing: border-box;

  .message-content {
    text-align: left;
  }

  .reflexion-badge {
    margin-top: 8px;
    padding: 4px 8px;
    background: rgba(255, 152, 0, 0.1);
    border: 1px solid #FF9800;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #F57C00;

    .badge-icon {
      font-size: 14px;
    }

    .badge-text {
      font-weight: 500;
    }
  }
}

.agent-message.final {
  padding: 10px 16px;
  background: transparent;
  border-radius: 8px;
  margin-left: 0;
  margin-right: 0;
  border-left: none;
  max-width: 100%;
  font-size: 14px;
  line-height: 1.6;

  .expert-system-info {
    margin-top: 12px;
    padding: 12px;
    background: rgba(66, 165, 245, 0.08);
    border: 1px solid rgba(66, 165, 245, 0.3);
    border-radius: 8px;

    .expert-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      background: rgba(66, 165, 245, 0.15);
      border-radius: 4px;
      margin-bottom: 8px;

      .badge-icon {
        font-size: 16px;
      }

      .badge-text {
        font-size: 12px;
        font-weight: 500;
        color: #1976D2;
      }
    }

    .expert-list {
      margin: 8px 0;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;

      .expert-label {
        font-size: 12px;
        color: #666;
        font-weight: 500;
      }

      .expert-tag {
        padding: 2px 8px;
        background: rgba(76, 175, 80, 0.1);
        border: 1px solid rgba(76, 175, 80, 0.3);
        border-radius: 12px;
        font-size: 12px;
        color: #2E7D32;
        white-space: nowrap;
      }
    }

    .conclusions, .recommendations {
      margin-top: 8px;

      h4 {
        font-size: 13px;
        margin: 0 0 6px 0;
        color: #333;
        font-weight: 600;
      }

      ul {
        margin: 0;
        padding-left: 20px;

        li {
          font-size: 12px;
          line-height: 1.6;
          color: #555;
          margin-bottom: 4px;
        }
      }
    }

    .expert-summaries {
      margin-top: 12px;

      h4 {
        font-size: 13px;
        margin: 0 0 8px 0;
        color: #333;
        font-weight: 600;
      }

      .expert-summary-item {
        margin-bottom: 10px;
        padding: 8px;
        background: rgba(255, 255, 255, 0.5);
        border: 1px solid rgba(66, 165, 245, 0.2);
        border-radius: 6px;

        &:last-child {
          margin-bottom: 0;
        }

        .expert-summary-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
          padding-bottom: 6px;
          border-bottom: 1px solid rgba(66, 165, 245, 0.2);

          .expert-summary-icon {
            font-size: 16px;
          }

          .expert-summary-name {
            font-size: 12px;
            font-weight: 600;
            color: #1976D2;
            flex: 1;
          }

          .expert-confidence {
            font-size: 11px;
            color: #2E7D32;
            font-weight: 500;
          }
        }

        .expert-summary-content {
          .markdown-summary {
            margin-bottom: 8px;
            padding: 8px;
            background: rgba(255, 255, 255, 0.6);
            border-radius: 4px;
            border-left: 2px solid #1976D2;

            // 继承MarkdownRenderer的样式，但调整字体大小
            :deep(h1) {
              font-size: 14px;
              font-weight: 600;
              color: #1976D2;
              margin: 0 0 8px 0;
            }

            :deep(h2) {
              font-size: 13px;
              font-weight: 600;
              color: #1976D2;
              margin: 10px 0 6px 0;
            }

            :deep(h3) {
              font-size: 12px;
              font-weight: 600;
              color: #333;
              margin: 8px 0 4px 0;
            }

            :deep(p) {
              font-size: 11px;
              line-height: 1.5;
              color: #444;
              margin: 4px 0;
            }

            :deep(ul), :deep(ol) {
              margin: 4px 0;
              padding-left: 16px;

              li {
                font-size: 11px;
                line-height: 1.5;
                color: #444;
                margin-bottom: 2px;
              }
            }

            :deep(table) {
              font-size: 10px;

              th, td {
                padding: 4px 6px;
              }
            }

            :deep(strong) {
              font-weight: 600;
              color: #333;
            }
          }

          .expert-summary-text {
            font-size: 12px;
            line-height: 1.6;
            color: #555;
            margin: 0 0 6px 0;
          }

          .expert-key-findings {
            background: rgba(66, 165, 245, 0.05);
            border-radius: 4px;
            padding: 6px 8px;
            border-left: 2px solid #1976D2;

            .findings-label {
              display: inline-block;
              font-size: 11px;
              font-weight: 600;
              color: #1976D2;
              margin-bottom: 4px;
            }

            .findings-list {
              margin: 0;
              padding-left: 16px;

              li {
                font-size: 11px;
                line-height: 1.5;
                color: #666;
                margin-bottom: 2px;

                &:last-child {
                  margin-bottom: 0;
                }
              }
            }
          }

          .report-full-content {
            .markdown-report {
              margin-bottom: 12px;
              padding: 10px;
              background: rgba(255, 255, 255, 0.8);
              border-radius: 6px;
              border-left: 3px solid #1976D2;

              // Markdown内容样式
              :deep(h1) {
                font-size: 16px;
                font-weight: 600;
                color: #1976D2;
                margin: 0 0 12px 0;
                padding-bottom: 6px;
                border-bottom: 2px solid #1976D2;
              }

              :deep(h2) {
                font-size: 14px;
                font-weight: 600;
                color: #1976D2;
                margin: 16px 0 8px 0;
              }

              :deep(h3) {
                font-size: 13px;
                font-weight: 600;
                color: #333;
                margin: 12px 0 6px 0;
              }

              :deep(p) {
                font-size: 12px;
                line-height: 1.6;
                color: #444;
                margin: 6px 0;
              }

              :deep(ul), :deep(ol) {
                margin: 8px 0;
                padding-left: 20px;

                li {
                  font-size: 12px;
                  line-height: 1.6;
                  color: #444;
                  margin-bottom: 4px;
                }
              }

              :deep(table) {
                width: 100%;
                border-collapse: collapse;
                margin: 8px 0;

                th, td {
                  font-size: 11px;
                  padding: 6px 8px;
                  border: 1px solid #ddd;
                  text-align: left;
                }

                th {
                  background-color: #f5f5f5;
                  font-weight: 600;
                  color: #1976D2;
                }
              }

              :deep(strong) {
                font-weight: 600;
                color: #333;
              }

              :deep(em) {
                font-style: italic;
                color: #666;
              }
            }

            .report-section {
              margin-bottom: 12px;
              padding: 10px;
              background: rgba(255, 255, 255, 0.8);
              border-radius: 6px;
              border-left: 3px solid #1976D2;

              .section-title {
                font-size: 13px;
                font-weight: 600;
                color: #1976D2;
                margin: 0 0 8px 0;
              }

              .section-content {
                font-size: 12px;
                line-height: 1.6;
                color: #444;

                ul {
                  margin: 4px 0;
                  padding-left: 20px;
                  li {
                    margin-bottom: 4px;
                  }
                }

                .subsection {
                  margin-bottom: 6px;
                  .subsection-key {
                    font-weight: 500;
                    color: #666;
                    margin-right: 6px;
                  }
                  .subsection-value {
                    color: #333;
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

.react-event {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  background: transparent;
  border-radius: 6px;
  border-left: 3px solid #ddd;
  margin-left: 0;
  margin-right: 0;
  max-width: 100%;
  font-size: 14px;

  &.event-start {
    border-left-color: #1976D2;
    background: transparent;
  }

  &.event-thought {
    border-left-color: #9C27B0;
    background: transparent;
  }

  &.event-action {
    border-left-color: #FF9800;
    background: transparent;
  }

  &.event-observation {
    border-left-color: #4CAF50;
    background: transparent;
  }

  &.event-tool-use {
    border-left-color: #2196F3;
    background: transparent;
  }

  &.event-tool-result {
    border-left-color: #9C27B0;
    background: transparent;
  }

  &.event-error {
    border-left-color: #F44336;
    background: transparent;
  }
}

.event-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;

  .event-icon {
    font-size: 18px;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .event-text {
    flex: 1;
    line-height: 1.6;
    color: #333;

    .action-main {
      font-weight: 500;
      color: #333;
    }

    .observation-main {
      font-weight: 500;
      color: #333;
    }

    .tool-use-main {
      font-weight: 500;
      color: #1976D2;
    }

    .tool-result-main {
      font-weight: 500;
      color: #7B1FA2;
    }

    .tool-use-details {
      margin-top: 8px;

      details {
        summary {
          cursor: pointer;
          color: #666;
          font-size: 12px;
          user-select: none;
          padding: 4px 8px;
          background: transparent;
          border-radius: 4px;
          display: inline-flex;
          align-items: center;
        }

        pre {
          margin-top: 8px;
          padding: 8px;
          background: #f5f5f5;
          border-radius: 4px;
          font-size: 12px;
          overflow-x: auto;
        }
      }
    }

    .tool-result-summary {
      margin-top: 8px;
      padding: 8px;
      background: #f3e5f5;
      border-radius: 4px;
      font-size: 13px;
      color: #4A148C;
    }

    .thought-context,
    .action-params,
    .observation-details {
      margin-top: 8px;

      details {
        summary {
          cursor: pointer;
          color: #666;
          font-size: 12px;
          user-select: none;
          padding: 4px 8px;
          background: transparent;
          border-radius: 4px;
          display: inline-flex;
          align-items: center;
          gap: 6px;

          &:before {
            content: '▶';
            font-size: 10px;
            transition: transform 0.2s;
          }

          &:hover {
            color: #1976D2;
          }
        }

        details[open] summary:before {
          transform: rotate(90deg);
        }

        .observation-content-wrapper,
        .thought-context-content-wrapper,
        .params-content-wrapper {
          // 固定高度 + 滚动条，宽度自适应容器，避免爆屏
          width: 100%;
          max-height: 260px;
          overflow-y: auto;
          overflow-x: auto;
          margin-top: 4px;
          padding: 8px 10px;
          background: #fafafa;
          border: 1px solid #e0e0e0;
          border-radius: 4px;
          box-sizing: border-box;

          // 自定义滚动条样式
          &::-webkit-scrollbar {
            width: 8px;
            height: 8px;
          }

          &::-webkit-scrollbar-track {
            background: #f5f5f5;
            border-radius: 4px;
          }

          &::-webkit-scrollbar-thumb {
            background: #c0c0c0;
            border-radius: 4px;

            &:hover {
              background: #a0a0a0;
            }
          }

          pre {
            margin: 0;
            padding: 0;
            background: transparent;
            font-size: 11px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
          }
        }
      }
    }
  }

  &.error {
    .event-text {
      color: #C62828;
    }
  }
}

// 【新增】内联图表样式 - 使用float实现文字环绕
.inline-chart-wrapper {
  float: right;
  margin: 4px 0 8px 12px;
  clear: right;

  .inline-chart-img {
    max-width: 280px;
    max-height: 200px;
    width: auto;
    height: auto;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    border: 1px solid #e0e0e0;
    display: block;
  }
}

// 清除markdown段落中的浮动
.markdown-report {
  overflow: hidden;
}

// 针对图片后面的段落恢复正常的文档流
.markdown-report p {
  overflow: hidden;
  clear: both;
}

// 处理过程折叠区域样式
.process-collapse {
  margin-top: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  overflow: hidden;

  summary {
    padding: 8px 12px;
    background: #f5f5f5;
    cursor: pointer;
    font-size: 14px;
    text-align: center;
    display: block;
    user-select: none;

    &:hover {
      background: #eeeeee;
    }
  }

  .process-content {
    padding: 8px 12px;
    background: #fafafa;
    max-height: 400px;
    overflow-y: auto;

    .process-item {
      padding: 6px 0;
      border-bottom: 1px solid #f0f0f0;

      &:last-child {
        border-bottom: none;
      }
    }

    .process-thought,
    .process-action,
    .process-observation {
      display: flex;
      align-items: flex-start;
      gap: 8px;

      .process-icon {
        font-size: 14px;
        flex-shrink: 0;
      }

      .process-label {
        font-size: 11px;
        font-weight: 600;
        color: #666;
        white-space: nowrap;
        min-width: 60px;
      }

      .process-text {
        font-size: 12px;
        color: #333;
        line-height: 1.5;
        word-break: break-word;
      }
    }

    .process-thought .process-label {
      color: #9C27B0;
    }

    .process-action .process-label {
      color: #1976D2;
    }

    .process-observation .process-label {
      color: #388E3C;
    }

    .process-reasoning,
    .event-reasoning {
      margin-top: 6px;
      padding: 6px 10px;
      background: #f8f9fa;
      border-radius: 6px;
      font-size: 12px;
      color: #555;
      line-height: 1.5;

      summary {
        cursor: pointer;
        font-size: 11px;
        color: #777;
        user-select: none;
      }

      .reasoning-text {
        margin-top: 4px;
        white-space: pre-wrap;
        word-break: break-word;
      }
    }
  }
}

// 附件样式
.message-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.message-attachment {
  position: relative;
}

.attachment-image {
  max-width: 200px;
  max-height: 200px;
  border-radius: 8px;
  cursor: pointer;
  object-fit: cover;
  transition: opacity 0.2s;

  &:hover {
    opacity: 0.85;
  }
}

.attachment-file {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.attachment-file-icon {
  width: 20px;
  height: 20px;
  color: #7c8db5;
  flex-shrink: 0;
}

.attachment-file-name {
  font-size: 13px;
  color: #6b7a99;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 图片预览模态框
.image-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: pointer;
}

.image-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: default;
}

.preview-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 4px;
}

.preview-info {
  position: absolute;
  bottom: -40px;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 8px;
  color: white;
}

.preview-filename {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: calc(100% - 80px);
}

.preview-download {
  color: white;
  text-decoration: none;
  font-size: 14px;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  transition: background 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.3);
  }
}

.preview-close {
  position: absolute;
  top: -50px;
  right: 0;
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.2);
  }

  svg {
    width: 20px;
    height: 20px;
    color: white;
  }
}
</style>
