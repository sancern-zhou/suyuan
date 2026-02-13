<template>
  <div class="analysis-view">
    <!-- 顶部导航 -->
    <TopBar
      :status="store.status"
      :debug-enabled="store.debugEnabled"
      :has-report="store.hasReport"
      @toggle-debug="store.toggleDebug"
      @open-report="store.openReport"
    />

    <!-- 主布局 -->
    <div class="main-layout">
      <!-- 对话区域 -->
      <div class="chat-area">
        <MessageList
          :messages="store.messages"
          :is-analyzing="store.isAnalyzing"
          :debug-enabled="store.debugEnabled"
        />

        <!-- 输入框 -->
        <InputBox
          v-model="store.input"
          :disabled="!store.isAnalyzing"
          :is-analyzing="store.isAnalyzing"
          @send="handleSend"
          @pause="handlePause"
        />
      </div>

      <!-- 可视化面板 -->
      <VisualizationPanel
        :content="store.currentVisualization"
      />

      <!-- 调试面板 -->
      <DebugPanel
        v-if="store.debugEnabled"
        :context="store.currentContext"
        :tool-calls="store.toolCalls"
        @close="store.toggleDebug"
      />
    </div>
  </div>
</template>

<script setup>
import { useAnalysisStore } from '@/stores/analysis'
import TopBar from '@/components/TopBar.vue'
import MessageList from '@/components/MessageList.vue'
import InputBox from '@/components/InputBox.vue'
import VisualizationPanel from '@/components/VisualizationPanel.vue'
import DebugPanel from '@/components/DebugPanel.vue'

const store = useAnalysisStore()

const handleSend = async (query) => {
  if (!query.trim()) return

  await store.startAnalysis(query)
}

const handlePause = async () => {
  await store.pauseAnalysis()
}
</script>

<style lang="scss" scoped>
.analysis-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}

.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  border-right: 1px solid #f0f0f0;
}
</style>
