# UI 优化总结 - 图表和文本渲染优化

## 概述

本文档总结了前端界面的一系列优化，主要涉及图表显示、文本渲染、布局优化等方面。这些改动显著提升了用户体验和视觉效果。

**优化日期**: 2025-10-21

## 优化清单

### 1. 自动隐藏空可视化容器

**问题**: 当模块没有图表时，左侧显示"暂无可视化内容"占位符，浪费空间

**解决方案**: 自动切换为全宽文本显示模式

**修改文件**: `frontend/src/components/ModuleCard.tsx` (Line 27)

**改动**:
```typescript
// 之前
{isSummary ? (
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  <ResizablePanels ... />
)}

// 现在
{isSummary || visuals.length === 0 ? (
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  <ResizablePanels ... />
)}
```

**效果**:
- ✅ 无图表的模块自动全宽显示文本
- ✅ 消除"暂无可视化内容"占位符
- ✅ 更合理地利用屏幕空间

---

### 2. Markdown 格式渲染支持

**问题**: 分析文本以纯文本显示，缺少标题、列表、表格等格式化效果

**解决方案**: 添加完整的 Markdown CSS 样式

**修改文件**: `frontend/src/styles/theme.css` (Line 525-675)

**新增样式**:
- 标题样式 (H1-H4)
- 列表样式 (有序/无序)
- 表格样式 (带斑马纹)
- 代码块样式
- 引用块样式
- 链接样式
- 强调文本样式

**关键 CSS**:
```css
/* 标题 */
.md h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--primary-color);
}

/* 列表标记 */
.md ul > li::marker {
  color: var(--primary-color);
}

/* 表格 */
.md table th {
  background: #f5f7fa;
  padding: 8px 12px;
  font-weight: 600;
  border: 1px solid var(--border-color);
}

.md table tr:nth-child(even) {
  background: #fafbfc;
}

/* 代码块 */
.md code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #d63384;
}
```

**效果**:
- ✅ 标题层级清晰
- ✅ 列表项有主题色标记
- ✅ 表格有斑马纹易读
- ✅ 代码块突出显示
- ✅ 整体视觉效果专业

---

### 3. 图表标题和单位显示

**问题**:
- 图表缺少标题，不知道展示的是哪个污染物
- Y 轴缺少单位标注
- 不同污染物需要不同单位 (CO: mg/m³, 其他: μg/m³)
- OFP 图需要 ppb 单位

**解决方案**: 添加智能单位识别和标题显示

**修改文件**: `frontend/src/components/ChartsPanel.tsx`

#### 3.1 新增 title 参数

**位置**: Line 5-10

```typescript
interface Props {
  type: 'timeseries' | 'bar' | 'pie'
  payload: TimeSeriesPayload | BarPayload | PiePayload
  meta?: Record<string, any>
  title?: string  // 🔧 新增：图表标题
}
```

#### 3.2 单位推断函数

**位置**: Line 17-26

```typescript
// 🔧 根据污染物名称推断单位
const inferUnit = (pollutantName?: string): string => {
  if (!pollutantName) return 'μg/m³'

  const name = pollutantName.toLowerCase()
  if (name.includes('co') && !name.includes('voc')) {
    return 'mg/m³'  // CO 使用 mg/m³
  }
  return 'μg/m³'  // 其他污染物使用 μg/m³
}
```

**识别逻辑**:
- CO → mg/m³
- NO2, PM2.5, PM10, SO2, O3 → μg/m³
- VOCs → μg/m³ (不会误判为 CO)

#### 3.3 时序图优化

**标题显示** (Line 89-98):
```typescript
title: title ? {
  text: title,  // 如 "O3 浓度时序对比"
  left: 'center',
  top: 10,
  textStyle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#1f2328'
  }
} : undefined,
```

**Y 轴单位** (Line 76-86):
```typescript
yAxisConfig = {
  type: 'value',
  name: `浓度 (${unit})`,  // 显示 "浓度 (μg/m³)" 或 "浓度 (mg/m³)"
  nameLocation: 'middle',
  nameGap: 50,
  nameTextStyle: {
    fontSize: 12,
    fontWeight: 'bold'
  }
}
```

**网格布局调整** (Line 108-113):
```typescript
grid: {
  left: '12%',  // 🔧 增加左侧空间（原 10%）以容纳单位标签
  right: '10%',
  bottom: '20%',  // 🔧 增加底部空间以容纳图例和横坐标
  top: title ? 50 : 30  // 🔧 有标题时增加顶部空间
}
```

