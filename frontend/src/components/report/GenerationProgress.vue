<template>
  <div class="generation-progress">
    <div class="progress-header">
      <h4>报告生成进度</h4>
      <span class="current-phase">{{ currentPhase }}</span>
    </div>

    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: progress + '%' }"></div>
    </div>

    <div class="events-list">
      <div
        v-for="(event, index) in events"
        :key="index"
        class="event-item"
        :class="{ completed: event.completed }"
      >
        <span class="event-phase">{{ event.phase }}</span>
        <span class="event-status">{{ event.status }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  progress: {
    type: Number,
    default: 0
  },
  currentPhase: {
    type: String,
    default: ''
  },
  events: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped>
.generation-progress {
  background: var(--bg-container);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--border-2);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-header h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-1);
}

.current-phase {
  font-size: 12px;
  color: var(--text-2);
  background: var(--border-1);
  padding: 4px 8px;
  border-radius: 4px;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--border-1);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 16px;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-muted);
  border-radius: 4px;
  font-size: 12px;
}

.event-item.completed {
  background: var(--color-success-bg);
}

.event-phase {
  color: var(--text-1);
  font-weight: 500;
}

.event-status {
  color: var(--text-2);
}
</style>
