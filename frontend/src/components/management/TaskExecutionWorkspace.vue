<template>
  <section class="task-workspace">
    <header class="workspace-header">
      <div>
        <h2>{{ task?.workspace_entry?.title || task?.name || '告警溯源' }}</h2>
        <p class="workspace-description">按执行日期查看分析结论、报告与文件产物</p>
      </div>
      <button v-if="showBackButton" type="button" class="back-button" @click="$emit('close')">返回</button>
    </header>

    <ScheduledTaskResultsView
      ref="resultsViewRef"
      :task="task"
      @restore-execution-session="$emit('restore-execution-session', $event)"
    />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import ScheduledTaskResultsView from './ScheduledTaskResultsView.vue'

defineProps({
  task: { type: Object, default: null },
  // 嵌入右侧面板时显示“返回”按钮，整页管理面板模式保持原有展示
  showBackButton: { type: Boolean, default: false }
})
defineEmits(['close', 'restore-execution-session'])

const resultsViewRef = ref(null)
</script>

<style scoped>
.task-workspace { height: 100%; overflow: auto; padding: 28px; background: var(--bg-muted); }
.workspace-header { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.back-button { flex: none; align-self: flex-start; min-height: 30px; border: 1px solid var(--border-2); border-radius: 6px; background: var(--bg-container); color: var(--text-1); cursor: pointer; padding: 4px 12px; font-size: 12px; }
.back-button:hover { border-color: var(--color-primary); color: var(--color-primary); }
h2 { margin: 4px 0; font-size: 22px; color: #17223b; }
.workspace-description { margin: 0; color: var(--text-2); }
@media (max-width: 700px) { .task-workspace { padding: 18px; } }
</style>
