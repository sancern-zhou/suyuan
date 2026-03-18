# 动态高度实现 - 左侧图表完整显示

## 用户需求

**原始要求**: "不要让左侧图片显示不完整，默认左侧图片要完整显示，不需要上下滑动，以左侧图片的容器高度为基准，计算右侧文本框的高度，两个高度一致。"

## 解决方案

### 核心思路

1. **左侧面板**: 内容完整显示，高度自适应（`height: 'auto'`）
2. **右侧面板**: 高度匹配左侧面板的实际高度
3. **容器**: 高度等于左侧面板的内容高度
4. **动态监听**: 使用 `ResizeObserver` 监听左侧内容变化，实时更新高度

### 技术实现

#### 1. 状态管理

```typescript
const [dynamicHeight, setDynamicHeight] = useState<number>(minHeight)
const leftPanelRef = useRef<HTMLDivElement>(null)
```

- `dynamicHeight`: 存储动态计算的高度
- `leftPanelRef`: 引用左侧面板 DOM 元素

#### 2. 高度测量与监听

```typescript
useEffect(() => {
  if (leftPanelRef.current) {
    // 使用 ResizeObserver 监听左侧内容变化
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const contentHeight = entry.target.scrollHeight
        setDynamicHeight(Math.max(contentHeight, minHeight))
      }
    })

    resizeObserver.observe(leftPanelRef.current)

    // 初始测量
    const initialHeight = leftPanelRef.current.scrollHeight
    setDynamicHeight(Math.max(initialHeight, minHeight))

    return () => {
      resizeObserver.disconnect()
    }
  }
}, [leftPanel, minHeight])
```

**关键点**:
- `ResizeObserver`: 监听 DOM 元素尺寸变化
- `scrollHeight`: 获取元素的完整内容高度（包括溢出部分）
- `Math.max(contentHeight, minHeight)`: 确保高度不小于 minHeight (400px)
- 依赖 `leftPanel`: 当左侧内容变化时重新测量

#### 3. 容器和面板布局

```typescript
// 容器
<div style={{
  display: 'flex',
  width: '100%',
  height: dynamicHeight, // 🔧 使用动态计算的高度
  gap: 0,
  position: 'relative',
}}>

  {/* 左侧面板 */}
  <div
    ref={leftPanelRef}
    style={{
      width: `${leftWidth}%`,
      flexShrink: 0,
      height: 'auto', // 🔧 自动高度，完整显示内容
      display: 'flex',
      flexDirection: 'column',
    }}
  >
    {leftPanel}
  </div>

  {/* 右侧面板 */}
  <div style={{
    width: `${rightWidth}%`,
    flexShrink: 0,
    height: dynamicHeight, // 🔧 与左侧高度一致
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  }}>
    {rightPanel}
  </div>
</div>
```

**关键点**:
- 容器高度 = `dynamicHeight`
- 左侧高度 = `'auto'` (完整显示，不滚动)
- 右侧高度 = `dynamicHeight` (匹配左侧)
- 右侧 `overflow: 'hidden'` (防止溢出)

### 修改的文件

#### 1. `frontend/src/components/ResizablePanels.tsx`

**新增状态**:
```typescript
const [dynamicHeight, setDynamicHeight] = useState<number>(minHeight)
const leftPanelRef = useRef<HTMLDivElement>(null)
```

**新增 useEffect** (line 65-85):
```typescript
// 动态计算左侧面板的实际内容高度
useEffect(() => {
  if (leftPanelRef.current) {
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const contentHeight = entry.target.scrollHeight
        setDynamicHeight(Math.max(contentHeight, minHeight))
      }
    })

    resizeObserver.observe(leftPanelRef.current)
    const initialHeight = leftPanelRef.current.scrollHeight
    setDynamicHeight(Math.max(initialHeight, minHeight))

    return () => {
      resizeObserver.disconnect()
    }
  }
}, [leftPanel, minHeight])
```

**更新容器高度** (line 111):
```typescript
height: dynamicHeight, // 之前: height: minHeight
```

**更新左侧面板** (line 118-122):
```typescript
<div
  ref={leftPanelRef} // 🔧 添加 ref
  style={{
    width: `${leftWidth}%`,
    flexShrink: 0,
    height: 'auto', // 🔧 之前: height: minHeight
    display: 'flex',
    flexDirection: 'column',
  }}
>
```

**更新右侧面板** (line 172-175):
```typescript
style={{
  width: `${rightWidth}%`,
  flexShrink: 0,
  height: dynamicHeight, // 🔧 之前: height: minHeight
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden', // 🔧 新增
}}
```

#### 2. `frontend/src/components/ModuleCard.tsx`

**移除左侧滚动** (line 38):
```typescript
// ❌ 之前
<div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', overflow: 'auto' }}>

// ✅ 现在
<div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
```

## 工作流程

### 初始渲染
```
1. 组件挂载
   ↓
2. leftPanelRef.current 引用左侧 DOM
   ↓
3. 测量 scrollHeight (实际内容高度)
   ↓
4. setDynamicHeight(scrollHeight)
   ↓
5. 容器和右侧面板应用 dynamicHeight
   ↓
6. ResizeObserver 开始监听
```

### 内容变化时
```
1. 左侧内容更新 (新图表加载)
   ↓
2. ResizeObserver 触发回调
   ↓
3. 重新测量 scrollHeight
   ↓
4. setDynamicHeight(新高度)
   ↓
5. 容器和右侧面板自动调整高度
```

