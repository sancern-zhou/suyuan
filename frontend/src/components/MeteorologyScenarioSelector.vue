<template>
  <div class="meteorology-scenario-selector">
    <div class="scenario-header">
      <h3>气象分析专家模式</h3>
      <p class="scenario-description">
        专注于气象条件分析，自动生成可视化图表<br />
        <span class="expert-type">单专家模式：专注气象 + 默认可视化</span>
      </p>
    </div>

    <div class="scenario-options">
      <div
        v-for="scenario in scenarios"
        :key="scenario.id"
        class="scenario-card"
        :class="{ active: selectedScenario === scenario.id }"
        @click="selectScenario(scenario.id)"
      >
        <div class="scenario-card-header">
          <div class="scenario-icon">{{ scenario.icon }}</div>
          <div class="scenario-title-group">
            <h4>{{ scenario.name }}</h4>
            <span class="scenario-badge" :class="scenario.badgeClass">{{ scenario.badge }}</span>
          </div>
        </div>

        <p class="scenario-detail">{{ scenario.description }}</p>

        <div class="scenario-tools">
          <div class="tools-label">核心工具：</div>
          <div class="tools-list">
            <span
              v-for="tool in scenario.tools.slice(0, 4)"
              :key="tool"
              class="tool-tag"
            >
              {{ tool }}
            </span>
            <span v-if="scenario.tools.length > 4" class="tool-tag-more">
              +{{ scenario.tools.length - 4 }}个
            </span>
          </div>
        </div>

        <div class="scenario-features">
          <div
            v-for="feature in scenario.features"
            :key="feature"
            class="feature-item"
          >
            <svg class="feature-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            <span>{{ feature }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="scenario-actions">
      <button
        @click="proceedWithScenario"
        :disabled="!selectedScenario"
        class="proceed-btn"
        :class="{ disabled: !selectedScenario }"
      >
        <svg v-if="!isLoading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14" />
          <path d="M12 5l7 7-7 7" />
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
        {{ isLoading ? '分析中...' : '开始分析' }}
      </button>

      <button @click="showAdvancedOptions = !showAdvancedOptions" class="advanced-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </svg>
        高级选项
      </button>
    </div>

    <div v-if="showAdvancedOptions" class="advanced-options">
      <h4>高级设置</h4>

      <div class="option-group">
        <label>分析深度</label>
        <div class="option-buttons">
          <button
            v-for="depth in analysisDepths"
            :key="depth.value"
            @click="advancedOptions.depth = depth.value"
            :class="{ active: advancedOptions.depth === depth.value }"
            class="option-btn"
          >
            {{ depth.label }}
          </button>
        </div>
      </div>

      <div class="option-group">
        <label>时间范围（小时）</label>
        <input
          v-model.number="advancedOptions.hours"
          type="number"
          min="24"
          max="168"
          step="24"
          class="option-input"
        />
      </div>

      <div class="option-group">
        <label>
          <input v-model="advancedOptions.includeSatellite" type="checkbox" />
          包含卫星数据
        </label>
      </div>

      <div class="option-group">
        <label>
          <input v-model="advancedOptions.includeFireHotspots" type="checkbox" />
          包含火点监测
        </label>
      </div>

      <div class="option-group">
        <label>
          <input v-model="advancedOptions.includeDustData" type="checkbox" />
          包含沙尘数据
        </label>
      </div>
    </div>

    <div v-if="selectedScenario" class="selected-summary">
      <h4>已选择：{{ scenarios.find(s => s.id === selectedScenario)?.name }}</h4>
      <p>{{ scenarios.find(s => s.id === selectedScenario)?.longDescription }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const emit = defineEmits(['select'])

const selectedScenario = ref('default')
const isLoading = ref(false)
const showAdvancedOptions = ref(false)

const advancedOptions = ref({
  depth: 'standard',
  hours: 72,
  includeSatellite: false,
  includeFireHotspots: false,
  includeDustData: false
})

const scenarios = [
  {
    id: 'default',
    name: '基础气象分析',
    badge: '推荐',
    badgeClass: 'badge-recommended',
    icon: '🌤️',
    description: '获取ERA5历史气象数据，生成基础分析图表',
    longDescription: '适合快速了解区域气象条件，自动生成时序图、风向玫瑰图等基础可视化内容。包含温度、湿度、风速风向等核心气象要素。',
    tools: [
      'get_weather_data',
      'smart_chart_generator',
      'generate_chart'
    ],
    features: [
      'ERA5历史气象数据',
      '自动生成基础图表',
      '风向风速分析',
      '温湿度趋势'
    ]
  },
  {
    id: 'enhanced',
    name: '增强气象分析',
    badge: '增强',
    badgeClass: 'badge-enhanced',
    icon: '🌈',
    description: '基础气象 + 当前天气 + 多种图表类型',
    longDescription: '在基础分析的基础上，增加当前实时天气数据，并生成多种类型的专业图表。适合需要综合了解历史和现状的场景。',
    tools: [
      'get_weather_data',
      'get_current_weather',
      'smart_chart_generator',
      'generate_chart'
    ],
    features: [
      '历史 + 实时天气',
      '多类型专业图表',
      '综合气象评估',
      '对比分析'
    ]
  },
  {
    id: 'trajectory',
    name: '轨迹传输分析',
    badge: '专业',
    badgeClass: 'badge-professional',
    icon: '🗺️',
    description: '后向轨迹分析 + 上风向企业 + 传输路径地图',
    longDescription: '专注于污染物传输路径分析，通过后向轨迹计算识别污染来源方向，生成专业的传输路径地图和上风向企业分析。',
    tools: [
      'get_weather_data',
      'meteorological_trajectory_analysis',
      'analyze_upwind_enterprises',
      'generate_map',
      'smart_chart_generator'
    ],
    features: [
      '后向轨迹计算',
      '传输路径地图',
      '上风向企业分析',
      '污染源识别'
    ]
  },
  {
    id: 'comprehensive',
    name: '综合气象分析',
    badge: '完整',
    badgeClass: 'badge-comprehensive',
    icon: '🌍',
    description: '完整气象分析：火点 + 沙尘 + 轨迹 + 多维度图表',
    longDescription: '最全面的气象分析模式，整合火点监测、沙尘传输、轨迹分析等多种数据源，生成全方位的专业气象分析报告。',
    tools: [
      'get_weather_data',
      'get_fire_hotspots',
      'get_dust_data',
      'meteorological_trajectory_analysis',
      'analyze_upwind_enterprises',
      'smart_chart_generator',
      'generate_map'
    ],
    features: [
      '火点数据监测',
      '沙尘传输分析',
      '多维度综合图表',
      '全方位专业报告'
    ]
  }
]

const analysisDepths = [
  { value: 'basic', label: '基础' },
  { value: 'standard', label: '标准' },
  { value: 'deep', label: '深度' },
  { value: 'expert', label: '专家级' }
]

const selectScenario = (scenarioId) => {
  selectedScenario.value = scenarioId
}

const proceedWithScenario = async () => {
  if (!selectedScenario.value || isLoading.value) return

  isLoading.value = true

  try {
    const scenario = scenarios.find(s => s.id === selectedScenario.value)

    emit('select', {
      scenario: selectedScenario.value,
      name: scenario.name,
      options: {
        ...advancedOptions.value,
        tools: scenario.tools,
        features: scenario.features
      }
    })
  } catch (error) {
    console.error('Failed to proceed with scenario:', error)
  } finally {
    isLoading.value = false
  }
}
</script>

<style lang="scss" scoped>
.meteorology-scenario-selector {
  padding: 24px;
  background: #f8f9fa;
  border-radius: 12px;
  border: 1px solid #e0e0e0;
}

.scenario-header {
  margin-bottom: 24px;

  h3 {
    margin: 0 0 8px 0;
    font-size: 20px;
    font-weight: 600;
    color: #1976d2;
  }

  .scenario-description {
    margin: 0;
    font-size: 14px;
    color: #666;
    line-height: 1.6;

    .expert-type {
      display: inline-block;
      margin-top: 4px;
      padding: 2px 8px;
      background: #e3f2fd;
      color: #1976d2;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 500;
    }
  }
}

.scenario-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.scenario-card {
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.3s ease;

  &:hover {
    border-color: #1976d2;
    box-shadow: 0 4px 12px rgba(25, 118, 210, 0.1);
    transform: translateY(-2px);
  }

  &.active {
    border-color: #1976d2;
    background: #f5f9ff;
    box-shadow: 0 4px 12px rgba(25, 118, 210, 0.15);
  }
}

.scenario-card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.scenario-icon {
  font-size: 32px;
  line-height: 1;
}

.scenario-title-group {
  flex: 1;

  h4 {
    margin: 0 0 4px 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
  }
}

.scenario-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;

  &.badge-recommended {
    background: #e8f5e9;
    color: #2e7d32;
  }

  &.badge-enhanced {
    background: #fff3e0;
    color: #f57c00;
  }

  &.badge-professional {
    background: #e3f2fd;
    color: #1976d2;
  }

  &.badge-comprehensive {
    background: #f3e5f5;
    color: #7b1fa2;
  }
}

