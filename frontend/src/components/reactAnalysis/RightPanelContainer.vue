<template>
  <div v-if="visible" class="viz-wrapper" :style="panelStyle">
    <!-- 报告生成专家 -->
    <template v-if="assistantMode === 'report-generation-expert'">
      <div class="right-panel-tabs">
        <button
          :class="['tab-btn', { active: activeTab !== 'files' }]"
          @click="handleTabChange('document')"
        >
          <span>报告</span>
          <span v-if="documentCount > 0" class="tab-count">{{ documentCount }}</span>
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'files' }]"
          @click="handleTabChange('files')"
        >
          <span>文件产物</span>
          <span v-if="fileProductCount > 0" class="tab-count">{{ fileProductCount }}</span>
        </button>
      </div>
      <ResourceProductsPanel
        v-if="activeTab === 'files' && sessionId"
        class="panel-content"
        @open-resource-tab="handleTabChange"
      />
      <ReportGenerationPanel
        v-else
        :assistant-mode="assistantMode"
      />
    </template>

    <!-- 其他模式：可视化面板 + Office文档预览面板 + 知识溯源面板 -->
    <template v-else>
      <!-- 标签页切换按钮 -->
      <div v-if="showTabs" class="right-panel-tabs" role="tablist" aria-label="右侧资源面板">
        <button
          :class="['tab-btn', { active: activeTab === 'visualization' }]"
          role="tab"
          :aria-selected="activeTab === 'visualization'"
          :disabled="!visualizationAvailable"
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
          :class="['tab-btn', { active: activeTab === 'document' }]"
          role="tab"
          :aria-selected="activeTab === 'document'"
          :disabled="!documentAvailable"
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
          :class="['tab-btn', { active: activeTab === 'knowledge' }]"
          role="tab"
          :aria-selected="activeTab === 'knowledge'"
          :disabled="knowledgeCount === 0"
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
          v-if="sessionId"
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
import { useSessionResourceStore } from '@/stores/sessionResourceStore.js'
import { summarizeRightPanelResources } from '@/components/resources/rightPanelResources.js'
import { buildResourceGroups, targetTab } from '@/services/resourceGroups.js'

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
  }
})

const emit = defineEmits([
  'tab-change',
  'board-xml-change',
  'board-selection-change',
  'board-snapshot-confirm',
  'board-version-restore'
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
const showBoardTab = computed(() => resourceSummary.value.counts.board > 0)
const explicitTarget = computed(() => {
  const state = resourceStore.activeSessionState
  if (state?.selectionOrigin !== 'explicit' || resourceStore.activeSessionId !== props.sessionId) return ''
  const selected = resourceStore.selectedResource(props.sessionId)
  const group = buildResourceGroups(state.resources || []).find(item => item.group_id === selected?.group_id)
  return group ? targetTab(group) : ''
})

const showTabs = computed(() => {
  // 只要有任意一个面板可见，就显示标签页切换按钮
  return props.sessionId || resourceSummary.value.hasArtifacts || props.knowledgePanelVisible || showBoardTab.value
})

const fileProductCount = computed(() => resourceSummary.value.counts.files)
const visualizationCount = computed(() => resourceSummary.value.counts.visualization)
const documentCount = computed(() => resourceSummary.value.counts.document)
const visualizationAvailable = computed(() => visualizationCount.value > 0 || explicitTarget.value === 'visualization')
const documentAvailable = computed(() => documentCount.value > 0 || explicitTarget.value === 'document')

const knowledgeCount = computed(() => props.knowledgeSources?.length || 0)

watch(
  () => [props.assistantMode, props.activeTab, visualizationAvailable.value, documentAvailable.value, knowledgeCount.value, showBoardTab.value],
  ([mode, tab, visualizations, documents, knowledge, board]) => {
    if (mode === 'report-generation-expert') return
    const unavailable = (
      (tab === 'visualization' && !visualizations)
      || (tab === 'document' && !documents)
      || (tab === 'knowledge' && knowledge === 0)
      || (tab === 'board' && !board)
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

const handleBoardVersionRestore = (versionId) => {
  emit('board-version-restore', versionId)
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
</style>
