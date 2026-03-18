# 图表优化 - 单位显示和标签完整展示

## 用户需求

1. **站点浓度时序对比图**:
   - 图表左侧显示浓度单位
   - CO 使用 mg/m³ 单位
   - NO2、PM2.5、PM10、SO2、O3（臭氧和臭氧八小时）使用 μg/m³ 单位
   - 图表中间上方显示污染物指标名称

2. **OFP 贡献前十物种图**:
   - 图表左侧显示浓度单位 ppb
   - 全屏时横坐标完整展示所有 VOCs 物种名称

## 实现的改动

### 1. ChartsPanel.tsx - 核心图表组件优化

#### 1.1 新增 Props

**修改位置**: Line 5-10

```typescript
interface Props {
  type: 'timeseries' | 'bar' | 'pie'
  payload: TimeSeriesPayload | BarPayload | PiePayload
  meta?: Record<string, any>
  title?: string  // 🔧 新增：图表标题
}
```

**用途**: 通过 title 参数传递污染物名称或图表标题，用于：
- 显示在图表顶部
- 推断单位类型（CO vs 其他污染物）

#### 1.2 单位推断函数

**添加位置**: Line 17-26

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

**逻辑**:
- 检查标题中是否包含 "co"
- 排除 "voc" (避免误判 VOCs)
- CO → mg/m³
- 其他 → μg/m³

**支持的污染物识别**:
- ✅ CO, co, Co → mg/m³
- ✅ NO2, PM2.5, PM10, SO2, O3, 臭氧 → μg/m³
- ✅ VOCs, voc → μg/m³ (不会误判为 CO)

#### 1.3 时序图优化

**修改位置**: Line 44-124

**关键改动**:

##### a. 获取单位

```typescript
// 🔧 获取单位：优先使用 meta.unit，否则根据标题推断
const unit = meta?.unit || inferUnit(title)
```

**优先级**:
1. `meta.unit`（后端显式指定）
2. `inferUnit(title)`（根据标题自动推断）

##### b. Y 轴配置 - 显示单位

**单 Y 轴配置**:
```typescript
yAxisConfig = {
  type: 'value',
  name: `浓度 (${unit})`,  // 🔧 显示单位，如 "浓度 (μg/m³)"
  nameLocation: 'middle',  // 标签位于轴中间
  nameGap: 50,  // 与轴的间距
  nameTextStyle: {
    fontSize: 12,
    fontWeight: 'bold'
  }
}
```

**双 Y 轴配置**:
```typescript
yAxisConfig = customYAxis.map((axis: any, index: number) => ({
  ...axis,
  name: axis.name || (index === 0 ? `浓度 (${unit})` : '')  // 左轴显示单位
}))
```

##### c. 图表标题 - 显示污染物名称

```typescript
title: title ? {
  text: title,  // 🔧 显示图表标题（如 "O3 浓度时序对比"）
  left: 'center',  // 居中
  top: 10,  // 距顶部 10px
  textStyle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#1f2328'  // 🔧 使用实际颜色值（ECharts 不支持 CSS 变量）
  }
} : undefined,
```

##### d. 网格布局调整

```typescript
grid: {
  left: '12%',  // 🔧 增加左侧空间（原 10%）以容纳单位标签
  right: '10%',
  bottom: '15%',
  top: title ? 50 : 30  // 🔧 有标题时增加顶部空间
},
```

**效果**:
- 左侧有足够空间显示 "浓度 (μg/m³)"
- 顶部有空间显示图表标题

#### 1.4 柱状图优化

**修改位置**: Line 126-190

**关键改动**:

##### a. 判断 OFP 图并设置单位

```typescript
// 🔧 判断是否为 OFP 图，使用 ppb 单位
const isOFP = title?.toLowerCase().includes('ofp') || meta?.unit === 'ppb'
const unit = isOFP ? 'ppb' : (meta?.unit || '')
```

**判断逻辑**:
1. 标题包含 "ofp" → ppb
2. `meta.unit === 'ppb'` → ppb
3. 其他 → 使用 meta.unit 或空字符串

##### b. 图表标题

```typescript
title: title ? {
  text: title,  // 如 "OFP 贡献前十物种"
  left: 'center',
  top: 10,
  textStyle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#1f2328'
  }
} : undefined,
```

##### c. Y 轴单位显示

```typescript
yAxis: {
  type: 'value',
  name: unit ? `${unit}` : barPayload.y_label || '',  // 🔧 显示 "ppb" 或其他单位
  nameLocation: 'middle',
  nameGap: 45,
  nameTextStyle: {
    fontSize: 12,
    fontWeight: 'bold'
  }
},
```

