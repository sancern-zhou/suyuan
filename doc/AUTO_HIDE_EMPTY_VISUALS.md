# 自动隐藏空可视化容器

## 用户需求

在全屏展示的分析模块中，如果某个模块没有可视化内容（图表），左侧会显示"暂无可视化内容"的占位符，浪费空间。

用户希望：**没有图表时，自动全宽显示文本**，不显示空的可视化容器。

## 问题分析

### 之前的逻辑

```typescript
{isSummary ? (
  // 综合分析：全宽文本
  <TextPanel autoHeight={true} />
) : (
  // 其他模块：左右分栏
  <ResizablePanels
    leftPanel={
      // 即使 visuals.length === 0，仍显示左侧面板
      {visuals.length === 0 && (
        <div>暂无可视化内容</div>  // ❌ 占位符浪费空间
      )}
    }
    rightPanel={<TextPanel />}
  />
)}
```

### 问题

- 只有综合分析（`isSummary=true`）使用全宽文本
- 其他模块即使没有图表，也会显示左右分栏
- 左侧显示"暂无可视化内容"占位符，浪费空间

## 解决方案

### 智能布局切换

根据是否有可视化内容自动选择布局：

```typescript
{isSummary || visuals.length === 0 ? (
  // 综合分析 或 无可视化内容：全宽文本
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  // 有可视化内容的模块：左右分栏
  <ResizablePanels
    leftPanel={
      // 只在有图表时渲染
      <div>
        {visuals.map(v => (
          <VisualRenderer visual={v} />
        ))}
      </div>
    }
    rightPanel={<TextPanel />}
  />
)}
```

### 判断条件

**全宽文本布局** (条件：`isSummary || visuals.length === 0`):
1. `isSummary === true`: 综合分析模块
2. `visuals.length === 0`: 任何没有可视化内容的模块

**左右分栏布局** (条件：`!isSummary && visuals.length > 0`):
- 非综合分析，且有可视化内容

## 修改的文件

### ModuleCard.tsx

**修改位置**: Line 27

**之前**:
```typescript
{isSummary ? (
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  <ResizablePanels ... />
)}
```

**现在**:
```typescript
{isSummary || visuals.length === 0 ? (
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  <ResizablePanels ... />
)}
```

**改动**:
- 添加 `|| visuals.length === 0` 条件
- 当任何模块没有可视化内容时，自动切换为全宽文本布局

## 效果对比

### 之前的布局（有问题）

```
┌────────────────────────────────────────────┐
│          分析模块 (标题)                    │
├─────────────────┬──────┬───────────────────┤
│ 暂无可视化内容  │ 分隔 │ 文本内容          │
│                 │  条  │                   │
│ (占位符)        │      │ 实际分析结果...   │
│                 │      │                   │
└─────────────────┴──────┴───────────────────┘
      ❌ 左侧浪费空间
```

### 现在的布局（已优化）

```
┌────────────────────────────────────────────┐
│          分析模块 (标题)                    │
├────────────────────────────────────────────┤
│                                            │
│ 文本内容（全宽显示）                        │
│                                            │
│ 实际分析结果...                            │
│                                            │
└────────────────────────────────────────────┘
      ✅ 充分利用空间
```

### 有图表的模块（保持不变）

```
┌────────────────────────────────────────────┐
│          气象与上风向分析 (标题)            │
├─────────────────┬──────┬───────────────────┤
│ 图表 (左侧)     │ 分隔 │ 文本 (右侧)       │
│                 │  条  │                   │
│ 📊 趋势图        │      │ 📝 分析内容       │
│ 📊 地图          │      │                   │
└─────────────────┴──────┴───────────────────┘
      ✅ 正常显示
```

## 适用场景

### 场景 1: 综合分析模块

**特点**: `isSummary = true`
**布局**: 全宽文本（自适应高度）
**原因**: 综合分析一般没有图表，只有总结文字

### 场景 2: 后端未返回可视化数据

**特点**: `visuals = []` 或 `visuals.length = 0`
**布局**: 全宽文本（自适应高度）
**原因**:
- API 可能因为数据不足而未生成图表
- 某些分析类型可能不需要图表
- 避免显示空的占位符

### 场景 3: 正常分析模块

**特点**: `visuals.length > 0`
**布局**: 左右分栏（图表 + 文本）
**原因**: 有可视化内容需要展示

## 技术细节

### 动态判断逻辑

**判断顺序**:
1. 检查 `isSummary`
2. 检查 `visuals.length === 0`
3. 如果任一条件为真 → 全宽文本布局
4. 否则 → 左右分栏布局

**TypeScript 类型**:
```typescript
const visuals: Visual[] = useMemo(() => module.visuals || [], [module.visuals])
```
- 确保 `visuals` 始终是数组
- 如果 `module.visuals` 为 `undefined`，使用空数组 `[]`

### TextPanel 自适应高度

**全宽文本布局**:
```typescript
<TextPanel
  content={module.content}
  anchors={module.anchors}
  autoHeight={true}  // 🔧 自适应高度
/>
```

