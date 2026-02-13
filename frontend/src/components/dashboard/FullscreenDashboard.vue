<template>
  <Teleport to="body">
    <div class="fullscreen-dashboard" :class="{ active: visible }">
      <div class="dashboard-header">
        <h1 class="dashboard-title">
          <span class="title-icon"></span>
          {{ dashboardTitle }}
        </h1>

        <!-- 多专家模式标签页切换 -->
        <div v-if="isMultiExpertMode" class="expert-tabs">
          <button
            v-for="tab in expertTabs"
            :key="tab.id"
            class="expert-tab"
            :class="{ active: activeExpertTab === tab.id }"
            @click="activeExpertTab = tab.id"
          >
            <span class="tab-icon">{{ tab.icon }}</span>
            <span class="tab-name">{{ tab.name }}</span>
            <span class="tab-count" v-if="getExpertVizCount(tab.id)">{{ getExpertVizCount(tab.id) }}</span>
          </button>
        </div>

        <div class="header-actions">
          <button class="exit-btn" @click="$emit('close')" title="退出大屏">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
            退出大屏
          </button>
        </div>
      </div>

      <div class="dashboard-body">
        <!-- 多专家模式：按标签页切换 -->
        <template v-if="isMultiExpertMode">
          <WeatherDashboard
            v-show="activeExpertTab === 'weather'"
            :visualizations="weatherVisualizations"
            :expert-results="expertResults"
            :query-city="queryCity"
          />
          <ComponentDashboard
            v-show="activeExpertTab === 'component'"
            :visualizations="componentVisualizations"
            :expert-results="expertResults"
          />
        </template>

        <!-- 单专家模式 -->
        <template v-else>
          <WeatherDashboard
            v-if="assistantMode === 'meteorology-expert'"
            :visualizations="visualizations"
            :expert-results="expertResults"
            :query-city="queryCity"
          />
          <ComponentDashboard
            v-else
            :visualizations="visualizations"
            :expert-results="expertResults"
          />
        </template>
      </div>

      <div class="dashboard-footer">
        <span class="footer-text">风清气智 - 大气污染溯源分析系统</span>
        <span class="footer-time">{{ currentTime }}</span>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useReactStore } from '@/stores/reactStore'
import WeatherDashboard from './WeatherDashboard.vue'
import ComponentDashboard from './ComponentDashboard.vue'

const store = useReactStore()

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  expertResults: {
    type: Object,
    default: null
  },
  queryCity: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close'])

const currentTime = ref('')
const activeExpertTab = ref('weather')
let timeInterval = null

// 多专家标签页配置
const expertTabs = [
  { id: 'weather', name: '气象分析', icon: '🌤️' },
  { id: 'component', name: '组分分析', icon: '🧪' }
]

// 判断是否为多专家模式
const isMultiExpertMode = computed(() => {
  return props.assistantMode === 'quick-tracing-expert' ||
         (props.expertResults?.expert_results && Object.keys(props.expertResults.expert_results).length > 0)
})

// 大屏标题
const dashboardTitle = computed(() => {
  if (isMultiExpertMode.value) {
    return '快速溯源分析大屏'
  }
  const titleMap = {
    'meteorology-expert': '气象分析专家大屏',
    'data-visualization-expert': '组分分析大屏'
  }
  return titleMap[props.assistantMode] || '综合分析大屏'
})

// 直接使用 store 中已分组的数据（优化：避免重复过滤）
const weatherVisualizations = computed(() => store.groupedVisualizations.weather || [])
const componentVisualizations = computed(() => store.groupedVisualizations.component || [])

// 单专家模式使用的可视化数据（根据assistantMode选择对应分组）
const visualizations = computed(() => {
  if (props.assistantMode === 'meteorology-expert') {
    return weatherVisualizations.value
  }
  return componentVisualizations.value
})

// 获取专家可视化数量
function getExpertVizCount(expertType) {
  return store.groupedVisualizations[expertType]?.length || 0
}

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// ESC键退出大屏
const handleKeydown = (event) => {
  if (event.key === 'Escape' && props.visible) {
    emit('close')
  }
}

// 处理设置激活专家标签页的事件
const handleSetActiveExpertTab = (event) => {
  const expertType = event.detail
  if (expertType && ['weather', 'component'].includes(expertType)) {
    activeExpertTab.value = expertType
  }
}

onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
  document.addEventListener('keydown', handleKeydown)
  window.addEventListener('setActiveExpertTab', handleSetActiveExpertTab)

  // 检查是否有存储的激活标签页
  const storedTab = localStorage.getItem('activeExpertTab')
  if (storedTab && ['weather', 'component'].includes(storedTab)) {
    activeExpertTab.value = storedTab
  }
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('setActiveExpertTab', handleSetActiveExpertTab)
})
</script>

<style lang="scss" scoped>
.fullscreen-dashboard {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: #ffffff;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.3s, visibility 0.3s;

  &.active {
    opacity: 1;
    visibility: visible;
  }
}

.dashboard-header {
  height: 60px;
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
  position: relative;
  z-index: 1;
}

.dashboard-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #1a73e8;
  display: flex;
  align-items: center;
  gap: 12px;
  letter-spacing: 2px;
}

.title-icon {
  width: 32px;
  height: 32px;
  background: radial-gradient(circle, #1a73e8 0%, transparent 70%);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.1); }
}

// 专家标签页样式
.expert-tabs {
  display: flex;
  gap: 8px;
  padding: 4px;
  background: #e8eaed;
  border-radius: 8px;
}

.expert-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.5);
    color: #333;
  }

  &.active {
    background: #1a73e8;
    color: #fff;
    box-shadow: 0 2px 4px rgba(26, 115, 232, 0.3);
  }

  .tab-icon {
    font-size: 18px;
  }

  .tab-count {
    padding: 2px 8px;
    background: rgba(255, 255, 255, 0.3);
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
  }

  &.active .tab-count {
    background: rgba(255, 255, 255, 0.3);
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.exit-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #f0f0f0;
  border: 1px solid #ddd;
  border-radius: 6px;
  color: #333;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #ffe5e5;
    border-color: #ff6b6b;
    color: #d32f2f;
  }
}

.dashboard-body {
  flex: 1;
  padding: 20px;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.dashboard-footer {
  height: 40px;
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8f9fa;
  border-top: 1px solid #e0e0e0;
  position: relative;
  z-index: 1;
}

.footer-text, .footer-time {
  font-size: 12px;
  color: #666;
}
</style>
