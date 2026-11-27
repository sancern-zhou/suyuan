<template>
  <section class="broadcast-ticker" aria-label="定时任务播报">
    <span class="ticker-label"><i aria-hidden="true"></i>任务播报</span>
    <div class="ticker-viewport" v-if="items.length">
      <TransitionGroup name="ticker" tag="div" class="ticker-track">
        <span
          v-for="item in items"
          :key="`${item.time}-${item.task_name}`"
          class="ticker-item"
        >
          <small>{{ formatDateTime(item.time).slice(5, 16) }}</small>
          <strong>[{{ item.task_name }}<template v-if="item.station_name"> · {{ item.station_name }}</template>]</strong>
          {{ item.text }}
        </span>
      </TransitionGroup>
    </div>
    <div v-else class="ticker-viewport"><span class="ticker-item muted">暂无播报</span></div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatDateTime } from './aqiLevels.js'

const props = defineProps({
  items: { type: Array, default: () => [] }
})

const cursor = ref(0)
let timer = null
const visibleCount = 2

const items = computed(() => {
  if (props.items.length <= visibleCount) return props.items
  // 窗口轮转：每次翻动一格，形成走马灯
  const window = []
  for (let index = 0; index < visibleCount; index += 1) {
    window.push(props.items[(cursor.value + index) % props.items.length])
  }
  return window
})

onMounted(() => {
  timer = setInterval(() => {
    if (props.items.length > visibleCount) {
      cursor.value = (cursor.value + 1) % props.items.length
    }
  }, 8000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style lang="scss" scoped>
.broadcast-ticker {
  display: flex;
  align-items: center;
  gap: 14px;
  height: 44px;
  padding: 0 20px;
  border: 1px solid rgba(63, 200, 212, 0.18);
  border-radius: 8px;
  background: rgba(7, 41, 59, 0.55);
  overflow: hidden;
}

.ticker-label {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  color: #3fc8d4;
  font-size: 13px;
  letter-spacing: 2px;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #3fc8d4;
    box-shadow: 0 0 8px #3fc8d4;
    animation: blink 2s ease-in-out infinite;
  }
}

.ticker-viewport {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.ticker-track {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ticker-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
  color: #c9dfe6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  small { color: #6f95a3; font-size: 12px; }
  strong { color: #3fc8d4; font-weight: 600; }
  &.muted { color: #6f95a3; }
}

.ticker-enter-active,
.ticker-leave-active {
  transition: all 0.6s ease;
}
.ticker-enter-from {
  opacity: 0;
  transform: translateY(14px);
}
.ticker-leave-to {
  opacity: 0;
  transform: translateY(-14px);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
</style>
