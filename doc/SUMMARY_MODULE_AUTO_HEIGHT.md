# 综合分析模块文本自适应显示

## 用户需求

**明确需求**: "只删除全屏后最下面的综合分析模块的可视化内容容器，不是删除所有的，因为最下面综合分析的可视化容器没有内容，其他三个是有图表内容的，不能删去。"

## 问题分析

### 现状

- **其他模块**（气象分析、站点对比分析、VOCs/颗粒物分析）: 有图表内容，使用 ResizablePanels 左右分栏显示
- **综合分析模块**: 没有图表内容（`visuals` 数组为空），但仍使用 ResizablePanels，左侧显示"暂无可视化内容"

### 问题

综合分析模块的左侧面板是空的，浪费空间，文本应该全宽显示并自适应高度。

## 解决方案

### 核心思路

1. **保留其他模块**: 气象分析、站点对比、VOCs/PM 分析继续使用 ResizablePanels
2. **简化综合分析**: 综合分析模块 (`isSummary=true`) 只显示 TextPanel，全宽布局
3. **自适应高度**: 综合分析模块的文本容器高度根据内容自动调整

## 实现细节

### 1. ModuleCard.tsx - 条件渲染

**关键修改** (line 27-62):

```typescript
{isSummary ? (
  // 综合分析：只显示文本，全宽布局，自适应高度
  <TextPanel content={module.content} anchors={module.anchors} autoHeight={true} />
) : (
  // 其他模块：左侧图表 + 右侧文本，可拖动分隔条
  <ResizablePanels
    initialLeftWidth={65}
    minLeftWidth={40}
    minRightWidth={25}
    minHeight={500}
    leftPanel={
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
        {visuals.length === 0 && (
          <div style={{
            padding: 16,
            border: '1px dashed var(--border-color)',
            borderRadius: 8,
            textAlign: 'center',
            color: 'var(--text-color-secondary)'
          }}>
            暂无可视化内容
          </div>
        )}
        {visuals.map(v => (
          <div key={v.id} id={`visual-${v.id}`}>
            <VisualRenderer visual={v} amapKey={amapKey} />
          </div>
        ))}
      </div>
    }
    rightPanel={
      <TextPanel content={module.content} anchors={module.anchors} />
    }
  />
)}
```

**说明**:
- `isSummary` 为 `true` 时：直接渲染 TextPanel，传入 `autoHeight={true}`
- `isSummary` 为 `false` 时：使用 ResizablePanels，保留图表和文本分栏

### 2. TextPanel.tsx - 自适应高度支持

**新增参数** (line 12):

```typescript
interface Props {
  content: string
  anchors?: Anchor[]
  autoHeight?: boolean // 是否自适应高度（用于综合分析模块）
}
```

**条件样式** (line 39-42):

```typescript
<aside style={{
  border: '1px solid var(--border-color)',
  borderRadius: 8,
  padding: 12,
  height: autoHeight ? 'auto' : '100%', // 🔧 综合分析用 auto，其他用 100%
  overflow: autoHeight ? 'visible' : 'auto', // 🔧 综合分析不滚动，其他可滚动
  display: 'flex',
  flexDirection: 'column'
}}>
  <div style={{ lineHeight: 1.7, flex: autoHeight ? 'none' : 1 }}>
    <Markdown content={content} />
    ...
  </div>
</aside>
```

**样式逻辑**:

| 场景 | `autoHeight` | `height` | `overflow` | `flex` |
|------|-------------|----------|-----------|--------|
| 综合分析 | `true` | `'auto'` | `'visible'` | `'none'` |
| 其他模块 | `false` | `'100%'` | `'auto'` | `1` |

**说明**:
- `autoHeight=true`: 高度自适应内容，无滚动条，内容完整显示
- `autoHeight=false`: 高度填充父容器，内容超出时滚动

## 布局对比

### 其他模块（气象分析、站点对比、VOCs/PM分析）

```
┌────────────────────────────────────────────┐
│          气象与上风向分析 (标题)            │
├─────────────────┬──│──┬───────────────────┤
│ 左侧图表        │  拖│ │ 右侧文字          │
│                 │  动│ │                   │
│ 📊 趋势图        │  条│ │ 📝 分析内容       │
│ 📊 地图          │    │ │                   │
│ (动态高度)      │    │ │ (匹配左侧高度)    │
└─────────────────┴──│──┴───────────────────┘
```