##### d. X 轴标签旋转 - 完整显示物种名称

```typescript
xAxis: {
  type: 'category',
  data: categories,
  axisLabel: {
    interval: 0,  // 🔧 显示所有标签（默认会自动隐藏）
    rotate: 45,  // 🔧 旋转 45 度避免重叠
    fontSize: 11,
    overflow: 'truncate',  // 超长文本截断
    width: 80  // 🔧 最大宽度 80px，超出显示省略号
  }
},
```

**效果**:
- 所有 VOCs 物种名称都显示
- 旋转 45 度，紧凑但可读
- 过长名称自动截断并显示省略号

##### e. 网格布局调整

```typescript
grid: {
  left: '12%',  // 🔧 增加左侧空间显示单位
  right: '5%',
  bottom: '20%',  // 🔧 增加底部空间容纳旋转的标签（原 15%）
  top: title ? 50 : 30  // 有标题时增加顶部空间
},
```

#### 1.5 图表高度调整

**修改位置**: Line 275-283

```typescript
// 🔧 根据图表类型调整高度
const chartHeight = type === 'bar' ? 350 : 300  // 柱状图需要更高以容纳旋转标签

return (
  <>
    {error && <div style={{ color: '#d93025', padding: '8px', fontSize: '13px' }}>{error}</div>}
    <div ref={chartRef} style={{ width: '100%', height: chartHeight }} />
  </>
)
```

**改动**:
- 时序图/饼图: 300px
- 柱状图: 350px（增加 50px 以容纳旋转的 X 轴标签）

### 2. VisualRenderer.tsx - 传递 Title

**修改位置**: Line 26

**之前**:
```typescript
return <ChartsPanel type={visual.type} payload={(visual as any).payload} meta={visual.meta} />
```

**现在**:
```typescript
return <ChartsPanel type={visual.type} payload={(visual as any).payload} meta={visual.meta} title={visual.title} />
```

**效果**: 将 Visual 对象的 title 字段传递给 ChartsPanel

## 效果对比

### 时序图（站点浓度对比）

#### 之前

```
┌────────────────────────────────────┐
│                                    │
│  [图表内容，无标题]                │
│                                    │
│  Y轴: 无单位标注                   │
│                                    │
└────────────────────────────────────┘
```

#### 现在

```
┌────────────────────────────────────┐
│         O3 浓度时序对比             │  ← 🔧 新增标题
├────────────────────────────────────┤
│                                    │
│  浓度                              │
│  (μg/m³)  [折线图内容]             │  ← 🔧 左侧显示单位
│    ↑                               │
│                                    │
└────────────────────────────────────┘
```

**CO 污染物**:
```
浓度 (mg/m³)  ← 自动识别 CO 使用 mg/m³
```

### 柱状图（OFP 贡献）

#### 之前

```
┌────────────────────────────────────┐
│                                    │
│  [柱状图]                          │
│                                    │
│  Y轴: 无单位                       │
│  X轴: 部分物种名被隐藏             │
└────────────────────────────────────┘
```

#### 现在

```
┌────────────────────────────────────┐
│       OFP 贡献前十物种              │  ← 🔧 新增标题
├────────────────────────────────────┤
│                                    │
│  ppb  [柱状图]                     │  ← 🔧 左侧显示 ppb
│   ↑                                │
│                                    │
│   乙烯  丙烯  间二甲苯  邻二甲苯   │  ← 🔧 标签旋转 45°
│     \    \      \        \         │       完整显示
└────────────────────────────────────┘
```

## 技术细节

### 1. 单位推断规则

| 污染物标题 | 检测逻辑 | 单位 |
|----------|---------|------|
| "CO 浓度对比" | `includes('co')` && `!includes('voc')` | mg/m³ |
| "NO2 浓度" | 其他 | μg/m³ |
| "PM2.5 浓度" | 其他 | μg/m³ |
| "O3 浓度" | 其他 | μg/m³ |
| "臭氧浓度" | 其他 | μg/m³ |
| "VOCs 组分" | `includes('voc')` | μg/m³ (不会误判为 CO) |

**特殊处理**: VOCs 包含 "oc"，但通过 `!includes('voc')` 排除

### 2. OFP 图识别

**判断条件** (满足任一即可):
1. `title.toLowerCase().includes('ofp')`
2. `meta.unit === 'ppb'`

