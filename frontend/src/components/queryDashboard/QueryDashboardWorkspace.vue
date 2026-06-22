<template>
  <div
    class="query-dashboard-workspace"
    :class="{ 'drag-over': dragOver }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <button
      v-if="hasVizContent"
      class="viz-toggle-btn"
      :class="{ expanded: rightPanelExpanded }"
      type="button"
      @click="$emit('toggle-viz-panel')"
      :title="rightPanelExpanded ? '隐藏右侧面板' : '显示右侧面板'"
    >
      <span>{{ rightPanelExpanded ? '»' : '«' }}</span>
    </button>

    <div class="dashboard-main">
      <div class="dashboard-content">
        <GuangdongOverviewMap
          :overview="overview"
          :focus="effectiveFocus"
          :layers="activeLayers"
        />

        <aside class="dashboard-side">
          <DashboardLayerControl v-model="activeLayers" />
          <DashboardFocusPanel :focus="effectiveFocus" />
          <button type="button" class="source-button" @click="sourceDrawerOpen = true">
            数据源
          </button>
        </aside>
      </div>
    </div>

    <section class="chat-overlay" aria-label="查询对话">
      <ReActMessageList
        class="overlay-message-list"
        :messages="messages"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :use-markdown="true"
        :assistant-mode="assistantMode"
        :selected-message-id="selectedMessageId"
        :visualization-panel-ref="null"
        :on-message-click="handleMessageClick"
        :has-more-messages="hasMoreMessages"
        :total-message-count="totalMessageCount"
        :loading-more="loadingMore"
        @load-more="$emit('load-more')"
      />
      <InputBox
        v-model="inputValue"
        :pending-steering-inputs="pendingSteeringInputs"
        :session-id="sessionId"
        :disabled="inputDisabled"
        :is-analyzing="isAnalyzing"
        placeholder="输入查询或追问..."
        :assistant-mode="assistantMode"
        :use-reranker="useReranker"
        @send="$emit('send', $event)"
        @pause="$emit('pause')"
        @update:useReranker="$emit('update:useReranker', $event)"
        @update:agentMode="$emit('update:agentMode', $event)"
      />
    </section>

    <DashboardSourceDrawer
      :open="sourceDrawerOpen"
      :sources="sources"
      @close="sourceDrawerOpen = false"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import InputBox from '@/components/InputBox.vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import { fetchGuangdongOverview } from '@/api/queryDashboard.js'
import { extractDashboardFocusFromMessages, normalizeDashboardFocus, normalizeLayerState } from './dashboardFocus.js'
import DashboardFocusPanel from './DashboardFocusPanel.vue'
import DashboardLayerControl from './DashboardLayerControl.vue'
import DashboardSourceDrawer from './DashboardSourceDrawer.vue'
import GuangdongOverviewMap from './GuangdongOverviewMap.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  pendingSteeringInputs: { type: Array, default: () => [] },
  isAnalyzing: { type: Boolean, default: false },
  inputDisabled: { type: Boolean, default: false },
  currentMessage: { type: String, default: '' },
  showReflexion: { type: Boolean, default: false },
  reflexionCount: { type: Number, default: 0 },
  assistantMode: { type: String, default: 'general-agent' },
  useReranker: { type: Boolean, default: false },
  sessionId: { type: String, default: '' },
  hasMoreMessages: { type: Boolean, default: false },
  totalMessageCount: { type: Number, default: 0 },
  loadingMore: { type: Boolean, default: false },
  selectedMessageId: { type: String, default: null },
  dashboardFocus: { type: Object, default: null },
  dragOver: { type: Boolean, default: false },
  rightPanelExpanded: { type: Boolean, default: false },
  hasVizContent: { type: Boolean, default: false }
})

const emit = defineEmits([
  'send',
  'pause',
  'update:useReranker',
  'update:agentMode',
  'select-message',
  'load-more',
  'drag-over',
  'drag-leave',
  'drop',
  'toggle-viz-panel'
])

