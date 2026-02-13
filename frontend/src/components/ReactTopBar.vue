<template>
  <div class="react-topbar">
    <div class="left">
      <h1>风清气智Agent</h1>
    </div>



    <div class="right">
      <button
        class="action-button"
        :class="{ active: debugMode }"
        @click="$emit('toggle-debug')"
        :title="debugMode ? '关闭调试模式' : '开启调试模式（显示LLM上下文）'"
      >
        <span class="icon">🛠️</span>
        {{ debugMode ? '调试开启' : '调试关闭' }}
      </button>

      <div class="view-switch">
        <button
          class="view-btn"
          :class="{ active: isAnalysisActive }"
          @click="goAnalysis"
        >
          分析页面
        </button>
        <button
          class="view-btn"
          :class="{ active: isFetchersActive }"
          @click="goFetchers"
        >
          Fetchers管理
        </button>
      </div>

      <button
        v-if="hasResults || isComplete"
        class="action-button"
        @click="$emit('restart')"
        title="清空对话，开始新分析"
      >
        <span class="icon">🔄</span>
        重新开始
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

defineProps({
  isAnalyzing: { type: Boolean, default: false },
  isComplete: { type: Boolean, default: false },
  hasResults: { type: Boolean, default: false },
  debugMode: { type: Boolean, default: false },
  iterations: { type: Number, default: 0 },
  maxIterations: { type: Number, default: 10 }
})

defineEmits(['toggle-debug', 'restart'])

const router = useRouter()
const route = useRoute()

const isAnalysisActive = computed(() =>
  route.path === '/' || route.path.startsWith('/session') || route.path.startsWith('/classic')
)
const isFetchersActive = computed(() => route.path.startsWith('/fetchers'))

const goAnalysis = () => {
  if (!isAnalysisActive.value) router.push('/')
}

const goFetchers = () => {
  if (!isFetchersActive.value) router.push('/fetchers')
}
</script>

<style lang="scss" scoped>
.react-topbar {
  height: 60px;
  background: white;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  flex-shrink: 0;
}

.left h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
  font-family: 'STKaiti', 'KaiTi', 'FZYaoti', 'SimHei', 'Microsoft YaHei', serif;
  letter-spacing: 2px;
  position: relative;
  padding-left: 12px;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 4px;
    height: 70%;
    background: linear-gradient(180deg, rgba(0,0,0,0.8), rgba(0,0,0,0));
    border-radius: 2px;
  }

  text-shadow:
    1px 1px 0 rgba(0, 0, 0, 0.25),
    -1px -1px 0 rgba(255, 255, 255, 0.3);
}



.right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.action-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: white;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;

  .icon {
    font-size: 14px;
  }

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
  }

  &.active {
    border-color: #ff9800;
    color: #f57c00;
  }
}

.view-switch {
  display: inline-flex;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  border: none;
  background: transparent;
  padding: 6px 12px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
  border-left: 1px solid #e0e0e0;

  &:first-child {
    border-left: none;
  }

  &.active {
    background: #1976d2;
    color: #fff;
    border-color: #1976d2;
  }
}


</style>