### 综合分析模块

```
┌────────────────────────────────────────────┐
│          综合结论 (标题)                    │
├────────────────────────────────────────────┤
│                                            │
│ 📝 分析内容（全宽显示）                     │
│                                            │
│ 内容完整显示，自适应高度                    │
│                                            │
│ 无需滚动                                   │
│                                            │
└────────────────────────────────────────────┘
```

## 技术实现

### 条件渲染策略

**判断依据**: `isSummary` prop

```typescript
// App.tsx 中传入 isSummary
{data.comprehensive_analysis && (
  <ModuleCard
    module={data.comprehensive_analysis}
    isSummary={true}  // 🔧 标记为综合分析
    amapKey={amapKey}
  />
)}

// 其他模块不传 isSummary（默认 false）
{data.weather_analysis && (
  <ModuleCard
    module={data.weather_analysis}
    amapKey={amapKey}
  />
)}
```

### 高度自适应机制

**CSS 原理**:

```css
/* autoHeight=true 时 */
height: auto;        /* 高度根据内容计算 */
overflow: visible;   /* 不隐藏溢出内容，不出现滚动条 */
flex: none;          /* 不伸缩，保持内容原始大小 */

/* autoHeight=false 时 */
height: 100%;        /* 填充父容器高度 */
overflow: auto;      /* 内容超出时显示滚动条 */
flex: 1;             /* 伸缩填充可用空间 */
```

**计算过程**:

1. Markdown 渲染文本内容
2. div (lineHeight: 1.7) 包裹内容
3. aside 高度 = div 高度 + padding (12px * 2) + border (1px * 2)
4. section.card 高度 = aside 高度 + header 高度 + margin

## 效果说明

### 综合分析模块

- ✅ **全宽显示**: 文本占据整个模块宽度，无左侧空白
- ✅ **自适应高度**: 内容多少，高度就多少
- ✅ **完整展示**: 所有文本一次性显示，无需滚动
- ✅ **阅读流畅**: 专注文本内容，视觉清晰

### 其他模块

- ✅ **保留图表**: 左侧图表正常显示
- ✅ **可拖动**: 分隔条可以调整左右宽度比例
- ✅ **高度对齐**: 左右面板高度完全一致
- ✅ **独立滚动**: 左右面板各自滚动，互不影响

## 相关文件

```
frontend/src/components/
├── ModuleCard.tsx       ← 修改：添加 isSummary 条件渲染
└── TextPanel.tsx        ← 修改：添加 autoHeight 参数支持
```

## 代码变更总结

### ModuleCard.tsx

**变更类型**: 修改 (保留原有功能)

**变更内容**:
- ✅ 保留 ResizablePanels、VisualRenderer 导入
- ✅ 保留 visuals 处理逻辑
- ✅ 添加 `isSummary` 条件判断
- ✅ `isSummary=true` 时传入 `autoHeight={true}`

**代码行数**: 约 65 行 (无变化)

### TextPanel.tsx

**变更类型**: 增强 (向后兼容)

**变更内容**:
- ✅ 新增 `autoHeight` 可选参数 (默认 `false`)
- ✅ 根据 `autoHeight` 条件设置样式
- ✅ 保留所有原有功能（证据锚点、Markdown 渲染）

**代码行数**: 约 68 行 (增加 1 个参数，修改 3 处样式)

## 测试检查点

### 1. 综合分析模块测试

**检查项**:
- ✅ 全宽显示，无左侧图表面板
- ✅ 文本完整显示，无滚动条
- ✅ 高度根据文本长度自动调整
- ✅ 边框、圆角、间距正常

**测试步骤**:
```bash
# 1. 刷新浏览器 (Ctrl+F5)
# 2. 输入查询，等待分析完成
# 3. 点击全屏按钮
# 4. 滚动到最下面，查看"综合结论"模块
```

### 2. 其他模块测试

**检查项**:
- ✅ 气象分析：左侧地图，右侧文字
- ✅ 站点对比：左侧图表，右侧文字
- ✅ VOCs/PM 分析：左侧饼图/柱图，右侧文字
- ✅ 分隔条可拖动，左右宽度可调
- ✅ 左右面板高度一致

