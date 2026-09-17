<template>
  <div
    v-if="visible"
    :class="['viz-wrapper', { 'full-bleed-resource-panel': fullBleedVisualizationPanel }]"
    :style="resolvedPanelStyle"
  >
    <!-- 报告生成专家 -->
    <template v-if="assistantMode === 'report-generation-expert'">
      <div class="right-panel-tabs">
        <button
          v-if="documentCount > 0"
          :class="['tab-btn', { active: activeTab === 'document' }]"
          @click="handleTabChange('document')"
        >
          <span>报告</span>
          <span v-if="documentCount > 0" class="tab-count">{{ documentCount }}</span>
        </button>
        <button
          v-if="fileProductCount > 0"
          :class="['tab-btn', { active: activeTab === 'files' }]"
          @click="handleTabChange('files')"
        >
          <span>文件产物</span>
          <span v-if="fileProductCount > 0" class="tab-count">{{ fileProductCount }}</span>
        </button>
        <button
          v-if="feedbackAvailable"
          :class="['tab-btn', { active: activeTab === 'feedback' }]"
          @click="handleTabChange('feedback')"
        >
          <span>待确认</span>
          <span class="tab-count">{{ feedbackCount }}</span>
        </button>
      </div>
      <ResourceProductsPanel
        v-if="activeTab === 'files' && sessionId"
        class="panel-content"
        @open-resource-tab="handleTabChange"
      />
      <ReportGenerationPanel
        v-else-if="activeTab !== 'feedback'"
        :assistant-mode="assistantMode"
      />
      <HumanFeedbackPanel
        v-else
        class="panel-content"
        :feedback="humanFeedback"
        :submitting="humanFeedbackSubmitting"
        :error="humanFeedbackError"
        @submit="$emit('submit-human-feedback', $event)"
      />
    </template>

    <!-- 其他模式：可视化面板 + Office文档预览面板 + 知识溯源面板 -->
    <template v-else>
      <!-- 标签页切换按钮 -->
      <div v-if="showTabs && !fullBleedVisualizationPanel" class="right-panel-tabs" role="tablist" aria-label="右侧资源面板">
        <button
          v-if="visualizationAvailable"
          :class="['tab-btn', { active: activeTab === 'visualization' }]"
          role="tab"
          :aria-selected="activeTab === 'visualization'"
          @click="handleTabChange('visualization')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 19V5" />
            <path d="M5 19h14" />
            <path d="M9 16v-5" />
            <path d="M13 16V8" />
            <path d="M17 16v-3" />
          </svg>
          <span>可视化</span>
          <span v-if="visualizationCount > 0" class="tab-count">{{ visualizationCount }}</span>
        </button>
        <button
          v-if="documentAvailable"
          :class="['tab-btn', { active: activeTab === 'document' }]"
          role="tab"
          :aria-selected="activeTab === 'document'"
          @click="handleTabChange('document')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 3.5h8l4 4v13H6v-17Z" />
            <path d="M14 3.5v4h4" />
            <path d="M9 12h6" />
            <path d="M9 15.5h5" />
          </svg>
          <span>文档预览</span>
          <span v-if="documentCount > 0" class="tab-count">{{ documentCount }}</span>
        </button>
        <button
          v-if="knowledgeCount > 0"
          :class="['tab-btn', { active: activeTab === 'knowledge' }]"
          role="tab"
          :aria-selected="activeTab === 'knowledge'"
          @click="handleTabChange('knowledge')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 5.5C5 4.67 5.67 4 6.5 4h11c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-13Z" />
            <path d="M8 8h8" />
            <path d="M8 11.5h8" />
            <path d="M8 15h5" />
          </svg>
          <span>知识溯源</span>
          <span v-if="knowledgeCount > 0" class="tab-count">{{ knowledgeCount }}</span>
        </button>
        <button
          v-if="fileProductCount > 0"
          :class="['tab-btn', { active: activeTab === 'files' }]"
          role="tab"
          :aria-selected="activeTab === 'files'"
          @click="handleTabChange('files')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 7h6l2 2h9v9.5a2 2 0 0 1-2 2h-17v-13.5Z"/><path d="M3.5 10h17"/></svg>
          <span>文件产物</span>
          <span v-if="fileProductCount > 0" class="tab-count">{{ fileProductCount }}</span>
        </button>
        <button
          v-if="feedbackAvailable"
          :class="['tab-btn', { active: activeTab === 'feedback' }]"
          role="tab"
          :aria-selected="activeTab === 'feedback'"
          @click="handleTabChange('feedback')"
        >
          <span>待确认</span>
          <span class="tab-count">{{ feedbackCount }}</span>
        </button>
        <button
          v-if="showBoardTab"
          :class="['tab-btn', { active: activeTab === 'board' }]"
          role="tab"
          :aria-selected="activeTab === 'board'"
          @click="handleTabChange('board')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5.5h16v13H4v-13Z" />
            <path d="M8 9h3v3H8V9Z" />
            <path d="M14 12h3v3h-3v-3Z" />
            <path d="M11 10.5h3" />
          </svg>
          <span>画板</span>
        </button>
        <button
          v-if="smartEventAvailable"
          :class="['tab-btn', { active: activeTab === 'smart-event' }]"
          role="tab"
          :aria-selected="activeTab === 'smart-event'"
          @click="handleTabChange('smart-event')"
        >
          <span>智能事件</span>
        </button>
        <button
          v-if="deviceControlAvailable"
          :class="['tab-btn', { active: activeTab === 'device-control' }]"
          role="tab"
          :aria-selected="activeTab === 'device-control'"
          @click="handleTabChange('device-control')"
        >
          <span>远程质控</span>
        </button>
      </div>

      <div
        v-if="activeTab === 'visualization'"
        class="panel-content visualization-panel-host"
      >
        <VisualizationGallery key="visualization-gallery" />
      </div>

      <ResourcePreviewHost
        v-if="['document', 'board'].includes(activeTab)"
        :key="`${activeTab}-resource-preview`"
        class="panel-content"
        :target="activeTab"
      />

      <!-- 知识溯源面板 -->
      <KnowledgeSourcePanel
        v-if="activeTab === 'knowledge'"
        ref="knowledgePanelRef"
        key="knowledge-panel"
        class="panel-content"
        :sources="knowledgeSources"
        :history="messages"
        :selected-message-id="selectedMessageId"
      />

      <ResourceProductsPanel
        v-if="activeTab === 'files' && sessionId"
        class="panel-content"
        @open-resource-tab="handleTabChange"
      />

      <HumanFeedbackPanel
        v-if="activeTab === 'feedback'"
        class="panel-content"
        :feedback="humanFeedback"
        :submitting="humanFeedbackSubmitting"
        :error="humanFeedbackError"
        @submit="$emit('submit-human-feedback', $event)"
      />

      <!-- 智能事件工作区：江苏事件任务 Agent 可在保留对话的同时调度该页面 -->
      <TaskExecutionWorkspace
        v-if="activeTab === 'smart-event' && taskWorkspaceTask"
        class="panel-content"
        :task="taskWorkspaceTask"
        show-back-button
        @close="$emit('close-smart-event-task')"
        @restore-execution-session="$emit('restore-execution-session', $event)"
      />
        <SmartEventCenterPanel
          v-else-if="activeTab === 'smart-event'"
          :category="smartEventCategory"
        class="panel-content"
        :workspace-command="smartEventCommand"
        @close="$emit('close-smart-event-panel')"
        @open-task="$emit('open-smart-event-task-side', $event)"
      />

      <!-- 远程质控工作区：设备反控 Agent 在右侧展示质控过程（状态核查/待确认/下发/回读/审计） -->
      <DeviceControlProcessPanel
        v-else-if="activeTab === 'device-control'"
        class="panel-content"
        :workspace-command="deviceControlCommand"
        :messages="messages"
        @close="$emit('close-device-control-panel')"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'
