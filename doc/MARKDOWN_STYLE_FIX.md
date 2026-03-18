# Markdown 样式支持修复

## 问题描述

用户反馈：站点对比分析右边的文字没有支持 Markdown 格式的文本渲染展示。

**表现**:
- 标题、列表、加粗等 Markdown 格式无法正常显示
- 文本以纯文本形式显示，没有样式

## 问题分析

### 根本原因

虽然 TextPanel 组件正确使用了 Markdown 组件进行渲染：

```typescript
// TextPanel.tsx
<Markdown content={content} />
```

并且 Markdown 组件也正确加载了 react-markdown：

```typescript
// Markdown.tsx
const ReactMarkdown = MD
return <ReactMarkdown className="md" remarkPlugins={gfm ? [gfm] : []}>{content}</ReactMarkdown>
```

**但是缺少 `.md` 类的 CSS 样式定义**！

导致虽然 Markdown 被正确解析为 HTML 元素（如 `<h1>`, `<ul>`, `<strong>` 等），但这些元素没有样式，显示效果与纯文本无异。

### 技术细节

**依赖检查**:
```bash
react-markdown@9.1.0  ✅ 已安装
remark-gfm@4.0.1      ✅ 已安装
```

**组件链路**:
```
ModuleCard
  └─ TextPanel (或 ResizablePanels → TextPanel)
      └─ Markdown
          └─ ReactMarkdown (className="md")
              └─ 渲染 HTML 元素
```

**缺失环节**: `.md` 类的 CSS 样式

## 解决方案

### 添加完整的 Markdown 样式

在 `theme.css` 中添加了完整的 `.md` 类样式定义。

**修改文件**: `frontend/src/styles/theme.css`

**添加位置**: 文件末尾（line 525-675）

### 样式覆盖的元素

#### 1. 标题样式

```css
.md h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--primary-color); /* 蓝色下划线 */
  color: var(--text-color);
}

.md h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 14px 0 10px 0;
  color: var(--text-color);
}

.md h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px 0;
  color: var(--text-color);
}

.md h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 10px 0 6px 0;
  color: var(--text-color);
}
```

**效果**:
- H1 有蓝色下划线
- 标题大小层级分明
- 适当的上下间距

#### 2. 段落和文本

```css
.md p {
  margin: 8px 0;
  line-height: 1.8; /* 行高 1.8，提升可读性 */
}

.md strong {
  font-weight: 600;
  color: var(--text-color);
}

.md em {
  font-style: italic;
}
```

**效果**:
- 段落间距合理
- 加粗文本更突出
- 斜体文本正确显示

#### 3. 列表样式

```css
.md ul,
.md ol {
  margin: 8px 0;
  padding-left: 24px;
}

.md li {
  margin: 4px 0;
  line-height: 1.7;
}

/* 列表项符号颜色 */
.md ul > li::marker {
  color: var(--primary-color); /* 蓝色圆点 */
}

.md ol > li::marker {
  color: var(--primary-color); /* 蓝色数字 */
  font-weight: 600;
}
```

**效果**:
- 无序列表使用蓝色圆点
- 有序列表使用蓝色加粗数字
- 列表项间距适中

#### 4. 代码样式

```css
.md code {
  background: #f5f7fa; /* 浅灰色背景 */
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  color: #d63384; /* 粉红色文字 */
}

.md pre {
  background: #f5f7fa;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto; /* 横向滚动 */
  margin: 12px 0;
}

.md pre code {
  background: transparent; /* 代码块内的 code 无背景 */
  padding: 0;
  color: var(--text-color);
  font-size: 13px;
  line-height: 1.6;
}
```

**效果**:
- 行内代码：浅灰背景 + 粉红色文字
- 代码块：浅灰背景 + 边框 + 横向滚动
- 等宽字体，易于阅读

#### 5. 引用样式

```css
.md blockquote {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 4px solid var(--primary-color); /* 蓝色左边框 */
  background: #f5f7fa;
  color: var(--text-color-secondary);
}
```

**效果**:
- 蓝色左边框标识引用
- 浅灰背景区分正文
- 次要文字颜色

#### 6. 表格样式

