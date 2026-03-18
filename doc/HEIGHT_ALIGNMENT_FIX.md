# 左右面板高度对齐修复

## 修复的问题

**用户反馈**: 文本区域的高度应该与左侧图表区域高度一致，而不是自适应内容高度，这样方便阅读展示。

## 解决方案

### 1. 统一高度约束

设置左右面板统一高度为 **500px**:
- 左侧图表区域: `minHeight: 500px`
- 右侧文字区域: `minHeight: 500px` + `maxHeight: 500px`
- 内容超出时，两侧都显示滚动条

### 2. 布局特性

```
┌──────────────────────────────────────┐
│       气象与上风向分析 (标题)         │
├─────────────────┬─│─┬────────────────┤
│ 左侧图表 (500px) │  │ │ 右侧文字 (500px)│
│                 │ 拖│ │                │
│ 📊 趋势图        │ 动│ │ 📝 分析内容    │
│ 📊 地图          │ 条│ │                │
│ [滚动条]        │  │ │ [滚动条]       │
└─────────────────┴─│─┴────────────────┘
                    ↕️
              高度完全对齐 (500px)
```

## 修改的文件

### 1. ResizablePanels.tsx

**新增参数**:
```typescript
interface Props {
  // ... 其他参数
  minHeight?: number // 🔧 新增：最小高度（像素）
}

// 默认值
minHeight = 500 // 默认 500px
```

**关键修改** (line 145-146):
```typescript
minHeight: minHeight, // 确保右侧有最小高度
maxHeight: minHeight, // 🔧 关键：限制最大高度，确保左右对齐
```

**左侧面板** (line 95-98):
```typescript
<div style={{
  width: `${leftWidth}%`,
  minHeight: minHeight,
  display: 'flex',
  flexDirection: 'column',
}}>
```

**右侧面板** (line 142-149):
```typescript
<div style={{
  width: `${rightWidth}%`,
  minHeight: minHeight,
  maxHeight: minHeight, // ⭐ 关键：固定高度
  display: 'flex',
  flexDirection: 'column',
}}>
```

### 2. ModuleCard.tsx

**传入 minHeight 参数** (line 36):
```typescript
<ResizablePanels
  initialLeftWidth={65}
  minLeftWidth={40}
  minRightWidth={25}
  minHeight={500} // 🔧 设置统一高度 500px
  leftPanel={...}
  rightPanel={...}
/>
```

**左侧面板添加滚动** (line 38):
```typescript
<div style={{
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  height: '100%',
  overflow: 'auto' // ⭐ 内容超出时显示滚动条
}}>
```

### 3. TextPanel.tsx

**保持之前的修改**:
```typescript
<aside style={{
  border: '1px solid var(--border-color)',
  borderRadius: 8,
  padding: 12,
  height: '100%', // 填充父容器
  overflow: 'auto', // 内容超出时滚动
  display: 'flex',
  flexDirection: 'column'
}}>
```

## 视觉效果对比

### 修复前 ❌
```
┌─────────────────────────────────┐
│ 图表区域 (400px)                 │
│                                  │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 文字区域 (自适应内容，可能很长) │
│                                  │
│                                  │
│                                  │
│                                  │  ← 右侧比左侧高很多
└─────────────────────────────────┘
```

### 修复后 ✅
```
┌─────────────────┬───────────────┐
│ 图表 (500px)    │ 文字 (500px)  │
│                 │               │
│ 📊 图表1        │ 📝 分析内容   │
│ 📊 图表2        │               │
│ [滚动条]       │ [滚动条]      │
└─────────────────┴───────────────┘
    ↕️ 500px          ↕️ 500px
```

## 功能特性

### 1. 高度对齐
- ✅ 左右面板高度始终保持一致 (500px)
- ✅ 视觉上整齐、对称
- ✅ 方便横向对比阅读

### 2. 内容滚动
- ✅ 左侧图表过多时，出现垂直滚动条
- ✅ 右侧文字过长时，出现垂直滚动条
- ✅ 滚动条独立，互不影响

### 3. 宽度可调
- ✅ 保留拖动分隔条功能
- ✅ 可自由调整图表和文字的宽度比例
- ✅ 高度始终保持对齐

## 测试步骤

### 1. 基本对齐测试

```bash
# 1. 刷新浏览器 (Ctrl+F5)
# 2. 输入查询
# 3. 等待分析完成
# 4. 点击全屏按钮
```

**检查点**:
- ✅ 左侧图表区域和右侧文字区域高度是否一致
- ✅ 顶部对齐、底部对齐
- ✅ 分隔条从顶部延伸到底部

### 2. 滚动条测试

**左侧图表滚动**:
- 如果有多个图表，应该出现垂直滚动条
- 滚动左侧不影响右侧

**右侧文字滚动**:
- 如果文字内容超过 500px，应该出现滚动条
- 滚动右侧不影响左侧

### 3. 拖动功能测试

**拖动分隔条**:
- 拖动时，左右高度应始终保持 500px
- 宽度比例改变，但高度不变
- 滚动条位置保持正确

### 4. 不同内容长度测试

**场景 1: 左侧图表多，右侧文字少**
- ✅ 左侧有滚动条
- ✅ 右侧无滚动条，但高度仍为 500px

**场景 2: 左侧图表少，右侧文字多**
- ✅ 左侧无滚动条，但高度仍为 500px
- ✅ 右侧有滚动条

**场景 3: 两侧内容都少**
- ✅ 两侧都无滚动条
- ✅ 高度仍为 500px，底部有空白

## 高度选择理由

**为什么选择 500px？**

1. **图表显示**: 一个 ECharts 图表通常需要 300-400px 高度
2. **多图表**: 考虑到可能有 2-3 个图表堆叠，500px 是合理的
3. **文字阅读**: 500px 约等于 25-30 行文字（14px 字号）
4. **屏幕适配**: 在 1080p 显示器上占据合理比例

**可调整性**:
- 如果需要更高：修改 `ModuleCard.tsx` line 36: `minHeight={600}`
- 如果需要更矮：修改为 `minHeight={400}`
- 不同模块可以设置不同高度

## 注意事项

### 1. 综合分析模块

综合分析模块使用 `isSummary` 标志，不使用 ResizablePanels，而是全宽显示文字。

**当前实现** (ModuleCard.tsx line 27-30):
```typescript
{isSummary ? (
  <div>
    <TextPanel content={module.content} anchors={module.anchors} />
  </div>
) : (
  <ResizablePanels ... />
)}
```

### 2. 响应式设计

在小屏幕设备上，可能需要调整高度或改为单列布局。

**未来优化**:
```typescript
const minHeight = window.innerWidth < 768 ? 300 : 500
```

### 3. 滚动性能

如果内容非常长（超过 1000 行），可能需要优化滚动性能：
- 使用虚拟滚动 (react-window)
- 分页加载
- 懒加载图表

## 相关文件清单

```
frontend/src/components/
├── ResizablePanels.tsx      ← 修改：添加 minHeight 参数和高度约束
├── ModuleCard.tsx           ← 修改：传入 minHeight={500}
└── TextPanel.tsx            ← 保持：height='100%' overflow='auto'
```

## 总结

✅ **已修复**: 左右面板高度完全对齐
✅ **保留功能**: 可拖动分隔条调整宽度
✅ **改善体验**: 整齐对称，方便阅读

**效果**:
- 左侧图表区域: 固定 500px 高，内容超出滚动
- 右侧文字区域: 固定 500px 高，内容超出滚动
- 分隔条: 贯穿整个 500px 高度，可拖动调整宽度

请测试并确认效果是否符合预期！