import KnowledgeSourcePanel from '@/components/visualization/panels/KnowledgeSourcePanel.vue'
import ResourceProductsPanel from '@/components/resources/ResourceProductsPanel.vue'
import ResourcePreviewHost from '@/components/resources/ResourcePreviewHost.vue'
import VisualizationGallery from '@/components/resources/VisualizationGallery.vue'
import HumanFeedbackPanel from './HumanFeedbackPanel.vue'
import DeviceControlProcessPanel from '@/components/management/DeviceControlProcessPanel.vue'
import SmartEventCenterPanel from '@/components/management/SmartEventCenterPanel.vue'
import TaskExecutionWorkspace from '@/components/management/TaskExecutionWorkspace.vue'
import { projectConfig } from '@/config/projectConfig.js'
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { summarizeRightPanelResources } from '@/components/resources/rightPanelResources.js'
import { buildResourceGroups, targetTab } from '@/services/resourceGroups.js'
import { visualizationGalleryItems } from '@/services/visualizationGallery.js'
import { isTaskReviewVisual } from '@/services/visualizationTypes.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  knowledgePanelVisible: {
    type: Boolean,
    default: false
  },
  activeTab: {
    type: String,
    default: 'visualization'
  },
  panelStyle: {
    type: Object,
    default: () => ({})
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  messages: {
    type: Array,
    default: () => []
  },
  selectedMessageId: {
    type: String,
    default: null
  },
  sessionId: {
    type: String,
    default: ''
  },
  expertResults: {
    type: Object,
    default: null
  },
  knowledgeSources: {
    type: Array,
    default: () => []
  },
  board: {
    type: Object,
    default: null
  },
  humanFeedback: {
    type: Object,
    default: null
  },
  humanFeedbackSubmitting: {
    type: Boolean,
    default: false
  },
  humanFeedbackError: {
    type: String,
    default: ''
  },
  smartEventCommand: {
    type: Object,
    default: null
  },
  deviceControlCommand: {
    type: Object,
    default: null
  },
  taskWorkspaceTask: {
    type: Object,
    default: null
  }
})