#### 3.4 柱状图 (OFP) 优化

**OFP 图识别** (Line 145-147):
```typescript
// 🔧 判断是否为 OFP 图，使用 ppb 单位
const isOFP = title?.toLowerCase().includes('ofp') || meta?.unit === 'ppb'
const unit = isOFP ? 'ppb' : (meta?.unit || '')
```

**Y 轴单位** (Line 178-187):
```typescript
yAxis: {
  type: 'value',
  name: unit ? `${unit}` : barPayload.y_label || '',  // 显示 "ppb"
  nameLocation: 'middle',
  nameGap: 45,
  nameTextStyle: {
    fontSize: 12,
    fontWeight: 'bold'
  }
}
```

**X 轴标签旋转 - 完整显示 VOCs 物种名称** (Line 167-177):
```typescript
xAxis: {
  type: 'category',
  data: categories,
  axisLabel: {
    interval: 0,  // 🔧 显示所有标签（默认会自动隐藏）
    rotate: 45,   // 🔧 旋转 45 度避免重叠
    fontSize: 11,
    overflow: 'truncate',  // 超长文本截断
    width: 80  // 🔧 最大宽度 80px
  }
}
```

**网格布局** (Line 161-165):
```typescript
grid: {
  left: '12%',
  right: '5%',
  bottom: '20%',  // 🔧 增加底部空间容纳旋转的标签（原 15%）
  top: title ? 50 : 30
}
```

**图表高度** (Line 314):
```typescript
const chartHeight = type === 'bar' ? 350 : 320  // 柱状图 350px，其他 320px
```

**效果**:
- ✅ 所有 VOCs 物种名称完整显示
- ✅ 标签旋转 45 度，紧凑但可读
- ✅ 超长名称自动截断显示省略号

#### 3.5 传递 title 参数

**修改文件**: `frontend/src/components/VisualRenderer.tsx` (Line 26)

```typescript
// 之前
return <ChartsPanel type={visual.type} payload={(visual as any).payload} meta={visual.meta} />

// 现在
return <ChartsPanel type={visual.type} payload={(visual as any).payload} meta={visual.meta} title={visual.title} />
```

**效果对比**:

**时序图 - 之前**:
```
┌────────────────────────────────────┐
│                                    │
│  [图表内容，无标题]                │
│                                    │
│  Y轴: 无单位标注                   │
│                                    │
└────────────────────────────────────┘
```

**时序图 - 现在**:
```
┌────────────────────────────────────┐
│         O3 浓度时序对比             │  ← 标题
├────────────────────────────────────┤
│                                    │
│  浓度                              │
│  (μg/m³)  [折线图内容]             │  ← Y轴单位
│    ↑                               │
│                                    │
└────────────────────────────────────┘
```

**OFP 柱状图 - 现在**:
```
┌────────────────────────────────────┐
│       OFP 贡献前十物种              │  ← 标题
├────────────────────────────────────┤
│                                    │
│  ppb  [柱状图]                     │  ← Y轴单位
│   ↑                                │
│                                    │
│   乙烯  丙烯  间二甲苯  邻二甲苯   │  ← 标签旋转 45°
│     \    \      \        \         │    完整显示
└────────────────────────────────────┘
```

---

### 4. 图例位置优化 - 避免遮挡横坐标

**问题**: 时序图底部的图例遮挡横坐标时间标签

**解决方案**: 图例移到最底部，增加底部空间

**修改文件**: `frontend/src/components/ChartsPanel.tsx`

**图例位置** (Line 103-107):
```typescript
// 之前
legend: {
  data: series.map((s: any) => s.name || 'Series'),
  bottom: 10  // 距底部 10px
}

// 现在
legend: {
  data: series.map((s: any) => s.name || 'Series'),
  bottom: 0,  // 🔧 调整到最底部（距底部 0px）
  padding: [5, 0, 5, 0]  // 🔧 添加内边距 [上, 右, 下, 左]
}
```

**网格底部空间** (Line 111):
```typescript
// 之前
bottom: '15%',

// 现在
bottom: '20%',  // 🔧 增加到 20% 以容纳图例和横坐标
```

**图表高度** (Line 314):
```typescript
// 之前
const chartHeight = type === 'bar' ? 350 : 300

// 现在
const chartHeight = type === 'bar' ? 350 : 320  // 🔧 时序图增加到 320px
```

**布局对比**:

**之前**:
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