const overview = ref(null)
const loading = ref(false)
const error = ref('')
const sourceDrawerOpen = ref(false)
const activeLayers = ref({
  city_metrics: true,
  stations: false,
  heatmap: false
})

const inputValue = computed({
  get: () => props.currentMessage,
  set: () => {}
})

const effectiveFocus = computed(() => {
  if (props.dashboardFocus) return normalizeDashboardFocus(props.dashboardFocus)
  return extractDashboardFocusFromMessages(props.messages)
})

const sources = computed(() => {
  const overviewSources = overview.value?.sources || overview.value?.source_details || overview.value?.data_sources
  if (Array.isArray(overviewSources)) return overviewSources
  const ids = effectiveFocus.value?.source_data_ids || []
  return ids.map((id) => ({ data_id: id }))
})

const loadOverview = async () => {
  loading.value = true
  error.value = ''
  try {
    overview.value = await fetchGuangdongOverview({
      include: ['realtime', 'month_to_date', 'year_to_date', 'layers']
    })
  } catch (err) {
    error.value = err?.message || '广东总览数据加载失败'
  } finally {
    loading.value = false
  }
}

const handleMessageClick = (messageId) => {
  emit('select-message', messageId)
}

const handleDragOver = (event) => {
  emit('drag-over', event)
}

const handleDragLeave = (event) => {
  emit('drag-leave', event)
}

const handleDrop = (event) => {
  emit('drop', event)
}

watch(
  () => effectiveFocus.value.layer_state,
  (layerState) => {
    const normalized = normalizeLayerState(layerState)
    if (Object.values(normalized).some(Boolean)) {
      activeLayers.value = normalized
    }
  },
  { immediate: true }
)

onMounted(() => {
  loadOverview()
})
</script>

<style scoped>
.query-dashboard-workspace {
  position: relative;
  display: flex;
  flex: 1 1 0%;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background: #eef3f2;
}

.query-dashboard-workspace.drag-over {
  background: #e6f7ff;
  outline: 2px dashed #1890ff;
  outline-offset: -2px;
}

.viz-toggle-btn {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 80px;
  border: 1px solid #d9d9d9;
  border-radius: 4px 0 0 4px;
  background: #f5f5f5;
  color: #666;
  cursor: pointer;
  font-weight: 700;
  transform: translateY(-50%);
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.viz-toggle-btn.expanded {
  background: #e8f4ff;
  color: #1890ff;
  border-color: #91d5ff;
}

.dashboard-main {
  display: flex;
  flex: 1 1 0%;
  min-width: 0;
  flex-direction: column;
  padding-bottom: 238px;
}

.dashboard-content {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  flex: 1;
  min-height: 0;
}

.dashboard-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border-left: 1px solid rgba(32, 49, 58, 0.1);
  background: rgba(247, 250, 249, 0.86);
  overflow: auto;
}

.source-button {
  flex: 0 0 auto;
  width: 100%;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid rgba(17, 128, 118, 0.22);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.72);
  color: #0f6c65;
  cursor: pointer;
  font-size: 13px;
}

.chat-overlay {
  position: absolute;
  right: 16px;
  bottom: 16px;
  left: 16px;
  z-index: 8;
  display: flex;
  flex-direction: column;
  max-height: 220px;
  min-height: 150px;
  border: 1px solid rgba(32, 49, 58, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 14px 34px rgba(22, 39, 46, 0.14);
  overflow: hidden;
}

.overlay-message-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.chat-overlay :deep(.input-box) {
  flex: 0 0 auto;
  border-top: 1px solid rgba(32, 49, 58, 0.1);
}

@media (max-width: 900px) {
  .dashboard-main {
    padding-bottom: 260px;
  }

  .dashboard-content {
    grid-template-columns: 1fr;
  }

  .dashboard-side {
    max-height: 190px;
    border-top: 1px solid rgba(32, 49, 58, 0.1);
    border-left: 0;
  }
}
</style>
