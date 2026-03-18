# 图表图例位置优化

## 问题描述

用户反馈：时序图底部的图例（legend）遮挡住了横坐标（x轴）的文字标签，导致时间标签无法完整显示。

**表现**:
- 图例与横坐标文字重叠
- 横坐标时间标签被部分遮挡
- 阅读体验不佳

## 解决方案

### 调整图例位置和图表布局

**修改文件**: `frontend/src/components/ChartsPanel.tsx`

#### 1. 图例位置调整

**修改位置**: Line 103-107

**之前**:
```typescript
legend: {
  data: series.map((s: any) => s.name || 'Series'),
  bottom: 10  // 距底部 10px
}
```

**现在**:
```typescript
legend: {
  data: series.map((s: any) => s.name || 'Series'),
  bottom: 0,  // 🔧 调整到最底部（距底部 0px）
  padding: [5, 0, 5, 0]  // 🔧 添加内边距 [上, 右, 下, 左]
}
```

**改动**:
- `bottom: 10` → `bottom: 0`: 图例移到容器最底部
- 添加 `padding: [5, 0, 5, 0]`: 上下各留 5px 内边距，避免紧贴边缘

#### 2. 网格底部空间增加

**修改位置**: Line 108-113

**之前**:
```typescript
grid: {
  left: '12%',
  right: '10%',
  bottom: '15%',  // 底部空间 15%
  top: title ? 50 : 30
}
```

**现在**:
```typescript
grid: {
  left: '12%',
  right: '10%',
  bottom: '20%',  // 🔧 增加到 20% 以容纳图例和横坐标
  top: title ? 50 : 30
}
```

**改动**:
- `bottom: '15%'` → `bottom: '20%'`: 增加 5% 底部空间
- 为图例和横坐标文字留出更多空间

#### 3. 图表高度调整

**修改位置**: Line 277

**之前**:
```typescript
const chartHeight = type === 'bar' ? 350 : 300
```

**现在**:
```typescript
const chartHeight = type === 'bar' ? 350 : 320  // 🔧 时序图增加到 320px
```

**改动**:
- 时序图高度: 300px → 320px（增加 20px）
- 柱状图高度: 350px（保持不变）
- 饼图高度: 320px（增加 20px）

## 效果对比

### 之前（有问题）

```
┌─────────────────────────────────────┐
│          站点浓度时序对比            │
│                                     │
│  [折线图内容]                       │
│                                     │
│  2025-08-09 00:00  05:00  10:00    │ ← X轴标签
│  ○ 目标站点 ○ 国控点 ○ 增城 ○ 从化  │ ← 图例遮挡X轴
└─────────────────────────────────────┘
      ❌ 图例与横坐标重叠
```

### 现在（已优化）

```
┌─────────────────────────────────────┐
│          站点浓度时序对比            │
│                                     │
│  [折线图内容]                       │
│                                     │
│                                     │
│  2025-08-09 00:00  05:00  10:00    │ ← X轴标签清晰
│                                     │
│  ○ 目标站点 ○ 国控点 ○ 增城 ○ 从化  │ ← 图例在最底部
└─────────────────────────────────────┘
      ✅ 图例与横坐标分离，不重叠
```

## 布局说明

### 图表垂直空间分配

**总高度**: 320px

**空间分配**:
```
┌─────────────────────┐
│ 标题区域 (50px)     │ ← title 存在时
├─────────────────────┤
│ 绘图区域 (约 200px) │ ← grid 区域
│                     │
│  [图表内容]         │
│                     │
├─────────────────────┤
│ X轴标签 (约 30px)   │ ← 横坐标文字
├─────────────────────┤
│ 图例区域 (约 40px)  │ ← legend (bottom: 0)
└─────────────────────┘
```

### Grid 配置详解

```typescript
grid: {
  left: '12%',   // 左侧留白 12% (Y轴单位)
  right: '10%',  // 右侧留白 10% (双Y轴预留)
  bottom: '20%', // 底部留白 20% (X轴 + 图例)
  top: 50        // 顶部留白 50px (标题)
}
```

**bottom: '20%' 包含**:
1. X 轴刻度标签高度：约 20px
2. 图例高度：约 40px
3. 间隔空间：约 4px
4. 总计约：64px (20% of 320px)

### Legend 配置详解

```typescript
legend: {
  data: [...],
  bottom: 0,              // 距容器底部 0px
  padding: [5, 0, 5, 0]   // 上下内边距各 5px
}
```

**padding 参数**:
- `[上, 右, 下, 左]` 顺序（CSS 标准）
- `[5, 0, 5, 0]`: 上下各 5px，左右 0px
- 防止图例文字紧贴容器边缘

## ECharts 图例定位

### bottom 参数

**类型**: `number | string`

**值含义**:
- `0`: 距底部 0 像素
- `10`: 距底部 10 像素
- `'20%'`: 距底部容器高度的 20%

**当前使用**: `bottom: 0`（紧贴底部）

### 其他定位参数（未使用）

```typescript
legend: {
  // 水平位置
  left: 'center',   // 左、右、中
  right: 10,

  // 垂直位置
  top: 10,          // 距顶部
  bottom: 0,        // 距底部

  // 方向
  orient: 'horizontal'  // 水平（默认）| vertical（垂直）
}
```

## 适配不同场景