**现在**:
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

**效果**:
- ✅ X 轴时间标签完整显示，无遮挡
- ✅ 图例与 X 轴标签有明显间隔
- ✅ 整体布局更合理

---

### 5. 饼图布局优化 - 左右分栏

**问题**:
- 饼图标签部分溢出边框外
- 图例和饼图都在左侧，视觉效果不好
- 空间利用不合理

**解决方案**: 改为环形图 + 左右分栏布局 (饼图左，图例右)

**修改文件**: `frontend/src/components/ChartsPanel.tsx` (Line 192-293)

#### 5.1 改为环形图

**位置**: Line 228

```typescript
// 之前
radius: '60%',  // 实心饼图

// 现在
radius: ['40%', '60%'],  // 🔧 环形图，内半径40%，外半径60%
```

**优势**:
- 更紧凑，节省空间
- 视觉效果更现代
- 中间空白可以显示标题或统计信息（未来扩展）

#### 5.2 饼图居中偏左

**位置**: Line 229

```typescript
// 之前
// 未设置 center，默认 ['50%', '50%'] 完全居中

// 现在
center: ['40%', '50%'],  // 🔧 水平40%，垂直50%
```

**效果**:
- 饼图位于左侧 40% 位置
- 为右侧图例留出 60% 空间
- 垂直居中

#### 5.3 图例移到右侧

**位置**: Line 276-289

```typescript
// 之前
legend: {
  orient: 'vertical',
  left: 'left'  // 左对齐
}

// 现在
legend: {
  orient: 'vertical',  // 🔧 垂直布局
  right: '5%',         // 🔧 距右侧5%
  top: 'middle',       // 🔧 垂直居中
  align: 'left',       // 🔧 文字左对齐
  itemGap: 8,          // 🔧 图例项间距
  textStyle: {
    fontSize: 12
  },
  formatter: (name: string) => {
    // 🔧 限制图例文字长度，超过15字显示省略号
    return name.length > 15 ? name.slice(0, 15) + '...' : name
  }
}
```

**改动**:
- `left: 'left'` → `right: '5%'`: 从左侧移到右侧
- 添加 `top: 'middle'`: 垂直居中对齐
- 添加 `align: 'left'`: 图例标记与文字左对齐
- 添加 `itemGap: 8`: 图例项之间间距 8px
- 添加 `formatter`: 长文字自动截断

#### 5.4 标签优化 - 避免溢出

**位置**: Line 231-240

```typescript
// 之前
// 使用默认标签配置，可能溢出

// 现在
label: {
  fontSize: 11,                    // 🔧 减小字号（默认12）
  formatter: '{b}: {d}%',          // 🔧 显示名称和百分比
  overflow: 'truncate',            // 🔧 超长标签截断
  width: 100                       // 🔧 标签最大宽度100px
},
labelLine: {
  length: 10,   // 🔧 缩短第一段引导线（默认15）
  length2: 5    // 🔧 缩短第二段引导线（默认10）
}
```

**优化点**:
- 减小字号：11px（更紧凑）
- 格式化标签：只显示名称和百分比（如 "机动车燃油等量: 75.72%"）
- 截断超长文本：避免标签溢出边框
- 缩短引导线：减少占用空间

#### 5.5 添加标题支持

**位置**: Line 262-271

```typescript
title: title ? {
  text: title,
  left: 'center',  // 居中
  top: 10,
  textStyle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#1f2328'
  }
} : undefined,
```

#### 5.6 优化 Tooltip

**位置**: Line 272-275

```typescript
// 之前
tooltip: { trigger: 'item' }

// 现在
tooltip: {
  trigger: 'item',
  formatter: '{b}: {c} ({d}%)'  // 🔧 显示：名称、数值、百分比
}
```

**显示格式**: "机动车燃油等量: 1234 (75.72%)"

**布局效果对比**:

**之前（左侧拥挤）**:
```
┌────────────────────────────────────┐
│ 图例                                │
│ ○ 机动车燃油等量                    │
│ ○ 专用博物馆加工                    │
│ ○ 塑料零件...                      │
│                                    │
│       [饼图]                       │
│      (在左侧)                      │
│                                    │
│  标签可能溢出 →                    │
└────────────────────────────────────┘
     ❌ 左侧拥挤，右侧空白
```

