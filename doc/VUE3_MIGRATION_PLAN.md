# Vue3 架构迁移详细方案

> **项目**: 大气污染溯源分析系统 (Air Pollution Source Traceability Analysis System)
> **迁移方向**: React 18 + TypeScript → Vue 3 + TypeScript
> **预估工期**: 2-3周全职开发
> **文档版本**: 1.0
> **创建日期**: 2025-10-21

---

## 📋 目录

1. [迁移背景与目标](#1-迁移背景与目标)
2. [技术选型方案](#2-技术选型方案)
3. [项目结构设计](#3-项目结构设计)
4. [组件迁移计划](#4-组件迁移计划)
5. [关键技术实现](#5-关键技术实现)
6. [迁移实施步骤](#6-迁移实施步骤)
7. [风险评估与应对](#7-风险评估与应对)
8. [测试策略](#8-测试策略)
9. [迁移检查清单](#9-迁移检查清单)

---

## 1. 迁移背景与目标

### 1.1 迁移原因
- **团队技术栈统一**: 团队其他项目使用Vue生态，统一技术栈降低维护成本
- **长期维护考虑**: Vue3在中国开发者社区中更受欢迎，易于招聘和培训
- **性能优化**: Vue3 Composition API 提供更灵活的状态管理和更好的 Tree-shaking

### 1.2 迁移目标
✅ **功能完全对等**: 保持所有现有功能不变
✅ **用户体验一致**: 界面和交互保持一致
✅ **性能不降低**: 首屏加载和运行性能不低于React版本
✅ **代码可维护**: 遵循Vue3最佳实践，代码结构清晰
✅ **类型安全**: 完整的TypeScript类型支持

### 1.3 现有架构分析

**当前技术栈 (React 18)**:
```
├── 框架: React 18.2.0 + TypeScript 5.2.2
├── 构建: Vite 5.2.0 + @vitejs/plugin-react
├── UI库: Ant Design 5.17.4
├── 可视化: ECharts 5.5.0 + echarts-for-react
├── 地图: 高德地图 AMap 2.0 (动态加载)
├── 其他: react-markdown, remark-gfm
└── 代码规模: 22个TS/TSX文件, 16个组件
```

**核心组件架构**:
```
App.tsx (根组件)
├── ChatOverlay - 全屏AI对话界面
├── FloatingChatButton - 浮动AI助手按钮
├── ModuleCard - 分析模块卡片容器
│   ├── MapPanel - 高德地图面板 (复杂度: ⭐⭐⭐)
│   ├── ChartsPanel - ECharts图表 (复杂度: ⭐⭐⭐⭐)
│   └── TextPanel - Markdown文本 (复杂度: ⭐)
├── ChatMessageRenderer - 聊天消息渲染 (复杂度: ⭐⭐)
├── StreamProgress - 流式进度显示 (复杂度: ⭐⭐)
└── KpiStrip - KPI指标条 (复杂度: ⭐)
```

**状态管理模式**:
- 使用 `useState` 管理本地状态
- 使用 `useEffect` 处理副作用
- 父子组件通过 `props` 传递数据
- 使用回调函数 (`onSubmit`, `onMaximize`) 处理事件

**API集成**:
- 使用 `fetch` API 进行HTTP请求
- 支持 **Server-Sent Events (SSE)** 流式数据
- 使用 `services/api.ts` 封装API调用

---

## 2. 技术选型方案

### 2.1 核心依赖对照表

| 功能类别 | React 生态 | Vue3 替代方案 | 备注 |
|---------|-----------|--------------|------|
| **核心框架** | react 18.2.0<br>react-dom 18.2.0 | vue ^3.4.0 | Vue3 Composition API |
| **构建工具** | @vitejs/plugin-react | @vitejs/plugin-vue | Vite原生支持Vue3 |
| **UI组件库** | antd 5.17.4 | ant-design-vue ^4.1.0 | API高度相似 |
| **可视化库** | echarts 5.5.0<br>echarts-for-react 3.0.2 | echarts 5.5.0<br>vue-echarts ^6.6.0 | ECharts核心库不变 |
| **地图SDK** | 高德地图 JS API 2.0 | 高德地图 JS API 2.0 | SDK不变，封装改为组合式函数 |
| **Markdown** | react-markdown 9.1.0<br>remark-gfm 4.0.1 | vue-markdown-render ^2.0.0<br>或 marked + DOMPurify | 需要重新选型 |
| **路由** | ❌ 未使用 | vue-router ^4.2.0 | 可选，未来扩展用 |
| **状态管理** | useState/useContext | Pinia ^2.1.0 | 推荐使用Pinia |
| **HTTP客户端** | fetch API | fetch API / axios | 建议保持fetch，代码可复用 |

### 2.2 推荐技术栈 (Vue3)

```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "ant-design-vue": "^4.1.0",
    "echarts": "^5.5.0",
    "vue-echarts": "^6.6.0",
    "pinia": "^2.1.0",
    "marked": "^11.0.0",
    "dompurify": "^3.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "@vue/tsconfig": "^0.5.0",
    "typescript": "^5.3.0",
    "vite": "^5.2.0",
    "vue-tsc": "^1.8.0"
  }
}
```

### 2.3 为什么选择这些技术？

#### ✅ Ant Design Vue vs Element Plus vs Naive UI
**选择 Ant Design Vue 的理由**:
1. API与React版本Ant Design高度一致，迁移成本低
2. 组件库成熟，企业级应用首选
3. TypeScript支持完善
4. 当前项目已使用Ant Design，保持UI风格一致

#### ✅ Pinia vs Vuex
**选择 Pinia 的理由**:
1. Vue官方推荐的状态管理库
2. TypeScript支持更好
3. API更简洁，无需mutations
4. 支持模块化，便于维护

#### ✅ vue-markdown-render vs @vueup/vue-quill
**选择 marked + DOMPurify 的理由**:
1. marked是最流行的Markdown解析器，稳定可靠
2. DOMPurify防止XSS攻击
3. 灵活性高，可以自定义渲染规则
4. 与react-markdown功能对等

---

## 3. 项目结构设计

### 3.1 目录结构对照

```bash
# React 项目结构 (现有)
frontend/
├── src/
│   ├── components/          # 16个React组件
│   ├── hooks/               # 1个自定义Hook
│   ├── services/            # API服务层
│   ├── types/               # TypeScript类型定义
│   ├── styles/              # CSS样式
│   ├── App.tsx              # 根组件
│   └── main.tsx             # 入口文件
├── package.json
└── vite.config.ts

# Vue3 项目结构 (目标)
frontend-vue/
├── src/
│   ├── components/          # 16个Vue单文件组件 (.vue)
│   ├── composables/         # 组合式函数 (替代hooks)
│   ├── services/            # API服务层 (几乎不变)
│   ├── types/               # TypeScript类型定义 (完全复用)
│   ├── stores/              # Pinia状态管理 (可选)
│   ├── styles/              # CSS样式 (完全复用)
│   ├── App.vue              # 根组件
│   └── main.ts              # 入口文件
├── package.json
└── vite.config.ts
```

### 3.2 关键文件迁移对照

| React 文件 | Vue3 文件 | 变化程度 |
|-----------|----------|---------|
| `main.tsx` | `main.ts` | 🟡 中等 (初始化代码改写) |
| `App.tsx` | `App.vue` | 🔴 高 (JSX→Template) |
| `components/*.tsx` | `components/*.vue` | 🔴 高 (所有组件重写) |
| `hooks/useAMapLoader.ts` | `composables/useAMapLoader.ts` | 🟢 低 (语法微调) |
| `services/api.ts` | `services/api.ts` | 🟢 极低 (几乎不变) |
| `types/api.ts` | `types/api.ts` | 🟢 无 (完全复用) |
| `styles/theme.css` | `styles/theme.css` | 🟢 无 (完全复用) |

### 3.3 关键文件示例

#### 📄 `main.ts` (Vue3 入口文件)
```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import App from './App.vue'

// 样式导入
import 'ant-design-vue/dist/reset.css'
import './styles/theme.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(Antd)

app.mount('#app')
```

#### 📄 `vite.config.ts` (Vite配置)
```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@components': path.resolve(__dirname, 'src/components'),
      '@services': path.resolve(__dirname, 'src/services'),
      '@types': path.resolve(__dirname, 'src/types'),
      '@styles': path.resolve(__dirname, 'src/styles'),
      '@composables': path.resolve(__dirname, 'src/composables'),
      '@stores': path.resolve(__dirname, 'src/stores'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

---

## 4. 组件迁移计划

### 4.1 迁移优先级分级

采用 **渐进式迁移策略**，按以下优先级顺序迁移：

#### 🟢 **P0 - 基础组件** (无依赖，优先迁移)
| 组件名 | 复杂度 | 预估工时 | 关键点 |
|-------|--------|---------|--------|
| `KpiStrip.tsx` | ⭐ | 2小时 | 简单数据展示，无复杂逻辑 |
| `TextPanel.tsx` | ⭐ | 2小时 | Markdown渲染，需选型新库 |
| `FloatingChatButton.tsx` | ⭐ | 1小时 | 简单按钮组件 |
| `StreamProgress.tsx` | ⭐⭐ | 3小时 | 进度条逻辑需改写 |
| `ErrorBoundary.tsx` | ⭐⭐ | 2小时 | 使用Vue3错误处理机制 |

#### 🟡 **P1 - 核心展示组件** (依赖P0，中等复杂度)
| 组件名 | 复杂度 | 预估工时 | 关键点 |
|-------|--------|---------|--------|
| `ChartsPanel.tsx` | ⭐⭐⭐⭐ | 8小时 | ECharts封装，支持3种图表类型 |
| `MapPanel.tsx` | ⭐⭐⭐ | 6小时 | 高德地图动态加载，标记点渲染 |
| `VisualRenderer.tsx` | ⭐⭐ | 3小时 | 路由到不同可视化组件 |
| `ModuleCard.tsx` | ⭐⭐ | 4小时 | 卡片容器，整合多个子组件 |

#### 🔴 **P2 - 复杂交互组件** (依赖P0+P1，高复杂度)
| 组件名 | 复杂度 | 预估工时 | 关键点 |
|-------|--------|---------|--------|
| `ChatMessageRenderer.tsx` | ⭐⭐⭐ | 5小时 | 消息渲染，支持多种类型 |
| `ChatOverlay.tsx` | ⭐⭐⭐⭐ | 8小时 | 全屏对话界面，状态复杂 |
| `ChatDock.tsx` | ⭐⭐⭐ | 5小时 | 侧边栏对话面板 |
| `QueryBar.tsx` | ⭐⭐ | 3小时 | 查询输入框 |

#### 🟣 **P3 - 根组件与布局** (最后集成)
| 组件名 | 复杂度 | 预估工时 | 关键点 |
|-------|--------|---------|--------|
| `App.vue` | ⭐⭐⭐⭐⭐ | 10小时 | 根组件，整合所有模块，状态管理 |
| `ResizablePanels.tsx` | ⭐⭐ | 3小时 | 可调整大小面板 |

**总工时预估**: 约 **65小时** (含调试和测试时间)

### 4.2 组件迁移模板

#### React组件示例 (KpiStrip.tsx)
```tsx
import React from 'react'
import type { KPIData } from '@app-types/api'

interface Props {
  data: KPIData
}

const KpiStrip: React.FC<Props> = ({ data }) => {
  return (
    <div className="kpi-strip">
      <div className="kpi-item">
        <label>峰值</label>
        <span>{data.peak_value} {data.unit}</span>
      </div>
      <div className="kpi-item">
        <label>均值</label>
        <span>{data.avg_value} {data.unit}</span>
      </div>
    </div>
  )
}

export default KpiStrip
```

#### Vue3组件示例 (KpiStrip.vue)
```vue
<script setup lang="ts">
import type { KPIData } from '@/types/api'

interface Props {
  data: KPIData
}

defineProps<Props>()
</script>

<template>
  <div class="kpi-strip">
    <div class="kpi-item">
      <label>峰值</label>
      <span>{{ data.peak_value }} {{ data.unit }}</span>
    </div>
    <div class="kpi-item">
      <label>均值</label>
      <span>{{ data.avg_value }} {{ data.unit }}</span>
    </div>
  </div>
</template>

<style scoped>
/* CSS样式可以直接复用 */
</style>
```

**关键差异**:
1. ✅ `React.FC<Props>` → `defineProps<Props>()`
2. ✅ `{data.peak_value}` → `{{ data.peak_value }}`
3. ✅ `className` → `class`
4. ✅ 使用 `<script setup>` 简化代码

---

## 5. 关键技术实现

### 5.1 状态管理迁移

#### React版本 (useState)
```tsx
// App.tsx
const [loading, setLoading] = useState(false)
const [data, setData] = useState<AnalysisData | null>(null)
const [chatOpen, setChatOpen] = useState(false)
```

#### Vue3版本 (Composition API)
```vue
<!-- App.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import type { AnalysisData } from '@/types/api'

const loading = ref(false)
const data = ref<AnalysisData | null>(null)
const chatOpen = ref(false)
</script>
```

#### 使用Pinia (推荐用于复杂状态)
```typescript
// stores/analysis.ts
import { defineStore } from 'pinia'
import type { AnalysisData } from '@/types/api'

export const useAnalysisStore = defineStore('analysis', () => {
  const loading = ref(false)
  const data = ref<AnalysisData | null>(null)
  const chatOpen = ref(false)

  const setData = (newData: AnalysisData) => {
    data.value = newData
  }

  return { loading, data, chatOpen, setData }
})
```

```vue
<!-- App.vue -->
<script setup lang="ts">
import { useAnalysisStore } from '@/stores/analysis'

const store = useAnalysisStore()
</script>

<template>
  <div v-if="store.loading">加载中...</div>
</template>
```

### 5.2 副作用处理 (useEffect → onMounted/watch)

#### React版本
```tsx
useEffect(() => {
  fetchConfig()
    .then(cfg => {
      if (cfg?.amapPublicKey) {
        setAmapKey(cfg.amapPublicKey)
      }
    })
    .catch(err => console.warn('Failed to load config:', err))
}, []) // 空依赖数组 = 仅在挂载时执行
```

#### Vue3版本
```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchConfig } from '@/services/api'

const amapKey = ref('')

onMounted(async () => {
  try {
    const cfg = await fetchConfig()
    if (cfg?.amapPublicKey) {
      amapKey.value = cfg.amapPublicKey
    }
  } catch (err) {
    console.warn('Failed to load config:', err)
  }
})
</script>
```

#### 监听响应式数据变化 (watch)
```vue
<script setup lang="ts">
import { ref, watch } from 'vue'

const chatOpen = ref(false)

// 等效于 useEffect(() => { ... }, [chatOpen])
watch(chatOpen, (newVal, oldVal) => {
  console.log('chatOpen changed:', oldVal, '->', newVal)
})
</script>
```

### 5.3 事件处理

#### React版本
```tsx
const handleChatSubmit = async (text: string) => {
  setChatLoading(true)
  try {
    await callAnalyzeApiStream({ query: text, stream: true }, {
      onStep: (event) => { /* ... */ },
      onResult: (module, data) => { /* ... */ }
    })
  } finally {
    setChatLoading(false)
  }
}

<ChatOverlay onSubmit={handleChatSubmit} />
```

#### Vue3版本
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { callAnalyzeApiStream } from '@/services/api'

const chatLoading = ref(false)

const handleChatSubmit = async (text: string) => {
  chatLoading.value = true
  try {
    await callAnalyzeApiStream({ query: text, stream: true }, {
      onStep: (event) => { /* ... */ },
      onResult: (module, data) => { /* ... */ }
    })
  } finally {
    chatLoading.value = false
  }
}
</script>

<template>
  <ChatOverlay @submit="handleChatSubmit" />
</template>
```

**关键差异**:
- `onSubmit={fn}` → `@submit="fn"`
- `setState(value)` → `ref.value = value`

### 5.4 自定义Hook → 组合式函数 (Composables)

#### React Hook (useAMapLoader.ts)
```typescript
import { useEffect, useState } from 'react'

export function useAMapLoader(amapKey?: string) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!amapKey) return

    if (window.AMap) {
      setLoaded(true)
      return
    }

    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey}`
    script.onload = () => setLoaded(true)
    script.onerror = () => setError('AMap脚本加载失败')
    document.body.appendChild(script)
  }, [amapKey])

  return { loaded, error, AMap: window.AMap }
}
```

#### Vue3 Composable (useAMapLoader.ts)
```typescript
import { ref, onMounted, watch } from 'vue'

export function useAMapLoader(amapKey: Ref<string | undefined>) {
  const loaded = ref(false)
  const error = ref<string | null>(null)

  const loadAMap = () => {
    if (!amapKey.value) return

    if (window.AMap) {
      loaded.value = true
      return
    }

    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey.value}`
    script.onload = () => { loaded.value = true }
    script.onerror = () => { error.value = 'AMap脚本加载失败' }
    document.body.appendChild(script)
  }

  onMounted(loadAMap)
  watch(amapKey, loadAMap)

  return { loaded, error, AMap: computed(() => window.AMap) }
}
```

### 5.5 ECharts 集成

#### React版本 (echarts-for-react)
```tsx
import ReactECharts from 'echarts-for-react'

const ChartsPanel: React.FC<Props> = ({ type, payload }) => {
  const option = {
    xAxis: { type: 'category', data: payload.x_axis },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: payload.series[0].data }]
  }

  return <ReactECharts option={option} />
}
```

#### Vue3版本 (vue-echarts)
```vue
<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'

interface Props {
  type: 'timeseries' | 'bar' | 'pie'
  payload: any
}

const props = defineProps<Props>()

const option = computed<EChartsOption>(() => ({
  xAxis: { type: 'category', data: props.payload.x_axis },
  yAxis: { type: 'value' },
  series: [{ type: 'line', data: props.payload.series[0].data }]
}))
</script>

<template>
  <v-chart :option="option" autoresize />
</template>

<style scoped>
.echarts {
  width: 100%;
  height: 320px;
}
</style>
```

### 5.6 高德地图集成

#### React版本 (MapPanel.tsx)
```tsx
const MapPanel: React.FC<Props> = ({ payload, amapKey }) => {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)

  useEffect(() => {
    if (!window.AMap || !mapRef.current) return

    const map = new window.AMap.Map(mapRef.current, {
      zoom: payload.zoom || 10,
      center: payload.center
    })

    mapInstanceRef.current = map

    return () => {
      map.destroy()
    }
  }, [payload, amapKey])

  return <div ref={mapRef} style={{ height: 400 }} />
}
```

#### Vue3版本 (MapPanel.vue)
```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { MapPayload } from '@/types/api'

interface Props {
  payload: MapPayload
  amapKey?: string
}

const props = defineProps<Props>()

const mapRef = ref<HTMLDivElement>()
let mapInstance: any = null

const initMap = () => {
  if (!window.AMap || !mapRef.value) return

  mapInstance = new window.AMap.Map(mapRef.value, {
    zoom: props.payload.zoom || 10,
    center: props.payload.center
  })
}

onMounted(initMap)
watch(() => props.payload, initMap)

onUnmounted(() => {
  mapInstance?.destroy()
})
</script>

<template>
  <div ref="mapRef" :style="{ height: '400px' }" />
</template>
```

### 5.7 流式数据处理 (SSE)

#### API服务层 (services/api.ts) - **无需改动**
```typescript
// ✅ 这部分代码在React和Vue3中完全通用！
export async function callAnalyzeApiStream(
  req: AnalyzeRequest,
  callbacks: StreamCallbacks
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...req, stream: true })
  })

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const event = JSON.parse(line.slice(6))

      if (event.type === 'step' && callbacks.onStep) {
        callbacks.onStep(event)
      }
      // ... 其他事件处理
    }
  }
}
```

#### Vue3组件中使用
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { callAnalyzeApiStream } from '@/services/api'

const progressSteps = ref<ProgressStep[]>([])
const data = ref<AnalysisData | null>(null)

const handleSubmit = async (query: string) => {
  await callAnalyzeApiStream({ query, stream: true }, {
    onStep: (event) => {
      progressSteps.value.push({
        step: event.step,
        status: event.status,
        message: event.message
      })
    },
    onResult: (module, moduleData) => {
      data.value = { ...data.value, [module]: moduleData }
    }
  })
}
</script>
```

### 5.8 Markdown渲染

#### React版本 (react-markdown)
```tsx
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const TextPanel: React.FC<Props> = ({ content }) => {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  )
}
```

#### Vue3版本 (marked + DOMPurify)
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

interface Props {
  content: string
}

const props = defineProps<Props>()

// 配置marked支持GFM (GitHub Flavored Markdown)
marked.setOptions({
  gfm: true,
  breaks: true
})

const html = computed(() => {
  const rawHtml = marked(props.content)
  return DOMPurify.sanitize(rawHtml)
})
</script>

<template>
  <div class="markdown-body" v-html="html" />
</template>

<style>
/* 使用GitHub Markdown样式 */
@import 'github-markdown-css';
</style>
```

---

## 6. 迁移实施步骤

### 阶段1: 环境搭建 (第1天)

**目标**: 创建Vue3项目骨架，配置开发环境

#### 步骤:
1. **创建新项目目录**
   ```bash
   cd D:\溯源
   npm create vite@latest frontend-vue -- --template vue-ts
   cd frontend-vue
   ```

2. **安装依赖**
   ```bash
   # 核心依赖
   npm install vue@^3.4.0
   npm install ant-design-vue@^4.1.0
   npm install echarts@^5.5.0 vue-echarts@^6.6.0
   npm install pinia@^2.1.0
   npm install marked@^11.0.0 dompurify@^3.0.0

   # 开发依赖
   npm install -D @vitejs/plugin-vue@^5.0.0
   npm install -D @vue/tsconfig@^0.5.0
   npm install -D typescript@^5.3.0
   npm install -D vue-tsc@^1.8.0

   # 类型定义
   npm install -D @types/dompurify
   ```

3. **配置Vite** (`vite.config.ts`)
   ```typescript
   import { defineConfig } from 'vite'
   import vue from '@vitejs/plugin-vue'
   import path from 'node:path'

   export default defineConfig({
     plugins: [vue()],
     resolve: {
       alias: {
         '@': path.resolve(__dirname, 'src'),
         '@components': path.resolve(__dirname, 'src/components'),
         '@services': path.resolve(__dirname, 'src/services'),
         '@types': path.resolve(__dirname, 'src/types'),
         '@composables': path.resolve(__dirname, 'src/composables'),
         '@stores': path.resolve(__dirname, 'src/stores'),
       },
     },
     server: {
       port: 5174, // 使用不同端口避免冲突
       proxy: {
         '/api': {
           target: 'http://localhost:8000',
           changeOrigin: true
         }
       }
     }
   })
   ```

4. **配置TypeScript** (`tsconfig.json`)
   ```json
   {
     "extends": "@vue/tsconfig/tsconfig.dom.json",
     "compilerOptions": {
       "baseUrl": ".",
       "paths": {
         "@/*": ["./src/*"],
         "@components/*": ["./src/components/*"],
         "@services/*": ["./src/services/*"],
         "@types/*": ["./src/types/*"],
         "@composables/*": ["./src/composables/*"],
         "@stores/*": ["./src/stores/*"]
       },
       "strict": true,
       "skipLibCheck": true
     },
     "include": ["src/**/*.ts", "src/**/*.vue"],
     "exclude": ["node_modules"]
   }
   ```

5. **复制可复用资源**
   ```bash
   # 从React项目复制
   cp -r ../frontend/src/types ./src/
   cp -r ../frontend/src/styles ./src/
   cp ../frontend/src/services/api.ts ./src/services/
   ```

6. **创建主入口** (`src/main.ts`)
   ```typescript
   import { createApp } from 'vue'
   import { createPinia } from 'pinia'
   import Antd from 'ant-design-vue'
   import App from './App.vue'

   import 'ant-design-vue/dist/reset.css'
   import './styles/theme.css'

   const app = createApp(App)

   app.use(createPinia())
   app.use(Antd)

   app.mount('#app')
   ```

7. **测试环境**
   ```bash
   npm run dev
   # 访问 http://localhost:5174，确保能正常启动
   ```

### 阶段2: 基础组件迁移 (第2-3天)

**目标**: 迁移P0级别组件，建立迁移模板

#### 任务列表:
- [ ] `KpiStrip.vue` (2小时)
- [ ] `TextPanel.vue` (2小时)
- [ ] `FloatingChatButton.vue` (1小时)
- [ ] `StreamProgress.vue` (3小时)
- [ ] `ErrorBoundary` (使用Vue3 `errorHandler`)

#### 迁移流程:
1. **创建组件文件** (以KpiStrip为例)
   ```bash
   touch src/components/KpiStrip.vue
   ```

2. **编写Vue3组件**
   ```vue
   <script setup lang="ts">
   import type { KPIData } from '@/types/api'

   interface Props {
     data: KPIData
   }

   defineProps<Props>()
   </script>

   <template>
     <!-- 从React JSX复制HTML结构，改为Vue Template语法 -->
   </template>

   <style scoped>
   /* 从原CSS文件复制样式 */
   </style>
   ```

3. **单元测试** (可选)
   ```bash
   npm install -D @vue/test-utils vitest
   # 创建测试文件 tests/KpiStrip.spec.ts
   ```

4. **集成到App.vue**
   ```vue
   <script setup lang="ts">
   import KpiStrip from '@/components/KpiStrip.vue'
   </script>

   <template>
     <KpiStrip v-if="data?.kpi_summary" :data="data.kpi_summary" />
   </template>
   ```

### 阶段3: 核心展示组件迁移 (第4-7天)

**目标**: 迁移P1级别组件，完成数据可视化功能

#### 任务列表:
- [ ] `ChartsPanel.vue` (8小时) - **关键组件**
  - 支持时序图、柱状图、饼图
  - 使用 `vue-echarts` 封装
  - 保持响应式设计

- [ ] `MapPanel.vue` (6小时) - **关键组件**
  - 高德地图动态加载
  - 标记点渲染
  - 风向箭头绘制

- [ ] `VisualRenderer.vue` (3小时)
  - 根据 `visual.type` 路由到对应组件
  - 支持动态和静态两种模式

- [ ] `ModuleCard.vue` (4小时)
  - 卡片容器组件
  - 整合 `ChartsPanel`, `MapPanel`, `TextPanel`

#### 关键实现: ChartsPanel.vue
```vue
<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import type { EChartsOption } from 'echarts'
import type { TimeSeriesPayload, BarPayload, PiePayload } from '@/types/api'

// 注册必需的 ECharts 组件 (Tree-shaking)
use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

interface Props {
  type: 'timeseries' | 'bar' | 'pie'
  payload: TimeSeriesPayload | BarPayload | PiePayload
  meta?: Record<string, any>
  title?: string
}

const props = defineProps<Props>()

const option = computed<EChartsOption>(() => {
  switch (props.type) {
    case 'timeseries': {
      const tsPayload = props.payload as TimeSeriesPayload
      return {
        title: { text: props.title },
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0 },
        xAxis: { type: 'category', data: tsPayload.x_axis },
        yAxis: { type: 'value', name: props.meta?.unit || 'μg/m³' },
        series: tsPayload.series.map(s => ({
          name: s.name,
          type: 'line',
          data: s.data,
          smooth: true
        }))
      }
    }
    case 'bar': {
      const barPayload = props.payload as BarPayload
      return {
        title: { text: props.title },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: barPayload.categories },
        yAxis: { type: 'value', name: barPayload.y_label },
        series: [{ type: 'bar', data: barPayload.values }]
      }
    }
    case 'pie': {
      const piePayload = props.payload as PiePayload
      return {
        title: { text: props.title },
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', right: '5%' },
        series: [{
          type: 'pie',
          radius: ['40%', '60%'],
          data: piePayload.data
        }]
      }
    }
    default:
      return {}
  }
})
</script>

<template>
  <v-chart :option="option" :style="{ height: '350px' }" autoresize />
</template>
```

### 阶段4: 复杂交互组件迁移 (第8-12天)

**目标**: 迁移P2级别组件,实现聊天和流式数据功能

#### 任务列表:
- [ ] `ChatMessageRenderer.vue` (5小时)
  - 消息类型判断 (text/progress/modules)
  - Markdown渲染
  - 模块卡片嵌入

- [ ] `ChatOverlay.vue` (8小时) - **最复杂组件**
  - 全屏/最小化状态切换
  - 消息列表滚动
  - 输入框自动聚焦
  - 流式数据实时更新

- [ ] `ChatDock.vue` (5小时)
  - 侧边栏面板
  - 可调整大小

- [ ] `QueryBar.vue` (3小时)
  - 查询输入框
  - 提交事件处理

#### 关键实现: ChatOverlay.vue
```vue
<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import type { ChatMsg } from '@/types/chat'
import ChatMessageRenderer from './ChatMessageRenderer.vue'

interface Props {
  open: boolean
  minimized: boolean
  messages: ChatMsg[]
  isLoading: boolean
  amapKey?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  submit: [text: string]
  maximize: []
  close: []
}>()

const inputText = ref('')
const messagesEndRef = ref<HTMLElement>()

const handleSubmit = () => {
  if (!inputText.value.trim()) return
  emit('submit', inputText.value)
  inputText.value = ''
}

// 自动滚动到底部
watch(() => props.messages.length, async () => {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
})
</script>

<template>
  <div
    v-if="open && !minimized"
    class="chat-overlay"
    :class="{ fullscreen: !minimized }"
  >
    <div class="chat-header">
      <h3>AI 助手</h3>
      <div class="chat-actions">
        <a-button @click="emit('maximize')">
          <template #icon><FullscreenOutlined /></template>
        </a-button>
        <a-button @click="emit('close')">
          <template #icon><CloseOutlined /></template>
        </a-button>
      </div>
    </div>

    <div class="chat-messages">
      <ChatMessageRenderer
        v-for="(msg, idx) in messages"
        :key="idx"
        :message="msg"
        :amap-key="amapKey"
      />
      <div ref="messagesEndRef" />
    </div>

    <div class="chat-input">
      <a-textarea
        v-model:value="inputText"
        placeholder="输入查询内容..."
        :auto-size="{ minRows: 2, maxRows: 4 }"
        @press-enter.prevent="handleSubmit"
      />
      <a-button
        type="primary"
        :loading="isLoading"
        @click="handleSubmit"
      >
        发送
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.chat-overlay {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 400px;
  height: 600px;
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  transition: all 0.3s ease;
}

.chat-overlay.fullscreen {
  top: 80px;
  left: 20px;
  right: 20px;
  bottom: 20px;
  width: auto;
  height: auto;
}

/* ... 其他样式 ... */
</style>
```

### 阶段5: 根组件集成 (第13-15天)

**目标**: 集成所有组件到App.vue,实现完整功能

#### 任务:
- [ ] `App.vue` (10小时)
  - 整合所有子组件
  - 状态管理 (使用Pinia)
  - 流式数据处理
  - 错误处理

- [ ] `ResizablePanels.vue` (3小时)
  - 可调整大小的面板布局

#### App.vue 结构
```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAnalysisStore } from '@/stores/analysis'
import { fetchConfig, callAnalyzeApiStream } from '@/services/api'
import ModuleCard from '@/components/ModuleCard.vue'
import ChatOverlay from '@/components/ChatOverlay.vue'
import FloatingChatButton from '@/components/FloatingChatButton.vue'

const store = useAnalysisStore()
const amapKey = ref('')

onMounted(async () => {
  const cfg = await fetchConfig()
  if (cfg?.amapPublicKey) {
    amapKey.value = cfg.amapPublicKey
  }
})

const handleChatSubmit = async (text: string) => {
  store.loading = true
  await callAnalyzeApiStream({ query: text, stream: true }, {
    onStep: (event) => store.addProgressStep(event),
    onResult: (module, data) => store.updateModule(module, data),
    onDone: (success) => { store.loading = false }
  })
}
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>大气污染溯源分析系统</h1>
      <div class="header-subtitle">
        Air Pollution Source Traceability Analysis System
      </div>
    </header>

    <main class="main-content">
      <div v-if="store.showDashboard && store.data" class="dashboard-modules">
        <ModuleCard
          v-if="store.data.weather_analysis"
          :module="store.data.weather_analysis"
          :amap-key="amapKey"
        />
        <ModuleCard
          v-if="store.data.regional_analysis"
          :module="store.data.regional_analysis"
          :amap-key="amapKey"
        />
        <!-- ... 其他模块 ... -->
      </div>

      <div v-else class="welcome-placeholder">
        <h2>欢迎使用大气污染溯源分析系统</h2>
        <p>点击右下角的 AI 助手按钮开始分析</p>
      </div>
    </main>

    <ChatOverlay
      :open="store.chatOpen"
      :minimized="store.chatMinimized"
      :messages="store.chatMessages"
      :is-loading="store.loading"
      :amap-key="amapKey"
      @submit="handleChatSubmit"
      @maximize="store.toggleFullscreen"
      @close="store.minimizeChat"
    />

    <FloatingChatButton
      v-if="store.chatMinimized || store.showDashboard"
      @open="store.openChat"
    />
  </div>
</template>

<style>
@import './styles/theme.css';
</style>
```

### 阶段6: 测试与优化 (第16-18天)

#### 测试任务:
- [ ] **功能测试**
  - 查询提交 → 流式数据接收 → 模块渲染
  - 地图加载 → 标记点显示
  - 图表渲染 → 数据正确性
  - 聊天界面 → 全屏/最小化切换

- [ ] **兼容性测试**
  - Chrome / Firefox / Edge / Safari
  - 不同分辨率 (1920x1080, 1366x768, 2560x1440)

- [ ] **性能测试**
  - 首屏加载时间 (目标: < 3秒)
  - Bundle大小 (目标: < 500KB gzipped)
  - 内存占用 (目标: < 100MB)

- [ ] **压力测试**
  - 快速连续查询
  - 大量数据渲染 (100+企业标记)
  - 长时间运行稳定性

#### 优化任务:
- [ ] **代码拆分** (Code Splitting)
  ```typescript
  // router/index.ts
  const ChatOverlay = defineAsyncComponent(() =>
    import('@/components/ChatOverlay.vue')
  )
  ```

- [ ] **懒加载地图组件**
  ```vue
  <script setup lang="ts">
  const MapPanel = defineAsyncComponent(() =>
    import('@/components/MapPanel.vue')
  )
  </script>
  ```

- [ ] **ECharts按需加载** (Tree-shaking)
  ```typescript
  // 只导入需要的图表类型
  import { LineChart, BarChart } from 'echarts/charts'
  ```

- [ ] **CSS优化**
  - 移除未使用的样式
  - 使用CSS变量统一主题
  - 压缩CSS文件

### 阶段7: 部署与文档 (第19-21天)

#### 部署准备:
- [ ] **构建生产版本**
  ```bash
  npm run build
  # 输出到 dist/ 目录
  ```

- [ ] **部署到服务器**
  ```bash
  # 方式1: 使用Nginx
  cp -r dist/* /var/www/html/

  # 方式2: 使用Docker
  docker build -t pollution-analysis-vue .
  docker run -p 5173:80 pollution-analysis-vue
  ```

- [ ] **配置反向代理**
  ```nginx
  # nginx.conf
  server {
    listen 80;
    server_name your-domain.com;

    location / {
      root /var/www/html;
      try_files $uri $uri/ /index.html;
    }

    location /api {
      proxy_pass http://localhost:8000;
      proxy_set_header Host $host;
    }
  }
  ```

#### 文档编写:
- [ ] **更新README.md**
  - 项目介绍
  - 快速开始
  - 开发指南
  - 部署说明

- [ ] **编写组件文档**
  - 每个组件的Props说明
  - 使用示例
  - API接口文档

- [ ] **编写迁移总结**
  - 迁移过程记录
  - 遇到的问题与解决方案
  - 经验总结

---

## 7. 风险评估与应对

### 7.1 技术风险

| 风险 | 影响 | 概率 | 应对措施 |
|-----|------|------|---------|
| **高德地图API兼容性** | 🔴 高 | 🟡 中 | - 提前测试Vue3环境下的AMap API<br>- 准备静态图片fallback方案 |
| **ECharts渲染问题** | 🟡 中 | 🟡 中 | - 使用官方推荐的vue-echarts<br>- 参考官方示例代码 |
| **SSE流式数据兼容性** | 🟢 低 | 🟢 低 | - fetch API在Vue3中完全兼容<br>- 提前编写单元测试 |
| **Markdown渲染差异** | 🟡 中 | 🟡 中 | - 对比React版本的渲染结果<br>- 确保GFM语法支持 |
| **TypeScript类型错误** | 🟡 中 | 🟡 中 | - 使用`vue-tsc`进行类型检查<br>- 复用现有类型定义 |

### 7.2 进度风险

| 风险 | 影响 | 概率 | 应对措施 |
|-----|------|------|---------|
| **工期延误** | 🔴 高 | 🟡 中 | - 预留20%缓冲时间<br>- 按优先级迁移,确保核心功能优先完成 |
| **人员变动** | 🟡 中 | 🟢 低 | - 编写详细文档<br>- 代码审查确保质量 |
| **需求变更** | 🟡 中 | 🟡 中 | - 冻结迁移期间的新需求<br>- 迁移完成后再添加新功能 |

### 7.3 质量风险

| 风险 | 影响 | 概率 | 应对措施 |
|-----|------|------|---------|
| **新bug引入** | 🔴 高 | 🔴 高 | - 充分测试每个组件<br>- 使用自动化测试<br>- 灰度发布 |
| **性能下降** | 🟡 中 | 🟡 中 | - 性能基准测试<br>- 使用Chrome DevTools分析 |
| **用户体验差异** | 🟡 中 | 🟡 中 | - UI像素级对比<br>- 用户验收测试 |

### 7.4 回滚方案

如果迁移失败或遇到严重问题,准备以下回滚方案:

1. **保留React版本**: 不删除原有`frontend/`目录,直到Vue3版本稳定运行1个月
2. **双版本并行**: 使用不同端口同时运行两个版本,逐步切换用户
3. **特性开关**: 使用环境变量控制是否启用Vue3版本
   ```bash
   # .env
   VITE_USE_VUE3=true  # 切换为false回退到React版本
   ```

---

## 8. 测试策略

### 8.1 单元测试

使用 **Vitest + @vue/test-utils** 进行组件单元测试

#### 测试框架配置
```bash
npm install -D vitest @vue/test-utils jsdom
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true
  }
})
```

#### 示例测试用例
```typescript
// tests/KpiStrip.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KpiStrip from '@/components/KpiStrip.vue'

describe('KpiStrip.vue', () => {
  it('renders peak value correctly', () => {
    const wrapper = mount(KpiStrip, {
      props: {
        data: {
          peak_value: 120,
          avg_value: 80,
          unit: 'μg/m³'
        }
      }
    })

    expect(wrapper.text()).toContain('120')
    expect(wrapper.text()).toContain('μg/m³')
  })

  it('renders avg value correctly', () => {
    const wrapper = mount(KpiStrip, {
      props: {
        data: {
          peak_value: 120,
          avg_value: 80,
          unit: 'μg/m³'
        }
      }
    })

    expect(wrapper.text()).toContain('80')
  })
})
```

### 8.2 集成测试

测试组件之间的交互和数据流

```typescript
// tests/ChatFlow.spec.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '@/App.vue'

describe('Chat Flow Integration', () => {
  it('submits query and receives results', async () => {
    // Mock API
    vi.mock('@/services/api', () => ({
      callAnalyzeApiStream: vi.fn((req, callbacks) => {
        callbacks.onStep({ step: 'extract_params', status: 'start' })
        callbacks.onResult('weather_analysis', { content: 'test' })
        callbacks.onDone(true, {})
      })
    }))

    const wrapper = mount(App)

    // 打开聊天框
    await wrapper.find('.floating-chat-button').trigger('click')

    // 输入查询
    await wrapper.find('textarea').setValue('测试查询')

    // 提交
    await wrapper.find('button[type="submit"]').trigger('click')

    // 验证结果
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('test')
  })
})
```

### 8.3 E2E测试 (可选)

使用 **Playwright** 进行端到端测试

```bash
npm install -D @playwright/test
```

```typescript
// e2e/analysis.spec.ts
import { test, expect } from '@playwright/test'

test('complete analysis flow', async ({ page }) => {
  await page.goto('http://localhost:5174')

  // 点击AI助手按钮
  await page.click('.floating-chat-button')

  // 输入查询
  await page.fill('textarea', '分析广州天河站2025-08-09的O3污染')

  // 提交
  await page.click('button:has-text("发送")')

  // 等待结果
  await page.waitForSelector('.module-card', { timeout: 30000 })

  // 验证模块卡片渲染
  const cards = await page.$$('.module-card')
  expect(cards.length).toBeGreaterThan(0)

  // 验证地图渲染
  await expect(page.locator('#amap-container')).toBeVisible()
})
```

### 8.4 性能测试

#### 首屏加载时间
```typescript
// tests/performance.spec.ts
import { test } from '@playwright/test'

test('measure first paint time', async ({ page }) => {
  const metrics = await page.evaluate(() => {
    const perfData = performance.getEntriesByType('navigation')[0]
    return {
      domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
      loadComplete: perfData.loadEventEnd - perfData.loadEventStart
    }
  })

  console.log('首屏加载时间:', metrics)
  expect(metrics.domContentLoaded).toBeLessThan(3000) // 目标: 3秒内
})
```

#### Bundle大小分析
```bash
npm run build -- --mode analyze

# 使用 rollup-plugin-visualizer
npm install -D rollup-plugin-visualizer
```

```typescript
// vite.config.ts
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    vue(),
    visualizer({
      open: true,
      filename: 'dist/stats.html'
    })
  ]
})
```

---

## 9. 迁移检查清单

### 环境搭建阶段
- [ ] 创建Vue3项目目录 `frontend-vue/`
- [ ] 安装所有必需依赖 (vue, ant-design-vue, echarts, pinia, etc.)
- [ ] 配置 `vite.config.ts` (路径别名, 代理)
- [ ] 配置 `tsconfig.json` (严格模式, 路径映射)
- [ ] 复制可复用资源 (types/, styles/, services/api.ts)
- [ ] 创建 `main.ts` 入口文件
- [ ] 测试开发服务器启动 (`npm run dev`)

### 基础组件迁移
- [ ] `KpiStrip.vue` - KPI指标条
- [ ] `TextPanel.vue` - Markdown文本面板
- [ ] `FloatingChatButton.vue` - 浮动按钮
- [ ] `StreamProgress.vue` - 流式进度显示
- [ ] 错误边界处理 (Vue3 errorHandler)

### 核心展示组件迁移
- [ ] `ChartsPanel.vue` - ECharts图表面板
  - [ ] 时序图 (timeseries)
  - [ ] 柱状图 (bar)
  - [ ] 饼图 (pie)
  - [ ] 响应式调整
- [ ] `MapPanel.vue` - 高德地图面板
  - [ ] AMap脚本动态加载
  - [ ] 标记点渲染
  - [ ] 风向箭头
  - [ ] 地图事件处理
- [ ] `VisualRenderer.vue` - 可视化路由组件
- [ ] `ModuleCard.vue` - 模块卡片容器

### 复杂交互组件迁移
- [ ] `ChatMessageRenderer.vue` - 聊天消息渲染
  - [ ] 文本消息
  - [ ] 进度消息
  - [ ] 模块卡片消息
- [ ] `ChatOverlay.vue` - 全屏对话界面
  - [ ] 全屏/最小化切换
  - [ ] 消息列表滚动
  - [ ] 输入框处理
  - [ ] 流式数据更新
- [ ] `ChatDock.vue` - 侧边栏对话面板
- [ ] `QueryBar.vue` - 查询输入框
- [ ] `ResizablePanels.vue` - 可调整大小面板

### 根组件集成
- [ ] `App.vue` - 根组件
  - [ ] 整合所有子组件
  - [ ] 状态管理 (Pinia)
  - [ ] 流式数据处理
  - [ ] 错误处理
- [ ] Pinia Store 配置
  - [ ] `stores/analysis.ts` - 分析数据状态
  - [ ] `stores/chat.ts` - 聊天状态

### 组合式函数迁移
- [ ] `composables/useAMapLoader.ts` - 地图加载Hook
- [ ] `composables/useMarkdown.ts` - Markdown渲染Hook (可选)

### 测试
- [ ] 单元测试 (Vitest)
  - [ ] 至少5个核心组件有测试覆盖
- [ ] 集成测试
  - [ ] 完整查询流程测试
- [ ] E2E测试 (Playwright, 可选)
  - [ ] 完整用户流程测试
- [ ] 性能测试
  - [ ] 首屏加载 < 3秒
  - [ ] Bundle大小 < 500KB gzipped
- [ ] 兼容性测试
  - [ ] Chrome
  - [ ] Firefox
  - [ ] Edge
  - [ ] Safari

### 优化
- [ ] 代码拆分 (Code Splitting)
- [ ] 懒加载地图组件
- [ ] ECharts按需加载
- [ ] CSS优化 (移除未使用样式)
- [ ] 图片压缩
- [ ] 启用Gzip压缩

### 部署
- [ ] 构建生产版本 (`npm run build`)
- [ ] 配置Nginx反向代理
- [ ] 配置环境变量
- [ ] 部署到服务器
- [ ] 验证生产环境功能
- [ ] 监控日志和错误

### 文档
- [ ] 更新 `README.md`
- [ ] 编写组件文档
- [ ] 编写迁移总结
- [ ] 编写开发指南
- [ ] 编写部署文档

---

## 附录

### A. 常见问题 FAQ

#### Q1: React的ref在Vue3中如何使用?
**A**: 使用 `ref()` 创建响应式引用
```vue
<script setup lang="ts">
import { ref } from 'vue'

// React: const mapRef = useRef<HTMLDivElement>(null)
const mapRef = ref<HTMLDivElement>()
</script>

<template>
  <!-- React: <div ref={mapRef}> -->
  <div ref="mapRef">...</div>
</template>
```

#### Q2: React的useCallback在Vue3中如何实现?
**A**: Vue3不需要useCallback,函数默认不会重复创建
```vue
<script setup lang="ts">
// 直接定义函数即可
const handleClick = () => {
  console.log('Clicked')
}
</script>
```

#### Q3: 如何在Vue3中实现React的Context?
**A**: 使用 `provide/inject` 或 Pinia
```vue
<!-- 父组件 -->
<script setup lang="ts">
import { provide } from 'vue'

const amapKey = ref('xxx')
provide('amapKey', amapKey)
</script>

<!-- 子组件 -->
<script setup lang="ts">
import { inject } from 'vue'

const amapKey = inject('amapKey')
</script>
```

#### Q4: Vue3如何实现React的useMemo?
**A**: 使用 `computed()`
```vue
<script setup lang="ts">
import { computed } from 'vue'

// React: const fullName = useMemo(() => `${first} ${last}`, [first, last])
const fullName = computed(() => `${first.value} ${last.value}`)
</script>
```

### B. 资源链接

**官方文档**:
- [Vue3官方文档](https://vuejs.org/)
- [Ant Design Vue文档](https://antdv.com/)
- [Pinia文档](https://pinia.vuejs.org/)
- [vue-echarts文档](https://github.com/ecomfe/vue-echarts)

**迁移指南**:
- [从React迁移到Vue3](https://vuejs.org/guide/extras/reactivity-in-depth.html)
- [Vue3 Composition API最佳实践](https://vuejs.org/guide/reusability/composables.html)

**工具**:
- [Vite官方文档](https://vitejs.dev/)
- [Vitest测试框架](https://vitest.dev/)
- [Playwright E2E测试](https://playwright.dev/)

### C. 联系方式

如有问题,请联系:
- 技术负责人: [您的名字]
- 邮箱: [您的邮箱]
- 项目仓库: [Git仓库地址]

---

**文档版本历史**:
- v1.0 (2025-10-21): 初始版本,完整迁移方案

---

**祝迁移顺利! 🎉**
