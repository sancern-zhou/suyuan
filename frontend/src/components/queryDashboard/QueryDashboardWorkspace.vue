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

    <!-- 管理面板插槽 -->
    <div v-show="showManagementPanel" class="management-panel-container">
      <slot name="management-panels"></slot>
    </div>

    <div class="dashboard-main" v-show="!showManagementPanel">
      <div class="dashboard-content">
        <GuangdongOverviewMap
          :overview="overview"
          :layers="activeLayers"
          :map-program="mapProgram"
          :session-id="sessionId"
          @map-event="$emit('map-event', $event)"
        />

        <aside class="dashboard-side">
          <DashboardLayerControl v-model="activeLayers" />
        </aside>
      </div>
    </div>

    <section class="chat-overlay" aria-label="查询对话" v-show="!showManagementPanel">
      <ReActMessageList
        class="overlay-message-list"
        :messages="messages"
        :is-analyzing="isAnalyzing"
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
        :hide-welcome="true"
        @load-more="$emit('load-more')"
      />
      <div v-if="readOnly" class="read-only-notice">
        <span>{{ readOnlyNotice }}</span>
        <button type="button" @click="$emit('new-web-conversation')">新建 Web 对话</button>
      </div>
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
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import InputBox from '@/components/InputBox.vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import { fetchGuangdongOverview } from '@/api/queryDashboard.js'
import DashboardLayerControl from './DashboardLayerControl.vue'
import GuangdongOverviewMap from './GuangdongOverviewMap.vue'
import { layerStateFromMapProgram } from './mapProgramDashboardLayers.js'

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
  mapProgram: { type: Object, default: null },
  dragOver: { type: Boolean, default: false },
  rightPanelExpanded: { type: Boolean, default: false },
  hasVizContent: { type: Boolean, default: false },
  showManagementPanel: { type: Boolean, default: false },
  readOnly: { type: Boolean, default: false },
  readOnlyNotice: { type: String, default: '' }
})

const emit = defineEmits([
  'send',
  'pause',
  'update:useReranker',
  'select-message',
  'load-more',
  'drag-over',
  'drag-leave',
  'drop',
  'toggle-viz-panel',
  'map-event',
  'new-web-conversation'
])

const overview = ref(null)
const loading = ref(false)
const error = ref('')
const activeLayers = ref({
  city_metrics: true,
  stations: false,
  heatmap: false
})

const inputValue = computed({
  get: () => props.currentMessage,
  set: () => {}
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
  () => props.mapProgram,
  (mapProgram) => {
    const layerState = layerStateFromMapProgram(mapProgram)
    if (layerState) {
      activeLayers.value = layerState
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

.management-panel-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: white;
}

.dashboard-main {
  position: absolute;
  inset: 0;
  display: block;
  flex: 1 1 0%;
  min-width: 0;
}

.dashboard-content {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.dashboard-side {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 7;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(260px, calc(100% - 32px));
  max-height: min(260px, calc(100% - 32px));
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  overflow: auto;
  pointer-events: auto;
}

.chat-overlay {
  position: absolute;
  top: 16px;
  right: 18px;
  bottom: 16px;
  z-index: 8;
  display: flex;
  flex-direction: column;
  width: min(480px, calc(100% - 36px));
  min-height: 0;
  border: 1px solid rgba(32, 49, 58, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 14px 34px rgba(22, 39, 46, 0.14);
  backdrop-filter: blur(8px);
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
  .dashboard-side {
    left: 12px;
    top: 12px;
    width: min(260px, calc(100% - 24px));
    max-height: 168px;
  }

  .chat-overlay {
    top: auto;
    right: 12px;
    bottom: 12px;
    left: 12px;
    width: auto;
    max-height: 230px;
    min-height: 150px;
  }
}
</style>