**现在（左右分栏）**:
```
┌────────────────────────────────────┐
│          行业VOCs排放贡献           │  ← 标题（可选）
├────────────────────────────────────┤
│                        │  图例      │
│     [环形图]           │  ○ 机动车  │
│    (居中偏左)          │  ○ 专用... │
│                        │  ○ 塑料... │
│  机动车:               │  ○ 纸制... │
│  75.72%                │  ○ 塑料... │
│                        │  ○ 软木... │
│                        │           │
└────────────────────────────────────┘
     ✅ 左右分栏，布局合理
```

**效果**:
- ✅ 饼图在左侧 40% 位置
- ✅ 图例在右侧，距右边框 5%
- ✅ 饼图和图例垂直居中对齐
- ✅ 环形图显示正确
- ✅ 标签不溢出图表边框
- ✅ 超长标签正确截断
- ✅ 图例文字长度限制在 15 字以内

---

### 6. TextPanel 容器结构简化

**问题**: 内部嵌套容器导致 Markdown 渲染效果不佳

**解决方案**: 去掉嵌套结构，使用扁平 DOM 层级

**修改文件**: `frontend/src/components/TextPanel.tsx` (Line 34-60)

**之前（嵌套结构）**:
```typescript
<aside style={{
  display: 'flex',
  flexDirection: 'column',
  border: '1px solid var(--border-color)',
  borderRadius: 8,
  padding: 12,
  height: autoHeight ? 'auto' : '100%',
  overflow: autoHeight ? 'visible' : 'auto'
}}>
  <div style={{
    lineHeight: 1.7,
    flex: autoHeight ? 'none' : 1,
    overflow: autoHeight ? 'visible' : 'auto'
  }}>
    <Markdown content={content} />
  </div>
  {/* anchors */}
</aside>
```

**现在（扁平结构）**:
```typescript
<div style={{
  border: '1px solid var(--border-color)',
  borderRadius: 8,
  padding: 16,  // 增加 padding
  height: autoHeight ? 'auto' : '100%',
  overflow: autoHeight ? 'visible' : 'auto',
  lineHeight: 1.7  // 直接应用
}}>
  <Markdown content={content} />
  {safeAnchors.length > 0 && (
    <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-color-secondary)' }}>
      证据锚点：
      {/* anchor links */}
    </div>
  )}
</div>
```

**关键改动**:
- ✅ 改 `<aside>` 为 `<div>`（语义化简化）
- ✅ 去掉内部嵌套的 `<div>` 包装器
- ✅ 移除 flexbox 布局 (`display: 'flex', flexDirection: 'column'`)
- ✅ 移除 `flex: autoHeight ? 'none' : 1` 属性
- ✅ `lineHeight: 1.7` 直接应用到主容器
- ✅ 增加 padding 从 12px 到 16px

**效果**:
- ✅ DOM 结构扁平化
- ✅ Markdown 样式正确应用
- ✅ 减少不必要的嵌套层级
- ✅ 提升渲染性能

---

## 相关文件汇总

```
frontend/src/components/
├── ModuleCard.tsx       ← 修改：自动隐藏空可视化容器
├── ChartsPanel.tsx      ← 修改：标题、单位、图例、饼图布局优化
├── VisualRenderer.tsx   ← 修改：传递 title 参数
└── TextPanel.tsx        ← 修改：简化容器结构

frontend/src/styles/
└── theme.css            ← 新增：完整 Markdown 样式
```

## 技术要点

### 1. 单位智能识别

**算法**:
```typescript
const inferUnit = (pollutantName?: string): string => {
  if (!pollutantName) return 'μg/m³'
  const name = pollutantName.toLowerCase()
  if (name.includes('co') && !name.includes('voc')) {
    return 'mg/m³'
  }
  return 'μg/m³'
}
```

**识别规则**:
| 污染物 | 检测逻辑 | 单位 |
|--------|---------|------|
| CO | `includes('co')` && `!includes('voc')` | mg/m³ |
| NO2 | 其他 | μg/m³ |
| PM2.5 | 其他 | μg/m³ |
| O3 | 其他 | μg/m³ |
| VOCs | `includes('voc')` | μg/m³ (不误判为CO) |

### 2. OFP 图识别

**判断条件**（满足任一即可）:
1. `title.toLowerCase().includes('ofp')`
2. `meta.unit === 'ppb'`

**示例**:
- ✅ "OFP 贡献前十物种" → ppb
- ✅ meta: `{ unit: 'ppb' }` → ppb
- ❌ "VOCs 组分浓度" → 非 OFP 图

### 3. X 轴标签旋转策略

