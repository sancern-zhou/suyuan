<template>
  <div v-if="visible" class="viz-wrapper" :style="panelStyle">
    <!-- 报告生成专家 -->
    <ReportGenerationPanel
      v-if="assistantMode === 'report-generation-expert'"
      :assistant-mode="assistantMode"
    />

    <!-- 其他模式：可视化面板 + Office文档预览面板 -->
    <template v-else>
      <!-- 标签页切换按钮 -->
      <div v-if="showTabs" class="right-panel-tabs">
        <button
          :class="['tab-btn', { active: activeTab === 'visualization' }]"
          @click="handleTabChange('visualization')"
        >
          可视化
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'document' }]"
          @click="handleTabChange('document')"
        >
          文档预览
        </button>
      </div>

      <!-- 可视化面板 -->
      <VisualizationPanel
        v-show="activeTab === 'visualization'"
        ref="vizPanelRef"
        :content="visualizationContent"
        :history="messages"
        :selected-message-id="selectedMessageId"
        :assistant-mode="assistantMode"
        :expert-results="expertResults"
      />

      <!-- Office文档预览面板 -->
      <OfficeDocumentPanel
        v-show="activeTab === 'document'"
        ref="officePanelRef"
        :history="messages"
        :session-id="sessionId"
        @submit-edit="handleOfficeEditSubmit"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import VisualizationPanel from '@/components/VisualizationPanel.vue'
import OfficeDocumentPanel from '@/components/OfficeDocumentPanel.vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'

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
  }
})

const emit = defineEmits([
  'tab-change',
  'office-edit-submit'
])

const vizPanelRef = ref(null)
const officePanelRef = ref(null)

const showTabs = computed(() => {
  return props.vizPanelVisible && props.officePanelVisible
})

const handleTabChange = (tab) => {
  emit('tab-change', tab)
}

const handleOfficeEditSubmit = async (editData) => {
  emit('office-edit-submit', editData)
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
  background: white;
  border-left: 1px solid #e8e8e8;
}

.right-panel-tabs {
  display: flex;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
}

.tab-btn {
  flex: 1;
  padding: 12px 16px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  transition: all 0.3s;
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: #1890ff;
  background: #f0f0f0;
}

.tab-btn.active {
  color: #1890ff;
  border-bottom-color: #1890ff;
  background: white;
  font-weight: 500;
}
</style>