.scenario-detail {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.scenario-tools {
  margin-bottom: 12px;

  .tools-label {
    font-size: 12px;
    color: #888;
    margin-bottom: 6px;
  }

  .tools-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
}

.tool-tag {
  padding: 3px 8px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 11px;
  color: #555;
  font-family: monospace;
}

.tool-tag-more {
  padding: 3px 8px;
  background: #fff3e0;
  border: 1px solid #ffe0b2;
  border-radius: 4px;
  font-size: 11px;
  color: #f57c00;
}

.scenario-features {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #555;

  .feature-icon {
    width: 14px;
    height: 14px;
    color: #2e7d32;
    flex-shrink: 0;
  }
}

.scenario-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.proceed-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover:not(.disabled) {
    background: #1565c0;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(25, 118, 210, 0.3);
  }

  &.disabled {
    background: #ccc;
    cursor: not-allowed;
  }
}

.advanced-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 20px;
  background: white;
  color: #1976d2;
  border: 1px solid #1976d2;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #e3f2fd;
  }
}

.advanced-options {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;

  h4 {
    margin: 0 0 16px 0;
    font-size: 16px;
    font-weight: 600;
    color: #333;
  }
}

.option-group {
  margin-bottom: 16px;

  label {
    display: block;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #555;
  }
}

.option-buttons {
  display: flex;
  gap: 8px;
}

.option-btn {
  padding: 8px 16px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
  }

  &.active {
    background: #1976d2;
    color: white;
    border-color: #1976d2;
  }
}

.option-input {
  width: 120px;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;

  &:focus {
    outline: none;
    border-color: #1976d2;
  }
}

.selected-summary {
  background: #f5f9ff;
  border: 1px solid #1976d2;
  border-radius: 8px;
  padding: 16px;

  h4 {
    margin: 0 0 8px 0;
    font-size: 15px;
    font-weight: 600;
    color: #1976d2;
  }

  p {
    margin: 0;
    font-size: 13px;
    color: #666;
    line-height: 1.5;
  }
}
</style>