### 拖动分隔条时
```
1. 用户拖动分隔条
   ↓
2. 左右宽度比例改变
   ↓
3. 左侧内容可能换行，高度变化
   ↓
4. ResizeObserver 触发
   ↓
5. 高度自动调整
```

## 效果说明

### 左侧面板
- ✅ **完整显示**: 所有图表完整可见，无需滚动
- ✅ **自适应高度**: 高度根据内容自动调整
- ✅ **无滚动条**: 不出现垂直滚动条

### 右侧面板
- ✅ **高度对齐**: 与左侧高度完全一致
- ✅ **内容滚动**: 如果文字超过高度，TextPanel 内部滚动
- ✅ **视觉整齐**: 顶部和底部与左侧对齐

### 整体容器
- ✅ **动态高度**: 根据左侧内容实时调整
- ✅ **最小高度保护**: 不会小于 minHeight (400px)
- ✅ **响应式**: 内容变化时自动更新

## 测试场景

### 场景 1: 单个图表
```
左侧: 1个图表 (高度约 400px)
结果: 容器高度 400px, 左右对齐
```

### 场景 2: 多个图表
```
左侧: 3个图表 (总高度约 1200px)
结果: 容器高度 1200px, 左右对齐, 右侧出现滚动条
```

### 场景 3: 拖动分隔条
```
操作: 拖动分隔条改变宽度
结果: 左侧内容可能换行, 高度自动调整, 右侧跟随
```

### 场景 4: 内容加载
```
操作: 异步加载新图表
结果: ResizeObserver 检测到变化, 高度自动更新
```

## 技术优势

### ResizeObserver vs 手动测量

**ResizeObserver** (✅ 当前方案):
- 自动监听尺寸变化
- 性能优化 (浏览器原生 API)
- 支持异步内容加载
- 无需手动触发

**手动测量** (❌ 替代方案):
```typescript
// 需要在每次内容变化时手动调用
useEffect(() => {
  const height = leftPanelRef.current?.scrollHeight || minHeight
  setDynamicHeight(height)
}, [leftPanel])
```
- 无法检测异步变化 (图片加载完成等)
- 需要手动管理依赖
- 可能遗漏某些变化

### scrollHeight vs clientHeight vs offsetHeight

**scrollHeight** (✅ 当前使用):
- 包含完整内容高度 (包括溢出部分)
- 适合测量实际内容大小

**clientHeight**:
- 只包含可见区域高度 (不含滚动条)
- 不适合测量完整内容

**offsetHeight**:
- 包含边框和滚动条
- 不适合纯内容测量

## 与之前固定高度方案的对比

### 之前的方案 (固定 500px)
```
容器:   height: 500px
├─ 左:  height: 500px  → 内容超出滚动
└─ 右:  height: 500px  → 内容超出滚动

问题: 左侧图表可能显示不完整 ❌
```

### 当前方案 (动态高度)
```
容器:   height: dynamicHeight (自动计算)
├─ 左:  height: auto  → 完整显示所有内容 ✅
└─ 右:  height: dynamicHeight  → 匹配左侧高度 ✅

优势: 左侧完整显示，右侧高度对齐 ✅
```

## 注意事项

### 1. 性能考虑

**ResizeObserver 性能**:
- 浏览器原生实现，性能优异
- 避免在回调中执行复杂计算
- 当前实现只更新一个状态，性能无影响

### 2. 浏览器兼容性

**ResizeObserver 支持**:
- Chrome 64+
- Firefox 69+
- Safari 13.1+
- Edge 79+

如果需要支持旧浏览器，可以使用 polyfill:
```bash
npm install resize-observer-polyfill
```

### 3. minHeight 的作用

```typescript
setDynamicHeight(Math.max(contentHeight, minHeight))
```

- 确保高度不会太小 (< 400px)
- 防止内容很少时布局过于紧凑
- 提供一个合理的最小视觉空间

### 4. 右侧面板溢出处理

```typescript
overflow: 'hidden'
```

- 防止右侧面板内容溢出
- TextPanel 内部仍有 `overflow: auto`，可以滚动
- 确保边界整齐

## 未来优化

### 可选改进

1. **平滑过渡动画**:
```typescript
style={{
  height: dynamicHeight,
  transition: 'height 0.3s ease-out'
}}
```

2. **高度缓存**:
```typescript
const [cachedHeights, setCachedHeights] = useState<Map<string, number>>(new Map())
```

3. **虚拟化长列表**:
如果左侧图表非常多 (>10 个)，可以使用虚拟滚动:
```bash
npm install react-window
```

4. **防抖优化**:
```typescript
const debouncedSetHeight = debounce(setDynamicHeight, 100)
```

## 总结

✅ **已实现**: 左侧图表完整显示，右侧高度自动匹配
✅ **方法**: ResizeObserver + scrollHeight 动态测量
✅ **效果**: 视觉整齐，左右完全对齐，无需手动滚动左侧

**核心改进**:
- 左侧: `height: 'auto'` (完整显示)
- 右侧: `height: dynamicHeight` (匹配左侧)
- 容器: `height: dynamicHeight` (包裹内容)
- 监听: `ResizeObserver` (自动更新)

刷新浏览器测试，左侧图表现在应该完整显示，右侧高度完全匹配！