const emit = defineEmits([
  'tab-change',
  'board-xml-change',
  'board-selection-change',
  'board-snapshot-confirm',
  'submit-human-feedback',
  'open-smart-event-task-side',
  'close-smart-event-panel',
  'close-smart-event-task',
  'close-device-control-panel',
  'restore-execution-session'
])
const resourceStore = useSessionResourceStore()

// 添加调试
watch(() => props.activeTab, (newVal) => {
  console.log('[RightPanelContainer] activeTab changed to:', newVal)
})

watch(() => props.visible, (newVal) => {
  console.log('[RightPanelContainer] visible changed to:', newVal)
})

const knowledgePanelRef = ref(null)
const resourceSummary = computed(() => summarizeRightPanelResources(
  resourceStore.activeSessionId === props.sessionId
    ? resourceStore.activeSessionState?.resources || []
    : []
))
const panelResources = computed(() => (
  resourceStore.activeSessionId === props.sessionId
    ? resourceStore.activeSessionState?.resources || []
    : []
))
const visualizationItems = computed(() => visualizationGalleryItems(panelResources.value))
const fullBleedVisualizationPanel = computed(() => (
  props.activeTab === 'visualization' &&
  visualizationItems.value.length === 1 &&
  isTaskReviewVisual(visualizationItems.value[0]?.resource)
))
const resolvedPanelStyle = computed(() => ({
  ...props.panelStyle,
  ...(fullBleedVisualizationPanel.value
    ? {
        overflowY: 'hidden',
        overflowX: 'hidden',
        background: 'transparent',
        borderLeft: '0'
      }
    : {})
}))
const showBoardTab = computed(() => resourceSummary.value.counts.board > 0)
const explicitTarget = computed(() => {
  const state = resourceStore.activeSessionState
  if (state?.selectionOrigin !== 'explicit' || resourceStore.activeSessionId !== props.sessionId) return ''
  const selected = resourceStore.selectedResource(props.sessionId)
  const group = buildResourceGroups(state.resources || []).find(item => item.group_id === selected?.group_id)
  return group ? targetTab(group) : ''
})