**示例**:
- ✅ "OFP 贡献前十物种" → ppb
- ✅ "ofp contribution top 10" → ppb
- ✅ meta: `{ unit: 'ppb' }` → ppb
- ❌ "VOCs 组分浓度" → 非 OFP 图

### 3. X 轴标签旋转

**ECharts 配置**:
```typescript
xAxis: {
  axisLabel: {
    interval: 0,     // 显示所有标签（默认自动隐藏）
    rotate: 45,      // 旋转角度
    fontSize: 11,    // 字号
    overflow: 'truncate',  // 超长处理方式
    width: 80        // 最大宽度
  }
}
```

**interval 参数**:
- `0`: 显示所有标签
- `'auto'` (默认): 自动隐藏部分标签避免重叠
- `n`: 每隔 n 个显示一个

**rotate 参数**:
- `0`: 水平（默认）
- `45`: 右倾斜 45 度
- `90`: 垂直
- `-45`: 左倾斜 45 度

**最佳实践**:
- 标签数量 < 10: rotate: 0（水平）
- 标签数量 10-20: rotate: 45（右倾斜）
- 标签数量 > 20: rotate: 90（垂直）+ 减小字号

### 4. Y 轴单位位置

**nameLocation 参数**:
- `'start'`: 轴的起点
- `'middle'`: 轴的中间（✅ 当前使用）
- `'end'`: 轴的终点

**nameGap 参数**:
- 单位标签与 Y 轴的距离（像素）
- 时序图: 50px
- 柱状图: 45px

**nameTextStyle**:
```typescript
{
  fontSize: 12,
  fontWeight: 'bold'
}
```

### 5. 图表标题样式

**位置**:
- `left: 'center'`: 水平居中
- `top: 10`: 距顶部 10px

**文字样式**:
- `fontSize: 15`: 标题字号
- `fontWeight: 'bold'`: 加粗
- `color: '#1f2328'`: 深色文字

**注意**: ECharts 不支持 CSS 变量，必须使用实际颜色值。

### 6. 网格布局优化

**left 参数增加原因**:
- 原值: `10%`
- 新值: `12%`
- 原因: Y 轴单位标签需要额外空间

**bottom 参数增加原因**:
- 时序图: `15%` (保持不变)
- 柱状图: `20%` (增加 5%)
- 原因: 旋转的 X 轴标签需要更多垂直空间

**top 参数动态调整**:
- 无标题: `30px`
- 有标题: `50px`
- 原因: 标题占据顶部空间

## 后端数据格式要求

### 时序图 Payload

```json
{
  "x_axis": ["00:00", "01:00", "02:00", ...],
  "series": [
    {
      "name": "天河站",
      "data": [120, 135, 150, ...]
    }
  ]
}
```

**Visual 对象**:
```json
{
  "id": "timeseries_1",
  "type": "timeseries",
  "title": "O3 浓度时序对比",  // 🔧 必须提供标题
  "mode": "dynamic",
  "payload": { ... },
  "meta": {
    "unit": "μg/m³"  // 🔧 可选，未提供时自动推断
  }
}
```

### 柱状图 Payload（OFP）

```json
{
  "categories": ["乙烯", "丙烯", "甲苯", "间二甲苯", ...],
  "values": [45.2, 38.7, 32.1, 28.5, ...]
}
```

**Visual 对象**:
```json
{
  "id": "bar_ofp",
  "type": "bar",
  "title": "OFP 贡献前十物种",  // 🔧 必须包含 "OFP" 关键字
  "mode": "dynamic",
  "payload": { ... },
  "meta": {
    "unit": "ppb"  // 🔧 或通过标题自动识别
  }
}
```

## 测试检查点

### 1. 时序图单位显示

**测试数据**:
```json
{
  "title": "O3 浓度时序对比",
  "type": "timeseries",
  "payload": { ... }
}
```

**检查**:
- ✅ Y 轴左侧显示 "浓度 (μg/m³)"
- ✅ 标题 "O3 浓度时序对比" 显示在图表顶部中间
- ✅ 左侧有足够空间容纳单位标签

**CO 测试数据**:
```json
{
  "title": "CO 浓度时序对比",
  "type": "timeseries",
  "payload": { ... }
}
```

**检查**:
- ✅ Y 轴左侧显示 "浓度 (mg/m³)"（自动识别 CO）

### 2. OFP 柱状图