**参数说明**:
- `autoHeight={true}`: 容器高度根据文本内容自动调整
- `height: 'auto'`: CSS 高度自适应
- `overflow: 'visible'`: 不出现滚动条

## 优势

### 1. 智能布局

**自动检测**:
- 无需手动配置
- 根据数据自动选择最佳布局
- 适应不同模块的需求

### 2. 空间利用

**之前**:
- 左侧占位符占据 60% 宽度
- 文本只能用 40% 宽度
- 总空间利用率 < 50%

**现在**:
- 文本占据 100% 宽度
- 无浪费空间
- 总空间利用率 = 100%

### 3. 用户体验

**阅读体验**:
- 文本更宽，阅读更舒适
- 无干扰的占位符
- 视觉更整洁

**视觉一致性**:
- 与综合分析模块保持一致
- 统一的全宽文本样式
- 减少视觉噪音

## 边界情况处理

### 1. visuals 为 undefined

**处理**:
```typescript
const visuals: Visual[] = useMemo(() => module.visuals || [], [module.visuals])
```
- 使用空数组 `[]` 作为默认值
- `visuals.length === 0` 条件成立
- 自动切换为全宽文本布局

### 2. visuals 为 null

**处理**: 同上，`|| []` 会将 `null` 转为空数组

### 3. visuals 有内容但渲染失败

**行为**:
- `visuals.length > 0` 条件不成立
- 仍使用左右分栏布局
- 左侧可能显示错误边界或空白
- 用户可以看到右侧文本

### 4. 动态加载图表

**场景**: 图表异步加载，初始为空

**处理**:
```typescript
const visuals: Visual[] = useMemo(() => module.visuals || [], [module.visuals])
```
- `useMemo` 依赖 `module.visuals`
- 当 `module.visuals` 更新时，重新计算
- 布局会自动切换（全宽 → 分栏）

## 后端兼容性

### API 响应格式

**后端返回的模块数据**:
```json
{
  "analysis_type": "weather_analysis",
  "content": "分析文本...",
  "visuals": [],  // 可能为空数组
  "anchors": [],
  "confidence": 0.85
}
```

**兼容情况**:
- `visuals: []` ✅ 显示全宽文本
- `visuals: null` ✅ 显示全宽文本（转为 `[]`）
- `visuals: undefined` ✅ 显示全宽文本（转为 `[]`）
- `visuals: [...]` ✅ 显示左右分栏

**无需后端修改**: 前端自动适应所有情况

## 测试检查点

### 1. 综合分析模块

**检查项**:
- ✅ 全宽显示文本
- ✅ 高度自适应
- ✅ 无左侧占位符

### 2. 无可视化内容的模块

**检查项**:
- ✅ 自动全宽显示文本
- ✅ 无"暂无可视化内容"占位符
- ✅ 布局与综合分析一致

### 3. 有可视化内容的模块

**检查项**:
- ✅ 左侧显示图表
- ✅ 右侧显示文本
- ✅ 分隔条可拖动
- ✅ 左右高度一致

### 4. 动态数据更新

**场景**: 图表数据后加载

**检查项**:
- ✅ 初始全宽显示（visuals 为空）
- ✅ 图表加载后自动切换为分栏
- ✅ 布局切换平滑

## 未来优化

### 1. 加载状态提示

**场景**: 图表正在加载

**优化**:
```typescript
{isLoadingVisuals ? (
  <div className="loading-placeholder">
    正在加载可视化内容...
  </div>
) : visuals.length === 0 ? (
  <TextPanel autoHeight={true} />
) : (
  <ResizablePanels ... />
)}
```

### 2. 用户偏好设置

**功能**: 允许用户选择布局模式

**实现**:
```typescript
const [layoutMode, setLayoutMode] = useState<'auto' | 'split' | 'full'>('auto')

{layoutMode === 'full' || (layoutMode === 'auto' && visuals.length === 0) ? (
  <TextPanel autoHeight={true} />
) : (
  <ResizablePanels ... />
)}
```

### 3. 动画过渡

**优化**: 布局切换时添加过渡动画

```css
.module-content {
  transition: all 0.3s ease-in-out;
}
```

## 相关文件

```
frontend/src/components/
└── ModuleCard.tsx  ← 修改：添加 visuals.length === 0 判断
```

## 总结

✅ **已完成**: 自动隐藏空可视化容器
✅ **智能布局**: 根据数据自动选择全宽或分栏
✅ **空间优化**: 充分利用可用宽度
✅ **用户体验**: 减少视觉干扰，提升阅读体验

**核心改动**:
- ModuleCard.tsx line 27: `isSummary || visuals.length === 0`

**效果**:
- 综合分析：全宽文本 ✅
- 无图表模块：全宽文本 ✅（新增）
- 有图表模块：左右分栏 ✅

刷新浏览器测试，没有图表的模块现在应该全宽显示文本，不再显示"暂无可视化内容"！
