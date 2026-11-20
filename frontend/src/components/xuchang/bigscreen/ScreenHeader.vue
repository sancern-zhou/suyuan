<template>
  <header class="screen-header">
    <div class="brand">
      <h1>许昌市大气环境管控数据大屏</h1>
      <p class="brand-sub">空气质量 · 排名 · 告警 · 达标态势</p>
    </div>

    <div class="meta-block">
      <p>数据截止 <strong>{{ formatDateTime(dataCutoffHour) }}</strong></p>
      <p class="status-line" :class="{ stale: error }">
        <i aria-hidden="true"></i>{{ error ? '数据刷新异常，展示最近一次快照' : (loading ? '正在刷新…' : '运行正常') }}
      </p>
    </div>
  </header>
</template>

<script setup>
import { formatDateTime } from './aqiLevels.js'

const props = defineProps({
  header: { type: Object, default: null },
  dataCutoffHour: { type: String, default: '' },
  generatedAt: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})
</script>

<style lang="scss" scoped>
.screen-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 220;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 20px 8px;
  background: linear-gradient(180deg, rgba(4, 20, 31, 0.85), rgba(4, 20, 31, 0.25) 80%, transparent);
  pointer-events: none;

  > * { pointer-events: auto; }
}

.brand {
  h1 {
    margin: 0;
    font-size: 22px;
    letter-spacing: 2px;
    color: #eaf6f8;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
  }
  .brand-sub {
    margin: 3px 0 0;
    font-size: 11px;
    letter-spacing: 5px;
    color: #3fc8d4;
  }
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-left: auto;
  font-size: 12px;
  color: #8ab6c2;
  text-align: right;

  strong { color: #d8ecf1; font-weight: 600; }

  .status-line {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    color: #21a366;

    i {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 8px currentColor;
    }
    &.stale { color: #e5ae22; }
  }
}
</style>