**测试数据**:
```json
{
  "title": "OFP 贡献前十物种",
  "type": "bar",
  "payload": {
    "categories": ["乙烯", "丙烯", "甲苯", "间二甲苯", "邻二甲苯", "1,2,4-三甲苯", "苯", "乙苯", "正己烷", "正戊烷"],
    "values": [45.2, 38.7, 32.1, 28.5, 25.3, 22.1, 19.8, 17.5, 15.2, 12.9]
  }
}
```

**检查**:
- ✅ Y 轴左侧显示 "ppb"
- ✅ 所有 10 个物种名称都显示
- ✅ 标签旋转 45 度，无重叠
- ✅ 图表高度 350px，底部有足够空间
- ✅ 标题 "OFP 贡献前十物种" 显示在顶部中间

### 3. 长物种名称处理

**测试数据**:
```json
{
  "categories": ["1,2,4-三甲基苯", "超长物种名称测试123456789"]
}
```

**检查**:
- ✅ 标签宽度限制为 80px
- ✅ 超长部分显示省略号 "..."
- ✅ 悬停时 tooltip 显示完整名称

### 4. 无标题场景

**测试数据**:
```json
{
  "title": null,
  "type": "timeseries"
}
```

**检查**:
- ✅ 不显示标题
- ✅ `grid.top` 为 30px（而非 50px）
- ✅ 单位仍正确显示（默认 μg/m³）

## 相关文件

```
frontend/src/components/
├── ChartsPanel.tsx       ← 修改：添加 title、单位推断、标签旋转
└── VisualRenderer.tsx    ← 修改：传递 title 参数
```

## 未来优化

### 1. 动态调整旋转角度

**根据标签数量自动调整**:
```typescript
const getLabelRotate = (categoriesCount: number): number => {
  if (categoriesCount <= 8) return 0    // 少量标签：水平
  if (categoriesCount <= 15) return 45  // 中等：45度
  return 90                             // 大量：垂直
}
```

### 2. 智能单位识别

**扩展识别规则**:
```typescript
const inferUnit = (pollutantName?: string, meta?: any): string => {
  // 优先使用 meta
  if (meta?.unit) return meta.unit

  if (!pollutantName) return 'μg/m³'

  const name = pollutantName.toLowerCase()

  // CO 系列
  if (name.match(/\bco\b/) && !name.includes('voc')) return 'mg/m³'

  // 气象参数
  if (name.includes('温度') || name.includes('temp')) return '℃'
  if (name.includes('湿度') || name.includes('humidity')) return '%'
  if (name.includes('风速') || name.includes('wind')) return 'm/s'

  // 默认
  return 'μg/m³'
}
```

### 3. 响应式标签

**根据图表宽度调整**:
```typescript
const chart = chartInstanceRef.current
const chartWidth = chart.getWidth()

const axisLabelConfig = {
  interval: 0,
  rotate: chartWidth > 600 ? 45 : 90,  // 宽屏 45°，窄屏 90°
  fontSize: chartWidth > 600 ? 11 : 10
}
```

### 4. 多语言单位

**支持中英文**:
```typescript
const getUnitLabel = (unit: string, language: 'zh' | 'en' = 'zh'): string => {
  const labels = {
    'μg/m³': { zh: '浓度 (μg/m³)', en: 'Concentration (μg/m³)' },
    'mg/m³': { zh: '浓度 (mg/m³)', en: 'Concentration (mg/m³)' },
    'ppb': { zh: 'ppb', en: 'ppb' }
  }
  return labels[unit]?.[language] || unit
}
```

### 5. 标签换行

**长标签自动换行**:
```typescript
xAxis: {
  axisLabel: {
    interval: 0,
    rotate: 45,
    formatter: (value: string) => {
      // 超过 10 个字符时换行
      if (value.length > 10) {
        return value.slice(0, 10) + '\n' + value.slice(10)
      }
      return value
    }
  }
}
```

## 总结

✅ **已完成**: 图表单位显示和标签完整展示优化
✅ **时序图**: 显示污染物名称标题 + 自动识别单位（CO: mg/m³, 其他: μg/m³）
✅ **柱状图**: 显示 ppb 单位 + X 轴标签旋转 45° + 完整显示所有物种名称
✅ **智能推断**: 根据标题自动判断单位类型和图表类型

**核心改动**:
- ChartsPanel.tsx: 添加 title prop、inferUnit 函数、优化 Y 轴和标题配置
- VisualRenderer.tsx: 传递 title 参数

**效果**:
- 用户一眼就能看到污染物名称和单位
- OFP 图所有物种名称完整显示
- 布局合理，标签不重叠

刷新浏览器（Ctrl+F5）测试，图表现在应该显示标题和单位，VOCs 物种名称完整展示！