```css
.md table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.md table th {
  background: #f5f7fa; /* 表头背景 */
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  border: 1px solid var(--border-color);
}

.md table td {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
}

.md table tr:nth-child(even) {
  background: #fafbfc; /* 斑马纹效果 */
}
```

**效果**:
- 表头有背景色
- 边框清晰
- 奇偶行背景色不同（斑马纹）

#### 7. 链接和图片

```css
.md a {
  color: var(--primary-color); /* 蓝色链接 */
  text-decoration: none;
}

.md a:hover {
  text-decoration: underline; /* 悬停时下划线 */
}

.md img {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  margin: 8px 0;
}
```

**效果**:
- 蓝色链接
- 悬停时下划线
- 图片自适应宽度，圆角

#### 8. 分隔线

```css
.md hr {
  margin: 16px 0;
  border: none;
  border-top: 1px solid var(--border-color);
}
```

**效果**:
- 细灰色分隔线
- 上下间距适中

## 效果对比

### 之前（无样式）

```
一、污染情况概述
污染物浓度特征
污染期段：2025年8月9日15-21时为臭氧污染高峰期
峰值浓度：226μg/m³（21时），达到轻度污染水平
日变化特征：早晨典雅化学污染较轻，午后至黄昏上升低（59-135μg/m³），午后显著上升
```
- ❌ 标题与正文无区别
- ❌ 加粗文本不明显
- ❌ 列表无缩进和符号

### 现在（有样式）

```
一、污染情况概述

污染物浓度特征
• 污染期段：2025年8月9日15-21时为臭氧污染高峰期
• 峰值浓度：226μg/m³（21时），达到轻度污染水平
• 日变化特征：早晨污染较轻，午后至黄昏上升低（59-135μg/m³），午后显著上升
```
- ✅ 标题加粗，层级分明
- ✅ 加粗文本突出
- ✅ 列表有蓝色圆点，缩进清晰

## 支持的 Markdown 语法

### GitHub Flavored Markdown (GFM)

由于使用了 `remark-gfm` 插件，支持以下 GFM 扩展：

1. **表格** (`|` 分隔)
2. **任务列表** (`- [ ]` / `- [x]`)
3. **删除线** (`~~删除~~`)
4. **自动链接** (URL 自动转为链接)

### 标准 Markdown

1. **标题**: `# H1`, `## H2`, `### H3`, `#### H4`
2. **加粗**: `**bold**`
3. **斜体**: `*italic*`
4. **列表**:
   - 无序: `- item` 或 `* item`
   - 有序: `1. item`
5. **代码**:
   - 行内: `` `code` ``
   - 代码块: ` ```language `
6. **引用**: `> quote`
7. **链接**: `[text](url)`
8. **图片**: `![alt](url)`
9. **分隔线**: `---` 或 `***`

## 样式设计原则

### 1. 可读性优先

- **行高**: 1.8（段落），1.7（列表）
- **字号**: 14px（正文），13-20px（标题）
- **间距**: 适当的上下边距

### 2. 视觉层级

- **主题色**: 蓝色 (`#1677ff`) 用于标题、链接、列表符号
- **背景色**: 浅灰色 (`#f5f7fa`) 用于代码、表头、引用
- **边框色**: 细边框 (`var(--border-color)`)

### 3. 品牌一致性

- 使用统一的主题色变量 (`--primary-color`)
- 与整体 UI 风格保持一致
- 蓝色系为主色调

### 4. 响应式友好

- `max-width: 100%` 防止内容溢出
- `overflow-x: auto` 代码块横向滚动
- 图片自适应宽度

## 技术栈

### Markdown 解析

**库**: `react-markdown@9.1.0`
- React 组件化 Markdown 渲染
- 支持自定义组件
- 安全（自动过滤 HTML）

**插件**: `remark-gfm@4.0.1`
- GitHub Flavored Markdown 扩展
- 支持表格、任务列表、删除线等

### 动态加载

```typescript
// Markdown.tsx
const [MD, setMD] = useState<any>(null)
const [gfm, setGfm] = useState<any>(null)

useEffect(() => {
  ;(async () => {
    const [{ default: ReactMarkdown }, { default: remarkGfm }] = await Promise.all([
      import('react-markdown'),
      import('remark-gfm')
    ])
    if (mounted) { setMD(() => ReactMarkdown); setGfm(() => remarkGfm) }
  })()
}, [])
```

