<template>
  <div
    v-if="visible"
    :class="['viz-wrapper', { 'full-bleed-resource-panel': fullBleedVisualizationPanel }]"
    :style="resolvedPanelStyle"
  >
    <!-- 报告生成专家 -->
    <template v-if="assistantMode === 'report-generation-expert'">
      <div class="right-panel-tabs" role="tablist" aria-label="报告资源面板">
        <button
          v-if="documentCount > 0"
          :class="['tab-btn', { active: activeTab === 'document' }]"
          role="tab"
          :aria-selected="activeTab === 'document'"
          @click="handleTabChange('document')"
        >
          <span>报告</span>
          <span v-if="documentCount > 0" class="tab-count">{{ documentCount }}</span>
        </button>
        <button
          v-if="fileProductCount > 0"
          :class="['tab-btn', { active: activeTab === 'files' }]"
          role="tab"
          :aria-selected="activeTab === 'files'"
          @click="handleTabChange('files')"
        >
          <span>文件产物</span>
          <span v-if="fileProductCount > 0" class="tab-count">{{ fileProductCount }}</span>
        </button>
        <button
          v-if="workflowAvailable"
          :class="['tab-btn', { active: activeTab === 'workflow' }]"
          @click="handleTabChange('workflow')"
        >
          <span>工作流</span>
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
      </div>
      <ResourceProductsPanel
        v-if="activeTab === 'files' && sessionId"
        class="panel-content"
        @open-resource-tab="handleTabChange"
      />
      <WorkflowPanel
        v-if="activeTab === 'workflow' && sessionId"
        class="panel-content"
        :session-id="sessionId"
      />
      <ReportGenerationPanel
        v-else-if="!['feedback', 'workflow'].includes(activeTab)"
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
          v-if="workflowAvailable"
          :class="['tab-btn', { active: activeTab === 'workflow' }]"
          role="tab"
          :aria-selected="activeTab === 'workflow'"
          @click="handleTabChange('workflow')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h5v5H5zM14 14h5v5h-5z"/><path d="M10 7.5h4M16.5 10v4"/></svg>
          <span>工作流</span>
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
          v-if="workOrderReviewAvailable"
          :class="['tab-btn', { active: activeTab === 'work-order-review' }]"
          role="tab"
          :aria-selected="activeTab === 'work-order-review'"
          @click="handleTabChange('work-order-review')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 4.5h6v3H9v-3Z" />
            <path d="M9 6H6.5A1.5 1.5 0 0 0 5 7.5v12A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-12A1.5 1.5 0 0 0 17.5 6H15" />
            <path d="M9 13.5l2 2 4-4" />
          </svg>
          <span>工单审核</span>
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

      <WorkflowPanel
        v-if="activeTab === 'workflow' && sessionId"
        class="panel-content"
        :session-id="sessionId"
      />

      <HumanFeedbackPanel
        v-if="activeTab === 'feedback'"
        class="panel-content"
        :feedback="humanFeedback"
        :submitting="humanFeedbackSubmitting"
        :error="humanFeedbackError"
        @submit="$emit('submit-human-feedback', $event)"
      />

      <!-- 智能事件中心：右侧 tab 只保留事件列表与事件详情两个页面；
           任务执行记录工作区统一走整页管理面板（open-smart-event-task） -->
      <SmartEventCenterPanel
        v-if="activeTab === 'smart-event'"
        :category="smartEventCategory"
        class="panel-content"
        :workspace-command="smartEventCommand"
        @close="$emit('close-smart-event-panel')"
        @open-task="$emit('open-smart-event-task', $event)"
      />

      <!-- 故障工单审核工作区：证据包拆分数据 + AI 研判 + 人工反馈/归档/退回 -->
      <WorkOrderReviewCenterPanel
        v-else-if="activeTab === 'work-order-review'"
        class="panel-content"
        :workspace-command="workOrderReviewCommand"
        @close="$emit('close-work-order-review-panel')"
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
import { onBeforeUnmount, onMounted, ref, computed, watch } from 'vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'
import KnowledgeSourcePanel from '@/components/visualization/panels/KnowledgeSourcePanel.vue'
import ResourceProductsPanel from '@/components/resources/ResourceProductsPanel.vue'
import ResourcePreviewHost from '@/components/resources/ResourcePreviewHost.vue'
import VisualizationGallery from '@/components/resources/VisualizationGallery.vue'
import HumanFeedbackPanel from './HumanFeedbackPanel.vue'
import DeviceControlProcessPanel from '@/components/management/DeviceControlProcessPanel.vue'
import SmartEventCenterPanel from '@/components/management/SmartEventCenterPanel.vue'
import WorkOrderReviewCenterPanel from '@/components/management/WorkOrderReviewCenterPanel.vue'
import WorkflowPanel from '@/components/workflow/WorkflowPanel.vue'
import { projectConfig } from '@/config/projectConfig.js'
import { listSessionWorkflows } from '@/services/workflowApi.js'
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
  workOrderReviewCommand: {
    type: Object,
    default: null
  },
  deviceControlCommand: {
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
  'open-smart-event-task',
  'close-smart-event-panel',
  'close-work-order-review-panel',
  'close-device-control-panel'
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
// 工单审核工作台：按需显示 —— Agent 工作区命令打开（ui_command），或用户从侧边栏
// 入口显式进入（此时 activeTab 即为 work-order-review）；不再按 ops 模式常驻占用标签栏。
const workOrderReviewAvailable = computed(() => (
  projectConfig.project === 'jiangsu-ops' &&
  (Boolean(props.workOrderReviewCommand) || props.activeTab === 'work-order-review')
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
  return workflowAvailable.value || visualizationAvailable.value || documentAvailable.value || fileProductCount.value > 0 || knowledgeCount.value > 0 || props.knowledgePanelVisible || showBoardTab.value || feedbackAvailable.value || smartEventAvailable.value || workOrderReviewAvailable.value || deviceControlAvailable.value
})

const fileProductCount = computed(() => resourceSummary.value.counts.files)
const visualizationCount = computed(() => resourceSummary.value.counts.visualization)
const documentCount = computed(() => resourceSummary.value.counts.document)
const visualizationAvailable = computed(() => visualizationCount.value > 0 || explicitTarget.value === 'visualization')
const documentAvailable = computed(() => documentCount.value > 0 || explicitTarget.value === 'document')
// 工作流 TAB 跟随会话实际数据：探测到工作流才显示。工作流由后端异步创建，
// 面板打开期间 15s 轮询一次，保证会话中途新起的工作流能及时出现。
const sessionWorkflowCount = ref(0)
const workflowProbed = ref(false)
let workflowProbeTimer = null
let workflowProbeToken = 0

async function probeSessionWorkflows() {
  const token = ++workflowProbeToken
  const sessionId = props.sessionId
  if (!sessionId) {
    sessionWorkflowCount.value = 0
    workflowProbed.value = true
    return
  }
  try {
    const payload = await listSessionWorkflows(sessionId)
    if (token !== workflowProbeToken) return
    sessionWorkflowCount.value = Array.isArray(payload?.workflows) ? payload.workflows.length : 0
    workflowProbed.value = true
  } catch {
    // 探测失败保留上次结果，避免 TAB 显隐因瞬时错误抖动
  }
}

watch(() => props.sessionId, () => {
  workflowProbed.value = false
  probeSessionWorkflows()
})

onMounted(() => {
  probeSessionWorkflows()
  workflowProbeTimer = setInterval(probeSessionWorkflows, 15000)
})

onBeforeUnmount(() => {
  if (workflowProbeTimer) clearInterval(workflowProbeTimer)
  workflowProbeTimer = null
})

const workflowAvailable = computed(() => Boolean(props.sessionId) && sessionWorkflowCount.value > 0)

const knowledgeCount = computed(() => props.knowledgeSources?.length || 0)
const feedbackCount = computed(() => props.humanFeedback?.items?.length || 0)
const feedbackAvailable = computed(() => feedbackCount.value > 0)

watch(
  () => [props.assistantMode, props.activeTab, visualizationAvailable.value, documentAvailable.value, knowledgeCount.value, showBoardTab.value, feedbackAvailable.value, workflowAvailable.value, workflowProbed.value],
  ([mode, tab, visualizations, documents, knowledge, board, feedback, workflow, workflowSettled]) => {
    if (mode === 'report-generation-expert') return
    const unavailable = (
      (tab === 'visualization' && !visualizations)
      || (tab === 'document' && !documents)
      || (tab === 'knowledge' && knowledge === 0)
      || (tab === 'board' && !board)
      || (tab === 'feedback' && !feedback)
      || (tab === 'files' && fileProductCount.value === 0)
      || (tab === 'smart-event' && !smartEventAvailable.value)
      || (tab === 'work-order-review' && !workOrderReviewAvailable.value)
      || (tab === 'device-control' && !deviceControlAvailable.value)
      || (tab === 'workflow' && workflowSettled && !workflow)
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
  background: var(--bg-muted);
  border-left: 1px solid var(--border-2);
}

.viz-wrapper.full-bleed-resource-panel {
  background: transparent;
  border-left: 0;
}

.right-panel-tabs {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-1);
  padding: var(--space-2);
  background: var(--bg-container);
  border-bottom: 1px solid var(--border-1);
  overflow-x: auto;
}

/* 卡片式标签（§6.5）：默认 --bg-muted 底 --text-2 字，选中白底 + --color-primary 字 + --border-2 描边 */
.tab-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 72px;
  height: var(--control-h-md);
  padding: 0 var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--bg-muted);
  cursor: pointer;
  font-family: inherit;
  font-size: var(--text-size-sm);
  color: var(--text-2);
  transition: color var(--transition-base), background var(--transition-base),
    border-color var(--transition-base), box-shadow var(--transition-base);
  white-space: nowrap;
}

.tab-btn:hover:not(:disabled) {
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.tab-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.tab-btn:disabled { cursor: not-allowed; color: var(--text-disabled); }
.tab-btn:disabled:hover { background: var(--bg-muted); }

.tab-btn.active,
.tab-btn.active:hover:not(:disabled) {
  color: var(--color-primary);
  border-color: var(--border-2);
  background: var(--bg-container);
  box-shadow: var(--shadow-1);
  font-weight: var(--font-weight-medium);
}

.tab-btn.active:focus-visible {
  box-shadow: var(--shadow-1), 0 0 0 3px var(--color-primary-ring);
}

.tab-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: 0 0 auto;
}

.tab-count {
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-container);
  color: var(--text-2);
  font-size: var(--text-size-xs);
  line-height: 18px;
  text-align: center;
}

.tab-btn:hover:not(:disabled) .tab-count {
  background: var(--color-primary-bg-hover);
  color: var(--color-primary);
}

.tab-btn.active .tab-count {
  background: var(--color-primary-bg);
  color: var(--color-primary);
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