const smartEventAvailable = computed(() => (
  projectConfig.project === 'jiangsu-ops' &&
  ['smart_event_external', 'smart_event_instrument'].includes(props.assistantMode)
))
const deviceControlAvailable = computed(() => (
  projectConfig.project === 'jiangsu-ops' && props.assistantMode === 'device_control'
))
const smartEventCategory = computed(() => {
  if (props.assistantMode === 'smart_event_external') return 'external-environment'
  if (props.assistantMode === 'smart_event_instrument') return 'instrument-fault'
  return 'all'
})

const showTabs = computed(() => {
  // 只要有任意一个面板可见，就显示标签页切换按钮
  return visualizationAvailable.value || documentAvailable.value || fileProductCount.value > 0 || knowledgeCount.value > 0 || showBoardTab.value || feedbackAvailable.value || smartEventAvailable.value || deviceControlAvailable.value
})

const fileProductCount = computed(() => resourceSummary.value.counts.files)
const visualizationCount = computed(() => resourceSummary.value.counts.visualization)
const documentCount = computed(() => resourceSummary.value.counts.document)
const visualizationAvailable = computed(() => visualizationCount.value > 0 || explicitTarget.value === 'visualization')
const documentAvailable = computed(() => documentCount.value > 0 || explicitTarget.value === 'document')

const knowledgeCount = computed(() => props.knowledgeSources?.length || 0)
const feedbackCount = computed(() => props.humanFeedback?.items?.length || 0)
const feedbackAvailable = computed(() => feedbackCount.value > 0)

watch(
  () => [props.assistantMode, props.activeTab, visualizationAvailable.value, documentAvailable.value, knowledgeCount.value, showBoardTab.value, feedbackAvailable.value],
  ([mode, tab, visualizations, documents, knowledge, board, feedback]) => {
    if (mode === 'report-generation-expert') return
    const unavailable = (
      (tab === 'visualization' && !visualizations)
      || (tab === 'document' && !documents)
      || (tab === 'knowledge' && knowledge === 0)
      || (tab === 'board' && !board)
      || (tab === 'feedback' && !feedback)
      || (tab === 'files' && fileProductCount.value === 0)
      || (tab === 'smart-event' && !smartEventAvailable.value)
      || (tab === 'device-control' && !deviceControlAvailable.value)
    )
    if (unavailable) emit('tab-change', 'files')
  },
  { immediate: true }
)

const handleTabChange = (tab) => {
  emit('tab-change', tab)
}

const handleBoardXmlChange = (xml) => {
  emit('board-xml-change', xml)
}

const handleBoardSelectionChange = (selection) => {
  emit('board-selection-change', selection)
}

const handleBoardSnapshotConfirm = (snapshot) => {
  emit('board-snapshot-confirm', snapshot)
}

</script>

<style scoped>
.viz-wrapper {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
  background: #f8fafc;
  border-left: 1px solid #edf1f7;
}

.viz-wrapper.full-bleed-resource-panel {
  background: transparent;
  border-left: 0;
}

.right-panel-tabs {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  padding: 8px;
  background: #f8fafc;
  border-bottom: 1px solid #edf1f7;
  overflow-x: auto;
}

.tab-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 72px;
  min-height: 34px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #526173;
  transition: color 0.16s ease, background 0.16s ease, border-color 0.16s ease;
  white-space: nowrap;
}

.tab-btn:hover {
  color: #1976D2;
  background: #eef4fb;
}

.tab-btn:disabled { cursor: not-allowed; opacity: .4; }
.tab-btn:disabled:hover { color: #526173; background: transparent; }

.tab-btn.active {
  color: #1976D2;
  border-color: #d8e9fb;
  background: #fff;
  font-weight: 500;
}

.tab-icon {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: 0 0 auto;
}

.tab-count {
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: #edf3fb;
  color: #526173;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.tab-btn.active .tab-count {
  background: #e3f2fd;
  color: #1976D2;
}

.panel-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 右侧面板容器无 16px 内边距，取消智能事件详情页的全出血负边距 */
.panel-content :deep(.smart-event-center.detail-mode) {
  width: 100%;
  height: 100%;
  margin: 0;
}
</style>