**优势**:
- 代码分割，减小初始包体积
- 异步加载，不阻塞主线程
- 降级处理（加载失败显示纯文本）

## 兼容性

### 浏览器支持

**CSS 特性**:
- `::marker` 伪元素: Chrome 86+, Firefox 68+, Safari 11.1+
- 其他样式: 所有现代浏览器

**降级方案**:
- 旧浏览器不支持 `::marker`，使用默认列表样式
- 不影响内容可读性

### React 版本

- React 18+ ✅
- React 17+ ✅（需要 Legacy Mode）

## 测试检查点

### 1. 标题渲染

**Markdown**:
```markdown
# 一级标题
## 二级标题
### 三级标题
```

**检查**:
- ✅ H1 有蓝色下划线
- ✅ 字号依次递减
- ✅ 加粗效果

### 2. 列表渲染

**Markdown**:
```markdown
- 无序列表项 1
- 无序列表项 2

1. 有序列表项 1
2. 有序列表项 2
```

**检查**:
- ✅ 无序列表有蓝色圆点
- ✅ 有序列表有蓝色加粗数字
- ✅ 缩进正确

### 3. 文本格式

**Markdown**:
```markdown
**加粗文本**
*斜体文本*
`行内代码`
```

**检查**:
- ✅ 加粗文本粗细正确
- ✅ 斜体文本倾斜
- ✅ 行内代码有粉红色背景

### 4. 代码块

**Markdown**:
````markdown
```python
def hello():
    print("Hello")
```
````

**检查**:
- ✅ 浅灰背景
- ✅ 边框清晰
- ✅ 等宽字体
- ✅ 横向滚动（长代码）

### 5. 表格

**Markdown**:
```markdown
| 站点 | 浓度 |
|------|------|
| A站  | 100  |
| B站  | 120  |
```

**检查**:
- ✅ 表头有背景色
- ✅ 边框完整
- ✅ 斑马纹效果

## 相关文件

```
frontend/src/
├── components/
│   ├── Markdown.tsx         ← Markdown 组件（已有，无修改）
│   └── TextPanel.tsx        ← TextPanel 组件（已有，无修改）
└── styles/
    └── theme.css            ← 修改：添加 .md 样式（line 525-675）
```

## 未来优化

### 1. 语法高亮

**当前**: 代码块纯文本显示

**优化**: 使用 `react-syntax-highlighter`

```typescript
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

// 自定义代码块渲染
<ReactMarkdown
  components={{
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      return !inline && match ? (
        <SyntaxHighlighter style={vscDarkPlus} language={match[1]}>
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className={className} {...props}>{children}</code>
      )
    }
  }}
/>
```

### 2. 数学公式支持

**插件**: `remark-math` + `rehype-katex`

```typescript
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

<ReactMarkdown
  remarkPlugins={[remarkGfm, remarkMath]}
  rehypePlugins={[rehypeKatex]}
/>
```

### 3. 自定义组件

**示例**: 警告框

```typescript
<ReactMarkdown
  components={{
    blockquote({ children }) {
      const text = String(children)
      if (text.startsWith('⚠️')) {
        return <div className="warning-box">{children}</div>
      }
      return <blockquote>{children}</blockquote>
    }
  }}
/>
```

### 4. 暗色主题

**适配**: 添加暗色模式样式

```css
@media (prefers-color-scheme: dark) {
  .md {
    color: #e6edf3;
  }

  .md code {
    background: #161b22;
    color: #ff7b72;
  }

  .md pre {
    background: #161b22;
    border-color: #30363d;
  }
}
```

## 总结

✅ **已修复**: Markdown 格式文本渲染显示
✅ **添加内容**: 完整的 `.md` 类样式定义（151行）
✅ **支持语法**: 标题、列表、表格、代码、链接等
✅ **设计原则**: 可读性、层级、一致性、响应式

**核心改动**:
- theme.css: 添加 `.md` 样式（line 525-675）

**效果**:
- 标题层级分明
- 列表缩进清晰，蓝色符号
- 代码块美观，易于阅读
- 表格整齐，斑马纹效果
- 整体视觉统一

刷新浏览器（Ctrl+F5）测试，Markdown 格式现在应该正确渲染！
