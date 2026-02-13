<template>
  <div class="react-analysis-view">
    <ReactTopBar
      :is-analyzing="store.isAnalyzing"
      :is-complete="store.isComplete"
      :has-results="store.hasResults"
      :debug-mode="store.debugMode"
      :iterations="store.iterations"
      :max-iterations="store.maxIterations"
      @toggle-debug="store.toggleDebug"
      @restart="store.restart"
    />

    <div class="main-layout">
      <AssistantSidebar
        v-model:activeModule="activeAssistant"
        @select="handleAssistantSelect"
      />

      <!-- 所有模式使用统一的分析面板 -->
      <div class="analysis-panel" ref="layoutRef">
        <div class="chat-area">
          <!-- ✅ 知识问答模式提示 -->
          <div v-if="activeAssistant === 'knowledge-qa'" class="react-mode-notice">
            <span class="react-icon">📚</span>
            <span class="react-text">
              <strong>知识问答模式</strong> - 基于知识库的智能问答，实时显示参考来源
            </span>
          </div>

          <!-- ✅ 通用Agent ReAct模式提示 -->
          <div v-else-if="activeAssistant === 'general-agent'" class="react-mode-notice">
            <span class="react-icon">🧠</span>
            <span class="react-text">
              <strong>ReAct循环模式</strong> - LLM自主决策：思考→行动→观察，支持动态工具调用
              <span class="restriction-hint">（禁用化学机理OBM分析，避免长时间等待）</span>
            </span>
          </div>


          <ReActMessageList
            :messages="store.messages"
            :debug-mode="store.debugMode"
            :show-reflexion="store.showReflexion"
            :reflexion-count="store.reflexionCount"
            :use-markdown="true"
            :assistant-mode="activeAssistant"
            :visualization-panel-ref="vizPanelRef"
            :on-message-click="selectMessage"
          />

          <InputBox
            v-model="store.currentMessage"
            :disabled="inputDisabled"
            :is-analyzing="store.isAnalyzing"
            :placeholder="inputPlaceholder"
            :assistant-mode="activeAssistant"
            :use-reranker="useReranker"
            @send="handleSend"
            @pause="handlePause"
            @update:precision="handlePrecisionChange"
            @update:enableReasoning="handleEnableReasoningChange"
            @update:useReranker="handleRerankerChange"
          />
        </div>

        <div
          class="resize-handle"
          :class="{ dragging: isDragging }"
          @mousedown="startDragging"
          @dblclick.stop="resetWidth"
          title="拖拽调整右侧面板宽度，双击恢复默认"
        ></div>

        <div class="viz-wrapper" :style="vizPanelStyle">
          <!-- 知识问答模式：来源详情面板 -->
          <template v-if="activeAssistant === 'knowledge-qa'">
            <!-- 有选中来源时显示详情 -->
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
            <!-- 未选中来源时显示提示 -->
            <div class="knowledge-qa-sidebar" v-else>
              <div class="sidebar-hint">
                <span class="hint-icon">📚</span>
                <p>点击AI回答查看检索到的参考来源详情</p>
              </div>
            </div>
          </template>

          <!-- 报告生成专家 -->
          <ReportGenerationPanel
            v-else-if="activeAssistant === 'report-generation-expert'"
            :assistant-mode="activeAssistant"
          />

          <!-- 其他模式：可视化面板 -->
          <VisualizationPanel
            v-else
            ref="vizPanelRef"
            :content="store.currentVisualization"
            :history="store.visualizationHistory"
            :assistant-mode="activeAssistant"
            :expert-results="store.lastExpertResults"
            @fullscreen="openFullscreen"
            @fullscreen-expert="handleExpertFullscreen"
          />
        </div>
      </div>
    </div>

    <!-- 大屏模式 -->
    <FullscreenDashboard
      :visible="fullscreenMode"
      :assistant-mode="activeAssistant"
      :expert-results="store.lastExpertResults"
      @close="closeFullscreen"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import ReactTopBar from '@/components/ReactTopBar.vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import VisualizationPanel from '@/components/VisualizationPanel.vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'
import AssistantSidebar from '@/components/AssistantSidebar.vue'
import MeteorologyScenarioSelector from '@/components/MeteorologyScenarioSelector.vue'
import FullscreenDashboard from '@/components/dashboard/FullscreenDashboard.vue'
import { knowledgeQAStream } from '@/api/knowledgeQA'  // ✅ 导入知识问答API

const store = useReactStore()
const kbStore = useKnowledgeBaseStore()

const defaultVizWidth = 30
const minVizWidth = 20
const maxVizWidth = 60