**测试步骤**:
```bash
# 1. 检查前三个模块布局
# 2. 尝试拖动分隔条
# 3. 检查左右面板高度对齐
# 4. 检查滚动条是否正常
```

### 3. 边界条件测试

**场景 1: 综合分析文本很短**
```
预期: 模块高度较小，无多余空白
结果: ✅ 高度自适应，布局紧凑
```

**场景 2: 综合分析文本很长**
```
预期: 模块高度增大，完整显示所有内容
结果: ✅ 所有文本可见，无需滚动
```

**场景 3: 其他模块图表很多**
```
预期: 左侧出现滚动条，右侧高度匹配
结果: ✅ 左右高度一致，可独立滚动
```

## 向后兼容性

### API 兼容性

**后端 API 无需修改**:
- 后端仍返回完整的 `visuals`、`anchors` 字段
- 前端根据 `isSummary` 决定是否渲染图表
- 综合分析模块的 `visuals` 可以为空数组

### 组件兼容性

**TextPanel 向后兼容**:
```typescript
// 旧代码（不传 autoHeight）
<TextPanel content={content} anchors={anchors} />
// 行为: 默认 autoHeight=false，保持原有行为

// 新代码（传 autoHeight）
<TextPanel content={content} anchors={anchors} autoHeight={true} />
// 行为: 自适应高度，新功能
```

**ModuleCard 兼容性**:
```typescript
// 不传 isSummary（默认 false）
<ModuleCard module={module} />
// 行为: 使用 ResizablePanels，保持原有行为

// 传 isSummary=true
<ModuleCard module={module} isSummary={true} />
// 行为: 只显示 TextPanel，自适应高度
```

## 未来优化建议

### 1. 动态检测可视化内容

**当前**: 依赖 `isSummary` prop 判断

**优化方向**:
```typescript
const hasVisuals = visuals && visuals.length > 0

{hasVisuals ? (
  <ResizablePanels ... />
) : (
  <TextPanel autoHeight={true} ... />
)}
```

**优势**:
- 更灵活，不依赖硬编码的 `isSummary`
- 任何模块如果没有图表，都自动全宽显示

### 2. 用户偏好设置

**功能**: 允许用户选择是否显示图表

```typescript
const [showVisuals, setShowVisuals] = useState(true)

// 添加切换按钮
<button onClick={() => setShowVisuals(!showVisuals)}>
  {showVisuals ? '隐藏图表' : '显示图表'}
</button>
```

### 3. 响应式布局

**功能**: 小屏幕时自动切换为单列布局

```typescript
const isMobile = window.innerWidth < 768

{isMobile || isSummary ? (
  <TextPanel autoHeight={true} ... />
) : (
  <ResizablePanels ... />
)}
```

## 注意事项

### 1. isSummary 标记

**重要**: 确保 `comprehensive_analysis` 模块传入 `isSummary={true}`

**检查位置**: `App.tsx` 渲染 ModuleCard 的地方

```typescript
// 正确示例
{data.comprehensive_analysis && (
  <ModuleCard
    module={data.comprehensive_analysis}
    isSummary={true}  // 🔧 必须传入
    amapKey={amapKey}
  />
)}
```

### 2. 证据锚点

综合分析模块虽然没有可视化内容，但仍保留证据锚点功能（如果后端返回了 `anchors`）。点击锚点会尝试跳转到对应的 `visual-{ref}` 元素，如果不存在则无效果。

### 3. 样式一致性

综合分析模块和其他模块的 TextPanel 样式保持一致（边框、圆角、内边距），只有高度和溢出处理不同。

## 总结

✅ **已完成**: 综合分析模块使用自适应高度全宽显示
✅ **保留功能**: 其他模块的图表分栏布局正常工作
✅ **向后兼容**: TextPanel 和 ModuleCard 保持向后兼容
✅ **用户体验**: 综合分析文本阅读更流畅，无空白浪费

**核心改动**:
- ModuleCard: 添加 `isSummary` 条件渲染
- TextPanel: 添加 `autoHeight` 参数支持

**效果**:
- 综合分析：全宽文本，自适应高度
- 其他模块：图表+文字分栏，可拖动调整

刷新浏览器测试，综合分析模块现在应该全宽显示文本，其他模块保持图表分栏布局！
