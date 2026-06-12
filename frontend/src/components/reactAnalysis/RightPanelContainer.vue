<template>
  <div v-if="visible" class="viz-wrapper" :style="panelStyle">
    <!-- 报告生成专家 -->
    <ReportGenerationPanel
      v-if="assistantMode === 'report-generation-expert'"
      :assistant-mode="assistantMode"
    />

    <!-- 其他模式：可视化面板 + Office文档预览面板 + 知识溯源面板 -->
    <template v-else>
      <!-- 标签页切换按钮 -->
      <div v-if="showTabs" class="right-panel-tabs">
        <button
          :class="['tab-btn', { active: activeTab === 'visualization' }]"
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
          @click="handleTabChange('document')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 3.5h8l4 4v13H6v-17Z" />
            <path d="M14 3.5v4h4" />
            <path d="M9 12h6" />
            <path d="M9 15.5h5" />
          </svg>
          <span>文档</span>
          <span v-if="documentCount > 0" class="tab-count">{{ documentCount }}</span>
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'knowledge' }]"
          @click="handleTabChange('knowledge')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 5.5C5 4.67 5.67 4 6.5 4h11c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5v-13Z" />
            <path d="M8 8h8" />
            <path d="M8 11.5h8" />
            <path d="M8 15h5" />
          </svg>
          <span>溯源</span>
          <span v-if="knowledgeCount > 0" class="tab-count">{{ knowledgeCount }}</span>
        </button>
        <button
          v-if="showBoardTab"
          :class="['tab-btn', { active: activeTab === 'board' }]"
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

      <!-- 可视化面板 -->
      <VisualizationPanel
        v-if="activeTab === 'visualization'"
        ref="vizPanelRef"
        key="visualization-panel"
        class="panel-content"
        :content="visualizationContent"
        :history="messages"
        :selected-message-id="selectedMessageId"
        :assistant-mode="assistantMode"
        :expert-results="expertResults"
      />

      <!-- Office文档预览面板（包含 PDF/Markdown/HTML） -->
      <OfficeDocumentPanel
        v-if="activeTab === 'document'"
        ref="officePanelRef"
        key="document-panel"
        class="panel-content"
        :history="messages"
        :session-id="sessionId"
        @submit-edit="handleOfficeEditSubmit"
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

      <!-- Draw.io画板面板 -->
      <DrawioBoardPanel
        v-if="showBoardTab && activeTab === 'board'"
        ref="boardPanelRef"
        key="board-panel"
        class="panel-content"
        :xml="board?.currentXml || board?.current_xml || board?.xml || ''"
        :title="board?.title || '画板'"
        @xml-change="handleBoardXmlChange"
        @selection-change="handleBoardSelectionChange"
        @board-snapshot-confirm="handleBoardSnapshotConfirm"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import VisualizationPanel from '@/components/VisualizationPanel.vue'
import OfficeDocumentPanel from '@/components/OfficeDocumentPanel.vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'
import KnowledgeSourcePanel from '@/components/visualization/panels/KnowledgeSourcePanel.vue'
import DrawioBoardPanel from '@/components/board/DrawioBoardPanel.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  vizPanelVisible: {
    type: Boolean,
    default: false
  },
  officePanelVisible: {
    type: Boolean,
    default: false
  },
  knowledgePanelVisible: {
    type: Boolean,
    default: false
  },
  boardPanelVisible: {
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
  visualizationContent: {
    type: Object,
    default: null
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
  'office-edit-submit',
  'board-xml-change',
  'board-selection-change',
  'board-snapshot-confirm'
])

// 添加调试
watch(() => props.activeTab, (newVal) => {
  console.log('[RightPanelContainer] activeTab changed to:', newVal)
})

watch(() => props.visible, (newVal) => {
  console.log('[RightPanelContainer] visible changed to:', newVal)
})

const vizPanelRef = ref(null)
const officePanelRef = ref(null)
const knowledgePanelRef = ref(null)
const boardPanelRef = ref(null)

const hasBoardXml = computed(() => !!(
  props.board?.currentXml ||
  props.board?.current_xml ||
  props.board?.xml
))
const showBoardTab = computed(() => props.boardPanelVisible || hasBoardXml.value)

const showTabs = computed(() => {
  // 只要有任意一个面板可见，就显示标签页切换按钮
  return props.vizPanelVisible || props.officePanelVisible || props.knowledgePanelVisible || showBoardTab.value
})

const visualizationCount = computed(() => {
  const visuals = props.visualizationContent?.visuals
  if (Array.isArray(visuals)) return visuals.length
  if (props.visualizationContent) return 1
  return 0
})

const documentCount = computed(() => {
  const docs = new Set()
  for (const msg of props.messages || []) {
    const result = msg?.data?.result
    const data = result?.data || result
    const id = data?.pdf_id || data?.pdf_url || data?.html_url || data?.file_path || data?.markdown_content
    if (id) docs.add(String(id))
  }
  return docs.size
})

const knowledgeCount = computed(() => props.knowledgeSources?.length || 0)

const handleTabChange = (tab) => {
  emit('tab-change', tab)
}

const handleOfficeEditSubmit = async (editData) => {
  emit('office-edit-submit', editData)
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

// 公开方法
const cancelOfficeEdit = () => {
  if (officePanelRef.value && typeof officePanelRef.value.cancelEdit === 'function') {
    officePanelRef.value.cancelEdit()
  }
}

defineExpose({
  cancelOfficeEdit
})
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
}

.tab-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
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
