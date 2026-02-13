<template>
  <div class="map-test-view">
    <div class="header">
      <h1>地图功能测试</h1>
      <div class="test-controls">
        <button
          v-for="(config, key) in testConfigs"
          :key="key"
          @click="loadTestData(key)"
          :class="['test-btn', { active: currentTest === key }]"
        >
          {{ config.label }}
        </button>
      </div>
    </div>

    <div class="content">
      <div v-if="!currentTest" class="placeholder">
        <p>请选择一个测试场景</p>
      </div>

      <div v-else class="map-wrapper">
        <MapPanel
          :config="currentConfig"
          @ready="onMapReady"
          @markerClick="onMarkerClick"
        />

        <div class="info-panel">
          <h3>当前测试: {{ testConfigs[currentTest].label }}</h3>
          <div class="stats">
            <div class="stat-item">
              <span class="label">站点</span>
              <span class="value">{{ currentConfig.station.name }}</span>
            </div>
            <div class="stat-item">
              <span class="label">企业数量</span>
              <span class="value">{{ currentConfig.enterprises.length }}</span>
            </div>
            <div class="stat-item">
              <span class="label">上风向路径</span>
              <span class="value">{{ currentConfig.upwind_paths ? '有' : '无' }}</span>
            </div>
            <div class="stat-item">
              <span class="label">风向扇区</span>
              <span class="value">{{ currentConfig.sectors ? '有' : '无' }}</span>
            </div>
          </div>

          <div v-if="clickedEnterprise" class="clicked-info">
            <h4>点击的企业</h4>
            <pre>{{ JSON.stringify(clickedEnterprise, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import MapPanel from '@/components/visualization/MapPanel.vue'
import {
  mockMapConfig,
  mockMapConfigWithPath,
  mockMapConfigWithSector,
  mockMapConfigFull,
  mockMapConfigMinimal
} from '@/mock/mapTestData'

const currentTest = ref(null)
const currentConfig = ref(null)
const clickedEnterprise = ref(null)

const testConfigs = {
  minimal: {
    label: '最小配置',
    data: mockMapConfigMinimal
  },
  basic: {
    label: '基础地图',
    data: mockMapConfig
  },
  withPath: {
    label: '带路径',
    data: mockMapConfigWithPath
  },
  withSector: {
    label: '带扇区',
    data: mockMapConfigWithSector
  },
  full: {
    label: '完整功能',
    data: mockMapConfigFull
  }
}

function loadTestData(key) {
  currentTest.value = key
  currentConfig.value = testConfigs[key].data
  clickedEnterprise.value = null
  console.log('加载测试数据:', key, testConfigs[key].data)
}

function onMapReady() {
  console.log('地图加载完成')
}

function onMarkerClick(enterprise) {
  clickedEnterprise.value = enterprise
  console.log('点击企业标记:', enterprise)
}
</script>

<style lang="scss" scoped>
.map-test-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.header {
  background: white;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

  h1 {
    margin: 0 0 16px 0;
    font-size: 24px;
    color: #333;
  }
}

.test-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.test-btn {
  padding: 10px 20px;
  border: 2px solid #e0e0e0;
  background: white;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
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

.content {
  flex: 1;
  padding: 20px;
  overflow: auto;
}

.placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 16px;
}

.map-wrapper {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 20px;
  height: 100%;
}

.info-panel {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow-y: auto;

  h3 {
    margin: 0 0 16px 0;
    font-size: 16px;
    color: #333;
    border-bottom: 2px solid #1976d2;
    padding-bottom: 8px;
  }

  h4 {
    margin: 16px 0 8px 0;
    font-size: 14px;
    color: #666;
  }
}

.stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: #f8f8f8;
  border-radius: 6px;

  .label {
    font-size: 13px;
    color: #666;
  }

  .value {
    font-size: 14px;
    font-weight: 600;
    color: #333;
  }
}

.clicked-info {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;

  pre {
    background: #f8f8f8;
    padding: 12px;
    border-radius: 6px;
    font-size: 12px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}
</style>
