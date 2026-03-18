# 修复左右面板高度不一致问题

## 问题描述

**症状**: 左侧图表区域和右侧文字区域高度不一致，左侧根据内容自动增长，右侧固定高度。

**原因**:
- 左侧面板: 使用 `minHeight`，没有上限，会随内容增长
- 右侧面板: 使用 `minHeight` + `maxHeight`，固定高度
- 容器: 使用 `minHeight`，也会随内容增长

## 修复方案

### 统一使用固定高度 (height)

将所有高度设置从 `minHeight` / `maxHeight` 改为固定的 `height`。

### 修改的代码

**文件**: `frontend/src/components/ResizablePanels.tsx`

#### 1. 容器 (line 85)
```typescript
// ❌ 之前
minHeight: minHeight

// ✅ 现在
height: minHeight  // 固定高度，不会随内容变化
```

#### 2. 左侧面板 (line 95)
```typescript
// ❌ 之前
minHeight: minHeight  // 只有最小值，会随内容增长

// ✅ 现在
height: minHeight  // 固定高度
```

#### 3. 右侧面板 (line 145)
```typescript
// ❌ 之前
minHeight: minHeight
maxHeight: minHeight  // 用 min + max 限制高度

// ✅ 现在
height: minHeight  // 直接固定高度，更简洁
```

## 关键改进

### 之前的问题
```
容器:   minHeight: 500px  → 会增长
├─ 左:  minHeight: 500px  → 会增长 ❌
└─ 右:  minHeight/maxHeight: 500px  → 固定 ✅

结果: 左侧 600px, 右侧 500px → 不对齐 ❌
```

### 修复后
```
容器:   height: 500px  → 固定
├─ 左:  height: 500px  → 固定 ✅
└─ 右:  height: 500px  → 固定 ✅

结果: 左右都是 500px → 完全对齐 ✅
```

## 效果说明

### 固定高度的优势
1. ✅ **完全对齐**: 左右面板始终保持相同高度
2. ✅ **简洁清晰**: 不需要 min/max 组合，直接用 height
3. ✅ **可预测性**: 高度不会意外变化
4. ✅ **视觉整齐**: 分隔条从上到下贯穿整个高度

### 内容处理
- **内容少于 500px**: 底部留白，但高度仍为 500px
- **内容多于 500px**: 出现滚动条，可滚动查看
- **左右独立滚动**: 左侧滚动不影响右侧，反之亦然

## 测试检查点

### 1. 高度对齐测试
```bash
# 浏览器开发者工具 (F12)
# Elements 标签页，选中左右面板
# 检查 computed height 是否都是 500px
```

**预期结果**:
- 容器高度: 500px
- 左侧面板高度: 500px
- 右侧面板高度: 500px
- 分隔条高度: 500px

### 2. 视觉对齐测试
- ✅ 顶部对齐: 左右面板顶部在同一水平线
- ✅ 底部对齐: 左右面板底部在同一水平线
- ✅ 分隔条贯通: 从顶部延伸到底部，无间隙

### 3. 滚动测试
**左侧图表多**:
- 左侧出现滚动条
- 可滚动查看所有图表
- 右侧不受影响

**右侧文字长**:
- 右侧出现滚动条
- 可滚动查看所有文字
- 左侧不受影响

### 4. 拖动测试
**拖动分隔条**:
- 宽度比例改变
- 高度始终保持 500px
- 左右始终对齐

## 相关文件

```
frontend/src/components/
└── ResizablePanels.tsx  ← 修改：统一使用 height 而不是 minHeight/maxHeight
```

## 技术细节

### CSS height vs minHeight/maxHeight

**minHeight/maxHeight**:
- 元素可以在范围内变化
- 当 `minHeight = maxHeight` 时，相当于固定高度
- 但语义不清晰，容易出错

**height**:
- 直接固定高度
- 语义清晰：这个元素就是这么高
- 内容超出使用 `overflow: auto` 处理

### Flexbox 行为

```typescript
display: 'flex'
flexDirection: 'row'
```

- 子元素（左、分隔条、右）在水平方向排列
- 当父容器有固定 `height` 时，子元素也会继承或约束到相同高度
- `flexShrink: 0` 确保子元素不会被压缩

## 总结

✅ **已修复**: 左右面板高度完全一致
✅ **方法**: 统一使用 `height: minHeight` 固定高度
✅ **效果**: 视觉整齐，左右对齐，方便阅读

**核心改动**:
- 容器、左侧、右侧都使用 `height` 而不是 `minHeight`/`maxHeight`
- 确保三者高度完全一致（都是 500px）
- 内容超出时使用滚动条

刷新浏览器测试，左右面板现在应该高度完全一致了！