### 场景 1: 单条折线（图例项少）

**效果**: 图例占用空间小，横坐标完全可见

### 场景 2: 多条折线（图例项多）

**当前配置**:
- 4-5 个图例项：单行显示
- 超过 5 个：可能换行

**如果图例项过多**，可启用滚动：
```typescript
legend: {
  type: 'scroll',  // 启用滚动图例
  bottom: 0
}
```

### 场景 3: 无图例

**如果 series.length === 1**:
- 可以隐藏图例
- 释放更多空间给绘图区

```typescript
legend: {
  show: series.length > 1,  // 单条曲线时隐藏图例
  bottom: 0
}
```

## 时序图与柱状图对比

| 图表类型 | 高度 | bottom | 图例位置 | 说明 |
|---------|------|--------|---------|------|
| 时序图 | 320px | 20% | bottom: 0 | 需容纳图例和X轴标签 |
| 柱状图 | 350px | 20% | bottom: 0 | 需容纳旋转标签 |
| 饼图 | 320px | - | left: 'left' | 图例在左侧，垂直布局 |

## 响应式优化

### 小屏幕适配

**当前**: 固定高度 320px

**优化方向**: 根据容器宽度动态调整
```typescript
const chartHeight = useMemo(() => {
  const containerWidth = chartRef.current?.offsetWidth || 600
  if (containerWidth < 400) return 280  // 小屏
  if (containerWidth < 600) return 320  // 中屏
  return 320  // 大屏
}, [])
```

### 图例自适应

**启用滚动图例** (多个系列时):
```typescript
legend: {
  type: series.length > 5 ? 'scroll' : 'plain',
  bottom: 0,
  pageButtonPosition: 'end'  // 翻页按钮位置
}
```

## 相关文件

```
frontend/src/components/
└── ChartsPanel.tsx  ← 修改：调整图例位置、grid.bottom、图表高度
```

## 测试检查点

### 1. 时序图（站点浓度对比）

**测试场景**:
- 4 个站点（目标站点、国控点、增城、从化）
- 24 小时数据

**检查项**:
- ✅ X 轴时间标签完整显示，无遮挡
- ✅ 图例在 X 轴标签下方
- ✅ 图例与 X 轴标签有明显间隔
- ✅ 图例不超出图表容器

### 2. 时序图（O3 与 AQI 综合）

**测试场景**:
- 5 个系列（O3、AQI、温度、湿度、风速）

**检查项**:
- ✅ 5 个图例项是否单行显示
- ✅ 如换行，是否与 X 轴标签有足够间距

### 3. 全屏模式

**检查项**:
- ✅ 全屏时图表高度是否适应
- ✅ 图例位置保持在底部
- ✅ X 轴标签清晰可读

### 4. 不同分辨率

**测试分辨率**:
- 1920x1080（常规桌面）
- 1366x768（笔记本）
- < 768px（移动端）

**检查项**:
- ✅ 各分辨率下图例不遮挡横坐标
- ✅ 图表高度适中

## 未来优化

### 1. 智能图例布局

**根据图例项数量自动选择布局**:
```typescript
const legendConfig = useMemo(() => {
  const itemCount = series.length

  if (itemCount <= 3) {
    // 少量图例：水平居中
    return {
      orient: 'horizontal',
      left: 'center',
      bottom: 0
    }
  } else if (itemCount <= 6) {
    // 中等数量：水平左对齐
    return {
      orient: 'horizontal',
      left: 'left',
      bottom: 0
    }
  } else {
    // 大量图例：启用滚动
    return {
      type: 'scroll',
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      pageButtonPosition: 'end'
    }
  }
}, [series])
```

### 2. 自定义图例样式

**优化视觉效果**:
```typescript
legend: {
  bottom: 0,
  padding: [5, 0, 5, 0],
  itemGap: 15,  // 图例项间距
  itemWidth: 25,  // 图例标记宽度
  itemHeight: 14,  // 图例标记高度
  textStyle: {
    fontSize: 12,
    color: '#57606a'
  }
}
```

### 3. 图例交互优化

**点击图例切换系列显示/隐藏**:
```typescript
legend: {
  bottom: 0,
  selectedMode: 'multiple',  // 允许多选
  inactiveColor: '#ccc'  // 未选中时的颜色
}
```

### 4. 动态调整 grid.bottom

**根据实际图例高度动态调整**:
```typescript
const calculateBottomSpace = () => {
  const legendHeight = 40  // 图例实际高度
  const xAxisLabelHeight = 20  // X轴标签高度
  const padding = 10  // 间距
  const total = legendHeight + xAxisLabelHeight + padding
  return `${(total / chartHeight) * 100}%`
}
```

## 总结

✅ **已完成**: 图表图例位置优化，避免遮挡横坐标文字
✅ **调整内容**:
  - 图例移到容器最底部（bottom: 0）
  - 增加 grid.bottom 从 15% 到 20%
  - 时序图高度从 300px 增加到 320px
  - 添加图例内边距

**核心改动**:
- ChartsPanel.tsx: 调整 legend、grid、chartHeight

**效果**:
- 横坐标文字完整显示，不被遮挡
- 图例与 X 轴标签有明显间隔
- 整体布局更合理，阅读体验更好

刷新浏览器（Ctrl+F5）测试，图例现在应该不会遮挡横坐标文字了！