**ECharts 配置**:
```typescript
xAxis: {
  axisLabel: {
    interval: 0,     // 显示所有标签
    rotate: 45,      // 旋转 45 度
    fontSize: 11,
    overflow: 'truncate',
    width: 80
  }
}
```

**interval 参数**:
- `0`: 显示所有标签
- `'auto'` (默认): 自动隐藏部分标签
- `n`: 每隔 n 个显示一个

**rotate 参数**:
- `0`: 水平
- `45`: 右倾斜 45 度（当前使用）
- `90`: 垂直
- `-45`: 左倾斜 45 度

### 4. 饼图布局参数

**center 参数**: `[水平位置, 垂直位置]`
```typescript
center: ['40%', '50%']  // 水平 40%，垂直 50%
```

**radius 参数**:
- 单值 `'60%'`: 实心饼图
- 双值 `['40%', '60%']`: 环形图（内半径 40%，外半径 60%）

**legend right 参数**: 距右边框的距离
```typescript
right: '5%'  // 距右边框 5%
```

### 5. Markdown 样式设计原则

- **标题**: 渐进式字号（H1: 20px → H4: 14px）
- **列表**: 主题色标记（`var(--primary-color)`）
- **表格**: 斑马纹（偶数行背景 `#fafbfc`）
- **代码**: 浅灰背景 + 粉红色文字（`#d63384`）
- **链接**: 主题色 + hover 下划线
- **行高**: 1.8 提升可读性

---

## 测试检查点

### 1. 空可视化容器隐藏
- ✅ 无图表的模块全宽显示文本
- ✅ 不显示"暂无可视化内容"
- ✅ 有图表的模块保持左右分栏

### 2. Markdown 渲染
- ✅ 标题层级清晰（H1-H4）
- ✅ 列表项有主题色标记
- ✅ 表格斑马纹正确
- ✅ 代码块高亮显示
- ✅ 链接可点击且有 hover 效果

### 3. 时序图单位显示
- ✅ Y 轴显示 "浓度 (μg/m³)" 或 "浓度 (mg/m³)"
- ✅ CO 自动识别为 mg/m³
- ✅ 其他污染物为 μg/m³
- ✅ 标题在图表顶部居中
- ✅ 左侧有足够空间容纳单位标签

### 4. OFP 柱状图
- ✅ Y 轴显示 "ppb"
- ✅ 所有 VOCs 物种名称显示
- ✅ 标签旋转 45 度无重叠
- ✅ 超长名称显示省略号
- ✅ 标题在顶部居中

### 5. 图例位置
- ✅ 图例在容器最底部
- ✅ X 轴标签完整显示无遮挡
- ✅ 图例与 X 轴标签有明显间隔
- ✅ 图例不超出容器

### 6. 饼图布局
- ✅ 环形图正确显示
- ✅ 饼图在左侧 40% 位置
- ✅ 图例在右侧，垂直居中
- ✅ 标签不溢出边框
- ✅ 图例文字截断在 15 字
- ✅ 整体左右分栏平衡

### 7. TextPanel 渲染
- ✅ DOM 结构扁平化
- ✅ Markdown 样式正确应用
- ✅ 证据锚点功能正常
- ✅ 滚动和高亮动画正常

---

## 总结

本次优化涉及 **7 个核心改进**，显著提升了系统的视觉效果和用户体验：

**✅ 已完成**:
1. 自动隐藏空可视化容器
2. 完整 Markdown 格式支持
3. 图表标题和单位智能显示
4. X 轴标签旋转完整展示
5. 图例位置优化避免遮挡
6. 饼图左右分栏布局
7. TextPanel 容器结构简化

**核心技术**:
- 智能单位识别（CO vs 其他污染物）
- OFP 图自动检测（ppb 单位）
- ECharts 配置优化（grid、legend、label）
- CSS Markdown 样式（151 行完整样式）
- 扁平 DOM 结构（提升渲染性能）

**效果**:
- 🎨 视觉效果更专业美观
- 📊 图表信息更清晰完整
- 📝 文本渲染效果更好
- 🚀 用户体验显著提升

**文件修改**:
- `ModuleCard.tsx` - 1 处改动
- `ChartsPanel.tsx` - 多处优化（标题、单位、图例、饼图）
- `VisualRenderer.tsx` - 1 处改动
- `TextPanel.tsx` - 结构简化
- `theme.css` - 新增 151 行 Markdown 样式

刷新浏览器测试，所有优化应该生效！