const vizWidth = ref(defaultVizWidth)
const isDragging = ref(false)
const layoutRef = ref(null)
const activeAssistant = ref('general-agent')
const fullscreenMode = ref(false)
const precision = ref('standard')  // 默认standard模式，点击按钮切换为fast
const vizPanelRef = ref(null)  // VisualizationPanel的引用

// 知识问答来源面板状态
const selectedMsgIndex = ref(-1)
const selectedSources = ref([])
const useReranker = ref(false)  // 精准检索开关

const handlePrecisionChange = (value) => {
  precision.value = value
  console.log('精度模式:', value === 'fast' ? '极速模式(fast)' : '标准模式(standard)')
}

const handleEnableReasoningChange = (value) => {
  // enableReasoning状态由InputBox组件管理，这里只是接收更新
  // 实际值会在handleSend时从payload中获取
  console.log('思考模式:', value ? '已启用（显示推理过程）' : '已禁用（隐藏推理过程）')
}

const handleRerankerChange = (value) => {
  useReranker.value = value
}

const vizPanelStyle = computed(() => ({
  width: `${vizWidth.value}%`
}))

const allVisualizations = computed(() => {
  const vizList = []
  if (store.visualizationHistory?.length) {
    vizList.push(...store.visualizationHistory)
  }
  if (store.currentVisualization) {
    if (store.currentVisualization.visuals) {
      // 兼容两种格式：VisualBlock格式 和 直接格式
      const visuals = store.currentVisualization.visuals.map(v => {
        if (v.payload) {
          return { ...v.payload, meta: v.meta }
        } else {
          return v
        }
      })
      vizList.push(...visuals)
    } else {
      vizList.push(store.currentVisualization)
    }
  }
  const seen = new Set()
  return vizList.filter(viz => {
    if (!viz) return false
    const key = viz.id || `${viz.type}_${JSON.stringify(viz.data || '')}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const openFullscreen = () => {
  fullscreenMode.value = true
}

const closeFullscreen = () => {
  fullscreenMode.value = false
  // 清理激活标签页存储
  localStorage.removeItem('activeExpertTab')
}

const handleExpertFullscreen = (expertType) => {
  // 始终保持多专家模式，但设置激活标签页
  if (!fullscreenMode.value) {
    // 首次打开时，保持当前assistantMode，但强制进入多专家模式
    fullscreenMode.value = true
    // 强制激活指定专家的标签页
    nextTick(() => {
      // 通过event bus或全局状态设置激活的专家标签
      // 这里使用localStorage作为临时方案
      localStorage.setItem('activeExpertTab', expertType)
      // 触发FullscreenDashboard更新
      window.dispatchEvent(new CustomEvent('setActiveExpertTab', { detail: expertType }))
    })
  }
}

const assistantNoticeMap = {
  'meteorology-expert': '气象分析专家已接入，可直接提问并查看专业气象分析结果。',
  'quick-tracing-expert': '快速溯源专家已接入，多专家协同快速识别污染来源和传输路径。',
  'deep-tracing-expert': '深度溯源专家已接入，基于HYSPLIT轨迹+源清单+RACM2化学机理进行深度分析（约5-10分钟）。',
  'data-visualization-expert': '数据可视化专家已接入，可根据数据特征智能生成专业图表。',
  'report-generation-expert': '报告生成专家已接入，可基于模板生成专业报告，支持上传历史报告或选择保存的模板。',
  'knowledge-qa': '知识问答专家已接入，基于您的知识库文档进行智能问答。',
  'general-agent': '通用Agent已接入，支持自然语言提问和多轮交互。'
}

const assistantNotice = computed(() => {
  const noNoticeAssistants = ['general-agent', 'meteorology-expert', 'quick-tracing-expert', 'deep-tracing-expert', 'data-visualization-expert', 'report-generation-expert', 'knowledge-qa']
  if (noNoticeAssistants.includes(activeAssistant.value)) {
    return ''
  }
  return assistantNoticeMap[activeAssistant.value] || '该助手尚未接入后台，敬请期待。'
})

const isAssistantReady = computed(() => {
  const readyAssistants = ['general-agent', 'meteorology-expert', 'quick-tracing-expert', 'deep-tracing-expert', 'data-visualization-expert', 'report-generation-expert', 'knowledge-qa']
  return readyAssistants.includes(activeAssistant.value)
})

const inputPlaceholder = computed(() => {
  return '输入您的问题...'
})

const inputDisabled = computed(() => {
  const baseDisabled = !store.canInput && !store.isAnalyzing
  return baseDisabled || !isAssistantReady.value
})

const clampWidth = (value) => {
  return Math.min(maxVizWidth, Math.max(minVizWidth, value))
}

const updateWidthFromCursor = (clientX) => {
  if (!layoutRef.value) return
  const bounds = layoutRef.value.getBoundingClientRect()
  const vizPixels = bounds.right - clientX
  const percent = (vizPixels / bounds.width) * 100
  vizWidth.value = clampWidth(percent)
}

const handleMouseMove = (event) => {
  if (!isDragging.value) return
  updateWidthFromCursor(event.clientX)
}

const stopDragging = () => {
  if (!isDragging.value) return
  isDragging.value = false
}

const startDragging = (event) => {
  isDragging.value = true
  updateWidthFromCursor(event.clientX)
  event.preventDefault()
}

const resetWidth = () => {
  vizWidth.value = defaultVizWidth
}

const switchToGeneral = () => {
  activeAssistant.value = 'general-agent'
}

const handleAssistantSelect = async (moduleId) => {
  if (moduleId !== 'general-agent' && store.isAnalyzing) {
    await store.pauseAnalysis()
  }
}

// 选择消息查看来源详情（知识问答模式）
function selectMessage(index, message) {
  // ReActMessageList的消息结构：type为final，sources在message.data.sources
  const msg = message || store.messages[index]
  if (msg && msg.type === 'final' && msg.data?.sources?.length > 0) {
    if (selectedMsgIndex.value === index) {
      // 取消选择
      selectedMsgIndex.value = -1
      selectedSources.value = []
    } else {
      // 选择该消息
      selectedMsgIndex.value = index
      selectedSources.value = msg.data.sources
    }
  }
}

onMounted(async () => {
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', stopDragging)
  await store.init()
  // 加载知识库列表并自动全选
  await kbStore.fetchKnowledgeBases()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', stopDragging)
})

const handleSend = async (payload) => {
  if (!isAssistantReady.value) return

  // 处理新的输入格式：可能是字符串（向后兼容）或对象
  const query = typeof payload === 'string' ? payload : payload.query
  const knowledgeBaseIds = typeof payload === 'object' ? payload.knowledgeBaseIds || [] : []
  const selectedPrecision = typeof payload === 'object' ? payload.precision || 'standard' : 'standard'
  const enableReasoning = typeof payload === 'object' ? payload.enableReasoning || false : false

  // 构建分析选项
  // ✅ 强制设置：通用Agent模式下禁用极速模式，使用默认standard
  const forceDisableFast = activeAssistant.value === 'general-agent'
  const options = {
    assistantMode: activeAssistant.value,
    precision: forceDisableFast ? 'standard' : selectedPrecision,  // 精度模式选项
    knowledgeBaseIds: knowledgeBaseIds,  // 选中的知识库ID列表
    enableMultiExpert: false,  // ✅ 通用Agent使用单专家模式，支持真正的ReAct循环
    enableReasoning: enableReasoning  // ✅ 思考模式开关（是否显示LLM推理过程）
  }

  // ✅ 如果是通用Agent模式，重置精度模式为默认
  if (forceDisableFast) {
    precision.value = 'standard'
  }

  // 根据选择的助手模式调用不同的分析方法
  if (activeAssistant.value === 'meteorology-expert') {
    // 气象专家模式
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else if (activeAssistant.value === 'quick-tracing-expert') {
    // 快速溯源专家模式
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else if (activeAssistant.value === 'deep-tracing-expert') {
    // 深度溯源专家模式（复用快速溯源逻辑，后端自动启用RACM2化学机理）
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else if (activeAssistant.value === 'data-visualization-expert') {
    // 数据可视化专家模式
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else if (activeAssistant.value === 'report-generation-expert') {
    // 报告生成专家模式
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else if (activeAssistant.value === 'knowledge-qa') {
    // ✅ 知识问答模式：调用专门的RAG知识问答API（非ReAct流程）
    // 直接向量检索 + LLM生成，不经过思考→行动→观察循环
    try {
      store.isAnalyzing = true
      store.isComplete = false
      store.error = null
      store.iterations = 0

      // 添加用户消息
      store.addMessage('user', query)

      // 调用知识问答流式API
      await knowledgeQAStream(
        query,
        {
          session_id: store.sessionId || null,
          knowledge_base_ids: knowledgeBaseIds.length > 0 ? knowledgeBaseIds : null,
          top_k: 3,
          score_threshold: null,
          use_reranker: useReranker.value  // 启用/禁用精准检索
        },
        // onMessage - 处理流式事件
        (eventData) => {
          console.log('[KnowledgeQA] 收到事件:', eventData.type)
          console.log('[KnowledgeQA] 完整数据:', JSON.stringify(eventData, null, 2))
          store.handleEvent(eventData)
        },
        // onError
        (error) => {
          console.error('[KnowledgeQA] 错误:', error)
          store.isAnalyzing = false
          store.error = error.message
          store.addMessage('error', `知识问答失败: ${error.message}`)
        },
        // onComplete
        (data) => {
          console.log('[KnowledgeQA] 完成:', data)
          store.isAnalyzing = false
          store.isComplete = true
          store.hasResults = true
        }
      )
    } catch (error) {
      console.error('[KnowledgeQA] 异常:', error)
      store.isAnalyzing = false
      store.error = error.message
      store.addMessage('error', `知识问答失败: ${error.message}`)
    }
  } else {
    // ✅ 通用Agent模式：切换为单专家模式，支持真正的ReAct循环
    // 思考→行动→观察的自主决策过程，而非固定流水线
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  }
}

const handlePause = async () => {
  await store.pauseAnalysis()
}

// 处理气象专家场景选择
const handleMeteorologyScenarioSelect = (scenario) => {
  console.log('选择了气象场景:', scenario)

  // 根据选择的场景生成查询
  let query = ''
  const location = prompt('请输入要分析的地区（如：北京、广州等）：', '北京')
  if (!location) return

  const today = new Date().toISOString().split('T')[0]
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split('T')[0]

  switch (scenario.scenario) {
    case 'default':
      query = `分析${location}地区${today}的气象条件，包括温度、湿度、风速风向等关键气象要素变化趋势，并生成相关图表`
      break
    case 'enhanced':
      query = `对${location}地区进行增强气象分析，结合历史气象数据和当前实时天气，分析气象条件变化，并生成多类型专业图表`
      break
    case 'trajectory':
      query = `分析${location}今天的风向对污染物传输的影响，通过后向轨迹计算识别污染来源方向，并生成传输路径地图`
      break
    case 'comprehensive':
      query = `对${location}地区进行完整的气象分析，包括火点监测、沙尘传输、轨迹分析等多维度数据，生成全方位专业报告`
      break
    default:
      query = `分析${location}地区的气象条件`
  }

  // 开始分析
  store.startAnalysis(query, { assistantMode: 'meteorology-expert' })
}
</script>

<style lang="scss" scoped>
.react-analysis-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f6fb;
}

.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.analysis-panel {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid #f0f0f5;
  min-width: 360px;
}

.scenario-selector-wrapper {
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.assistant-notice {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff7e6;
  border-bottom: 1px solid #ffe6bf;
  color: #ad6a00;
  font-size: 13px;
}

.notice-button {
  border: none;
  background: #ffb74d;
  color: #fff;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  cursor: pointer;
}

// ✅ 通用Agent ReAct模式提示样式
.react-mode-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
  border-bottom: 1px solid #bbdefb;
  color: #1565c0;
  font-size: 13px;
}

.react-icon {
  font-size: 16px;
}

.react-text {
  flex: 1;
}

.react-text strong {
  color: #0d47a1;
  font-weight: 600;
}

.restriction-hint {
  margin-left: 8px;
  color: #666;
  font-size: 12px;
  font-weight: normal;
}

// 知识问答侧边栏
.knowledge-qa-sidebar {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #f8f9fa 0%, #fff 100%);
  padding: 20px;
}

.sidebar-hint {
  text-align: center;
  color: #666;
  max-width: 200px;

  .hint-icon {
    font-size: 32px;
    display: block;
    margin-bottom: 12px;
  }

  p {
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    color: #7a86a0;
  }
}

// 来源详情面板样式
.sources-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
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

.viz-wrapper {
  height: 100%;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.resize-handle {
  width: 6px;
  cursor: col-resize;
  background: linear-gradient(90deg, #f0f0f0 0%, #e0e0e0 100%);
  border-left: 1px solid #e0e0e0;
  border-right: 1px solid #e0e0e0;
  transition: background 0.2s;
}

.resize-handle:hover,
.resize-handle.dragging {
  background: linear-gradient(90deg, #d0e3ff 0%, #c0d8ff 100%);
}

@media (max-width: 1280px) {
  .react-analysis-view {
    height: auto;
  }

  .main-layout {
    flex-direction: column;
  }

  .analysis-panel {
    flex-direction: column;
  }

  .chat-area {
    min-width: 100%;
  }

  .resize-handle {
    height: 6px;
    width: 100%;
    cursor: row-resize;
  }

  .viz-wrapper {
    width: 100% !important;
  }
}
</style>
